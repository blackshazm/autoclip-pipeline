"""
Testes unitários para o SupoclipClient (autenticação HMAC/API key, mock e retries).
"""
import pytest
from pathlib import Path
from src.services.supoclip_client import SupoclipClient
from src.core.exceptions import SupoclipError

def test_supoclip_client_mock_submit(monkeypatch):
    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "MOCK_SUPOCLIP", True)
    client = SupoclipClient()
    job_id = client.submit_job(Path("dummy_video.mp4"))
    assert job_id.startswith("mock-job-")

def test_supoclip_client_mock_status(tmp_path, monkeypatch):
    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(cfg.settings, "MOCK_SUPOCLIP", True)

    client = SupoclipClient()
    res = client.get_job_status("mock-job-1234")
    assert res["status"] == "COMPLETED"
    assert len(res["clips"]) == 3
    assert res["clips"][0]["virality_score"] == 88

def test_supoclip_client_auth_headers_api_key(monkeypatch):
    client = SupoclipClient()
    client.api_key = "test_custom_api_key"
    headers = client._get_auth_headers()
    assert headers == {"x-api-key": "test_custom_api_key"}

def test_supoclip_client_auth_headers_hmac(monkeypatch):
    client = SupoclipClient()
    client.api_key = ""
    client.user_id = "test_user"
    client.auth_secret = "secret123"
    headers = client._get_auth_headers()
    assert headers["x-supoclip-user-id"] == "test_user"
    assert "x-supoclip-ts" in headers
    assert "x-supoclip-signature" in headers
    assert len(headers["x-supoclip-signature"]) == 64

def test_supoclip_client_submit_nonexistent_file(monkeypatch):
    client = SupoclipClient()
    client.is_mock = False
    with pytest.raises(SupoclipError, match="nao encontrado"):
        client.submit_job(Path("non_existent_file_xyz.mp4"))
