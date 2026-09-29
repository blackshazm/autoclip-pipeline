"""
Testes de ingestão determinística e idempotência por hash SHA-256.
"""
from pathlib import Path
from src.robot1_ingest import compute_sha256, is_file_fully_written, process_single_video
from src.services.supoclip_client import SupoclipClient
from src.core.database import get_db

def test_compute_sha256(temp_dir):
    f1 = temp_dir / "test1.mp4"
    f2 = temp_dir / "test2.mp4"

    content = b"VIDEO_BINARY_DATA_SAMPLE_12345"
    f1.write_bytes(content)
    f2.write_bytes(content)

    hash1 = compute_sha256(f1)
    hash2 = compute_sha256(f2)

    assert hash1 == hash2
    assert len(hash1) == 64

def test_is_file_fully_written(temp_dir):
    f = temp_dir / "stable.mp4"
    f.write_bytes(b"DATA")
    # Intervalo reduzido para teste rápido
    assert is_file_fully_written(f, check_interval=0.1) is True

def test_ingest_duplicate_rejection(temp_dir, monkeypatch):
    """Garante que o mesmo arquivo enviado duas vezes não cria registro duplicado."""
    db_file = temp_dir / "ingest_test.db"
    from src.database.migrations import run_migrations
    run_migrations(db_file)

    # Monkeypatch do banco global para apontar para o banco de teste
    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)
    monkeypatch.setattr(cfg.settings, "MOCK_SUPOCLIP", True)

    # Mock de verificação de mídia para teste sem ffprobe real no dummy
    import src.robot1_ingest as r1
    monkeypatch.setattr(r1, "verify_media_integrity", lambda p: True)
    monkeypatch.setattr(r1, "inspect_media_file", lambda p: {"duration_seconds": 1200.0, "file_size_bytes": 1024})
    monkeypatch.setattr(r1, "is_file_fully_written", lambda p: True)

    client = SupoclipClient()
    video_path = temp_dir / "mock_video.mp4"
    video_path.write_bytes(b"DUMMY_MP4_CONTENT")

    # Primeira ingestão: deve ter sucesso (retorna True)
    success1 = r1.process_single_video(video_path, client)
    assert success1 is True

    # Segunda ingestão com exatamente o mesmo conteúdo: deve rejeitar por hash duplicado (retorna False)
    success2 = r1.process_single_video(video_path, client)
    assert success2 is False

    # Valida no banco que existe apenas 1 registro em long_videos
    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM long_videos;")
        assert cursor.fetchone()["cnt"] == 1
