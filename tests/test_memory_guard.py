"""
Testes Unitários para Proteção de Memória RAM e Concorrência Inteligente (Supoclip vs Copywriter).
Valida que:
1. Quando LLM é local (Ollama/localhost), a política de exclusão mútua protege o host.
2. Quando LLM é remota (NVIDIA NIM/Nuvem), Supoclip e Copywriter rodam simultaneamente sem bloqueios.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.pipeline_control import PipelineController, init_controls_table
from src.core.database import get_db
from src.robot1_ingest import run_ingestor_cycle
from src.services.llm_copywriter import generate_clip_copy, unload_ollama_model

@pytest.fixture(autouse=True)
def clean_pipeline_state(monkeypatch):
    """Garante estado limpo de controles e jobs de teste antes e depois de cada teste."""
    monkeypatch.setattr(PipelineController, "get_system_memory_info", classmethod(lambda cls: {
        "percent": 50.0,
        "used_gb": 8.0,
        "total_gb": 16.0,
        "free_gb": 8.0,
        "available": True
    }))
    init_controls_table()
    with get_db() as conn:
        conn.execute("DELETE FROM supoclip_jobs WHERE supoclip_job_id LIKE 'test-mem-%';")
        conn.execute("DELETE FROM long_videos WHERE id = 9999;")
        conn.execute("UPDATE pipeline_controls SET is_paused = 0;")
        conn.execute("DELETE FROM pipeline_controls WHERE service_name = 'copywriter_running';")
        # Cria vídeo pai para testes com supoclip_jobs (respeita FK)
        conn.execute("""
            INSERT OR IGNORE INTO long_videos (id, file_hash, file_name, file_path, status)
            VALUES (9999, 'test-mem-hash', 'test_vid.mp4', 'dummy/path.mp4', 'PROCESSING');
        """)
    yield
    with get_db() as conn:
        conn.execute("DELETE FROM supoclip_jobs WHERE supoclip_job_id LIKE 'test-mem-%';")
        conn.execute("DELETE FROM long_videos WHERE id = 9999;")
        conn.execute("UPDATE pipeline_controls SET is_paused = 0;")
        conn.execute("DELETE FROM pipeline_controls WHERE service_name = 'copywriter_running';")


def test_can_ingest_blocked_when_supoclip_busy():
    """Valida que o Robô 1 não permite despacho se houver job ativo no Supoclip (independente de LLM)."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO supoclip_jobs (long_video_id, supoclip_job_id, status)
            VALUES (9999, 'test-mem-active-job', 'PROCESSING');
        """)

    can_ingest, reason = PipelineController.can_ingest_new_video()
    assert can_ingest is False
    assert "Supoclip ocupado" in reason


def test_local_llm_blocks_concurrency(monkeypatch):
    """Valida que no modo LLM local (Ollama) o RAM Shield bloqueia concorrência mútua."""
    monkeypatch.setattr(PipelineController, "is_local_llm", classmethod(lambda cls: True))

    # 1. Ingestor é bloqueado se copywriter local estiver rodando
    PipelineController.set_copywriter_active(True)
    can_ingest, reason = PipelineController.can_ingest_new_video()
    assert can_ingest is False
    assert "RAM Shield" in reason

    PipelineController.set_copywriter_active(False)

    # 2. Copywriter é bloqueado se Supoclip estiver cortando vídeo
    with get_db() as conn:
        conn.execute("""
            INSERT INTO supoclip_jobs (long_video_id, supoclip_job_id, status)
            VALUES (9999, 'test-mem-cutting', 'SUBMITTED');
        """)

    can_run, reason = PipelineController.can_run_copywriter()
    assert can_run is False
    assert "RAM Shield" in reason


def test_remote_llm_allows_concurrency(monkeypatch):
    """Valida que no modo LLM remoto (NVIDIA NIM/Nuvem) Supoclip e Copywriter rodam simultaneamente."""
    monkeypatch.setattr(PipelineController, "is_local_llm", classmethod(lambda cls: False))

    # 1. Ingestor NÃO é bloqueado mesmo se copywriter estiver ativo
    PipelineController.set_copywriter_active(True)
    can_ingest, reason = PipelineController.can_ingest_new_video()
    assert can_ingest is True, f"Falhou can_ingest_new_video: {reason}"

    # 2. Copywriter NÃO é bloqueado mesmo se Supoclip estiver fatiando vídeo
    with get_db() as conn:
        conn.execute("""
            INSERT INTO supoclip_jobs (long_video_id, supoclip_job_id, status)
            VALUES (9999, 'test-mem-concurrent', 'PROCESSING');
        """)

    can_run, reason = PipelineController.can_run_copywriter()
    assert can_run is True


def test_generate_clip_copy_fallback_when_local_shield_active(monkeypatch):
    """Garante que no modo local, o copywriter desvia para fallback se o Supoclip estiver ocupado."""
    monkeypatch.setattr(PipelineController, "is_local_llm", classmethod(lambda cls: True))
    with get_db() as conn:
        conn.execute("""
            INSERT INTO supoclip_jobs (long_video_id, supoclip_job_id, status)
            VALUES (9999, 'test-mem-shield', 'PROCESSING');
        """)

    res = generate_clip_copy(9999, "Texto de transcrição de podcast para teste de segurança de memória.")
    assert res["is_fallback"] is True
    assert res["status"] == "FALLBACK"
    assert "title" in res["metadata"]
    assert PipelineController.is_copywriter_active() is False


def test_robot1_ingest_strictly_one_by_one(monkeypatch, tmp_path):
    """Garante que run_ingestor_cycle processa estritamente NO MÁXIMO 1 vídeo por ciclo."""
    from src.core import config

    test_watch = tmp_path / "videos"
    test_watch.mkdir()
    (test_watch / "vid1.mp4").write_bytes(b"dummy1")
    (test_watch / "vid2.mp4").write_bytes(b"dummy2")
    (test_watch / "vid3.mp4").write_bytes(b"dummy3")

    monkeypatch.setattr(config.settings, "WATCH_DIR", test_watch)

    with patch("src.robot1_ingest.process_single_video", return_value=True) as mock_process:
        with patch.object(PipelineController, "can_ingest_new_video", return_value=(True, "Pronto")):
            ingested = run_ingestor_cycle()
            assert ingested == 1
            assert mock_process.call_count == 1
