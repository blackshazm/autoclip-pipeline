"""
Testes unitários para resiliência e consistência transacional do Robô 2 (robot2_publish.py).
"""
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.core.database import get_db
import src.robot2_publish as r2

def test_process_due_publications_aborts_and_commits_on_invalid_media(temp_dir, monkeypatch):
    """Testa se mídia corrompida/inválida é abortada, comitada como FAILED e bloqueada."""
    db_file = temp_dir / "r2_invalid_media_test.db"
    from src.database.migrations import run_migrations
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)

    # Cria arquivo fictício de 0 bytes
    fake_video = temp_dir / "corrupted_clip.mp4"
    fake_video.touch()

    now_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO long_videos (file_hash, file_name, file_path, status) VALUES ('h_inv', 'v.mp4', 'p.mp4', 'COMPLETED');")
        vid_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score, title, moderation_status
            ) VALUES (?, 'uid_corrupt', ?, 88, '🔥 Clip Corrompido', 'APPROVED');
        """, (vid_id, str(fake_video)))
        clip_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO publications (
                clip_id, publishing_account_id, platform, status, scheduled_for, idempotency_key
            ) VALUES (?, 1, 'youtube', 'SCHEDULED', ?, 'key_corrupt_1');
        """, (clip_id, now_iso))
        pub_id = cursor.lastrowid

    # Força verify_media_integrity a retornar False
    with patch("src.robot2_publish.verify_media_integrity", return_value=False):
        with patch("src.robot2_publish.notify_alert"):
            done = r2.process_due_publications()
            assert done == 0

    # Verifica se as alterações foram devidamente commitadas no banco
    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, error_message FROM publications WHERE id = ?;", (pub_id,))
        pub_row = cursor.fetchone()
        assert pub_row["status"] == "FAILED"
        assert "inválido" in pub_row["error_message"].lower()

        cursor.execute("SELECT moderation_status, error_log FROM clips WHERE id = ?;", (clip_id,))
        clip_row = cursor.fetchone()
        assert clip_row["moderation_status"] == "MODERATION_BLOCKED"
        assert "inválido" in clip_row["error_log"].lower()

def test_process_due_publications_syncs_clips_on_final_retry_exhaustion(temp_dir, monkeypatch):
    """Testa se a exaustão de 3 tentativas atualiza tanto publications quanto clips para FAILED."""
    db_file = temp_dir / "r2_retry_sync_test.db"
    from src.database.migrations import run_migrations
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)

    fake_video = temp_dir / "valid_file.mp4"
    fake_video.write_bytes(b"dummy video data")

    now_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO long_videos (file_hash, file_name, file_path, status) VALUES ('h_ret', 'v.mp4', 'p.mp4', 'COMPLETED');")
        vid_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score, title, moderation_status, youtube_status
            ) VALUES (?, 'uid_exhaust', ?, 80, '🔥 Clip Retry', 'APPROVED', 'PENDING');
        """, (vid_id, str(fake_video)))
        clip_id = cursor.lastrowid

        # Simula publicação já na 2ª tentativa (retry_count = 2), próxima será a 3ª (definitiva)
        cursor.execute("""
            INSERT INTO publications (
                clip_id, publishing_account_id, platform, status, scheduled_for, idempotency_key, retry_count
            ) VALUES (?, 1, 'youtube', 'SCHEDULED', ?, 'key_ret_exhaust', 2);
        """, (clip_id, now_iso))
        pub_id = cursor.lastrowid

    monkeypatch.setattr(cfg.settings, "YOUTUBE_PUBLISHER_MODE", "api")

    with patch("src.robot2_publish.verify_media_integrity", return_value=True):
        with patch("src.robot2_publish.notify_alert"):
            with patch.object(r2.YouTubePublisher, "publish_short", side_effect=RuntimeError("Upload fatal network failure")):
                done = r2.process_due_publications()
                assert done == 0

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, retry_count, error_message FROM publications WHERE id = ?;", (pub_id,))
        pub_row = cursor.fetchone()
        assert pub_row["status"] == "FAILED"
        assert pub_row["retry_count"] == 3
        assert "fatal network failure" in pub_row["error_message"]

        cursor.execute("SELECT youtube_status, error_log FROM clips WHERE id = ?;", (clip_id,))
        clip_row = cursor.fetchone()
        assert clip_row["youtube_status"] == "FAILED"
        assert "fatal network failure" in clip_row["error_log"]
