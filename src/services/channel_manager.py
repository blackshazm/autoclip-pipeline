"""
Gerenciador de Canais Monitorados pelo Radar do YouTube.
Resolve handles (@canal), URLs e channel_ids via yt-dlp e cadastra no banco.
"""

import re
import sys
import subprocess
import urllib.request
from typing import Optional, Dict, Any, List
from src.core.database import get_db
from src.core.logger import get_logger

logger = get_logger("channel_manager")


def resolve_channel(identifier: str) -> Optional[Dict[str, str]]:
    """
    Resolve um identificador (URL, @handle ou channel_id) para channel_id e nome.
    Tenta primeiro via HTML scrape super rápido (<1s) e recorre ao yt-dlp como fallback.
    """
    clean_id = identifier.strip()
    if clean_id.startswith("@"):
        url = f"https://www.youtube.com/{clean_id}"
    elif "youtube.com" in clean_id or "youtu.be" in clean_id:
        url = clean_id
    elif clean_id.startswith("UC") and len(clean_id) >= 20:
        url = f"https://www.youtube.com/channel/{clean_id}"
    else:
        url = f"https://www.youtube.com/@{clean_id}"

    # 1. Tentativa rápida: Scrape de metadados da página pública do YouTube
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        )
        html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
        cid_match = (
            re.search(r'itemprop="identifier" content="(UC[a-zA-Z0-9_-]+)"', html)
            or re.search(r'"channelId":"(UC[a-zA-Z0-9_-]+)"', html)
            or re.search(r'"browseId":"(UC[a-zA-Z0-9_-]+)"', html)
        )
        title_match = (
            re.search(r'itemprop="name" content="([^"]+)"', html)
            or re.search(r'<meta property="og:title" content="([^"]+)"', html)
        )
        if cid_match:
            ch_id = cid_match.group(1).strip()
            ch_name = title_match.group(1).strip() if title_match else identifier
            return {
                "channel_id": ch_id,
                "name": ch_name,
                "rss_url": f"https://www.youtube.com/feeds/videos.xml?channel_id={ch_id}",
            }
    except Exception as e:
        logger.debug(f"HTML scrape fallback para {identifier}: {e}")

    # 2. Tentativa secundária: yt-dlp
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--print",
        "%(channel_id)s|%(channel)s",
        "--playlist-items",
        "1",
        "--no-warnings",
        url,
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=25, check=False)
        lines = [line.strip() for line in res.stdout.splitlines() if "|" in line]
        if lines:
            parts = lines[-1].split("|", 1)
            ch_id = parts[0].strip()
            ch_name = parts[1].strip() if len(parts) > 1 else identifier
            return {
                "channel_id": ch_id,
                "name": ch_name,
                "rss_url": f"https://www.youtube.com/feeds/videos.xml?channel_id={ch_id}",
            }
    except Exception as e:
        logger.error(f"Erro ao resolver canal {identifier} via yt-dlp: {e}")

    # Fallback final se já for um channel_id puro
    if clean_id.startswith("UC") and len(clean_id) >= 20:
        return {
            "channel_id": clean_id,
            "name": clean_id,
            "rss_url": f"https://www.youtube.com/feeds/videos.xml?channel_id={clean_id}",
        }

    return None


def add_source_channel(
    identifier: str,
    name: Optional[str] = None,
    min_duration_minutes: int = 15,
    vph_threshold: int = 2000,
    multiplier_threshold: float = 2.0,
    median_vph: float = 1000.0,
    license_mode: str = "owned",
    niche: str = "financas",
    max_videos_per_cycle: int = 3,
) -> Dict[str, Any]:
    """
    Resolve o canal e insere na tabela source_channels com nicho e limites configurados.
    """
    resolved = resolve_channel(identifier)
    if not resolved:
        raise ValueError(f"Não foi possível identificar o canal do YouTube a partir de '{identifier}'.")

    ch_id = resolved["channel_id"]
    ch_name = name or resolved["name"]
    rss_url = resolved["rss_url"]

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO source_channels (
                youtube_channel_id, name, rss_url, active,
                min_duration_minutes, vph_absolute_threshold,
                vph_multiplier_threshold, median_vph, license_mode,
                niche, max_videos_per_cycle
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(youtube_channel_id) DO UPDATE SET
                name = excluded.name,
                rss_url = excluded.rss_url,
                active = 1,
                min_duration_minutes = excluded.min_duration_minutes,
                vph_absolute_threshold = excluded.vph_absolute_threshold,
                vph_multiplier_threshold = excluded.vph_multiplier_threshold,
                median_vph = excluded.median_vph,
                license_mode = excluded.license_mode,
                niche = excluded.niche,
                max_videos_per_cycle = excluded.max_videos_per_cycle,
                updated_at = datetime('now');
        """,
            (
                ch_id,
                ch_name,
                rss_url,
                min_duration_minutes,
                vph_threshold,
                multiplier_threshold,
                median_vph,
                license_mode,
                niche,
                max_videos_per_cycle,
            ),
        )

        cursor.execute("SELECT * FROM source_channels WHERE youtube_channel_id = ?;", (ch_id,))
        row = cursor.fetchone()
        logger.info(f"Canal '{ch_name}' ({ch_id}) configurado com sucesso no Radar (Nicho: {niche}).")
        res_data = dict(row)
        res_data["ok"] = True
        return res_data


def list_source_channels() -> List[Dict[str, Any]]:
    """Lista todos os canais configurados."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM source_channels ORDER BY active DESC, id ASC;")
        return [dict(r) for r in cursor.fetchall()]


def toggle_channel_status(channel_id: int | str, active: Optional[bool] = None) -> bool:
    """Ativa ou desativa o monitoramento de um canal. Se active for None, inverte o estado atual."""
    cid = int(channel_id)
    with get_db() as conn:
        cursor = conn.cursor()
        if active is None:
            cursor.execute("SELECT active FROM source_channels WHERE id = ?;", (cid,))
            row = cursor.fetchone()
            if not row:
                return False
            new_active = 0 if row["active"] == 1 else 1
        else:
            new_active = 1 if active else 0

        cursor.execute(
            "UPDATE source_channels SET active = ?, updated_at = datetime('now') WHERE id = ?;",
            (new_active, cid),
        )
        return cursor.rowcount > 0


def delete_source_channel(channel_id: int | str) -> bool:
    """Remove um canal do monitoramento."""
    cid = int(channel_id)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM source_channels WHERE id = ?;", (cid,))
        return cursor.rowcount > 0
