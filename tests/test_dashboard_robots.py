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
