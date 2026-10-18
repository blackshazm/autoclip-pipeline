"""
Serviço de Otimização Audiovisual: Pacing, Retenção e Seamless Loop (Loop Infinito).
Aplica técnicas avançadas com FFmpeg:
1. Pacing Acelerado (atempo 1.05x com preservação de pitch vocal e sincronismo labial).
2. Normalização de Volume Broadcast EBU R128 (-14 LUFS para YouTube Shorts / TikTok).
3. Seamless Loop: Detecção e eliminação de cauda de silêncio (tail trimming) e micro-fades
   de áudio anti-pop (zero-crossing smoothing) para retenção >100% em vídeos repetidos.
"""

import subprocess
import shutil
import time
import re
from pathlib import Path
from typing import Optional

from src.core.config import settings
from src.core.logger import get_logger
from src.services.media_validator import verify_media_integrity, inspect_media_file

logger = get_logger("video_pacing")


def detect_tail_silence(
    clip_path: Path,
    total_duration: float,
    threshold_db: int = -35,
    min_silence_sec: float = 0.20,
    max_tail_window_sec: float = 3.0,
) -> Optional[float]:
    """
    Analisa o áudio do arquivo e detecta se há silêncio morto na cauda final do vídeo.
    Retorna o timestamp (em segundos) onde o áudio útil encerra, ou None se não houver silêncio.
    """
    if not clip_path.exists() or total_duration <= 1.0:
        return None

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(clip_path),
        "-af",
        f"silencedetect=n={threshold_db}dB:d={min_silence_sec}",
        "-f",
        "null",
        "-",
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        stderr = res.stderr

        starts = [float(x) for x in re.findall(r"silence_start:\s*([\d\.]+)", stderr)]
        ends = [float(x) for x in re.findall(r"silence_end:\s*([\d\.]+)", stderr)]

        if not starts:
            return None

        last_start = starts[-1]
        tail_diff = total_duration - last_start

        # Verifica se o silêncio iniciou na janela final do vídeo
        if 0.15 <= tail_diff <= max_tail_window_sec:
            # Se não houver fim de silêncio após esse início, ou o fim estiver no final do arquivo
            if not ends or ends[-1] <= last_start or (total_duration - ends[-1]) <= 0.25:
                logger.info(
                    f"Cauda de silêncio detectada em {clip_path.name}: início={last_start:.2f}s, "
                    f"duração_total={total_duration:.2f}s (economia de {tail_diff:.2f}s para loop contínuo)."
                )
                return round(last_start, 3)

        return None

    except Exception as e:
        logger.warning(f"Erro ao detectar silêncio de cauda para {clip_path.name}: {e}")
        return None


def optimize_clip_pacing(
    clip_path: Path, speed_factor: Optional[float] = None, enable_loop: Optional[bool] = None
) -> bool:
    """
    Otimiza ritmo e retenção do vídeo em passagem única no FFmpeg:
    - Pacing com preservação vocal (1.05x por padrão).
    - Remoção de silêncio morto na cauda (Seamless Loop).
    - Micro-fades de áudio anti-pop (25ms in / 25ms out) para loop contínuo.
    - Normalização de áudio para -14 LUFS.
    """
    pacing_active = getattr(settings, "ENABLE_VIDEO_PACING", True)
    loop_active = getattr(settings, "ENABLE_SEAMLESS_LOOP", True) if enable_loop is None else enable_loop

    if not pacing_active and not loop_active:
        logger.debug("Otimização de pacing e seamless loop desativadas nas configurações.")
        return True

    if not clip_path.exists() or clip_path.stat().st_size <= 0:
        logger.error(f"Arquivo não encontrado para otimização: {clip_path}")
        return False

    try:
        media_meta = inspect_media_file(clip_path)
        orig_duration = float(media_meta.get("duration_seconds") or 0.0)
    except Exception as e_meta:
        logger.warning(f"Não foi possível obter duração de {clip_path.name}: {e_meta}")
        orig_duration = 0.0

    if orig_duration <= 0.5:
        logger.debug(f"Duração de {clip_path.name} muito curta ({orig_duration}s). Ignorando otimização.")
        return True

    # 1. Pacing Factor
    factor = speed_factor if speed_factor is not None else getattr(settings, "VIDEO_SPEED_FACTOR", 1.05)
    if not pacing_active or factor < 1.01 or factor > 1.25:
        factor = 1.0  # Sem aceleração de tempo

    # 2. Seamless Loop: Tail Silence Trimming
    tail_trim_timestamp: Optional[float] = None
    if loop_active and getattr(settings, "SEAMLESS_LOOP_TRIM_TAIL_SILENCE", True):
        threshold_db = getattr(settings, "SEAMLESS_LOOP_TAIL_SILENCE_THRESHOLD_DB", -35)
        min_silence = getattr(settings, "SEAMLESS_LOOP_TAIL_MIN_SILENCE_SEC", 0.20)
        tail_trim_timestamp = detect_tail_silence(clip_path, orig_duration, threshold_db, min_silence)

    input_duration = tail_trim_timestamp if tail_trim_timestamp is not None else orig_duration
    final_duration = input_duration / factor
    pts_factor = round(1.0 / factor, 5)

    # 3. Micro-fades Anti-Pop de Áudio
    audio_filters = []
    if factor != 1.0:
        audio_filters.append(f"atempo={factor}")

    audio_filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")

    if loop_active:
        fade_ms = getattr(settings, "SEAMLESS_LOOP_FADE_MS", 25)
        fade_sec = max(0.01, min(0.08, fade_ms / 1000.0))
        fade_out_start = max(0.0, round(final_duration - fade_sec, 3))
        audio_filters.append(f"afade=t=in:ss=0:d={fade_sec}")
        audio_filters.append(f"afade=t=out:st={fade_out_start}:d={fade_sec}")

    filter_complex_audio = ",".join(audio_filters)
    filter_complex = f"[0:v]setpts={pts_factor}*PTS[v];[0:a]{filter_complex_audio}[a]"

    temp_output = clip_path.with_suffix(".pacing.tmp.mp4")

    cmd = [
        "ffmpeg",
        "-y",
    ]
    if tail_trim_timestamp is not None:
        cmd.extend(["-t", str(tail_trim_timestamp)])

    cmd.extend(
        [
            "-i",
            str(clip_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(temp_output),
        ]
    )

    start_time = time.time()
    try:
        logger.info(
            f"Otimizando clipe {clip_path.name} (Pacing: {factor}x, Loop: {loop_active}, "
            f"Cauda Cortada: {tail_trim_timestamp is not None})..."
        )
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # Fallback se loudnorm falhar por áudio muito curto
        if res.returncode != 0:
            logger.warning(f"Otimização com loudnorm falhou para {clip_path.name}. Executando fallback sem loudnorm...")
            fallback_audio_filters = [f for f in audio_filters if not f.startswith("loudnorm")]
            fb_audio_str = ",".join(fallback_audio_filters) if fallback_audio_filters else "anull"
            fallback_filter = f"[0:v]setpts={pts_factor}*PTS[v];[0:a]{fb_audio_str}[a]"

            cmd_fallback = ["ffmpeg", "-y"]
            if tail_trim_timestamp is not None:
                cmd_fallback.extend(["-t", str(tail_trim_timestamp)])
            cmd_fallback.extend(
                [
                    "-i",
                    str(clip_path),
                    "-filter_complex",
                    fallback_filter,
                    "-map",
                    "[v]",
                    "-map",
                    "[a]",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "22",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-movflags",
                    "+faststart",
                    str(temp_output),
                ]
            )
            res = subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=120)

        if res.returncode != 0:
            logger.error(f"Falha no FFmpeg ao otimizar clipe {clip_path.name}: {res.stderr[:200]}")
            temp_output.unlink(missing_ok=True)
            return False

        if not temp_output.exists() or temp_output.stat().st_size <= 0:
            logger.error(f"Arquivo temporário gerado vazio para {clip_path.name}")
            temp_output.unlink(missing_ok=True)
            return False

        # Valida integridade do arquivo gerado antes de substituir o original
        if not verify_media_integrity(temp_output):
            logger.error(f"Arquivo otimizado reprovado na validação de integridade: {temp_output}")
            temp_output.unlink(missing_ok=True)
            return False

        # Substituição atômica
        shutil.move(str(temp_output), str(clip_path))
        elapsed = round(time.time() - start_time, 2)
        logger.info(
            f"Otimização concluída com sucesso para {clip_path.name} em {elapsed}s "
            f"(Pacing={factor}x, Duração={final_duration:.2f}s).",
            extra={"event": "pacing_optimized", "clip": clip_path.name, "elapsed": elapsed},
        )
        return True

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout ao otimizar clipe {clip_path.name}")
        temp_output.unlink(missing_ok=True)
        return False
    except Exception as e:
        logger.error(f"Exceção ao otimizar clipe {clip_path.name}: {e}", exc_info=True)
        temp_output.unlink(missing_ok=True)
        return False
