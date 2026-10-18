"""
Aplicação Principal FastAPI do AutoClip Pipeline.
Integra rotas REST, WebSockets e renderização do painel SPA reativo.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from src.web.routes.media import router as media_router
from src.web.routes.robots import router as robots_router
from src.web.routes.clips import router as clips_router
from src.web.routes.channels import router as channels_router
from src.web.routes.logs import router as logs_router
from src.web.routes.telemetry import router as telemetry_router

# Inicializa aplicação
app = FastAPI(
    title="Centro de Controle • AutoClip Pipeline",
    description="Painel de controle, curadoria e telemetria em tempo real para a esteira autônoma de cortes.",
    version="2.0.0",
    docs_url="/docs",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(media_router)
app.include_router(robots_router)
app.include_router(clips_router)
app.include_router(channels_router)
app.include_router(logs_router)
app.include_router(telemetry_router)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@app.get("/", response_class=HTMLResponse)
async def get_dashboard_html():
    """Serve a interface principal do Centro de Controle."""
    index_file = TEMPLATES_DIR / "index.html"
    if index_file.exists():
        content = index_file.read_text(encoding="utf-8")
        return HTMLResponse(content)
    return HTMLResponse("<h1>Template index.html não localizado</h1>", status_code=500)
