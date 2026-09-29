"""
Serviço de Coleta e Cálculo de Métricas de Vídeos do YouTube (VPH e Outlier Factor).
"""
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import math
import requests
import json

from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger("youtube_metrics")

def parse_iso8601_duration(duration_str: str) -> int:
    """Converte duração no formato ISO 8601 (ex: PT1H23M45S) em segundos."""
    import re
    pattern = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
    match = pattern.match(duration_str)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds

def calculate_vph(view_count: int, published_at: datetime, reference_time: Optional[datetime] = None) -> float:
    """
    Calcula Views Per Hour (VPH):
    VPH = Total de Visualizações / Horas Decorridas desde a Publicação.
    """
    ref = reference_time or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    
    elapsed_seconds = max((ref - published_at).total_seconds(), 60.0)
    elapsed_hours = elapsed_seconds / 3600.0
    return round(view_count / elapsed_hours, 2)

def calculate_median_factor(vph: float, channel_median_vph: Optional[float]) -> float:
    """Calcula a taxa de aceleração sobre a mediana histórica do canal."""
    if not channel_median_vph or channel_median_vph <= 0:
        return 1.0
    return round(vph / channel_median_vph, 2)

def calculate_engagement_ratio(view_count: int, like_count: int, comment_count: int) -> float:
    """
    Calcula o índice percentual ponderado de engajamento da audiência:
    Engagement = ((likes * 2 + comments * 5) / views) * 100
    Vídeos com alta discussão e aprovação geram cortes com maior retenção e comentários.
    """
    if not view_count or view_count <= 0:
        return 0.0
    weighted_score = (like_count * 2) + (comment_count * 5)
    return round((weighted_score / view_count) * 100, 2)

def extract_video_heatmap_and_chapters(youtube_id: str) -> Dict[str, Any]:
    """
    Extrai metadados analíticos profundos via yt-dlp:
    - chapters: Divisões temáticas e títulos definidos pelos criadores.
    - heatmap: Curva de retenção ("Most Replayed") do YouTube.
    - top_peaks: Os 5 intervalos de tempo de maior replay.
    """
    import subprocess
    import sys
    cmd = [
        sys.executable,
        "-m", "yt_dlp",
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
        f"https://www.youtube.com/watch?v={youtube_id}"
    ]
    if settings.YTDLP_COOKIES_PATH.exists():
        cmd.extend(["--cookies", str(settings.YTDLP_COOKIES_PATH)])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            raw_heatmap = data.get("heatmap") or []
            chapters = data.get("chapters") or []
            
            top_peaks = []
            if raw_heatmap:
                # Ordena pontos por valor de repetição decrescente
                sorted_points = sorted(raw_heatmap, key=lambda x: x.get("value", 0.0), reverse=True)
                top_peaks = sorted_points[:8]

            return {
                "youtube_id": youtube_id,
                "has_heatmap": bool(raw_heatmap),
                "has_chapters": bool(chapters),
                "chapters": chapters,
                "top_peaks": top_peaks,
                "raw_heatmap_points": len(raw_heatmap)
            }
    except Exception as e:
        logger.warning(f"Não foi possível extrair heatmap/capítulos de {youtube_id}: {e}")

    return {
        "youtube_id": youtube_id,
        "has_heatmap": False,
        "has_chapters": False,
        "chapters": [],
        "top_peaks": [],
        "raw_heatmap_points": 0
    }

def fetch_video_metrics(youtube_id: str, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Consulta métricas na YouTube Data API v3.
    Retorna dicionário com views, likes, comments, duration_seconds e published_at.
    """
    key = api_key or settings.YOUTUBE_API_KEY
    if not key:
        logger.debug(f"YOUTUBE_API_KEY não definida. Utilizando extração alternativa para {youtube_id}")
        return fetch_video_metrics_fallback(youtube_id)

    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,contentDetails,statistics",
        "id": youtube_id,
        "key": key
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            if not items:
                return None

            item = items[0]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})

            published_str = snippet.get("publishedAt")
            published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00")) if published_str else datetime.now(timezone.utc)
            duration_seconds = parse_iso8601_duration(content.get("duration", "PT0S"))

            return {
                "youtube_id": youtube_id,
                "title": snippet.get("title", ""),
                "published_at": published_at,
                "duration_seconds": duration_seconds,
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "source": "youtube_data_api"
            }
        else:
            logger.warning(
                f"YouTube Data API retornou status {response.status_code}: {response.text}",
                extra={"event": "youtube_api_error", "youtube_id": youtube_id}
            )
            return fetch_video_metrics_fallback(youtube_id)
    except Exception as e:
        logger.error(f"Erro ao consultar YouTube API para {youtube_id}: {e}")
        return fetch_video_metrics_fallback(youtube_id)

def fetch_video_metrics_fallback(youtube_id: str) -> Optional[Dict[str, Any]]:
    """
    Fallback usando yt-dlp sem baixar o vídeo (apenas metadados em JSON).
    """
    import subprocess
    import sys
    cmd = [
        sys.executable,
        "-m", "yt_dlp",
        "--dump-single-json",
        "--no-download",
        "--no-warnings",
        f"https://www.youtube.com/watch?v={youtube_id}"
    ]

    if settings.YTDLP_COOKIES_PATH.exists():
        cmd.extend(["--cookies", str(settings.YTDLP_COOKIES_PATH)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            raw_ts = data.get("timestamp") or data.get("release_timestamp")
            if raw_ts:
                try:
                    published_at = datetime.fromtimestamp(raw_ts, timezone.utc)
                except Exception:
                    published_at = datetime.now(timezone.utc)
            else:
                upload_date_str = data.get("upload_date") # YYYYMMDD
                published_at = datetime.now(timezone.utc)
                if upload_date_str and len(upload_date_str) == 8:
                    try:
                        published_at = datetime.strptime(upload_date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
                    except Exception:
                        pass

            return {
                "youtube_id": youtube_id,
                "title": data.get("title", ""),
                "published_at": published_at,
                "duration_seconds": int(data.get("duration") or 0),
                "view_count": int(data.get("view_count") or 0),
                "like_count": int(data.get("like_count") or 0),
                "comment_count": int(data.get("comment_count") or 0),
                "source": "yt_dlp_fallback"
            }
    except Exception as e:
        logger.error(f"Fallback yt-dlp falhou para {youtube_id}: {e}")

    return None
