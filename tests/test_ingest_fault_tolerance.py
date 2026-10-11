"""
Testes de tolerância a falhas e consistência transacional no Ingestor (src/robot1_ingest.py).
Valida que falhas de rede no Supoclip marcam o status 'FAILED' no SQLite com mensagem de erro.
"""
import pytest
from pathlib import Path
from src.robot1_ingest import process_single_video
from src.services.supoclip_client import SupoclipClient
from src.core.database import get_db
from src.core.exceptions import SupoclipError
from src.database.migrations import run_migrations

def test_ingest_marks_failed_on_supoclip_error(temp_dir, monkeypatch):
    """Quando o Supoclip falha, o vídeo deve ser persistido como FAILED com mensagem de erro."""
    db_file = temp_dir / "fault_test.db"
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)

    import src.robot1_ingest as r1
    monkeypatch.setattr(r1, "verify_media_integrity", lambda p: True)
    monkeypatch.setattr(r1, "inspect_media_file", lambda p: {"duration_seconds": 600.0, "file_size_bytes": 2048})
    monkeypatch.setattr(r1, "is_file_fully_written", lambda p: True)

    client = SupoclipClient()
    # Mock de falha no envio para o Supoclip
    def mock_submit_error(video_path):
        raise SupoclipError("Erro 502 Bad Gateway no servidor de corte")

    monkeypatch.setattr(client, "submit_job", mock_submit_error)

    video_path = temp_dir / "crash_video.mp4"
    video_path.write_bytes(b"DUMMY_FAIL_DATA")

    success = process_single_video(video_path, client)
    assert success is False

    # Valida no banco de dados que o vídeo foi registrado com FAILED
    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, error_message FROM long_videos;")
        row = cursor.fetchone()
        assert row is not None
        assert row["status"] == "FAILED"
        assert "502 Bad Gateway" in row["error_message"]

def test_ingest_retries_previously_failed_video(temp_dir, monkeypatch):
    """Vídeo anteriormente com status FAILED deve ser reprocessado com sucesso se o Supoclip responder."""
    db_file = temp_dir / "retry_test.db"
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)
    monkeypatch.setattr(cfg.settings, "MOCK_SUPOCLIP", True)

    import src.robot1_ingest as r1
    monkeypatch.setattr(r1, "verify_media_integrity", lambda p: True)
    monkeypatch.setattr(r1, "inspect_media_file", lambda p: {"duration_seconds": 600.0, "file_size_bytes": 2048})
    monkeypatch.setattr(r1, "is_file_fully_written", lambda p: True)

    client = SupoclipClient()
    video_path = temp_dir / "retry_video.mp4"
    video_path.write_bytes(b"DUMMY_RETRY_DATA")

    # 1. Primeira tentativa falha
    monkeypatch.setattr(client, "submit_job", lambda p: (_ for _ in ()).throw(SupoclipError("Timeout temporário")))
    assert process_single_video(video_path, client) is False

    # 2. Segunda tentativa tem sucesso
    monkeypatch.setattr(client, "submit_job", lambda p: "mock-retry-job-999")
    success2 = process_single_video(video_path, client)
    assert success2 is True

    # Valida que o status foi recuperado e o job registrado
    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, error_message, supoclip_job_id FROM long_videos;")
        row = cursor.fetchone()
        assert row is not None
        assert row["status"] == "PROCESSING"
        assert row["error_message"] is None
        assert row["supoclip_job_id"] == "mock-retry-job-999"
