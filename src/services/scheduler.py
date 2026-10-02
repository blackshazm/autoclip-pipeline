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

def get_next_available_slot(account_id: int, platform: str, conn: sqlite3.Connection) -> datetime:
    """
    Calcula a próxima data/hora de publicação elegível para a conta:
    - Respeita as janelas diárias (ex: 11:30, 15:00, 18:30, 21:30).
    - Respeita o intervalo mínimo de 180 min após a última publicação agendada.
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
    ordena por maior virality_score e agenda nas janelas ideais.
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

        from src.services.overlap_filter import filter_overlapping_clips, round_robin_interleave

        # 3. Busca clips aprovados que possuem metadados gerados
        cursor.execute("""
            SELECT c.id, c.clip_uid, c.virality_score, c.title, c.created_at, 
                   c.series_id, c.part_number, c.total_parts,
                   c.long_video_id, c.start_seconds, c.end_seconds, c.duration_seconds,
                   lv.source_channel_id
            FROM clips c
            LEFT JOIN long_videos lv ON c.long_video_id = lv.id
            WHERE c.virality_score >= ? 
              AND c.moderation_status = 'APPROVED'
              AND c.title IS NOT NULL;
        """, (settings.MIN_VIRALITY_SCORE,))
        raw_clips = [dict(r) for r in cursor.fetchall()]

        # 3.1 Filtra cortes com sobreposição temporal excessiva (> 25% de trecho duplicado)
        valid_clips, discarded_clips = filter_overlapping_clips(raw_clips, max_overlap_threshold=0.25)
        for disc in discarded_clips:
            reason = disc.get("_overlap_reason", "Sobreposição temporal detectada")
            cursor.execute("""
                UPDATE clips
                SET youtube_status = 'SKIPPED_OVERLAP', tiktok_status = 'SKIPPED_OVERLAP', error_log = ?
                WHERE id = ? AND (youtube_status = 'PENDING' OR youtube_status IS NULL);
            """, (reason, disc["id"]))
            logger.info(f"Corte {disc.get('clip_uid')} descartado do agendamento: {reason}")

        # 3.2 Intercala os cortes válidos em Round-Robin (evita canais e episódios repetidos em sequência)
        interleaved_clips = round_robin_interleave(valid_clips, group_key="long_video_id", secondary_key="source_channel_id")

        for clip in interleaved_clips:
            clip_id = clip["id"]
            clip_uid = clip["clip_uid"]

            for acc in accounts:
                acc_id = acc["id"]
                platform = acc["platform"]
                idempotency_key = generate_idempotency_key(clip_uid, platform, acc_id)

                # Verifica se publicação já foi criada
                cursor.execute("SELECT id FROM publications WHERE idempotency_key = ?;", (idempotency_key,))
                if cursor.fetchone():
                    continue

                slot_utc = get_next_available_slot(acc_id, platform, conn)

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

                enqueued_count += 1
                logger.info(
                    f"Clip {clip_uid} (score {clip['virality_score']}) agendado para {platform} em {slot_utc.isoformat()}",
                    extra={"event": "clip_scheduled", "clip_uid": clip_uid, "platform": platform, "slot": slot_utc.isoformat()}
                )

    return enqueued_count
