"""
Serviço de Coleta e Cálculo de Métricas de Vídeos do YouTube (VPH e Outlier Factor).
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import sys
import requests
import json

from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger("youtube_metrics")


def parse_iso8601_duration(duration_str: Optional[str]) -> int:
    """Converte duração no formato ISO 8601 (ex: PT1H23M45S) em segundos."""
    if not duration_str or not isinstance(duration_str, str):
        return 0
    import re

    pattern = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
    match = pattern.match(duration_str)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def calculate_vph(
    view_count: Optional[int], published_at: Optional[datetime], reference_time: Optional[datetime] = None
) -> float:
    """
    Calcula Views Per Hour (VPH):
    VPH = Total de Visualizações / Horas Decorridas desde a Publicação.
    """
    views = max(int(view_count or 0), 0)
    ref = reference_time or datetime.now(timezone.utc)
    if published_at is None:
        published_at = ref
    elif published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    elapsed_seconds = max((ref - published_at).total_seconds(), 60.0)
    elapsed_hours = elapsed_seconds / 3600.0
    return round(views / elapsed_hours, 2)


def calculate_median_factor(vph: Optional[float], channel_median_vph: Optional[float]) -> float:
    """Calcula a taxa de aceleração sobre a mediana histórica do canal."""
    safe_vph = max(float(vph or 0.0), 0.0)
    if not channel_median_vph or channel_median_vph <= 0:
        return 1.0
    return round(safe_vph / channel_median_vph, 2)


def calculate_engagement_ratio(
    view_count: Optional[int], like_count: Optional[int], comment_count: Optional[int]
) -> float:
    """
    Calcula o índice percentual ponderado de engajamento da audiência:
    Engagement = ((likes * 2 + comments * 5) / views) * 100
    Vídeos com alta discussão e aprovação geram cortes com maior retenção e comentários.
    """
    views = max(int(view_count or 0), 0)
    if views <= 0:
        return 0.0
    likes = max(int(like_count or 0), 0)
    comments = max(int(comment_count or 0), 0)
    weighted_score = (likes * 2) + (comments * 5)
    return round((weighted_score / views) * 100, 2)


def extract_video_heatmap_and_chapters(youtube_id: str) -> Dict[str, Any]:
    """
    Extrai metadados analíticos profundos via yt-dlp:
    - chapters: Divisões temáticas e títulos definidos pelos criadores.
    - heatmap: Curva de retenção ("Most Replayed") do YouTube.
    - top_peaks: Os 5 intervalos de tempo de maior replay.
    """
    if not youtube_id or not isinstance(youtube_id, str):
        return {
            "youtube_id": "",
            "has_heatmap": False,
            "has_chapters": False,
            "chapters": [],
            "top_peaks": [],
            "raw_heatmap_points": 0,
        }

    import subprocess
    config_dir = Path("./config")
    valid_cookies = [
        c for c in [
            config_dir / "cookies_fitness.txt",
            config_dir / "cookies_financas.txt",
            Path(settings.YTDLP_COOKIES_PATH),
        ] if c.exists() and c.stat().st_size > 0
    ]
    freshest_cookie = max(valid_cookies, key=lambda c: c.stat().st_mtime) if valid_cookies else None

    def _run_meta(use_cookies: bool = False):
        base_cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--dump-single-json",
            "--skip-download",
            "--ignore-no-formats-error",
            "--js-runtimes",
            "node",
            "--remote-components",
            "ejs:github",
            "--no-warnings",
        ]
        if use_cookies and freshest_cookie:
            base_cmd.extend(["--cookies", str(freshest_cookie)])
        base_cmd.append(f"https://www.youtube.com/watch?v={youtube_id}")
        return subprocess.run(base_cmd, capture_output=True, text=True, timeout=40)

    try:
        res = _run_meta(use_cookies=False)
        if res.returncode != 0 and freshest_cookie:
            res = _run_meta(use_cookies=True)

        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            raw_heatmap = data.get("heatmap") or []
            chapters = data.get("chapters") or []

            top_peaks = []
            if isinstance(raw_heatmap, list) and raw_heatmap:
                # Ordena pontos por valor de repetição decrescente
                valid_points = [p for p in raw_heatmap if isinstance(p, dict)]
                sorted_points = sorted(valid_points, key=lambda x: float(x.get("value") or 0.0), reverse=True)
                top_peaks = sorted_points[:8]

            return {
                "youtube_id": youtube_id,
                "has_heatmap": bool(raw_heatmap),
                "has_chapters": bool(chapters),
                "chapters": chapters if isinstance(chapters, list) else [],
                "top_peaks": top_peaks,
                "raw_heatmap_points": len(raw_heatmap) if isinstance(raw_heatmap, list) else 0,
            }
    except Exception as e:
        logger.warning(f"Não foi possível extrair heatmap/capítulos de {youtube_id}: {e}")

    return {
        "youtube_id": youtube_id,
        "has_heatmap": False,
        "has_chapters": False,
        "chapters": [],
        "top_peaks": [],
        "raw_heatmap_points": 0,
    }


def fetch_video_metrics(youtube_id: str, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Consulta métricas na YouTube Data API v3.
    Retorna dicionário com views, likes, comments, duration_seconds e published_at.
    """
    if not youtube_id or not isinstance(youtube_id, str):
        return None

    key = api_key or settings.YOUTUBE_API_KEY
    if not key:
        logger.debug(f"YOUTUBE_API_KEY não definida. Utilizando extração alternativa para {youtube_id}")
        return fetch_video_metrics_fallback(youtube_id)

    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {"part": "snippet,contentDetails,statistics", "id": youtube_id, "key": key}

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
            try:
                published_at = (
                    datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    if published_str
                    else datetime.now(timezone.utc)
                )
            except Exception:
                published_at = datetime.now(timezone.utc)

            duration_seconds = parse_iso8601_duration(content.get("duration", "PT0S"))

            try:
                view_count = int(stats.get("viewCount") or 0)
            except (ValueError, TypeError):
                view_count = 0

            try:
                like_count = int(stats.get("likeCount") or 0)
            except (ValueError, TypeError):
                like_count = 0

            try:
                comment_count = int(stats.get("commentCount") or 0)
            except (ValueError, TypeError):
                comment_count = 0

            return {
                "youtube_id": youtube_id,
                "title": str(snippet.get("title") or ""),
                "published_at": published_at,
                "duration_seconds": duration_seconds,
                "view_count": view_count,
                "like_count": like_count,
                "comment_count": comment_count,
                "source": "youtube_data_api",
            }
        else:
            if response.status_code in (403, 429):
                logger.warning(
                    f"YouTube Data API com limitação/quota (HTTP {response.status_code}): {response.text}",
                    extra={"event": "youtube_api_quota_or_rate_limit", "youtube_id": youtube_id},
                )
            else:
                logger.warning(
                    f"YouTube Data API retornou status {response.status_code}: {response.text}",
                    extra={"event": "youtube_api_error", "youtube_id": youtube_id},
                )
            return fetch_video_metrics_fallback(youtube_id)
    except Exception as e:
        logger.error(f"Erro ao consultar YouTube API para {youtube_id}: {e}")
        return fetch_video_metrics_fallback(youtube_id)


def fetch_video_metrics_fallback(youtube_id: str) -> Optional[Dict[str, Any]]:
    """
    Fallback usando yt-dlp sem baixar o vídeo (apenas metadados em JSON).
    """
    if not youtube_id or not isinstance(youtube_id, str):
        return None

    import subprocess
    import sys

    config_dir = Path("./config")
    valid_cookies = [
        c for c in [
            config_dir / "cookies_fitness.txt",
            config_dir / "cookies_financas.txt",
            Path(settings.YTDLP_COOKIES_PATH),
        ] if c.exists() and c.stat().st_size > 0
    ]
    freshest_cookie = max(valid_cookies, key=lambda c: c.stat().st_mtime) if valid_cookies else None

    def _run_extract(use_cookies: bool = False):
        base_cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--dump-single-json",
            "--skip-download",
            "--ignore-no-formats-error",
            "--js-runtimes",
            "node",
            "--remote-components",
            "ejs:github",
            "--no-warnings",
        ]
        if use_cookies and freshest_cookie:
            base_cmd.extend(["--cookies", str(freshest_cookie)])
        base_cmd.append(f"https://www.youtube.com/watch?v={youtube_id}")
        return subprocess.run(base_cmd, capture_output=True, text=True, timeout=40)

    try:
        result = _run_extract(use_cookies=False)
        if result.returncode != 0 and freshest_cookie:
            result = _run_extract(use_cookies=True)

        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            raw_ts = data.get("timestamp") or data.get("release_timestamp")
            if raw_ts:
                try:
                    published_at = datetime.fromtimestamp(float(raw_ts), timezone.utc)
                except Exception:
                    published_at = datetime.now(timezone.utc)
            else:
                upload_date_str = data.get("upload_date")  # YYYYMMDD
                published_at = datetime.now(timezone.utc)
                if upload_date_str and len(str(upload_date_str)) == 8:
                    try:
                        published_at = datetime.strptime(str(upload_date_str), "%Y%m%d").replace(tzinfo=timezone.utc)
                    except Exception:
                        pass

            try:
                duration = int(data.get("duration") or 0)
            except (ValueError, TypeError):
                duration = 0

            try:
                views = int(data.get("view_count") or 0)
            except (ValueError, TypeError):
                views = 0

            try:
                likes = int(data.get("like_count") or 0)
            except (ValueError, TypeError):
                likes = 0

            try:
                comments = int(data.get("comment_count") or 0)
            except (ValueError, TypeError):
                comments = 0

            return {
                "youtube_id": youtube_id,
                "title": str(data.get("title") or ""),
                "published_at": published_at,
                "duration_seconds": duration,
                "view_count": views,
                "like_count": likes,
                "comment_count": comments,
                "source": "yt_dlp_fallback",
            }
        else:
            logger.warning(
                f"Fallback yt-dlp retornou código {result.returncode} para {youtube_id}: {result.stderr.strip()}",
                extra={"event": "yt_dlp_fallback_failed", "youtube_id": youtube_id},
            )
    except FileNotFoundError:
        logger.warning(f"yt-dlp não encontrado no ambiente para fallback de métricas de {youtube_id}")
    except Exception as e:
        logger.error(f"Fallback yt-dlp falhou para {youtube_id}: {e}")

    return None
