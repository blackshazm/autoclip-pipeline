"""
Testes automatizados para o desacoplamento e processamento de jobs no media_pipeline_worker.
"""
from pathlib import Path
from unittest.mock import MagicMock
from src.core.database import get_db
from src.database.migrations import run_migrations
import src.core.config as cfg
from src.services.media_pipeline_worker import sync_supoclip_jobs


def test_sync_supoclip_jobs_decoupled_db(tmp_path, monkeypatch):
    """Garante que sync_supoclip_jobs processa clips e persiste no banco sem lock contention."""
    db_file = tmp_path / "test_media_sync.db"
    run_migrations(db_file)

    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)
    monkeypatch.setattr(cfg.settings, "ENABLE_SMART_REFRAME", False)
    monkeypatch.setattr(cfg.settings, "ENABLE_VIDEO_PACING", False)
    monkeypatch.setattr(cfg.settings, "AUTO_DELETE_LONG_VIDEOS_ON_COMPLETION", True)

    original_video = tmp_path / "original_long.mp4"
    original_video.write_bytes(b"FAKE_LONG_VIDEO_BYTES_12345")

    clip_file = tmp_path / "clip_01.mp4"
    clip_file.write_bytes(b"FAKE_CLIP_BYTES")

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO long_videos (file_hash, file_name, file_path, status)
            VALUES ('hash_long_1', 'original_long.mp4', ?, 'PROCESSING');
        """, (str(original_video),))
        long_vid_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO supoclip_jobs (long_video_id, supoclip_job_id, status)
            VALUES (?, 'supo_job_999', 'SUBMITTED');
        """, (long_vid_id,))

    mock_client = MagicMock()
    mock_client.get_job_status.return_value = {
        "status": "COMPLETED",
        "clips": [
            {
                "clip_uid": "clip_test_abc",
                "file_path": str(clip_file),
                "virality_score": 85,
                "duration_seconds": 32.5,
                "start_seconds": 10.0,
                "end_seconds": 42.5,
                "width": 1080,
                "height": 1920,
                "fps": 30,
            }
        ]
    }

    completed = sync_supoclip_jobs(mock_client)
    assert completed == 1

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM supoclip_jobs WHERE supoclip_job_id = 'supo_job_999';")
        job_row = cursor.fetchone()
        assert job_row["status"] == "COMPLETED"

        cursor.execute("SELECT status, is_deleted_from_disk FROM long_videos WHERE id = ?;", (long_vid_id,))
        lv_row = cursor.fetchone()
        assert lv_row["status"] == "COMPLETED"
        assert lv_row["is_deleted_from_disk"] == 1

        cursor.execute("SELECT clip_uid, moderation_status, youtube_status, tiktok_status, virality_score FROM clips WHERE long_video_id = ?;", (long_vid_id,))
        clips = cursor.fetchall()
        assert len(clips) == 1
        assert clips[0]["clip_uid"] == "clip_test_abc"
        assert clips[0]["moderation_status"] == "APPROVED"
        assert clips[0]["youtube_status"] == "PENDING"
        assert clips[0]["tiktok_status"] == "PENDING"

    # Verifica que o vídeo longo bruto foi purgado
    assert not original_video.exists()


def test_notify_supoclip_job_completed(monkeypatch):
    """Garante que notify_supoclip_job_completed formata mensagem comemorativa e despacha notificações."""
    from unittest.mock import MagicMock
    from src.services.notifier import notify_supoclip_job_completed
    import src.services.notifier as notif_mod

    mock_discord = MagicMock(return_value=True)
    mock_telegram = MagicMock(return_value=True)
    monkeypatch.setattr(notif_mod, "send_discord_notification", mock_discord)
    monkeypatch.setattr(notif_mod, "send_telegram_notification", mock_telegram)

    notify_supoclip_job_completed(
        job_id="supo_123",
        video_title="Podcast Exemplo",
        total_clips=10,
        qualified_clips=7,
        top_score=92,
    )

    assert mock_discord.called
    call_args = mock_discord.call_args[0]
    title, desc = call_args[0], call_args[1]
    assert "Supoclip Concluído" in title
    assert "Podcast Exemplo" in desc
    assert "Cortes Gerados:** `10`" in desc
    assert "Aprovados" in desc
    assert "Maior Virality Score:** `92/100`" in desc
    assert mock_telegram.called

