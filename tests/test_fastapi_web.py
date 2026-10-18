"""
Testes de Integração da API Web FastAPI do AutoClip Pipeline.
Valida rotas REST, streaming de mídia (Range Requests) e segurança.
"""
import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from src.web.app import app
from src.core.config import settings
from src.core.pipeline_control import PipelineController, init_controls_table
from src.core.database import get_db

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture(autouse=True)
def setup_controls():
    init_controls_table()
    PipelineController.resume_all()
    yield
    PipelineController.resume_all()

def test_home_page_returns_html(client):
    """Garante que a rota raiz entrega o template com Alpine.js, HTMX e Pixel Office HQ."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Centro de Controle • AutoClip Pipeline" in response.text
    assert "alpinejs" in response.text
    assert "htmx.org" in response.text
    assert "pixelOfficeCanvas" in response.text
    assert "Pixel Office HQ" in response.text
    assert "selectedRobotModal" in response.text
    assert "view-toggle" in response.text

def test_robots_api_endpoints(client):
    """Testa status e alternância de pausa de robôs."""
    # Status
    res = client.get("/api/robots/status")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "controls" in data
    assert "system_memory" in data

    # Toggle individual
    res_toggle = client.post("/api/robots/toggle?service=media_processor")
    assert res_toggle.status_code == 200
    data_toggle = res_toggle.json()
    assert data_toggle["ok"] is True
    assert data_toggle["service"] == "media_processor"
    assert data_toggle["is_paused"] is True
    assert PipelineController.is_paused("media_processor") is True

    # Resume All
    res_resume = client.post("/api/robots/resume_all")
    assert res_resume.status_code == 200
    assert PipelineController.is_paused("media_processor") is False

def test_media_streaming_and_path_traversal(client, tmp_path, monkeypatch):
    """Testa streaming com HTTP 206 Partial Content e bloqueio contra path traversal."""
    output_dir = tmp_path / "output_test"
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "OUTPUT_DIR", output_dir)

    # 1. Arquivo legítimo
    test_file = output_dir / "sample_clip.mp4"
    dummy_content = b"0123456789ABCDEF0123456789ABCDEF"  # 32 bytes
    test_file.write_bytes(dummy_content)

    # Download completo 200
    res = client.get("/media/sample_clip.mp4")
    assert res.status_code == 200
    assert res.content == dummy_content
    assert res.headers["accept-ranges"] == "bytes"

    # Range Request 206
    headers = {"Range": "bytes=0-9"}
    res_range = client.get("/media/sample_clip.mp4", headers=headers)
    assert res_range.status_code == 206
    assert res_range.content == b"0123456789"
    assert "bytes 0-9/32" in res_range.headers["content-range"]

    # 404 para arquivo inexistente
    res_404 = client.get("/media/missing.mp4")
    assert res_404.status_code == 404

    # 403 para Path Traversal
    res_traversal = client.get("/media/%2e%2e/secret.txt")
    assert res_traversal.status_code == 403

def test_clips_crud_and_scheduling(client):
    """Testa listagem, atualização e reagendamento de cortes."""
    # Cria long_video e clip no banco para teste
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO long_videos (id, file_hash, file_name, file_path)
            VALUES (999, 'hash_test_123', 'video.mp4', 'data/downloads/video.mp4');
        """)
        cur.execute("""
            INSERT INTO clips (long_video_id, clip_uid, file_path, virality_score, title, description, tags, duration_seconds)
            VALUES (999, 'clip_test_123', 'output/clip_test.mp4', 90, 'Título Antigo', 'Desc', '#tag', 45);
        """)
        clip_id = cur.lastrowid
        conn.commit()

    # Listagem
    res = client.get("/api/clips")
    assert res.status_code == 200
    clips = res.json()["clips"]
    assert any(c["id"] == clip_id for c in clips)

    # Detalhes
    res_detail = client.get(f"/api/clips/{clip_id}")
    assert res_detail.status_code == 200
    assert res_detail.json()["clip"]["title"] == "Título Antigo"

    # Atualização de Metadados
    payload = {
        "title": "Novo Título Atraente",
        "description": "Nova descrição otimizada",
        "tags": "#shorts #financas"
    }
    res_up = client.post(f"/api/clips/{clip_id}/update", json=payload)
    assert res_up.status_code == 200
    assert res_up.json()["updated"] is True

    # Valida no banco
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT title, description FROM clips WHERE id = ?;", (clip_id,))
        row = cur.fetchone()
        assert row["title"] == "Novo Título Atraente"

    # Reagendamento com novo intervalo
    res_int = client.post("/api/schedule/interval", json={"interval_minutes": 20})
    assert res_int.status_code == 200
    assert res_int.json()["interval_minutes"] == 20

def test_telemetry_endpoint(client):
    """Valida o endpoint consolidado de telemetria."""
    res = client.get("/api/telemetry")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "stats" in data["data"]
    assert "disk" in data["data"]
    assert "system_memory" in data["data"]

def test_pixel_agents_static_assets_served(client):
    """Garante que os spritesheets oficiais do Pixel Agents são servidos via /static."""
    res = client.get("/static/pixel-agents/characters/char_0.png")
    assert res.status_code == 200
    assert "image/png" in res.headers["content-type"]
    assert len(res.content) > 1000
