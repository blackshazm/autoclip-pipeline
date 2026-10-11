"""
Testes Unitários e de Integração para Controle de Pausa da Pipeline e RAM Conflict Shield.
"""
import pytest
import sqlite3
from unittest.mock import patch, MagicMock

from src.core.pipeline_control import PipelineController, init_controls_table
from src.core.database import get_db

@pytest.fixture(autouse=True)
def clean_controls():
    """Garante que a tabela de controles seja limpa e inicializada antes de cada teste."""
    init_controls_table()
    PipelineController.resume_all()
    yield
    PipelineController.resume_all()

def test_pipeline_controller_initial_state():
    """Valida que todos os serviços começam despausados por padrão."""
    assert PipelineController.is_paused("radar_youtube") is False
    assert PipelineController.is_paused("robot1_ingest") is False
    assert PipelineController.is_paused("robot2_publish") is False
    assert PipelineController.is_paused("llm_copywriter") is False
    assert PipelineController.is_paused("all") is False

def test_individual_toggle_pause():
    """Testa alternância de pausa para serviços individuais."""
    # Pausa apenas o copywriter
    new_state = PipelineController.toggle_pause("llm_copywriter")
    assert new_state is True
    assert PipelineController.is_paused("llm_copywriter") is True
    # Demais serviços continuam despausados
    assert PipelineController.is_paused("radar_youtube") is False
    assert PipelineController.is_paused("robot1_ingest") is False
    assert PipelineController.is_paused("robot2_publish") is False

    # Despausa o copywriter
    new_state = PipelineController.toggle_pause("llm_copywriter")
    assert new_state is False
    assert PipelineController.is_paused("llm_copywriter") is False

def test_master_pause_all():
    """Testa que ao pausar 'all', todos os serviços reportam is_paused = True."""
    PipelineController.pause_all(reason="teste_unitario")
    assert PipelineController.is_paused("all") is True
    assert PipelineController.is_paused("radar_youtube") is True
    assert PipelineController.is_paused("robot1_ingest") is True
    assert PipelineController.is_paused("robot2_publish") is True
    assert PipelineController.is_paused("llm_copywriter") is True

    # Retoma todos
    PipelineController.resume_all()
    assert PipelineController.is_paused("all") is False
    assert PipelineController.is_paused("radar_youtube") is False
    assert PipelineController.is_paused("robot1_ingest") is False
    assert PipelineController.is_paused("robot2_publish") is False
    assert PipelineController.is_paused("llm_copywriter") is False

def test_get_all_statuses_structure():
    """Verifica se get_all_statuses retorna a estrutura esperada para a API e Dashboard."""
    res = PipelineController.get_all_statuses()
    assert "controls" in res
    assert "all_paused" in res
    assert "clip_cutting_active" in res
    assert "system_memory" in res
    assert "percent" in res["system_memory"]
    assert "used_gb" in res["system_memory"]
    assert "total_gb" in res["system_memory"]

def test_ram_conflict_shield_detection():
    """Testa se is_clip_processing_active detecta corretamente jobs no Supoclip."""
    with get_db() as conn:
        cur = conn.cursor()
        # Garante que a tabela supoclip_jobs exista
        cur.execute("DELETE FROM supoclip_jobs WHERE supoclip_job_id = 'test-job-active';")
        cur.execute("DELETE FROM long_videos WHERE file_hash = 'hash-active-test';")

        cur.execute("""
            INSERT INTO long_videos (file_hash, file_name, file_path, status)
            VALUES ('hash-active-test', 'video_test.mp4', 'path/test.mp4', 'PROCESSING');
        """)
        vid_id = cur.lastrowid

        cur.execute("""
            INSERT INTO supoclip_jobs (long_video_id, supoclip_job_id, status)
            VALUES (?, 'test-job-active', 'PROCESSING');
        """, (vid_id,))
        conn.commit()

    # Deve detectar que o corte está ativo
    assert PipelineController.is_clip_processing_active() is True

    # Limpeza
    with get_db() as conn:
        conn.execute("DELETE FROM supoclip_jobs WHERE supoclip_job_id = 'test-job-active';")
        conn.execute("DELETE FROM long_videos WHERE id = ?;", (vid_id,))
        conn.commit()

    # Após concluir/remover, volta a ser False
    assert PipelineController.is_clip_processing_active() is False
