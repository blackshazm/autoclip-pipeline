"""
Rotas de Controle dos Robôs e Serviços da Pipeline.
"""

from typing import Optional
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel
from src.core.pipeline_control import PipelineController

router = APIRouter(prefix="/api/robots", tags=["Robots"])


class ToggleRequest(BaseModel):
    service: Optional[str] = None
    reason: Optional[str] = "dashboard_toggle"


@router.get("/status")
async def get_robots_status():
    """Retorna os estados de controle, pausados e telemetria de RAM."""
    statuses = PipelineController.get_all_statuses()
    return {"ok": True, **statuses}


@router.post("/toggle")
async def toggle_robot(request: Request, service: Optional[str] = Query(None)):
    """Pausa ou retoma um robô individualmente."""
    target_service = service
    reason = "dashboard_toggle"

    if not target_service:
        try:
            body = await request.json()
            if isinstance(body, dict):
                target_service = body.get("service")
                reason = body.get("reason", reason)
        except Exception:
            pass

    if not target_service:
        return {"ok": False, "error": "Serviço não especificado"}, 400

    new_state = PipelineController.toggle_pause(target_service, reason=reason)
    statuses = PipelineController.get_all_statuses()
    return {"ok": True, "service": target_service, "is_paused": new_state, **statuses}


@router.post("/pause_all")
async def pause_all_robots():
    """Pausa todos os robôs da esteira simultaneamente."""
    PipelineController.pause_all(reason="dashboard_button")
    statuses = PipelineController.get_all_statuses()
    return {"ok": True, **statuses}


@router.post("/resume_all")
async def resume_all_robots():
    """Retoma todos os robôs da esteira simultaneamente."""
    PipelineController.resume_all()
    statuses = PipelineController.get_all_statuses()
    return {"ok": True, **statuses}
