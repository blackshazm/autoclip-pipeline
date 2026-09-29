"""
Gerenciador de Canais Monitorados pelo Radar do YouTube.
Resolve handles (@canal), URLs e channel_ids via yt-dlp e cadastra no banco.
"""
import subprocess
import json
import re
from typing import Optional, Dict, Any, List
from src.core.database import get_db
from src.core.logger import get_logger

logger = get_logger("channel_manager")

def resolve_channel(identifier: str) -> Optional[Dict[str, str]]:
    """
    Resolve um identificador (URL, @handle ou channel_id) para channel_id e nome.
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

    cmd = [
        "python", "-m", "yt_dlp",
        "--print", "%(channel_id)s|%(channel)s",
        "--playlist-items", "1",
        "--no-warnings",
        url
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
                "rss_url": f"https://www.youtube.com/feeds/videos.xml?channel_id={ch_id}"
            }
    except Exception as e:
        logger.error(f"Erro ao resolver canal {identifier}: {e}")

    # Fallback se já for um channel_id puro
    if clean_id.startswith("UC") and len(clean_id) >= 20:
        return {
            "channel_id": clean_id,
            "name": clean_id,
            "rss_url": f"https://www.youtube.com/feeds/videos.xml?channel_id={clean_id}"
        }

    return None

def add_source_channel(
    identifier: str,
    name: Optional[str] = None,
    min_duration_minutes: int = 15,
    vph_threshold: int = 2000,
    multiplier_threshold: float = 2.0,
    median_vph: float = 1000.0,
    license_mode: str = "owned"
) -> Dict[str, Any]:
    """
    Resolve o canal e insere na tabela source_channels.
    """
    resolved = resolve_channel(identifier)
    if not resolved:
        raise ValueError(f"Não foi possível identificar o canal do YouTube a partir de '{identifier}'.")

    ch_id = resolved["channel_id"]
    ch_name = name or resolved["name"]
    rss_url = resolved["rss_url"]

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO source_channels (
                youtube_channel_id, name, rss_url, active,
                min_duration_minutes, vph_absolute_threshold,
                vph_multiplier_threshold, median_vph, license_mode
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(youtube_channel_id) DO UPDATE SET
                name = excluded.name,
                rss_url = excluded.rss_url,
                active = 1,
                min_duration_minutes = excluded.min_duration_minutes,
                vph_absolute_threshold = excluded.vph_absolute_threshold,
                vph_multiplier_threshold = excluded.vph_multiplier_threshold,
                median_vph = excluded.median_vph,
                license_mode = excluded.license_mode,
                updated_at = datetime('now');
        """, (ch_id, ch_name, rss_url, min_duration_minutes, vph_threshold, multiplier_threshold, median_vph, license_mode))

        cursor.execute("SELECT * FROM source_channels WHERE youtube_channel_id = ?;", (ch_id,))
        row = cursor.fetchone()
        logger.info(f"Canal '{ch_name}' ({ch_id}) configurado com sucesso no Radar.")
        return dict(row)

def list_source_channels() -> List[Dict[str, Any]]:
    """Lista todos os canais configurados."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM source_channels ORDER BY active DESC, id ASC;")
        return [dict(r) for r in cursor.fetchall()]

def toggle_channel_status(channel_id: int, active: bool) -> bool:
    """Ativa ou desativa o monitoramento de um canal."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE source_channels SET active = ?, updated_at = datetime('now') WHERE id = ?;", (1 if active else 0, channel_id))
        return cursor.rowcount > 0

def delete_source_channel(channel_id: int) -> bool:
    """Remove um canal do monitoramento."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM source_channels WHERE id = ?;", (channel_id,))
        return cursor.rowcount > 0
