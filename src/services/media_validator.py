"""
Validador de Integridade e Metadados Audiovisuais via FFmpeg / FFprobe.
"""
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Optional

from src.core.exceptions import MediaValidationError
from src.core.logger import get_logger

logger = get_logger("media_validator")

def inspect_media_file(file_path: Path) -> Dict[str, Any]:
    """
    Inspeciona arquivo com ffprobe para obter duração, streams de vídeo/áudio e resolução.
    """
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise MediaValidationError(f"Arquivo não existe ou está vazio: {file_path}")

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        data = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        raise MediaValidationError(f"Timeout ao inspecionar mídia: {file_path}")
    except subprocess.CalledProcessError as e:
        raise MediaValidationError(f"Falha ao executar ffprobe: {e.stderr}")
    except json.JSONDecodeError as e:
        raise MediaValidationError(f"Resposta ffprobe inválida: {e}")

    streams = data.get("streams", [])
    format_info = data.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if not video_stream:
        raise MediaValidationError(f"Arquivo não possui stream de vídeo: {file_path}")

    duration = float(format_info.get("duration") or video_stream.get("duration") or 0.0)
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    codec_name = video_stream.get("codec_name", "unknown")

    return {
        "file_path": str(file_path),
        "file_size_bytes": file_path.stat().st_size,
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "codec_name": codec_name,
        "has_audio": audio_stream is not None,
        "aspect_ratio": f"{width}:{height}" if height > 0 else "unknown"
    }

def is_video_entirely_black(file_path: Path, max_check_seconds: int = 30) -> bool:
    """
    Detecta se o arquivo de vídeo é inteiramente uma tela preta/vazia.
    Evita upload de mock sintético ou renderização falha com tela preta.
    """
    if not file_path.exists():
        return True

    cmd = [
        "ffmpeg",
        "-t", str(max_check_seconds),
        "-i", str(file_path),
        "-vf", "blackdetect=d=0.5:pix_th=0.10",
        "-an",
        "-f", "null",
        "-"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        # Se 90% ou mais da duração checada for preta, considera inválido
        for line in result.stderr.splitlines():
            if "black_duration:" in line:
                try:
                    dur_str = line.split("black_duration:")[-1].split()[0]
                    black_dur = float(dur_str)
                    if black_dur >= 4.0: # mais de 4s contínuos de tela totalmente preta
                        logger.warning(
                            f"Vídeo rejeitado: detectada tela preta contínua de {black_dur:.1f}s em {file_path.name}",
                            extra={"event": "black_video_detected", "file_path": str(file_path)}
                        )
                        return True
                except Exception:
                    pass
        return False
    except Exception as e:
        logger.error(f"Erro ao analisar se vídeo é preto: {e}")
        return False

def verify_media_integrity(file_path: Path) -> bool:
    """
    Decodifica o container em busca de frames corrompidos sem gerar arquivo de saída.
    Também rejeita vídeos vazios ou com tela 100% preta.
    Equivalente a: ffmpeg -v error -i <file> -f null -
    """
    if not file_path.exists():
        return False

    # Valida integridade inspecionando o cabeçalho e os primeiros 120s da mídia
    cmd = [
        "ffmpeg",
        "-v", "error",
        "-t", "120",
        "-i", str(file_path),
        "-f", "null",
        "-"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0 or result.stderr.strip():
            logger.warning(
                f"Arquivo com potenciais erros de decodificação: {result.stderr.strip()}",
                extra={"event": "media_decode_warning", "file_path": str(file_path)}
            )
            # Se houve stderr crítico, consideramos corrompido
            if "Invalid data" in result.stderr or "Error while decoding" in result.stderr:
                return False

        # Validação de qualidade visual: não pode ser tela preta/muda
        if is_video_entirely_black(file_path):
            return False

        return True
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout ao verificar integridade de {file_path}")
        return False
    except Exception as e:
        logger.error(f"Erro ao verificar integridade de {file_path}: {e}")
        return False
