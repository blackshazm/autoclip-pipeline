"""
Rotas e WebSocket de Streaming de Logs em Tempo Real.
"""

import asyncio
import json
from pathlib import Path
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

router = APIRouter(prefix="/api/logs", tags=["Logs"])
LOGS_DIR = Path("logs").resolve()

ALLOWED_LOGS = {
    "radar_youtube.log": "Radar de Hype",
    "robot1_ingest.log": "Robô Ingestor",
    "media_processor.log": "Fábrica de Cortes",
    "pub_yt_financas.log": "YouTube Finanças",
    "pub_yt_fitness.log": "YouTube Fitness",
    "pub_tk_financas.log": "TikTok Finanças",
    "pub_tk_fitness.log": "TikTok Fitness",
    "watchdog.log": "Watchdog Guardião",
    "dashboard.log": "Painel Web",
    "downloader.log": "Downloader yt-dlp",
}


@router.get("/files")
async def list_log_files():
    """Lista os arquivos de logs disponíveis para acompanhamento."""
    files = []
    if LOGS_DIR.exists():
        for f in LOGS_DIR.glob("*.log"):
            files.append(
                {
                    "filename": f.name,
                    "label": ALLOWED_LOGS.get(f.name, f.name),
                    "size_bytes": f.stat().st_size,
                    "modified_at": f.stat().st_mtime,
                }
            )
    return {"ok": True, "files": sorted(files, key=lambda x: x["filename"])}


@router.get("/tail")
async def get_log_tail(file: str = Query("radar_youtube.log"), lines: int = Query(60)):
    """Retorna as últimas N linhas do log especificado."""
    safe_name = Path(file).name
    target_path = LOGS_DIR / safe_name

    if not target_path.exists() or not target_path.is_file():
        return {"ok": False, "error": "Arquivo não encontrado", "lines": []}

    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return {"ok": True, "file": safe_name, "lines": tail_lines}
    except Exception as e:
        return {"ok": False, "error": str(e), "lines": []}


@router.websocket("/stream")
async def websocket_logs_endpoint(websocket: WebSocket):
    """
    WebSocket bidirecional para streaming contínuo de logs.
    O cliente pode enviar `{"file": "novo_log.log"}` para trocar o log monitorado.
    """
    await websocket.accept()
    current_file = "radar_youtube.log"
    file_pos = 0

    target_path = LOGS_DIR / current_file
    if target_path.exists():
        # Posiciona perto do final para não inundar o WebSocket de imediato
        size = target_path.stat().st_size
        file_pos = max(0, size - 15000)

    try:
        while True:
            # Checa se o cliente enviou comando de troca de arquivo (não bloqueante)
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                data = json.loads(msg)
                new_file = data.get("file")
                if new_file and (LOGS_DIR / Path(new_file).name).exists():
                    current_file = Path(new_file).name
                    target_path = LOGS_DIR / current_file
                    size = target_path.stat().st_size
                    file_pos = max(0, size - 15000)
                    await websocket.send_json({"type": "switched", "file": current_file})
            except asyncio.TimeoutError:
                pass
            except json.JSONDecodeError:
                pass

            # Lê novos bytes adicionados ao log atual
            target_path = LOGS_DIR / current_file
            if target_path.exists():
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(file_pos)
                    chunk = f.read()
                    file_pos = f.tell()
                    if chunk:
                        lines = chunk.splitlines(keepends=True)
                        await websocket.send_json({"type": "log_delta", "file": current_file, "lines": lines})

            await asyncio.sleep(1.2)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
