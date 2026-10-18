"""
Rotas de Gerenciamento, Curadoria e Agendamento de Cortes.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from src.core.database import get_db
from src.core.logger import get_logger

logger = get_logger("web_clips")
router = APIRouter(prefix="/api", tags=["Clips & Publications"])


class UpdateClipPayload(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None


class ReschedulePayload(BaseModel):
    interval_minutes: int = 15


@router.get("/clips")
async def list_clips(limit: int = 50, status: Optional[str] = None):
    """Retorna os cortes mais recentes com metadados e status de agendamento."""
    query = """
        SELECT c.id, c.clip_uid, c.file_path, c.title, c.description, c.tags,
               c.virality_score, c.duration_seconds, c.created_at, c.scheduled_for,
               p.id as pub_id, p.platform, p.status as pub_status, p.published_at
        FROM clips c
        LEFT JOIN publications p ON c.id = p.clip_id
    """
    params = []
    if status:
        query += " WHERE p.status = ? "
        params.append(status)
    query += " ORDER BY c.id DESC LIMIT ?;"
    params.append(limit)

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

    clips_list = []
    for r in rows:
        d = dict(r)
        # Extrai nome base do arquivo para servir no player /media/<filename>
        fp = d.get("file_path") or ""
        d["filename"] = Path(fp).name if fp else ""
        clips_list.append(d)

    return {"ok": True, "clips": clips_list}


@router.get("/clips/{clip_id}")
async def get_clip_details(clip_id: int):
    """Retorna dados completos de um corte específico."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM clips WHERE id = ?;", (clip_id,))
        clip_row = cur.fetchone()
        if not clip_row:
            raise HTTPException(status_code=404, detail="Corte não encontrado")

        cur.execute("SELECT * FROM publications WHERE clip_id = ? ORDER BY id DESC;", (clip_id,))
        pubs = [dict(p) for p in cur.fetchall()]

    data = dict(clip_row)
    data["filename"] = Path(data.get("file_path", "")).name if data.get("file_path") else ""
    data["publications"] = pubs
    return {"ok": True, "clip": data}


@router.post("/clips/{clip_id}/update")
async def update_clip_metadata(clip_id: int, payload: UpdateClipPayload):
    """Atualiza título, descrição ou tags do corte gerado pela IA."""
    fields = []
    values = []
    if payload.title is not None:
        fields.append("title = ?")
        values.append(payload.title)
    if payload.description is not None:
        fields.append("description = ?")
        values.append(payload.description)
    if payload.tags is not None:
        fields.append("tags = ?")
        values.append(payload.tags)

    if not fields:
        return {"ok": True, "message": "Nenhum campo para atualizar"}

    values.append(clip_id)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE clips SET {', '.join(fields)} WHERE id = ?;", tuple(values))
        conn.commit()

    return {"ok": True, "clip_id": clip_id, "updated": True}


@router.post("/clips/{clip_id}/approve")
async def approve_clip(clip_id: int, immediate: bool = Query(False)):
    """Aprova o corte e agenda ou enfileira para publicação imediata."""
    now_utc = datetime.now(timezone.utc)
    scheduled_time = (
        (now_utc - timedelta(minutes=1)).isoformat() if immediate else (now_utc + timedelta(minutes=15)).isoformat()
    )

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM clips WHERE id = ?;", (clip_id,))
        clip = cur.fetchone()
        if not clip:
            raise HTTPException(status_code=404, detail="Corte não encontrado")

        cur.execute(
            "UPDATE clips SET moderation_status = 'APPROVED', scheduled_for = ? WHERE id = ?;",
            (scheduled_time, clip_id),
        )

        # Enfileira ou atualiza publications para YouTube e TikTok
        for platform in ["youtube", "tiktok"]:
            cur.execute("SELECT id FROM publishing_accounts WHERE platform = ? AND active = 1 LIMIT 1;", (platform,))
            account_row = cur.fetchone()
            account_id = account_row["id"] if account_row else 1

            cur.execute(
                """
                SELECT id FROM publications WHERE clip_id = ? AND platform = ?;
            """,
                (clip_id, platform),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE publications
                    SET status = 'SCHEDULED', scheduled_for = ?, lease_owner = NULL,
                        lease_expires_at = NULL, retry_count = 0
                    WHERE id = ?;
                """,
                    (scheduled_time, existing["id"]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO publications (clip_id, publishing_account_id, platform, scheduled_for, status)
                    VALUES (?, ?, ?, ?, 'SCHEDULED');
                """,
                    (clip_id, account_id, platform, scheduled_time),
                )

        conn.commit()

    return {"ok": True, "clip_id": clip_id, "status": "SCHEDULED", "scheduled_for": scheduled_time}


@router.post("/clips/{clip_id}/reject")
async def reject_clip(clip_id: int):
    """Descarta ou cancela a publicação de um corte."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE clips SET moderation_status = 'MODERATION_BLOCKED' WHERE id = ?;", (clip_id,))
        cur.execute("UPDATE publications SET status = 'CANCELLED' WHERE clip_id = ?;", (clip_id,))
        conn.commit()
    return {"ok": True, "clip_id": clip_id, "status": "REJECTED"}


@router.post("/schedule/interval")
async def set_post_interval(payload: ReschedulePayload):
    """Reagenda a fila ativa de cortes com base em novo intervalo de postagem."""
    interval_min = max(1, payload.interval_minutes)
    now_utc = datetime.now(timezone.utc)
    total_rescheduled = 0

    with get_db() as conn:
        cur = conn.cursor()
        for platform in ["youtube", "tiktok"]:
            cur.execute(
                """
                SELECT id, clip_id FROM publications
                WHERE platform = ? AND status = 'SCHEDULED'
                ORDER BY id ASC;
            """,
                (platform,),
            )
            rows = cur.fetchall()

            for idx, row in enumerate(rows):
                slot_iso = (
                    now_utc - timedelta(minutes=1) if idx == 0 else now_utc + timedelta(minutes=idx * interval_min)
                ).isoformat()
                cur.execute(
                    """
                    UPDATE publications
                    SET scheduled_for = ?, lease_owner = NULL, lease_expires_at = NULL
                    WHERE id = ?;
                """,
                    (slot_iso, row["id"]),
                )
                cur.execute(
                    """
                    UPDATE clips
                    SET scheduled_for = ?
                    WHERE id = ?;
                """,
                    (slot_iso, row["clip_id"]),
                )
                total_rescheduled += 1

        conn.commit()

    return {"ok": True, "count": total_rescheduled, "interval_minutes": interval_min}


@router.post("/publications/retry")
async def retry_failed_publications():
    """Libera e reinicia publicações com falha da fila DLQ."""
    now_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE publications
            SET status = 'SCHEDULED', retry_count = 0, error_code = NULL, error_message = NULL,
                scheduled_for = ?, lease_owner = NULL, lease_expires_at = NULL
            WHERE status = 'FAILED';
        """,
            (now_iso,),
        )
        reopened = cur.rowcount
        conn.commit()

    return {"ok": True, "reopened_count": reopened}
