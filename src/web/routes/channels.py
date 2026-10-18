"""
Rotas de Gerenciamento de Canais Monitorados pelo Radar.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.core.database import get_db
from src.services.channel_manager import add_source_channel, delete_source_channel, toggle_channel_status

router = APIRouter(prefix="/api/channels", tags=["Channels"])


class AddChannelPayload(BaseModel):
    identifier: str
    niche: Optional[str] = "financas"
    min_duration_minutes: Optional[int] = 8
    vph_threshold: Optional[int] = 2000


@router.get("")
async def list_channels():
    """Lista todos os canais cadastrados para varredura do radar."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM source_channels ORDER BY active DESC, id ASC;")
        channels = [dict(r) for r in cur.fetchall()]
    return {"ok": True, "channels": channels}


@router.post("")
async def create_channel(payload: AddChannelPayload):
    """Adiciona um novo canal ao radar resolvendo nome e URL."""
    try:
        res = add_source_channel(
            identifier=payload.identifier,
            niche=payload.niche or "financas",
            min_duration_minutes=payload.min_duration_minutes or 8,
            vph_threshold=payload.vph_threshold or 2000,
        )
        return {"ok": True, "channel": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{channel_id}/toggle")
async def toggle_channel(channel_id: int):
    """Ativa ou desativa o monitoramento de um canal específico."""
    ok = toggle_channel_status(channel_id)
    return {"ok": ok}


@router.delete("/{channel_id}")
async def remove_channel(channel_id: int):
    """Remove um canal do monitoramento."""
    ok = delete_source_channel(channel_id)
    return {"ok": ok}
