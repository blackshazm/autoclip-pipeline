"""
Testes para retenção de disco, limpeza normal e proteção emergencial.
"""
from pathlib import Path
from src.core.database import get_db
from src.services.cleanup import run_disk_cleanup, get_disk_usage_percent

def test_cleanup_deletes_completed_long_videos(temp_dir, monkeypatch):
    """Testa se o arquivo físico é deletado após status COMPLETED mas a linha permanece no DB."""
    db_file = temp_dir / "clean_test.db"
    from src.database.migrations import run_migrations
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)
    monkeypatch.setattr(cfg.settings, "WATCH_DIR", temp_dir)

    # Cria arquivo físico no disco
    video_file = temp_dir / "raw_video_done.mp4"
    video_file.write_bytes(b"DUMMY_RAW_VIDEO_BYTES_12345")
    assert video_file.exists()

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO long_videos (file_hash, file_name, file_path, status, is_deleted_from_disk)
            VALUES ('hash_done_1', 'raw_video_done.mp4', ?, 'COMPLETED', 0);
        """, (str(video_file),))
        video_id = cursor.lastrowid

    # Executa a limpeza
    result = run_disk_cleanup()

    assert result["deleted_long_videos"] == 1
    # Arquivo físico deve ter sido removido
    assert not video_file.exists()

    # Registro no banco deve permanecer com is_deleted_from_disk = 1 (idempotência preservada)
    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, is_deleted_from_disk FROM long_videos WHERE id = ?;", (video_id,))
        row = cursor.fetchone()
        assert row["status"] == "COMPLETED"
        assert row["is_deleted_from_disk"] == 1

def test_get_disk_usage_percent(temp_dir):
    pct = get_disk_usage_percent(temp_dir)
    assert 0.0 <= pct <= 100.0
