"""
Cliente HTTP para Integracao com o Motor de Corte Supoclip (Docker/API Local).
Suporta envio real para FastAPI (/upload e /tasks/create) com autenticacao HMAC,
alem de fallback mock para desenvolvimento e testes.
"""
import time
import uuid
import json
import hmac
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests

from src.core.config import settings
from src.core.logger import get_logger
from src.core.exceptions import SupoclipError

logger = get_logger("supoclip_client")

class SupoclipClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.SUPOCLIP_API_URL).rstrip("/")
        self.timeout = settings.SUPOCLIP_TIMEOUT_SECONDS
        self.is_mock = settings.MOCK_SUPOCLIP
        self.user_id = settings.SUPOCLIP_USER_ID
        self.auth_secret = getattr(settings, "SUPOCLIP_AUTH_SECRET", "change_me_backend_auth_secret")
        self.api_key = getattr(settings, "SUPOCLIP_API_KEY", "")

    def _get_auth_headers(self) -> Dict[str, str]:
        if self.api_key:
            return {"x-api-key": self.api_key}
        ts = str(int(time.time()))
        sig = hmac.new(
            self.auth_secret.encode("utf-8"),
            f"{self.user_id}:{ts}".encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return {
            "x-supoclip-user-id": self.user_id,
            "x-supoclip-ts": ts,
            "x-supoclip-signature": sig,
        }

    def submit_job(self, video_path: Path) -> str:
        """
        Envia o video para o Supoclip:
        1. POST /upload -> retorna {"video_path": "upload://..."}
        2. POST /tasks/create -> retorna {"task_id": "...", ...}
        """
        if self.is_mock:
            job_id = f"mock-job-{uuid.uuid4().hex[:8]}"
            logger.info(f"[MOCK] Job submetido com sucesso: {job_id}", extra={"event": "supoclip_mock_submit", "job_id": job_id})
            return job_id

        if not video_path.exists():
            raise SupoclipError(f"Arquivo de video nao encontrado para envio: {video_path}")

        headers = self._get_auth_headers()

        # 1. Upload do arquivo bruto
        upload_url = f"{self.base_url}/upload"
        try:
            logger.info(f"Fazendo upload do video {video_path.name} para o Supoclip ({upload_url})...")
            with open(video_path, "rb") as f:
                files = {"video": (video_path.name, f, "video/mp4")}
                resp_upload = requests.post(upload_url, files=files, headers=headers, timeout=self.timeout)

            if resp_upload.status_code not in (200, 201):
                raise SupoclipError(f"Erro no upload ({resp_upload.status_code}): {resp_upload.text}")

            upload_data = resp_upload.json()
            video_ref = upload_data.get("video_path")
            if not video_ref:
                raise SupoclipError(f"Resposta de upload sem video_path: {upload_data}")
        except requests.RequestException as e:
            raise SupoclipError(f"Falha de conexao com Supoclip /upload ({upload_url}): {e}")

        # 2. Criacao da tarefa de corte
        create_task_url = f"{self.base_url}/tasks/create"
        payload = {
            "source": {
                "url": video_ref,
                "title": video_path.stem
            },
            "output_format": "vertical",
            "processing_mode": "fast",
            "add_subtitles": True,
            "caption_template": "default",
            "min_duration": getattr(settings, "CLIP_MIN_DURATION_SECONDS", 50),
            "max_duration": getattr(settings, "CLIP_MAX_DURATION_SECONDS", 75),
            "target_duration": 60
        }
        try:
            headers_json = self._get_auth_headers()
            headers_json["Content-Type"] = "application/json"
            resp_task = requests.post(create_task_url, json=payload, headers=headers_json, timeout=30)
            if resp_task.status_code not in (200, 201):
                raise SupoclipError(f"Erro ao criar tarefa no Supoclip ({resp_task.status_code}): {resp_task.text}")

            task_data = resp_task.json()
            task_id = task_data.get("task_id") or task_data.get("id")
            if not task_id:
                raise SupoclipError(f"Resposta de criacao sem task_id: {task_data}")

            logger.info(f"Tarefa de corte criada no Supoclip: {task_id}", extra={"event": "supoclip_task_created", "task_id": task_id})
            return str(task_id)
        except requests.RequestException as e:
            raise SupoclipError(f"Falha ao despachar tarefa no Supoclip ({create_task_url}): {e}")

    def get_job_status(self, job_id: str, original_video_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Consulta o status do job (task_id) no Supoclip.
        Retorna dicionario com:
        - status: 'PROCESSING' | 'COMPLETED' | 'FAILED'
        - clips: lista de clips com virality_score, transcricao e metadados.
        """
        if self.is_mock:
            return self._generate_mock_result(job_id, original_video_path)

        url = f"{self.base_url}/tasks/{job_id}"
        headers = self._get_auth_headers()
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 404:
                return {"status": "FAILED", "error": f"Job/Task {job_id} nao encontrado no Supoclip."}
            if response.status_code != 200:
                return {"status": "PROCESSING", "message": f"HTTP {response.status_code}"}

            task = response.json()
            backend_status = (task.get("status") or "").lower()

            if backend_status == "completed":
                raw_clips = task.get("clips", [])
                clips: List[Dict[str, Any]] = []
                output_dir = settings.OUTPUT_DIR
                output_dir.mkdir(parents=True, exist_ok=True)

                for c in raw_clips:
                    clip_id = str(c.get("id"))
                    clip_filename = c.get("filename") or f"{clip_id}.mp4"
                    local_clip_path = output_dir / clip_filename
                    local_transcript_path = output_dir / f"{clip_id}_transcript.txt"

                    # Download do arquivo de video se ainda nao salvo localmente
                    video_url = c.get("video_url")
                    if video_url and not local_clip_path.exists():
                        download_url = f"{self.base_url}{video_url}" if video_url.startswith("/") else video_url
                        try:
                            dl_headers = self._get_auth_headers()
                            with requests.get(download_url, headers=dl_headers, stream=True, timeout=120) as r:
                                if r.status_code == 200:
                                    with open(local_clip_path, "wb") as f_out:
                                        for chunk in r.iter_content(chunk_size=65536):
                                            f_out.write(chunk)
                                else:
                                    logger.warning(f"Nao foi possivel baixar o corte {clip_id}: HTTP {r.status_code}")
                        except Exception as e:
                            logger.error(f"Erro ao baixar corte {clip_id}: {e}")

                    # Salva transcricao
                    transcript_text = c.get("text", "")
                    if transcript_text:
                        with open(local_transcript_path, "w", encoding="utf-8") as f_tr:
                            f_tr.write(transcript_text)

                    # Calcula virality_score
                    virality = int(c.get("virality_score") or 0)
                    if virality == 0 and c.get("relevance_score"):
                        virality = int(float(c["relevance_score"]) * 100)
                    if virality == 0:
                        virality = 80

                    # Extrai dados de série se disponíveis
                    series_id = c.get("series_id")
                    try:
                        part_number = int(c.get("part_number") or 1)
                    except (ValueError, TypeError):
                        part_number = 1
                    try:
                        total_parts = int(c.get("total_parts") or 1)
                    except (ValueError, TypeError):
                        total_parts = 1

                    hook_title = c.get("hook_title") or ""
                    if not series_id and hook_title:
                        p_match = re.search(r'\[Parte\s*(\d+)/(\d+)\]', hook_title, re.IGNORECASE)
                        if p_match:
                            series_id = f"series-{job_id}"
                            part_number = int(p_match.group(1))
                            total_parts = int(p_match.group(2))

                    clips.append({
                        "clip_uid": clip_id,
                        "file_path": str(local_clip_path),
                        "start_seconds": c.get("start_time"),
                        "end_seconds": c.get("end_time"),
                        "duration_seconds": float(c.get("duration") or 0),
                        "virality_score": virality,
                        "transcription_path": str(local_transcript_path),
                        "width": 1080,
                        "height": 1920,
                        "fps": 30.0,
                        "subtitle_mode": "burned",
                        "crop_mode": "face_center",
                        "series_id": series_id,
                        "part_number": part_number,
                        "total_parts": total_parts,
                        "hook_title": hook_title,
                    })

                return {
                    "job_id": job_id,
                    "status": "COMPLETED",
                    "clips": clips
                }

            elif backend_status in ("failed", "error", "cancelled"):
                return {
                    "job_id": job_id,
                    "status": "FAILED",
                    "error": task.get("error_code") or task.get("progress_message") or "Supoclip processing failed"
                }
            else:
                return {
                    "job_id": job_id,
                    "status": "PROCESSING",
                    "progress": task.get("progress", 0),
                    "message": task.get("progress_message", "Processando corte...")
                }

        except requests.RequestException as e:
            logger.warning(f"Erro ao consultar status da tarefa {job_id}: {e}")
            return {"status": "PROCESSING", "error": str(e)}

    def _generate_mock_result(self, job_id: str, original_video_path: Optional[Path]) -> Dict[str, Any]:
        """
        Gera resultado sintetico para desenvolvimento/testes, criando arquivos reais de clips 9:16.
        """
        output_dir = settings.OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        clips: List[Dict[str, Any]] = []
        scores = [88, 76, 52] # 2 qualificados (>=70) e 1 reprovado (<70)

        for i, score in enumerate(scores, 1):
            clip_uid = f"{job_id}-clip-{i}"
            clip_filename = f"{clip_uid}.mp4"
            clip_path = output_dir / clip_filename
            transcription_path = output_dir / f"{clip_uid}_transcript.txt"

            # Cria transcricao de exemplo
            transcript_text = (
                "Esse e o maior segredo que ninguem nunca te contou sobre como a inteligencia artificial "
                "esta revolucionando o mercado em 2026. Se voce nao prestar atencao agora, vai ficar para tras."
            )
            with open(transcription_path, "w", encoding="utf-8") as f:
                f.write(transcript_text)

            # Gera um video vertical 9:16 sintetico curto de 5s usando ffmpeg caso nao exista
            if not clip_path.exists():
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=5:r=30",
                    "-f", "lavfi", "-i", "sine=f=440:d=5",
                    "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-shortest",
                    str(clip_path)
                ]
                try:
                    subprocess.run(cmd, capture_output=True, timeout=15)
                except Exception:
                    with open(clip_path, "wb") as f:
                        f.write(b"\x00" * 1024)

            clips.append({
                "clip_uid": clip_uid,
                "file_path": str(clip_path),
                "start_seconds": float(i * 60),
                "end_seconds": float(i * 60 + 58),
                "duration_seconds": 58.0,
                "virality_score": score,
                "transcription_path": str(transcription_path),
                "width": 1080,
                "height": 1920,
                "fps": 30.0,
                "subtitle_mode": "burned",
                "crop_mode": "face_center"
            })

        return {
            "job_id": job_id,
            "status": "COMPLETED",
            "clips": clips
        }
