"""
Serviço de Download de Vídeos Longos via yt-dlp com Proteção Anti-Bot.
"""
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from src.core.config import settings
from src.core.logger import get_logger
from src.services.media_validator import inspect_media_file, verify_media_integrity

logger = get_logger("downloader")

def download_youtube_video(youtube_id: str, output_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Baixa um vídeo do YouTube em qualidade 720p/1080p usando yt-dlp de forma segura e atômica.
    """
    dest_dir = output_dir or settings.WATCH_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    final_file = dest_dir / f"{youtube_id}.mp4"
    temp_template = str(dest_dir / f"{youtube_id}.temp.%(ext)s")

    if final_file.exists() and final_file.stat().st_size > 0:
        logger.info(f"Vídeo {youtube_id} já existe no diretório.", extra={"event": "download_skip_exists"})
        return final_file

    url = f"https://www.youtube.com/watch?v={youtube_id}"

    import sys
    cmd = [
        sys.executable,
        "-m", "yt_dlp",
        "--js-runtimes", "node",
        "--format", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--output", temp_template,
        "--no-playlist",
        "--no-warnings",
        "--limit-rate", "15M",  # Prevenção contra bloqueio por banda excessiva
        url
    ]

    # Injeta cookies se o arquivo existir
    if settings.YTDLP_COOKIES_PATH.exists() and settings.YTDLP_COOKIES_PATH.stat().st_size > 0:
        cmd.extend(["--cookies", str(settings.YTDLP_COOKIES_PATH)])
        logger.debug("Utilizando cookies.txt para autenticação do yt-dlp.")

    logger.info(f"Iniciando download do vídeo {youtube_id}...", extra={"event": "download_start", "youtube_id": youtube_id})

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            logger.error(
                f"Falha no download yt-dlp para {youtube_id}: {result.stderr}",
                extra={"event": "download_error", "youtube_id": youtube_id}
            )
            return None

        # Procura o arquivo gerado com o prefixo temp
        candidates = list(dest_dir.glob(f"{youtube_id}.temp.*"))
        if not candidates:
            logger.error(f"Arquivo de download não localizado para {youtube_id}")
            return None

        temp_file = candidates[0]
        # Renomeia atomicamente para o nome final
        shutil.move(str(temp_file), str(final_file))

        # Valida integridade do arquivo baixado
        if not verify_media_integrity(final_file):
            logger.error(f"Arquivo baixado corrompido: {final_file}")
            final_file.unlink(missing_ok=True)
            return None

        logger.info(
            f"Download de {youtube_id} concluído com sucesso: {final_file.name}",
            extra={"event": "download_success", "youtube_id": youtube_id, "size_bytes": final_file.stat().st_size}
        )
        return final_file

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout ao baixar vídeo {youtube_id}")
        return None
    except Exception as e:
        logger.error(f"Exceção inesperada no download de {youtube_id}: {e}")
        return None
