"""
Serviço de Retenção, Limpeza Normal, Auto-Cleanup e Proteção Emergencial de Disco.
"""
import os
import shutil
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from src.core.config import settings
from src.core.logger import get_logger
from src.core.database import get_db
from src.core.utils import safe_unlink
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

def purge_clip_files(clip_id: int, file_path_str: str, conn=None) -> int:
    """
    Remove fisicamente o arquivo do corte e seus arquivos auxiliares (.txt/transcrição),
    marcando atomicamente is_deleted_from_disk = 1 no banco de dados.
    Preserva intacto o registro da publicação, IDs externos e métricas.
    """
    freed = 0
    p = Path(file_path_str) if file_path_str else None

    if p and p.exists():
        try:
            size = p.stat().st_size
            if safe_unlink(p):
                freed += size
                logger.info(
                    f"Arquivo de vídeo do corte purgado do disco ({size / (1024*1024):.2f} MB): {p.name}",
                    extra={"event": "purge_clip_file", "clip_id": clip_id, "file_name": p.name}
                )
        except Exception as e:
            logger.error(f"Erro ao remover arquivo de vídeo {p}: {e}")

        # Remove arquivos de transcrição ou legendas associadas
        for txt_candidate in (p.with_suffix(".txt"), p.parent / f"{p.stem}_transcript.txt"):
            if txt_candidate.exists():
                try:
                    txt_size = txt_candidate.stat().st_size
                    if safe_unlink(txt_candidate):
                        freed += txt_size
                        logger.debug(f"Arquivo de transcrição auxiliar removido: {txt_candidate.name}")
                except Exception:
                    pass

    # Atualiza o status no SQLite
    def _update_db(c):
        cursor = c.cursor()
        cursor.execute("UPDATE clips SET is_deleted_from_disk = 1 WHERE id = ?;", (clip_id,))

    if conn is not None:
        _update_db(conn)
    else:
        with get_db() as local_conn:
            _update_db(local_conn)

    return freed

def check_and_purge_clip_if_fully_published(clip_id: int, conn=None) -> bool:
    """
    Hook Reativo: Verifica se o corte já cumpriu seu ciclo de vida em ambas as plataformas
    (YouTube e TikTok). Se ambas estiverem 'POSTED' ou 'SKIPPED', e o auto-cleanup estiver
    habilitado, apaga os arquivos do disco imediatamente.
    """
    if not getattr(settings, "AUTO_DELETE_POSTED_CLIPS", True):
        return False

    def _query_and_purge(c) -> bool:
        cursor = c.cursor()
        cursor.execute("""
            SELECT id, file_path, youtube_status, tiktok_status, is_deleted_from_disk
            FROM clips
            WHERE id = ?;
        """, (clip_id,))
        row = cursor.fetchone()
        if not row:
            return False

        if row["is_deleted_from_disk"] == 1:
            return False

        # Verifica se ainda há publicações ativas ou pendentes na fila
        cursor.execute("""
            SELECT count(*) as pending_count
            FROM publications
            WHERE clip_id = ? AND status IN ('SCHEDULED', 'UPLOADING', 'PENDING');
        """, (clip_id,))
        p_row = cursor.fetchone()
        if p_row and p_row["pending_count"] > 0:
            return False  # Ainda há publicações ativas aguardando este arquivo físico!

        yt_done = row["youtube_status"] in ("POSTED", "SKIPPED")
        tk_done = row["tiktok_status"] in ("POSTED", "SKIPPED")

        if yt_done and tk_done:
            freed = purge_clip_files(clip_id, row["file_path"], conn=c)
            logger.info(
                f"Auto-cleanup imediato acionado para clip #{clip_id}: YouTube ({row['youtube_status']}) "
                f"& TikTok ({row['tiktok_status']}). {freed / (1024*1024):.2f} MB liberados.",
                extra={
                    "event": "clip_auto_purged_on_dual_publish",
                    "clip_id": clip_id,
                    "freed_bytes": freed
                }
            )
            return True
        return False

    if conn is not None:
        return _query_and_purge(conn)
    else:
        with get_db() as local_conn:
            return _query_and_purge(local_conn)

def purge_orphan_temporary_files(hours_threshold: float = 2.0) -> int:
    """
    Varre os diretórios de trabalho (WATCH_DIR e OUTPUT_DIR) e exclui arquivos
    temporários abandonados (.part, .ytdl, .tmp, .temp) criados há mais de hours_threshold horas.
    """
    freed = 0
    cutoff_time = time.time() - (hours_threshold * 3600)
    dirs_to_scan = [settings.WATCH_DIR, settings.OUTPUT_DIR]

    for scan_dir in dirs_to_scan:
        if not scan_dir or not scan_dir.exists():
            continue
        try:
            for item in scan_dir.iterdir():
                if item.is_file():
                    ext = item.suffix.lower()
                    name = item.name.lower()
                    if ext in (".part", ".ytdl", ".tmp") or ".temp." in name or name.startswith("tmp_"):
                        try:
                            if item.stat().st_mtime < cutoff_time:
                                size = item.stat().st_size
                                if safe_unlink(item):
                                    freed += size
                                    logger.info(
                                        f"Arquivo temporário/órfão removido ({size / 1024:.1f} KB): {item.name}",
                                        extra={"event": "purge_temp_file", "file_name": item.name}
                                    )
                        except Exception as e:
                            logger.debug(f"Erro ao avaliar/remover temporário {item}: {e}")
        except Exception as e:
            logger.error(f"Erro ao varrer diretório {scan_dir} para limpeza temporária: {e}")

    return freed

def run_disk_cleanup(dry_run: bool = False) -> Dict[str, Any]:
    """
    Executa ciclo determinístico e proativo de limpeza de disco:
    1. Remove vídeos brutos de jobs finalizados no Supoclip.
    2. Remove clips reprovados por score.
    3. Remove clips com postagem confirmada em ambas as plataformas (imediatamente ou pós-retenção).
    4. Remove arquivos temporários e downloads interrompidos (.part, .ytdl, .tmp).
    5. Avalia limites de 75% e 85% para notificação de saúde de armazenamento.
    """
    started_at = datetime.now(timezone.utc)
    deleted_long_videos = 0
    deleted_clips = 0
    freed_bytes = 0

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Purga de vídeos longos já processados pelo Supoclip ou falhados/estagnados
        if getattr(settings, "AUTO_DELETE_LONG_VIDEOS_ON_COMPLETION", True):
            # 1.1 Concluídos ou Falhados
            cursor.execute("""
                SELECT id, file_path, status
                FROM long_videos
                WHERE status IN ('COMPLETED', 'FAILED') AND is_deleted_from_disk = 0;
            """)
            stale_long = cursor.fetchall()

            for row in stale_long:
                p = Path(row["file_path"])
                if p.exists():
                    size = p.stat().st_size
                    if not dry_run:
                        try:
                            if safe_unlink(p):
                                freed_bytes += size
                                deleted_long_videos += 1
                                cursor.execute("UPDATE long_videos SET is_deleted_from_disk = 1 WHERE id = ?;", (row["id"],))
                                logger.info(
                                    f"Vídeo longo ({row['status']}) purgado do disco ({size / (1024*1024):.2f} MB): {p.name}",
                                    extra={"event": "purge_long_video", "video_id": row["id"], "status": row["status"]}
                                )
                        except Exception as e:
                            logger.error(f"Erro ao remover vídeo bruto {p}: {e}")
                    else:
                        freed_bytes += size
                        deleted_long_videos += 1
                else:
                    if not dry_run:
                        cursor.execute("UPDATE long_videos SET is_deleted_from_disk = 1 WHERE id = ?;", (row["id"],))

            # 1.2 Vídeos travados em PROCESSING há mais de 24h sem jobs em andamento
            stale_processing_cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                SELECT id, file_path
                FROM long_videos
                WHERE status = 'PROCESSING' 
                  AND is_deleted_from_disk = 0
                  AND created_at < ?
                  AND id NOT IN (SELECT long_video_id FROM supoclip_jobs WHERE status IN ('SUBMITTED', 'PROCESSING'));
            """, (stale_processing_cutoff,))
            abandoned_processing = cursor.fetchall()

            for row in abandoned_processing:
                p = Path(row["file_path"])
                if p.exists():
                    size = p.stat().st_size
                    if not dry_run:
                        try:
                            if safe_unlink(p):
                                freed_bytes += size
                                deleted_long_videos += 1
                                cursor.execute("UPDATE long_videos SET status = 'FAILED', is_deleted_from_disk = 1, error_message = 'Timeout de processamento (>24h)' WHERE id = ?;", (row["id"],))
                                logger.info(
                                    f"Vídeo longo abandonado em PROCESSING (>24h) purgado ({size / (1024*1024):.2f} MB): {p.name}",
                                    extra={"event": "purge_stale_processing_long_video", "video_id": row["id"]}
                                )
                        except Exception as e:
                            logger.error(f"Erro ao remover vídeo longo abandonado {p}: {e}")
                    else:
                        freed_bytes += size
                        deleted_long_videos += 1
                else:
                    if not dry_run:
                        cursor.execute("UPDATE long_videos SET status = 'FAILED', is_deleted_from_disk = 1, error_message = 'Timeout de processamento (>24h)' WHERE id = ?;", (row["id"],))

            # 1.3 Arquivos .mp4 órfãos em WATCH_DIR não vinculados a nenhum vídeo ativo
            if not dry_run and settings.WATCH_DIR.exists():
                try:
                    for f in settings.WATCH_DIR.glob("*.mp4"):
                        cursor.execute("SELECT id, status FROM long_videos WHERE file_name = ? OR file_path LIKE ?;", (f.name, f"%{f.name}"))
                        db_entry = cursor.fetchone()
                        # Se não existe no banco e tem mais de 2 horas
                        if not db_entry and (time.time() - f.stat().st_mtime > 7200):
                            size = f.stat().st_size
                            if safe_unlink(f):
                                freed_bytes += size
                                deleted_long_videos += 1
                                logger.info(f"Arquivo de vídeo órfão sem registro no banco purgado: {f.name} ({size / (1024*1024):.2f} MB)")
                except Exception as e:
                    logger.debug(f"Erro na checagem de órfãos em {settings.WATCH_DIR}: {e}")

        # 2. Purga de clips reprovados (virality_score < MIN_VIRALITY_SCORE)
        if settings.MIN_VIRALITY_SCORE > 0:
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
                    if not dry_run:
                        try:
                            if safe_unlink(p):
                                freed_bytes += size
                                deleted_clips += 1
                        except Exception as e:
                            logger.error(f"Erro ao remover clip de baixo score {p}: {e}")
                    else:
                        freed_bytes += size
                        deleted_clips += 1
                if not dry_run:
                    cursor.execute("UPDATE clips SET is_deleted_from_disk = 1 WHERE id = ?;", (row["id"],))

        # 3. Purga de clips com ciclo de vida completo (YouTube + TikTok)
        if getattr(settings, "AUTO_DELETE_POSTED_CLIPS", True):
            keep_hours = getattr(settings, "KEEP_POSTED_CLIPS_HOURS", 0)
            if keep_hours <= 0:
                # Imediato
                cursor.execute("""
                    SELECT id, file_path
                    FROM clips
                    WHERE youtube_status IN ('POSTED', 'SKIPPED')
                      AND tiktok_status IN ('POSTED', 'SKIPPED')
                      AND is_deleted_from_disk = 0;
                """)
            else:
                retention_cutoff = datetime.now(timezone.utc) - timedelta(hours=keep_hours)
                cursor.execute("""
                    SELECT id, file_path
                    FROM clips
                    WHERE youtube_status IN ('POSTED', 'SKIPPED')
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
                    if not dry_run:
                        freed = purge_clip_files(row["id"], row["file_path"], conn=conn)
                        freed_bytes += freed
                        deleted_clips += 1
                    else:
                        freed_bytes += size
                        deleted_clips += 1
                else:
                    if not dry_run:
                        cursor.execute("UPDATE clips SET is_deleted_from_disk = 1 WHERE id = ?;", (row["id"],))

        # 4. Purga de arquivos residuais e parciais (.part, .ytdl, etc.)
        if not dry_run:
            temp_freed = purge_orphan_temporary_files(hours_threshold=2.0)
            freed_bytes += temp_freed

        # 5. Avaliação de Limites de Disco
        current_disk_pct = get_disk_usage_percent(settings.WATCH_DIR)

        if not dry_run:
            if current_disk_pct >= settings.DISK_HARD_THRESHOLD:
                notify_alert(
                    "CRITICAL",
                    "cleanup",
                    "Espaço em Disco Crítico",
                    f"Uso do disco em {current_disk_pct}% (Acima do limite rígido de {settings.DISK_HARD_THRESHOLD}%).",
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

            # 6. Registra o run na tabela cleanup_runs
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
        "freed_mb": round(freed_bytes / (1024 * 1024), 2),
        "disk_usage_percent": current_disk_pct,
        "dry_run": dry_run
    }
    logger.info(f"Ciclo de limpeza de disco concluído: {result}", extra={"event": "cleanup_finished", **result})
    return result

if __name__ == "__main__":
    import sys
    is_dry = "--dry-run" in sys.argv
    res = run_disk_cleanup(dry_run=is_dry)
    print(f"Limpeza de disco executada: {res}")
