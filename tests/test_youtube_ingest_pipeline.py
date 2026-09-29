"""
Teste de Integração End-to-End do Pipeline de Ingestão de Vídeos do YouTube:
YouTube Metadados / Download -> Ingestão Determinística (robot1_ingest) -> SupoClip Backend -> SQLite (long_videos e supoclip_jobs).
"""
import pytest
import sqlite3
from pathlib import Path
from src.core.config import settings
from src.core.database import get_db
from src.services.youtube_metrics import fetch_video_metrics
from src.services.downloader import download_youtube_video
from src.services.supoclip_client import SupoclipClient
from src.robot1_ingest import process_single_video

def test_fetch_real_youtube_video_metadata():
    """Valida coleta real de metadados de vídeo do YouTube usando o ambiente configurado."""
    yt_id = "jNQXAC9IVRw"  # 'Me at the zoo'
    metrics = fetch_video_metrics(yt_id)
    
    assert metrics is not None, f"Falha ao obter metadados para {yt_id}"
    assert metrics["youtube_id"] == yt_id
    assert "zoo" in metrics["title"].lower()
    assert metrics["duration_seconds"] > 0
    assert metrics["view_count"] > 1000

def test_end_to_end_youtube_ingest_pipeline():
    """
    Executa o fluxo completo com vídeo real do YouTube:
    1. Download via yt-dlp
    2. Ingestão determinística com hash SHA-256 e validação FFmpeg
    3. Inserção no banco SQLite (long_videos)
    4. Submissão e despacho para a API real do SupoClip
    5. Confirmação dos status e IDs no banco de dados
    """
    yt_id = "jNQXAC9IVRw"
    dest_dir = settings.WATCH_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    video_file = dest_dir / f"{yt_id}.mp4"

    # Garante download real se ainda não existir na pasta de vigilância
    if not video_file.exists() or video_file.stat().st_size == 0:
        downloaded = download_youtube_video(yt_id, output_dir=dest_dir)
        assert downloaded is not None and downloaded.exists()

    # Prepara cliente SupoClip
    client = SupoclipClient()

    # Limpa eventual registro prévio deste vídeo no DB para garantir teste de ingestão limpo
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM long_videos WHERE youtube_id = ?;", (yt_id,))

    # Executa a ingestão do vídeo real
    ingest_success = process_single_video(video_file, client)
    assert ingest_success is True, "Falha ao processar e ingerir o vídeo real no pipeline"

    # Valida inserção no banco de dados
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM long_videos WHERE youtube_id = ?;", (yt_id,))
        row = cursor.fetchone()

        assert row is not None, "Registro do vídeo real não encontrado na tabela long_videos"
        assert row["youtube_id"] == yt_id
        assert row["media_valid"] == 1
        assert row["status"] in ("PROCESSING", "COMPLETED")
        assert row["supoclip_job_id"] is not None
        assert len(row["supoclip_job_id"]) > 0

        # Valida registro correspondente em supoclip_jobs
        cursor.execute("SELECT * FROM supoclip_jobs WHERE long_video_id = ?;", (row["id"],))
        job_row = cursor.fetchone()
        assert job_row is not None, "Registro do job não encontrado na tabela supoclip_jobs"
        assert job_row["supoclip_job_id"] == row["supoclip_job_id"]
        assert job_row["status"] in ("SUBMITTED", "PROCESSING", "COMPLETED")

def test_idempotency_prevents_duplicate_reingest():
    """Valida que uma segunda tentativa de ingerir o mesmo vídeo é ignorada de forma idempotente."""
    yt_id = "jNQXAC9IVRw"
    video_file = settings.WATCH_DIR / f"{yt_id}.mp4"
    assert video_file.exists()

    client = SupoclipClient()
    reingest = process_single_video(video_file, client)
    assert reingest is False, "A reingestão do mesmo vídeo deveria ter sido prevenida por idempotência"
