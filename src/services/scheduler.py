"""
Agendador de Publicações com Buffer Anti-Spam, Janelas Horárias e Jitter.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import random
from typing import List, Optional
import sqlite3

from src.core.config import settings
from src.core.logger import get_logger
from src.core.database import get_db

logger = get_logger("scheduler")

def generate_idempotency_key(clip_uid: str, platform: str, account_id: int) -> str:
    """Gera chave SHA-256 única para assegurar zero duplicidade de publicação."""
    raw = f"{clip_uid}_{platform}_{account_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def get_next_available_slot(
    account_id: int, 
    platform: str, 
    conn: sqlite3.Connection,
    long_video_id: Optional[int] = None
) -> datetime:
    """
    Calcula a próxima data/hora de publicação elegível para a conta:
    - Respeita as janelas diárias (ex: 11:30, 15:00, 18:30, 21:30).
    - Respeita o intervalo mínimo entre publicações da conta (ex: 15 min).
    - Respeita o espaçamento anti-repetição entre cortes do MESMO vídeo longo (mínimo 120 minutos).
    - Adiciona jitter de 1 a 5 minutos para evitar horários exatos previsíveis.
    """
    tz = ZoneInfo(settings.TIMEZONE)
    now_local = datetime.now(tz)

    cursor = conn.cursor()
    cursor.execute("""
        SELECT posting_windows, min_interval_minutes
        FROM publishing_accounts
        WHERE id = ?;
    """, (account_id,))
    acc_row = cursor.fetchone()

    interval_minutes = settings.POST_INTERVAL_MINUTES
    windows = None
    if acc_row:
        if acc_row["min_interval_minutes"]:
            interval_minutes = int(acc_row["min_interval_minutes"])
        if acc_row["posting_windows"]:
            try:
                windows = json.loads(acc_row["posting_windows"])
            except Exception:
                pass

    min_interval = timedelta(minutes=interval_minutes)

    cursor.execute("""
        SELECT MAX(scheduled_for) as last_sched
        FROM publications
        WHERE publishing_account_id = ? AND platform = ? AND status IN ('SCHEDULED', 'UPLOADING', 'POSTED');
    """, (account_id, platform))
    row = cursor.fetchone()

    base_time = now_local

    if row and row["last_sched"]:
        try:
            clean_sched = row["last_sched"].replace("Z", "+00:00")
            last_dt = datetime.fromisoformat(clean_sched).astimezone(tz)
            if last_dt + min_interval > base_time:
                base_time = last_dt + min_interval
        except Exception:
            pass

    # Espaçamento Anti-Repetição: Evita rajadas consecutivas do mesmo vídeo longo
    if long_video_id:
        cursor.execute("""
            SELECT MAX(p.scheduled_for) as last_video_sched
            FROM publications p
            JOIN clips c ON p.clip_id = c.id
            WHERE p.publishing_account_id = ? AND p.platform = ?
              AND c.long_video_id = ?
              AND p.status IN ('SCHEDULED', 'UPLOADING', 'POSTED');
        """, (account_id, platform, long_video_id))
        row_v = cursor.fetchone()
        if row_v and row_v["last_video_sched"]:
            try:
                clean_v_sched = row_v["last_video_sched"].replace("Z", "+00:00")
                last_v_dt = datetime.fromisoformat(clean_v_sched).astimezone(tz)
                min_video_gap = timedelta(minutes=getattr(settings, "MIN_SAME_VIDEO_INTERVAL_MINUTES", 120))
                if last_v_dt + min_video_gap > base_time:
                    base_time = last_v_dt + min_video_gap
            except Exception:
                pass

    # Se não houver janelas definidas na conta, gera janelas contínuas baseadas no intervalo
    if not windows:
        if interval_minutes <= 60:
            windows = [f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, max(5, interval_minutes))]
        else:
            windows = sorted(settings.DEFAULT_POSTING_WINDOWS)
    else:
        windows = sorted(windows)

    candidate_date = base_time.date()

    for day_offset in range(14): # Procura nos próximos 14 dias
        current_day = candidate_date + timedelta(days=day_offset)
        for window_str in windows:
            try:
                hour, minute = map(int, window_str.split(":"))
            except Exception:
                continue
            jitter_seconds = random.randint(10, 60) if interval_minutes <= 15 else random.randint(30, 180)
            slot = datetime(current_day.year, current_day.month, current_day.day, hour, minute, tzinfo=tz) + timedelta(seconds=jitter_seconds)

            if slot >= base_time:
                return slot.astimezone(timezone.utc)

    # Fallback seguro: intervalo a partir de agora
    return (now_local + min_interval).astimezone(timezone.utc)

def schedule_pending_clips() -> int:
    """
    Examina clips aprovados que ainda não foram enfileirados em publications,
    aplica filtros rigorosos de sobreposição temporal (histórica e no lote),
    intercala por vídeo longo e agenda com espaçamento anti-repetição.
    """
    enqueued_count = 0
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Expira clips antigos (> 7 dias)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.MAX_CLIP_AGE_DAYS)
        cursor.execute("""
            UPDATE clips
            SET youtube_status = 'SKIPPED', tiktok_status = 'SKIPPED'
            WHERE created_at < ? AND (youtube_status = 'PENDING' OR tiktok_status = 'PENDING');
        """, (cutoff_date.isoformat(),))

        # 2. Busca contas ativas
        cursor.execute("SELECT id, platform, timezone, max_daily_posts FROM publishing_accounts WHERE active = 1;")
        accounts = cursor.fetchall()
        if not accounts:
            logger.warning("Nenhuma conta de publicação ativa encontrada.")
            return 0

        from src.services.overlap_filter import filter_overlapping_clips, filter_against_database, round_robin_interleave

        # 3. Busca clips aprovados com metadados que ainda estão pendentes de envio
        cursor.execute("""
            SELECT c.id, c.clip_uid, c.virality_score, c.title, c.created_at, 
                   c.series_id, c.part_number, c.total_parts,
                   c.long_video_id, c.start_seconds, c.end_seconds, c.duration_seconds,
                   c.youtube_status, c.tiktok_status,
                   lv.source_channel_id
            FROM clips c
            LEFT JOIN long_videos lv ON c.long_video_id = lv.id
            WHERE c.virality_score >= ? 
              AND c.moderation_status = 'APPROVED'
              AND c.title IS NOT NULL
              AND (c.youtube_status = 'PENDING' OR c.tiktok_status = 'PENDING' OR c.youtube_status IS NULL);
        """, (settings.MIN_VIRALITY_SCORE,))
        raw_clips = [dict(r) for r in cursor.fetchall()]

        if not raw_clips:
            return 0

        # 3.1 Filtra cortes contra histórico do banco de dados (evita duplicação com cortes já agendados/postados)
        after_db_check, discarded_by_db = filter_against_database(raw_clips, conn=conn, max_overlap_threshold=0.25)
        for disc in discarded_by_db:
            reason = disc.get("_overlap_reason", "Sobreposição com corte histórico existente")
            cursor.execute("""
                UPDATE clips
                SET youtube_status = 'SKIPPED_OVERLAP', tiktok_status = 'SKIPPED_OVERLAP', error_log = ?
                WHERE id = ?;
            """, (reason, disc["id"]))
            # Cancela publicações pendentes se houver
            cursor.execute("""
                DELETE FROM publications 
                WHERE clip_id = ? AND status = 'SCHEDULED';
            """, (disc["id"],))
            logger.info(f"Corte {disc.get('clip_uid')} descartado por sobreposição histórica: {reason}")

        # 3.2 Filtra cortes com sobreposição temporal excessiva interna no lote
        valid_clips, discarded_clips = filter_overlapping_clips(after_db_check, max_overlap_threshold=0.25)
        for disc in discarded_clips:
            reason = disc.get("_overlap_reason", "Sobreposição temporal detectada no lote")
            cursor.execute("""
                UPDATE clips
                SET youtube_status = 'SKIPPED_OVERLAP', tiktok_status = 'SKIPPED_OVERLAP', error_log = ?
                WHERE id = ?;
            """, (reason, disc["id"]))
            cursor.execute("""
                DELETE FROM publications 
                WHERE clip_id = ? AND status = 'SCHEDULED';
            """, (disc["id"],))
            logger.info(f"Corte {disc.get('clip_uid')} descartado do agendamento: {reason}")

        # 3.3 Intercala os cortes válidos em Round-Robin (distribui por vídeo longo e canal)
        interleaved_clips = round_robin_interleave(valid_clips, group_key="long_video_id", secondary_key="source_channel_id")

        for clip in interleaved_clips:
            clip_id = clip["id"]
            clip_uid = clip["clip_uid"]
            long_vid_id = clip.get("long_video_id")

            for acc in accounts:
                acc_id = acc["id"]
                platform = acc["platform"]

                # Pula se a plataforma já foi postada ou agendada para este clip
                if platform == "youtube" and clip.get("youtube_status") in ("SCHEDULED", "POSTED", "UPLOADING"):
                    continue
                if platform == "tiktok" and clip.get("tiktok_status") in ("SCHEDULED", "POSTED", "UPLOADING"):
                    continue

                idempotency_key = generate_idempotency_key(clip_uid, platform, acc_id)

                # Verifica se publicação já foi criada
                cursor.execute("SELECT id FROM publications WHERE idempotency_key = ?;", (idempotency_key,))
                if cursor.fetchone():
                    continue

                # Calcula slot com espaçamento anti-repetição por vídeo longo
                slot_utc = get_next_available_slot(acc_id, platform, conn, long_video_id=long_vid_id)

                cursor.execute("""
                    INSERT INTO publications (
                        clip_id, publishing_account_id, platform, status,
                        scheduled_for, idempotency_key
                    ) VALUES (?, ?, ?, 'SCHEDULED', ?, ?);
                """, (clip_id, acc_id, platform, slot_utc.isoformat(), idempotency_key))

                # Atualiza status na tabela clips para rastreabilidade
                if platform == "youtube":
                    cursor.execute("UPDATE clips SET youtube_status = 'SCHEDULED', scheduled_for = ? WHERE id = ?;", (slot_utc.isoformat(), clip_id))
                elif platform == "tiktok":
                    cursor.execute("UPDATE clips SET tiktok_status = 'SCHEDULED' WHERE id = ?;", (clip_id,))

                conn.commit()
                enqueued_count += 1
                logger.info(
                    f"Clip {clip_uid} (Vídeo {long_vid_id}, score {clip['virality_score']}) agendado para {platform} em {slot_utc.isoformat()}",
                    extra={"event": "clip_scheduled", "clip_uid": clip_uid, "platform": platform, "slot": slot_utc.isoformat()}
                )

    return enqueued_count

