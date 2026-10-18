"""
Teste de Integração dos Endpoints de Robôs no Dashboard HTTP.
"""
import json
import urllib.request
import urllib.parse
from io import BytesIO
from unittest.mock import MagicMock

from src.dashboard import PipelineDashboardHandler
from src.core.pipeline_control import PipelineController

class DummyRequest:
    def __init__(self, data=b""):
        self.data = data
    def makefile(self, *args, **kwargs):
        return BytesIO(self.data)
    def sendall(self, *args):
        pass

def test_dashboard_robots_api_endpoints():
    """Valida se o handler do dashboard responde corretamente para /api/robots/status e /api/robots/toggle."""
    handler = PipelineDashboardHandler.__new__(PipelineDashboardHandler)
    handler.rfile = BytesIO()
    handler.wfile = BytesIO()
    handler.headers = {}

    # Teste GET /api/robots/status
    handler.path = "/api/robots/status"
    handler.wfile = BytesIO()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()

    handler.do_GET()
    response_data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert response_data["ok"] is True
    assert "controls" in response_data
    assert "system_memory" in response_data

    # Teste POST /api/robots/toggle?service=llm_copywriter
    handler.path = "/api/robots/toggle?service=llm_copywriter"
    handler.wfile = BytesIO()
    handler.do_POST()
    post_res = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert post_res["ok"] is True
    assert post_res["service"] == "llm_copywriter"
    assert post_res["is_paused"] is True
    assert PipelineController.is_paused("llm_copywriter") is True

    # Despausa via POST /api/robots/resume_all
    handler.path = "/api/robots/resume_all"
    handler.wfile = BytesIO()
    handler.do_POST()
    res_all = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert res_all["ok"] is True
    assert PipelineController.is_paused("llm_copywriter") is False


def test_dashboard_media_path_traversal_protection(tmp_path, monkeypatch):
    """Garante que a rota /media/ impede qualquer tentativa de Path Traversal."""
    from src.core.config import settings
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "OUTPUT_DIR", output_dir)

    # 1. Arquivo legítimo dentro de OUTPUT_DIR
    valid_file = output_dir / "valid_clip.mp4"
    valid_file.write_bytes(b"VIDEO_BINARY_DATA")

    handler = PipelineDashboardHandler.__new__(PipelineDashboardHandler)
    handler.rfile = BytesIO()
    handler.wfile = BytesIO()
    handler.headers = {}
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()
    handler.copyfile = MagicMock()

    handler.path = "/media/valid_clip.mp4"
    handler.do_GET()
    handler.send_response.assert_called_with(200)
    handler.copyfile.assert_called_once()

    # 2. Arquivo inexistente dentro de OUTPUT_DIR -> 404
    handler.send_error.reset_mock()
    handler.path = "/media/non_existent.mp4"
    handler.do_GET()
    handler.send_error.assert_called_with(404, "Vídeo não encontrado")

    # 3. Path Traversal com '..' saindo de OUTPUT_DIR -> 403
    secret_file = tmp_path / "secret.env"
    secret_file.write_text("SENSITIVE_DATA=123")
    handler.send_error.reset_mock()
    handler.path = "/media/../secret.env"
    handler.do_GET()
    handler.send_error.assert_called_with(403, "Acesso proibido")

    # 4. Path Traversal com URL encoding (%2e%2e) -> 403
    handler.send_error.reset_mock()
    handler.path = "/media/%2e%2e/secret.env"
    handler.do_GET()
    handler.send_error.assert_called_with(403, "Acesso proibido")


def test_dashboard_host_port_config(monkeypatch):
    """Garante que o dashboard utiliza 127.0.0.1 como host seguro padrão e respeita customizações."""
    from src.core.config import Settings
    s = Settings(DASHBOARD_HOST="192.168.1.100", DASHBOARD_PORT=9090)
    assert s.DASHBOARD_HOST == "192.168.1.100"
    assert s.DASHBOARD_PORT == 9090

    default_s = Settings()
    assert default_s.DASHBOARD_HOST == "127.0.0.1"
    assert default_s.DASHBOARD_PORT == 8085


