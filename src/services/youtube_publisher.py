"""
Publicador do YouTube Shorts via YouTube Data API v3 com OAuth2 Resiliente.
"""
from pathlib import Path
from typing import Dict, Any, Optional
import os
import json
from datetime import datetime, timezone
import google.auth
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from src.core.config import settings
from src.core.logger import get_logger
from src.core.exceptions import YouTubePublishError, QuotaExceededError

logger = get_logger("youtube_publisher")

class YouTubePublisher:
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    def __init__(self, token_path: Optional[Path] = None):
        self.token_path = token_path or settings.YOUTUBE_TOKEN_PATH

    def get_authenticated_service(self):
        """Carrega e renova silenciosamente as credenciais OAuth2."""
        if not self.token_path.exists():
            return None

        try:
            creds = Credentials.from_authorized_user_file(str(self.token_path), self.SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(self.token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            return build("youtube", "v3", credentials=creds)
        except Exception as e:
            logger.error(f"Erro ao autenticar cliente YouTube: {e}")
            return None

    def publish_short(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list,
        clip_uid: str
    ) -> Dict[str, Any]:
        """
        Publica o corte vertical como Shorts no YouTube com tag #Shorts e referência de idempotência.
        """
        if not video_path.exists():
            raise YouTubePublishError(f"Arquivo do clip não existe: {video_path}")

        # Se credenciais não existirem, simula envio seguro em modo sandbox/dry-run
        service = self.get_authenticated_service()
        if not service:
            logger.warning(
                f"[SIMULAÇÃO] Credenciais do YouTube não configuradas. Simulando envio para {clip_uid}.",
                extra={"event": "youtube_mock_publish", "clip_uid": clip_uid}
            )
            return {
                "youtube_video_id": f"mock_yt_{clip_uid[:11]}",
                "status": "POSTED",
                "simulated": True
            }

        # Garante a tag #Shorts no título ou descrição
        final_title = title.strip()
        if "#Shorts" not in final_title and "#shorts" not in final_title:
            if len(final_title) <= 52:
                final_title += " #Shorts"

        # Inclui referência interna discreta para reconciliação
        ref_footer = f"\n\n#Shorts ref:{clip_uid}"
        final_desc = (description + ref_footer)[:5000]

        body = {
            "snippet": {
                "title": final_title[:100],
                "description": final_desc,
                "tags": tags,
                "categoryId": "24"  # Entretenimento
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)

        try:
            request = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.debug(f"Upload YouTube Shorts: {int(status.progress() * 100)}%")

            video_id = response.get("id")
            logger.info(
                f"Vídeo publicado com sucesso no YouTube Shorts: https://youtube.com/shorts/{video_id}",
                extra={"event": "youtube_publish_success", "video_id": video_id, "clip_uid": clip_uid}
            )
            return {
                "youtube_video_id": video_id,
                "status": "POSTED",
                "response": response
            }

        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                logger.error("Cota da YouTube Data API excedida!", extra={"event": "youtube_quota_exceeded"})
                raise QuotaExceededError("YouTube API quota exceeded")
            raise YouTubePublishError(f"HttpError ao enviar Shorts: {e}")
        except Exception as e:
            raise YouTubePublishError(f"Erro inesperado no envio ao YouTube: {e}")
