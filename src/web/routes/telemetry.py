"""
Rotas e WebSocket de Telemetria Unificada em Tempo Real.
"""

import asyncio
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.core.config import settings
from src.core.database import get_db
from src.core.pipeline_control import PipelineController
from src.core.process_signals import SignalTracker

router = APIRouter(prefix="/api/telemetry", tags=["Telemetry"])


def get_telemetry_snapshot() -> Dict[str, Any]:
    """Coleta e agrega métricas de integridade, banco de dados e hardware."""
    # 1. Controles e Memória
    status_ctrl = PipelineController.get_all_statuses()

    # 2. Sinais de Processos
    signals = SignalTracker.get_all_signals()

    # 3. Métricas de Disco
    try:
        total_b, used_b, free_b = shutil.disk_usage(Path(settings.BASE_DIR).resolve())
        disk_pct = round((used_b / total_b) * 100, 1)
        disk_free_gb = round(free_b / (1024**3), 1)
    except Exception:
        disk_pct = 0.0
        disk_free_gb = 0.0

    # 4. Dados do Banco
    today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_db() as conn:
        cur = conn.cursor()

        # Contagens de publicações
        cur.execute("SELECT COUNT(*) as c FROM publications WHERE status = 'SCHEDULED';")
        active_queue = cur.fetchone()["c"]

        cur.execute("SELECT COUNT(*) as c FROM publications WHERE status = 'POSTED';")
        total_posted = cur.fetchone()["c"]

        cur.execute("SELECT COUNT(*) as c FROM publications WHERE status = 'FAILED';")
        failed_count = cur.fetchone()["c"]

        cur.execute(
            """
            SELECT COUNT(*) as c FROM publications
            WHERE platform = 'youtube' AND status = 'POSTED' AND published_at LIKE ?;
            """,
            (f"{today_prefix}%",),
        )
        today_youtube = cur.fetchone()["c"]

        cur.execute(
            """
            SELECT COUNT(*) as c FROM publications
            WHERE platform = 'tiktok' AND status = 'POSTED' AND published_at LIKE ?;
            """,
            (f"{today_prefix}%",),
        )
        today_tiktok = cur.fetchone()["c"]

        cur.execute("SELECT COUNT(*) as c FROM clips;")
        total_clips = cur.fetchone()["c"]

        cur.execute("SELECT COUNT(*) as c FROM long_videos;")
        total_long = cur.fetchone()["c"]

        # Próxima publicação agendada
        cur.execute(
            """
            SELECT p.id, p.platform, p.scheduled_for, c.title, c.virality_score
            FROM publications p
            JOIN clips c ON p.clip_id = c.id
            WHERE p.status = 'SCHEDULED'
            ORDER BY p.scheduled_for ASC LIMIT 1;
        """
        )
        next_pub_row = cur.fetchone()
        next_pub = dict(next_pub_row) if next_pub_row else None

        # Heartbeats
        cur.execute("SELECT service_name, last_ping, status, extra_info FROM system_heartbeats;")
        heartbeats = [dict(r) for r in cur.fetchall()]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "controls": status_ctrl.get("controls", {}),
        "system_memory": status_ctrl.get("system_memory", {}),
        "signals": signals,
        "disk": {
            "percent": disk_pct,
            "free_gb": disk_free_gb,
        },
        "stats": {
            "active_queue": active_queue,
            "total_posted": total_posted,
            "failed_count": failed_count,
            "today_youtube": today_youtube,
            "today_tiktok": today_tiktok,
            "total_clips": total_clips,
            "total_long": total_long,
            "max_daily_youtube": getattr(settings, "YOUTUBE_DAILY_UPLOAD_LIMIT", 100),
            "max_daily_tiktok": getattr(settings, "MAX_DAILY_UPLOADS_TIKTOK", 50),
        },
        "next_publication": next_pub,
        "heartbeats": heartbeats,
    }


@router.get("")
async def telemetry_endpoint():
    """Retorna um snapshot completo da telemetria."""
    return {"ok": True, "data": get_telemetry_snapshot()}


@router.websocket("/stream")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """WebSocket contínuo emitindo o snapshot a cada 1.5s."""
    await websocket.accept()
    try:
        while True:
            snapshot = get_telemetry_snapshot()
            await websocket.send_json(snapshot)
            await asyncio.sleep(1.5)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
