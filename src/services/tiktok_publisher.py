"""
Publicador do TikTok via Content Posting API com Isolamento de Falhas.
"""
from pathlib import Path
from typing import Dict, Any, Optional
import requests
import json

from src.core.config import settings
from src.core.logger import get_logger
from src.core.exceptions import TikTokPublishError

logger = get_logger("tiktok_publisher")

class TikTokPublisher:
    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or settings.TIKTOK_ACCESS_TOKEN
        self.mode = settings.TIKTOK_MODE

    def publish_video(
        self,
        video_path: Path,
        title: str,
        tags: list,
        clip_uid: str
    ) -> Dict[str, Any]:
        """
        Publica vídeo vertical no TikTok via Content Posting API oficial ou simulação isolada.
        """
        if not video_path.exists():
            raise TikTokPublishError(f"Arquivo não encontrado: {video_path}")

        # Se token não configurado, opera em modo simulado/skip seguro
        if not self.access_token:
            logger.warning(
                f"[SIMULAÇÃO] Token do TikTok não configurado. Simulando envio para {clip_uid}.",
                extra={"event": "tiktok_mock_publish", "clip_uid": clip_uid}
            )
            return {
                "tiktok_post_id": f"mock_tk_{clip_uid[:10]}",
                "status": "POSTED",
                "simulated": True
            }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8"
        }

        # 1. Inicializa o post
        init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
        caption = f"{title} " + " ".join([f"#{t.lstrip('#')}" for t in tags])
        payload = {
            "post_info": {
                "title": caption[:150],
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_duet": False,
                "disable_stitch": False,
                "disable_comment": False
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_path.stat().st_size,
                "chunk_size": video_path.stat().st_size,
                "total_chunk_count": 1
            }
        }

        try:
            init_res = requests.post(init_url, headers=headers, json=payload, timeout=30)
            if init_res.status_code != 200:
                raise TikTokPublishError(f"Erro init TikTok ({init_res.status_code}): {init_res.text}")

            data = init_res.json().get("data", {})
            publish_id = data.get("publish_id")
            upload_url = data.get("upload_url")

            if not upload_url:
                raise TikTokPublishError(f"Upload URL não retornada pelo TikTok: {init_res.text}")

            # 2. Upload do arquivo
            with open(video_path, "rb") as f:
                upload_res = requests.put(
                    upload_url,
                    data=f,
                    headers={"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{video_path.stat().st_size - 1}/{video_path.stat().st_size}"},
                    timeout=180
                )

            if upload_res.status_code not in (200, 201, 204):
                raise TikTokPublishError(f"Erro upload vídeo TikTok ({upload_res.status_code}): {upload_res.text}")

            logger.info(
                f"Vídeo postado no TikTok com sucesso! Publish ID: {publish_id}",
                extra={"event": "tiktok_publish_success", "publish_id": publish_id, "clip_uid": clip_uid}
            )
            return {
                "tiktok_post_id": publish_id,
                "status": "POSTED",
                "response": data
            }

        except requests.RequestException as e:
            raise TikTokPublishError(f"Falha de rede ao publicar no TikTok: {e}")
