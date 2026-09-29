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
        SELECT MAX(scheduled_for) as last_sched
        FROM publications
        WHERE publishing_account_id = ? AND platform = ? AND status IN ('SCHEDULED', 'UPLOADING', 'POSTED');
    """, (account_id, platform))
    row = cursor.fetchone()

    min_interval = timedelta(minutes=settings.POST_INTERVAL_MINUTES)
    base_time = now_local

    if row and row["last_sched"]:
        try:
            last_dt = datetime.fromisoformat(row["last_sched"]).astimezone(tz)
            if last_dt + min_interval > base_time:
                base_time = last_dt + min_interval
        except Exception:
            pass

    windows = sorted(settings.DEFAULT_POSTING_WINDOWS)
    candidate_date = base_time.date()

    for day_offset in range(14): # Procura nos próximos 14 dias
        current_day = candidate_date + timedelta(days=day_offset)
        for window_str in windows:
            hour, minute = map(int, window_str.split(":"))
            jitter_seconds = random.randint(30, 300)
            slot = datetime(current_day.year, current_day.month, current_day.day, hour, minute, tzinfo=tz) + timedelta(seconds=jitter_seconds)

            if slot >= base_time:
                return slot.astimezone(timezone.utc)

    # Fallback seguro: 3 horas a partir de agora
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

        # 3. Busca clips aprovados que possuem metadados gerados ordenados por virality_score DESC
        cursor.execute("""
            SELECT id, clip_uid, virality_score, title, created_at
            FROM clips
            WHERE virality_score >= ? 
              AND moderation_status = 'APPROVED'
              AND title IS NOT NULL
            ORDER BY virality_score DESC, created_at DESC;
        """, (settings.MIN_VIRALITY_SCORE,))
        clips = cursor.fetchall()

        for clip in clips:
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
