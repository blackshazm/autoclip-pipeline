"""
MÓDULO 1: Ingestão Determinística e Despacho para Supoclip (robot1_ingest.py).
Validação de integridade audiovisual, hash SHA-256 e submissão atômica de jobs.
"""
import argparse
import hashlib
import time
from pathlib import Path
from typing import Optional, List

from src.core.config import settings
from src.core.logger import get_logger
from src.core.database import get_db
from src.services.media_validator import inspect_media_file, verify_media_integrity
from src.services.supoclip_client import SupoclipClient
from src.services.watchdog import record_heartbeat
from src.core.process_signals import SignalTracker

logger = get_logger("robot1_ingest")

KNOWN_FILES_CACHE: dict = {}

def compute_sha256(file_path: Path) -> str:
    """Calcula hash SHA-256 em blocos para evitar sobrecarga de memória RAM."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def is_file_fully_written(file_path: Path, check_interval: float = 2.5) -> bool:
    """Valida se o arquivo terminou de ser gravado no disco (trava de download incompleto)."""
    try:
        initial_size = file_path.stat().st_size
        time.sleep(check_interval)
        final_size = file_path.stat().st_size
        return initial_size == final_size and final_size > 0
    except Exception:
        return False

def process_single_video(video_path: Path, client: SupoclipClient) -> bool:
    """
    Processa um único arquivo de vídeo longo:
    Validação -> Hash SHA-256 -> Registro no DB -> Despacho para Supoclip.
    """
    path_key = str(video_path.resolve())
    try:
        stat_info = video_path.stat()
        mtime = stat_info.st_mtime
        size = stat_info.st_size
    except Exception:
        return False

    cached = KNOWN_FILES_CACHE.get(path_key)
    if cached and cached.get("mtime") == mtime and cached.get("size") == size:
        return False

    if not is_file_fully_written(video_path):
        logger.debug(f"Arquivo {video_path.name} ainda em escrita. Postergando...")
        return False

    # Valida integridade via FFmpeg
    if not verify_media_integrity(video_path):
        logger.error(f"Arquivo corrompido ou inválido detectado: {video_path.name}")
        return False

    try:
        media_info = inspect_media_file(video_path)
    except Exception as e:
        logger.error(f"Erro ao extrair metadados de {video_path.name}: {e}")
        return False

    file_hash = compute_sha256(video_path)
    file_name = video_path.name
    youtube_id = video_path.stem if len(video_path.stem) == 11 else None

    with get_db() as conn:
        cursor = conn.cursor()

        # Checagem de Idempotência Primária: Hash já processado?
        cursor.execute("SELECT id, status, supoclip_job_id FROM long_videos WHERE file_hash = ?;", (file_hash,))
        existing = cursor.fetchone()

        if existing:
            if existing["status"] in ("COMPLETED", "PROCESSING"):
                KNOWN_FILES_CACHE[path_key] = {"mtime": mtime, "size": size}
                logger.info(
                    f"Vídeo '{file_name}' já processado com sucesso ou em andamento (ID {existing['id']}, Status: {existing['status']}). Ignorando duplicação.",
                    extra={"event": "ingest_duplicate_ignored", "file_hash": file_hash}
                )
                return False
            else:
                logger.info(
                    f"Vídeo '{file_name}' com status FAILED (ID {existing['id']}). Reenviando para o Supoclip...",
                    extra={"event": "ingest_retry_failed", "file_hash": file_hash}
                )
                long_video_id = existing["id"]
                cursor.execute("UPDATE long_videos SET status = 'PROCESSING', error_message = NULL WHERE id = ?;", (long_video_id,))
        else:
            channel_name = None
            source_channel_id = None
            youtube_url = f"https://www.youtube.com/watch?v={youtube_id}" if youtube_id else None

            if youtube_id:
                cursor.execute("""
                    SELECT rc.source_channel_id, sc.name as channel_name
                    FROM radar_candidates rc
                    LEFT JOIN source_channels sc ON rc.source_channel_id = sc.id
                    WHERE rc.youtube_id = ?;
                """, (youtube_id,))
                cand_info = cursor.fetchone()
                if cand_info:
                    source_channel_id = cand_info["source_channel_id"]
                    channel_name = cand_info["channel_name"]

            # Registra novo vídeo em long_videos com status PROCESSING
            cursor.execute("""
                INSERT INTO long_videos (
                    file_hash, youtube_id, channel_name, source_channel_id,
                    file_name, file_path, youtube_url,
                    duration_seconds, file_size_bytes, media_valid, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'PROCESSING');
            """, (
                file_hash, youtube_id, channel_name, source_channel_id,
                file_name, str(video_path.resolve()), youtube_url,
                int(media_info["duration_seconds"]), media_info["file_size_bytes"]
            ))
            long_video_id = cursor.lastrowid

        # Envia para Supoclip
        try:
            SignalTracker.emit_progress("robot1_ingest", 2, 3, f"Enviando '{file_name}' para o Supoclip...")
            job_id = client.submit_job(video_path)
            cursor.execute("UPDATE long_videos SET supoclip_job_id = ? WHERE id = ?;", (job_id, long_video_id))
            cursor.execute("""
                INSERT INTO supoclip_jobs (long_video_id, supoclip_job_id, status, submitted_at)
                VALUES (?, ?, 'SUBMITTED', datetime('now'));
            """, (long_video_id, job_id))

            SignalTracker.emit_progress("robot1_ingest", 3, 3, f"Job despachado para Supoclip: ID {job_id}")
            logger.info(
                f"Vídeo '{file_name}' despachado com sucesso para o Supoclip (Job ID: {job_id})",
                extra={"event": "ingest_submitted", "long_video_id": long_video_id, "job_id": job_id}
            )
            return True

        except Exception as e:
            logger.error(f"Falha ao enviar vídeo para Supoclip: {e}", exc_info=True)
            cursor.execute("UPDATE long_videos SET status = 'FAILED', error_message = ? WHERE id = ?;", (str(e), long_video_id))
            SignalTracker.emit_finish("robot1_ingest", f"Falha no envio para Supoclip: {e}", success=False)
            return False

def run_ingestor_cycle() -> int:
    """Varre a pasta de entrada de vídeos longos e ingere novos arquivos elegíveis."""
    record_heartbeat("robot1_ingest", "RUNNING", "Iniciando varredura de vídeos longos")
    watch_dir = settings.WATCH_DIR
    watch_dir.mkdir(parents=True, exist_ok=True)

    client = SupoclipClient()
    processed_count = 0

    # Filtra arquivos reais de video, ignorando fragmentos temporários de download (.temp, .part, etc.)
    video_files = [
        f for f in watch_dir.iterdir() 
        if f.is_file() 
        and f.suffix.lower() in (".mp4", ".mkv", ".mov")
        and not f.name.startswith(".")
        and ".temp." not in f.name.lower()
        and ".part" not in f.name.lower()
        and not f.name.lower().endswith(".temp.mp4")
    ]
    total_files = len(video_files)

    if total_files > 0:
        SignalTracker.emit_start(
            "robot1_ingest",
            "Ingestão de Vídeos",
            total_steps=total_files,
            message=f"{total_files} arquivo(s) detectado(s) na pasta de entrada"
        )

    for idx, vf in enumerate(video_files, 1):
        SignalTracker.emit_progress("robot1_ingest", idx, total_files, f"Processando vídeo {idx}/{total_files}: {vf.name}")
        if process_single_video(vf, client):
            processed_count += 1

    msg_finish = f"Varredura concluída. Novos vídeos ingeridos: {processed_count}"
    record_heartbeat("robot1_ingest", "OK", msg_finish)
    SignalTracker.emit_finish("robot1_ingest", msg_finish, success=True, metadata={"ingested": processed_count})
    return processed_count

def main():
    parser = argparse.ArgumentParser(description="Módulo 1: Ingestor de Vídeos Longos")
    parser.add_argument("--once", action="store_true", help="Executa uma única rodada e finaliza")
    args = parser.parse_args()

    logger.info("Robô 1 (Ingestor) iniciado.")
    while True:
        try:
            run_ingestor_cycle()
        except Exception as e:
            logger.error(f"Erro no ciclo do robô 1: {e}", exc_info=True)

        if args.once:
            break

        time.sleep(15)

if __name__ == "__main__":
    main()
