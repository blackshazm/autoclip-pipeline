"""
Testes de integração e validação do motor PRO no worker desacoplado (publish_worker.py)
e no publicador monolítico (robot2_publish.py).
"""
import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.core.database import get_db
from src.database.migrations import run_migrations
import src.services.publish_worker as pw
import src.robot2_publish as r2
from src.services.youtube_browser_publisher_pro import PublishPayloadPro


def test_publish_worker_uses_pro_engine_financas(temp_dir, monkeypatch):
    """Garante que publish_worker utiliza YouTubeBrowserPublisherPro com categoria Educação para financas."""
    db_file = temp_dir / "worker_pro_financas.db"
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)
    monkeypatch.setattr(cfg.settings, "YOUTUBE_BROWSER_ENGINE", "pro")
    monkeypatch.setattr(cfg.settings, "YOUTUBE_DEFAULT_AI_DISCLOSURE", True)

    fake_video = temp_dir / "clip_financas.mp4"
    fake_video.write_bytes(b"dummy video data")

    now_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO long_videos (file_hash, file_name, file_path, status) VALUES ('h_pro_fin', 'v.mp4', 'p.mp4', 'COMPLETED');")
        vid_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score, title, description, tags, moderation_status
            ) VALUES (?, 'uid_pro_fin', ?, 95, 'Como Investir em 2026', 'Dicas financeiras', '["investimentos", "renda"]', 'APPROVED');
        """, (vid_id, str(fake_video)))
        clip_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO publishing_accounts (platform, profile_name, display_name, credentials_ref, niche)
            VALUES ('youtube', 'yt_financas', 'Canal Finanças', 'config/youtube_financas_state.json', 'financas');
        """)
        account_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO publications (
                clip_id, publishing_account_id, platform, status, scheduled_for, idempotency_key
            ) VALUES (?, ?, 'youtube', 'SCHEDULED', ?, 'key_pro_fin_1');
        """, (clip_id, account_id, now_iso))
        pub_id = cursor.lastrowid

    captured_payloads = []

    def mock_publish_pro(payload: PublishPayloadPro):
        captured_payloads.append(payload)
        return {
            "youtube_video_id": "dQw4w9WgXcQ",
            "status": "POSTED"
        }

    with patch("src.services.publish_worker.verify_media_integrity", return_value=True):
        with patch("src.services.publish_worker.notify_published_clip"):
            with patch("src.services.publish_worker.check_and_purge_clip_if_fully_published"):
                with patch("src.services.youtube_browser_publisher_pro.YouTubeBrowserPublisherPro.publish_short_pro", side_effect=mock_publish_pro):
                    result = pw.run_single_publish_cycle("youtube", "financas", "worker_test", "test_proc")
                    assert result == 1

    assert len(captured_payloads) == 1
    p = captured_payloads[0]
    assert p.category_name == "Educação"
    assert p.is_synthetic_ai is True
    assert p.title == "Como Investir em 2026"
    assert "investimentos" in p.tags
    assert p.clip_uid == "uid_pro_fin"

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, external_id FROM publications WHERE id = ?;", (pub_id,))
        row = cursor.fetchone()
        assert row["status"] == "POSTED"
        assert row["external_id"] == "dQw4w9WgXcQ"


def test_publish_worker_uses_pro_engine_fitness(temp_dir, monkeypatch):
    """Garante que publish_worker utiliza categoria Esportes para fitness."""
    db_file = temp_dir / "worker_pro_fitness.db"
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)
    monkeypatch.setattr(cfg.settings, "YOUTUBE_BROWSER_ENGINE", "pro")

    fake_video = temp_dir / "clip_fitness.mp4"
    fake_video.write_bytes(b"dummy video data")

    now_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO long_videos (file_hash, file_name, file_path, status) VALUES ('h_pro_fit', 'v.mp4', 'p.mp4', 'COMPLETED');")
        vid_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score, title, description, tags, moderation_status
            ) VALUES (?, 'uid_pro_fit', ?, 90, 'Treino de Pernas Insano', 'Treino pesado', '["treino", "academia"]', 'APPROVED');
        """, (vid_id, str(fake_video)))
        clip_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO publishing_accounts (platform, profile_name, display_name, credentials_ref, niche)
            VALUES ('youtube', 'yt_fitness', 'Canal Fitness', 'config/youtube_fitness_state.json', 'fitness');
        """)
        account_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO publications (
                clip_id, publishing_account_id, platform, status, scheduled_for, idempotency_key
            ) VALUES (?, ?, 'youtube', 'SCHEDULED', ?, 'key_pro_fit_1');
        """, (clip_id, account_id, now_iso))

    captured_payloads = []

    def mock_publish_pro(payload: PublishPayloadPro):
        captured_payloads.append(payload)
        return {"youtube_video_id": "fitVideo123", "status": "POSTED"}

    with patch("src.services.publish_worker.verify_media_integrity", return_value=True):
        with patch("src.services.publish_worker.notify_published_clip"):
            with patch("src.services.publish_worker.check_and_purge_clip_if_fully_published"):
                with patch("src.services.youtube_browser_publisher_pro.YouTubeBrowserPublisherPro.publish_short_pro", side_effect=mock_publish_pro):
                    result = pw.run_single_publish_cycle("youtube", "fitness", "worker_test", "test_proc")
                    assert result == 1

    assert len(captured_payloads) == 1
    p = captured_payloads[0]
    assert p.category_name == "Esportes"
    assert p.is_synthetic_ai is True


def test_robot2_publish_with_pro_engine(temp_dir, monkeypatch):
    """Testa se robot2_publish.py invoca YouTubeBrowserPublisherPro quando configurado para browser."""
    db_file = temp_dir / "r2_pro_test.db"
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)
    monkeypatch.setattr(cfg.settings, "YOUTUBE_PUBLISHER_MODE", "browser")
    monkeypatch.setattr(cfg.settings, "YOUTUBE_BROWSER_ENGINE", "pro")

    fake_video = temp_dir / "r2_clip.mp4"
    fake_video.write_bytes(b"dummy video data")

    now_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO long_videos (file_hash, file_name, file_path, status) VALUES ('h_r2_pro', 'v.mp4', 'p.mp4', 'COMPLETED');")
        vid_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score, title, description, tags, moderation_status
            ) VALUES (?, 'uid_r2_pro', ?, 85, 'Corte Geral R2', 'Desc R2', '["cortes"]', 'APPROVED');
        """, (vid_id, str(fake_video)))
        clip_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO publications (
                clip_id, publishing_account_id, platform, status, scheduled_for, idempotency_key
            ) VALUES (?, 1, 'youtube', 'SCHEDULED', ?, 'key_r2_pro_1');
        """, (clip_id, now_iso))

    captured_payloads = []

    def mock_publish_pro(payload: PublishPayloadPro):
        captured_payloads.append(payload)
        return {"youtube_video_id": "r2VideoId99", "status": "POSTED"}

    with patch("src.robot2_publish.verify_media_integrity", return_value=True):
        with patch("src.robot2_publish.notify_alert"):
            with patch("src.robot2_publish.check_and_purge_clip_if_fully_published"):
                with patch("src.services.youtube_browser_publisher_pro.YouTubeBrowserPublisherPro.publish_short_pro", side_effect=mock_publish_pro):
                    published = r2.process_due_publications()
                    assert published == 1

    assert len(captured_payloads) == 1
    assert captured_payloads[0].clip_uid == "uid_r2_pro"
    assert captured_payloads[0].is_synthetic_ai is True


def test_publish_worker_post_upload_error_does_not_revert_posted_status(temp_dir, monkeypatch):
    """Garante que falhas em notificações ou telemetria pós-upload NÃO revertem status POSTED para SCHEDULED."""
    db_file = temp_dir / "worker_anti_repeat.db"
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)

    fake_video = temp_dir / "clip_safe.mp4"
    fake_video.write_bytes(b"dummy video data")

    now_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO long_videos (file_hash, file_name, file_path, status) VALUES ('h_safe', 'v.mp4', 'p.mp4', 'COMPLETED');")
        vid_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score, title, description, tags, moderation_status
            ) VALUES (?, 'uid_safe_1', ?, 90, 'Vídeo Teste Anti-Duplicação', 'Desc', '["shorts"]', 'APPROVED');
        """, (vid_id, str(fake_video)))
        clip_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO publishing_accounts (platform, profile_name, display_name, credentials_ref, niche)
            VALUES ('youtube', 'yt_safe', 'Canal Finanças', 'config/youtube_financas_state.json', 'financas');
        """)
        account_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO publications (
                clip_id, publishing_account_id, platform, status, scheduled_for, idempotency_key
            ) VALUES (?, ?, 'youtube', 'SCHEDULED', ?, 'key_safe_1');
        """, (clip_id, account_id, now_iso))
        pub_id = cursor.lastrowid

    def mock_publish_pro(payload: PublishPayloadPro):
        return {"youtube_video_id": "postedId123", "status": "POSTED"}

    # Simula falha catastrófica no webhook do Discord/Telegram e na telemetria
    with patch("src.services.publish_worker.verify_media_integrity", return_value=True):
        with patch("src.services.publish_worker.notify_published_clip", side_effect=RuntimeError("Discord webhook offline")):
            with patch("src.services.publish_worker.SignalTracker.emit_finish", side_effect=Exception("Telemetry network error")):
                with patch("src.services.youtube_browser_publisher_pro.YouTubeBrowserPublisherPro.publish_short_pro", side_effect=mock_publish_pro):
                    result = pw.run_single_publish_cycle("youtube", "financas", "worker_test", "test_proc")
                    assert result == 1

    # Verifica se a publicação continua como POSTED (e não SCHEDULED)
    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, retry_count, external_id FROM publications WHERE id = ?;", (pub_id,))
        row = cursor.fetchone()
        assert row["status"] == "POSTED"
        assert row["external_id"] == "postedId123"
        assert row["retry_count"] == 0


def test_publish_worker_syncs_failed_to_clips(temp_dir, monkeypatch):
    """Garante que quando esgotam as 3 tentativas, clips.youtube_status é sincronizado para FAILED."""
    db_file = temp_dir / "worker_failed_sync.db"
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)

    fake_video = temp_dir / "clip_fail.mp4"
    fake_video.write_bytes(b"dummy video data")

    now_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO long_videos (file_hash, file_name, file_path, status) VALUES ('h_fail', 'v.mp4', 'p.mp4', 'COMPLETED');")
        vid_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score, title, description, tags, moderation_status, youtube_status
            ) VALUES (?, 'uid_fail_1', ?, 90, 'Vídeo Falho', 'Desc', '["shorts"]', 'APPROVED', 'SCHEDULED');
        """, (vid_id, str(fake_video)))
        clip_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO publishing_accounts (platform, profile_name, display_name, credentials_ref, niche)
            VALUES ('youtube', 'yt_fail_acc', 'Canal Finanças', 'config/youtube_financas_state.json', 'financas');
        """)
        account_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO publications (
                clip_id, publishing_account_id, platform, status, scheduled_for, idempotency_key, retry_count
            ) VALUES (?, ?, 'youtube', 'SCHEDULED', ?, 'key_fail_1', 2);
        """, (clip_id, account_id, now_iso))
        pub_id = cursor.lastrowid

    # Simula falha no upload que atinge o limite de 3 tentativas
    with patch("src.services.publish_worker.verify_media_integrity", return_value=True):
        with patch("src.services.youtube_browser_publisher_pro.YouTubeBrowserPublisherPro.publish_short_pro", side_effect=RuntimeError("Erro fatal no upload")):
            result = pw.run_single_publish_cycle("youtube", "financas", "worker_test", "test_proc")
            assert result == 0

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, retry_count, error_message FROM publications WHERE id = ?;", (pub_id,))
        pub_row = cursor.fetchone()
        assert pub_row["status"] == "FAILED"
        assert pub_row["retry_count"] == 3
        assert "Erro fatal no upload" in pub_row["error_message"]

        cursor.execute("SELECT youtube_status, error_log FROM clips WHERE id = ?;", (clip_id,))
        clip_row = cursor.fetchone()
        assert clip_row["youtube_status"] == "FAILED"
        assert "Erro fatal no upload" in clip_row["error_log"]


