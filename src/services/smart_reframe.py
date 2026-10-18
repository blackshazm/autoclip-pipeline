"""
Serviço de Enquadramento Facial Inteligente (Smart Reframe) para Shorts & TikTok.
Modo Híbrido:
- 1 Pessoa Detectada (Solo): Formato Smart Headroom (foco no rosto com 20% de respiro superior).
- 2 ou Mais Pessoas (Diálogo/Debate): Formato Blurred Background Fit (vídeo 16:9 completo no centro + fundo desfocado).
"""

import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional

try:
    import cv2
except ImportError:
    cv2 = None

from src.core.config import settings
from src.core.logger import get_logger
from src.services.media_validator import verify_media_integrity, inspect_media_file

logger = get_logger("smart_reframe")


def detect_speaker_count(video_path: Path, max_samples: int = 5) -> int:
    """
    Analisa frames do vídeo com MediaPipe Face Detection para contar o número de pessoas no plano.
    Retorna a quantidade consistente de rostos encontrados (1 para solo, 2+ para diálogo/grupo).
    """
    if cv2 is None:
        logger.debug("OpenCV (cv2) não instalado no ambiente. Usando 1 interlocutor padrão.")
        return 1

    if not video_path.exists() or video_path.stat().st_size <= 0:
        return 1

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 1

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        return 1

    # Amostra frames distribuídos ao longo do vídeo (evitando introdução/encerramento estáticos)
    step = max(1, total_frames // (max_samples + 1))
    sample_indices = [step * i for i in range(1, max_samples + 1)]

    face_counts = []

    try:
        import mediapipe as mp

        # MediaPipe Face Detection (modelo 0 para rostos próximos/médios)
        mp_face = mp.solutions.face_detection
        with mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.45) as detector:
            for idx in sample_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue

                # Converte para RGB para o MediaPipe
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = detector.process(rgb)

                if results.detections:
                    # Filtra detecções com área razoável para evitar falsos positivos no fundo
                    valid_detections = 0
                    for det in results.detections:
                        box = det.location_data.relative_bounding_box
                        # Bounding box com largura e altura mínimas de 5% da tela
                        if box.width >= 0.05 and box.height >= 0.05:
                            valid_detections += 1
                    face_counts.append(valid_detections)
                else:
                    face_counts.append(0)

    except Exception as e:
        logger.warning(f"Erro na detecção MediaPipe para {video_path.name}: {e}. Assumindo 1 pessoa.")
        cap.release()
        return 1
    finally:
        cap.release()

    if not face_counts:
        return 1

    # Se na maioria dos frames válidos ou em pelo menos 2 frames foram vistos 2 ou mais rostos
    multi_person_frames = [c for c in face_counts if c >= 2]
    if len(multi_person_frames) >= 2 or (
        len(face_counts) > 0 and max(face_counts) >= 2 and len(multi_person_frames) >= len(face_counts) / 2
    ):
        logger.info(f"Cena de diálogo com múltiplos interlocutores detectada em {video_path.name}: {face_counts}")
        return 2

    logger.info(f"Cena com 1 interlocutor principal detectada em {video_path.name}: {face_counts}")
    return 1


def build_reframe_filter(mode: str, width: int, height: int, headroom_ratio: float = 0.20) -> str:
    """
    Constrói a cadeia de filtros FFmpeg para o modo selecionado:
    - 'blurred_fit': Vídeo 16:9 completo no centro (1080x608) com fundo blur 1080x1920.
    - 'headroom': Vídeo com 20% de respiro no topo para nunca cortar a cabeça e fundo blur.
    """
    if mode == "blurred_fit":
        return (
            "[0:v]split=2[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg_blur];"
            "[fg]scale=1080:608:flags=lanczos[fg_fit];"
            "[bg_blur][fg_fit]overlay=0:(H-h)/2-80[v]"
        )

    # Modo 'headroom' padrão (garante 220px de respiro acima do topo da cabeça)
    return (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg_blur];"
        "[fg]crop=w='min(in_w,in_h*9/16*1.4)':h='in_h':x='(in_w-out_w)/2':y=0,scale=960:1152:flags=lanczos[fg_scaled];"
        "[bg_blur][fg_scaled]overlay=(W-w)/2:220[v]"
    )


def apply_smart_reframe(clip_path: Path, mode_override: Optional[str] = None) -> bool:
    """
    Aplica o enquadramento facial inteligente no clipe.
    No modo 'hybrid', escolhe 'blurred_fit' se houver 2+ interlocutores ou 'headroom' para 1 pessoa.
    Retorna True se processado com sucesso ou se já estiver no formato correto.
    """
    if not getattr(settings, "ENABLE_SMART_REFRAME", True):
        return True

    if not clip_path.exists() or clip_path.stat().st_size <= 0:
        logger.error(f"Arquivo de vídeo não encontrado para reframe: {clip_path}")
        return False

    try:
        meta = inspect_media_file(clip_path)
        w = int(meta.get("width", 0))
        h = int(meta.get("height", 0))
    except Exception as e:
        logger.warning(f"Erro ao obter dimensões de {clip_path.name}: {e}")
        w, h = 0, 0

    # Se já for vertical (w <= h, ex: 1080x1920) e não houver solicitação explícita de override,
    # mantém o enquadramento original de IA do Supoclip que já foca perfeitamente nos rostos.
    is_horizontal = w > h
    if not is_horizontal and not mode_override:
        logger.info(
            f"Vídeo {clip_path.name} já está em formato vertical 9:16 ({w}x{h}) com enquadramento facial da IA. Reframe ignorado para preservar os rostos e a qualidade."
        )
        return True

    chosen_mode = mode_override or getattr(settings, "REFRAME_MODE", "hybrid")
    if chosen_mode == "disabled":
        return True

    if chosen_mode == "hybrid":
        speakers = detect_speaker_count(clip_path)
        active_mode = "blurred_fit" if speakers >= 2 else "headroom"
    else:
        active_mode = chosen_mode

    logger.info(f"Aplicando Smart Reframe em {clip_path.name} (Modo: {active_mode}, Origem: {w}x{h})...")

    headroom_ratio = getattr(settings, "REFRAME_HEADROOM_RATIO", 0.20)
    filter_complex = build_reframe_filter(active_mode, w, h, headroom_ratio=headroom_ratio)

    temp_output = clip_path.with_suffix(".reframe.tmp.mp4")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(clip_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(temp_output),
    ]

    start_time = time.time()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            logger.error(f"Falha ao executar smart reframe em {clip_path.name}: {res.stderr[:200]}")
            temp_output.unlink(missing_ok=True)
            return False

        if not temp_output.exists() or temp_output.stat().st_size <= 0:
            temp_output.unlink(missing_ok=True)
            return False

        if not verify_media_integrity(temp_output):
            logger.error(f"Vídeo reenquadrado reprovado na validação de integridade: {temp_output}")
            temp_output.unlink(missing_ok=True)
            return False

        shutil.move(str(temp_output), str(clip_path))
        elapsed = round(time.time() - start_time, 2)
        logger.info(
            f"Smart Reframe concluído para {clip_path.name} em {elapsed}s (Modo: {active_mode}).",
            extra={"event": "smart_reframe_applied", "mode": active_mode, "elapsed": elapsed},
        )
        return True

    except Exception as e:
        logger.error(f"Exceção ao aplicar smart reframe em {clip_path.name}: {e}", exc_info=True)
        temp_output.unlink(missing_ok=True)
        return False
