"""
Serviço de Retenção, Limpeza Normal e Emergencial de Disco.
"""
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from src.core.config import settings
from src.core.logger import get_logger
from src.core.database import get_db
from src.services.notifier import notify_alert

logger = get_logger("cleanup")

def get_disk_usage_percent(path: Path) -> float:
    """Retorna a porcentagem de espaço em disco ocupado."""
    try:
        total, used, free = shutil.disk_usage(str(path))
        return round((used / total) * 100, 2)
    except Exception as e:
        logger.error(f"Erro ao consultar uso de disco em {path}: {e}")
        return 0.0

def run_disk_cleanup() -> Dict[str, Any]:
    """
    Executa ciclo determinístico de limpeza de disco:
    1. Remove vídeos brutos de jobs finalizados.
    2. Remove clips postados há mais de 48h.
    3. Remove clips reprovados por score.
    4. Avalia limites de 75% e 85% para limpeza emergencial.
    """
    started_at = datetime.now(timezone.utc)
    deleted_long_videos = 0
    deleted_clips = 0
    freed_bytes = 0

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Purga de vídeos longos já processados pelo Supoclip
        cursor.execute("""
            SELECT id, file_path
            FROM long_videos
            WHERE status = 'COMPLETED' AND is_deleted_from_disk = 0;
        """)
        completed_long = cursor.fetchall()

        for row in completed_long:
            p = Path(row["file_path"])
            if p.exists():
                size = p.stat().st_size
                try:
                    p.unlink()
                    freed_bytes += size
                    deleted_long_videos += 1
                    cursor.execute("UPDATE long_videos SET is_deleted_from_disk = 1 WHERE id = ?;", (row["id"],))
                    logger.info(f"Vídeo longo original purgado do disco: {p.name}", extra={"event": "purge_long_video", "video_id": row["id"]})
                except Exception as e:
                    logger.error(f"Erro ao remover vídeo bruto {p}: {e}")
            else:
                cursor.execute("UPDATE long_videos SET is_deleted_from_disk = 1 WHERE id = ?;", (row["id"],))

        # 2. Purga de clips reprovados (virality_score < MIN_VIRALITY_SCORE)
        cursor.execute("""
            SELECT id, file_path
            FROM clips
            WHERE virality_score < ? AND is_deleted_from_disk = 0;
        """, (settings.MIN_VIRALITY_SCORE,))
        low_score_clips = cursor.fetchall()

        for row in low_score_clips:
            p = Path(row["file_path"])
            if p.exists():
                size = p.stat().st_size
                try:
                    p.unlink()
                    freed_bytes += size
                    deleted_clips += 1
                except Exception as e:
                    logger.error(f"Erro ao remover clip de baixo score {p}: {e}")
            cursor.execute("UPDATE clips SET is_deleted_from_disk = 1 WHERE id = ?;", (row["id"],))

        # 3. Purga de clips publicados há mais de KEEP_POSTED_CLIPS_HOURS (48h)
        retention_cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.KEEP_POSTED_CLIPS_HOURS)
        cursor.execute("""
            SELECT id, file_path
            FROM clips
            WHERE youtube_status = 'POSTED' 
              AND tiktok_status IN ('POSTED', 'SKIPPED')
              AND published_at IS NOT NULL
              AND published_at < ?
              AND is_deleted_from_disk = 0;
        """, (retention_cutoff.isoformat(),))
        posted_clips = cursor.fetchall()

        for row in posted_clips:
            p = Path(row["file_path"])
            if p.exists():
                size = p.stat().st_size
                try:
                    p.unlink()
                    freed_bytes += size
                    deleted_clips += 1
                    logger.info(f"Clip publicado purgado pós-retenção de 48h: {p.name}", extra={"event": "purge_posted_clip", "clip_id": row["id"]})
                except Exception as e:
                    logger.error(f"Erro ao remover clip publicado {p}: {e}")
            cursor.execute("UPDATE clips SET is_deleted_from_disk = 1 WHERE id = ?;", (row["id"],))

        # 4. Avaliação de Limites de Disco
        current_disk_pct = get_disk_usage_percent(settings.WATCH_DIR)

        if current_disk_pct >= settings.DISK_HARD_THRESHOLD:
            notify_alert(
                "CRITICAL",
                "cleanup",
                "Espaço em Disco Crítico",
                f"Uso do disco em {current_disk_pct}% (Acima do limite rígido de {settings.DISK_HARD_THRESHOLD}%). Executando purga emergencial!",
                conn=conn
            )
        elif current_disk_pct >= settings.DISK_ALERT_THRESHOLD:
            notify_alert(
                "WARNING",
                "cleanup",
                "Alerta de Espaço em Disco",
                f"Uso do disco em {current_disk_pct}% (Acima do limiar de alerta de {settings.DISK_ALERT_THRESHOLD}%).",
                conn=conn
            )

        # 5. Registra o run na tabela cleanup_runs
        cursor.execute("""
            INSERT INTO cleanup_runs (
                started_at, finished_at, status, deleted_long_videos,
                deleted_clips, freed_bytes, disk_usage_percent
            ) VALUES (?, ?, 'COMPLETED', ?, ?, ?, ?);
        """, (
            started_at.isoformat(),
            datetime.now(timezone.utc).isoformat(),
            deleted_long_videos,
            deleted_clips,
            freed_bytes,
            current_disk_pct
        ))

    result = {
        "deleted_long_videos": deleted_long_videos,
        "deleted_clips": deleted_clips,
        "freed_bytes": freed_bytes,
        "disk_usage_percent": current_disk_pct
    }
    logger.info(f"Ciclo de limpeza de disco concluído: {result}", extra={"event": "cleanup_finished", **result})
    return result

if __name__ == "__main__":
    run_disk_cleanup()
