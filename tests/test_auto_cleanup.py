"""
Testes automatizados para a suíte de Auto-Cleanup e Purga de Mídia Pós-Publicação.
"""
import os
import time
from pathlib import Path
from src.core.database import get_db
from src.services.cleanup import (
    run_disk_cleanup,
    check_and_purge_clip_if_fully_published,
    purge_clip_files,
    purge_orphan_temporary_files
)

def _setup_test_db(temp_dir, monkeypatch):
    db_file = temp_dir / "test_auto_clean.db"
    from src.database.migrations import run_migrations
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)
    monkeypatch.setattr(cfg.settings, "WATCH_DIR", temp_dir / "watch")
    monkeypatch.setattr(cfg.settings, "OUTPUT_DIR", temp_dir / "output")
    monkeypatch.setattr(cfg.settings, "AUTO_DELETE_POSTED_CLIPS", True)
    monkeypatch.setattr(cfg.settings, "AUTO_DELETE_LONG_VIDEOS_ON_COMPLETION", True)
    monkeypatch.setattr(cfg.settings, "KEEP_POSTED_CLIPS_HOURS", 0)

    cfg.settings.WATCH_DIR.mkdir(parents=True, exist_ok=True)
    cfg.settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    return db_file

def test_clip_not_purged_if_only_one_platform_posted(temp_dir, monkeypatch):
    """Garante a Regra de Ouro: Não apaga se ainda estiver pendente em uma rede."""
    db_file = _setup_test_db(temp_dir, monkeypatch)

    clip_file = temp_dir / "output" / "clip_partial.mp4"
    clip_file.write_bytes(b"CLIP_DATA_123")

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO long_videos (file_hash, file_name, file_path, status)
            VALUES ('hash_lv1', 'video.mp4', 'dummy', 'COMPLETED');
        """)
        lv_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score,
                youtube_status, tiktok_status, is_deleted_from_disk
            ) VALUES (?, 'uid_part_1', ?, 80, 'POSTED', 'PENDING', 0);
        """, (lv_id, str(clip_file)))
        clip_id = cursor.lastrowid

    # Executa hook reativo
    purged = check_and_purge_clip_if_fully_published(clip_id)

    assert purged is False
    assert clip_file.exists()  # Arquivo DEVE ser mantido no disco!

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_deleted_from_disk FROM clips WHERE id = ?;", (clip_id,))
        assert cursor.fetchone()["is_deleted_from_disk"] == 0

def test_clip_purged_when_both_platforms_posted(temp_dir, monkeypatch):
    """Clip postado em ambas as plataformas deve ser apagado e marcado is_deleted_from_disk = 1."""
    db_file = _setup_test_db(temp_dir, monkeypatch)

    clip_file = temp_dir / "output" / "clip_done.mp4"
    clip_file.write_bytes(b"CLIP_DATA_FULL_POSTED")
    txt_file = temp_dir / "output" / "clip_done.txt"
    txt_file.write_text("Transcrição completa")

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO long_videos (file_hash, file_name, file_path, status)
            VALUES ('hash_lv2', 'video2.mp4', 'dummy', 'COMPLETED');
        """)
        lv_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score,
                youtube_status, tiktok_status, is_deleted_from_disk
            ) VALUES (?, 'uid_done_1', ?, 95, 'POSTED', 'POSTED', 0);
        """, (lv_id, str(clip_file)))
        clip_id = cursor.lastrowid

    purged = check_and_purge_clip_if_fully_published(clip_id)

    assert purged is True
    assert not clip_file.exists()  # .mp4 deve ser apagado
    assert not txt_file.exists()   # .txt correspondente deve ser apagado

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_deleted_from_disk, youtube_status, tiktok_status FROM clips WHERE id = ?;", (clip_id,))
        row = cursor.fetchone()
        assert row["is_deleted_from_disk"] == 1
        # Integridade dos status preservada
        assert row["youtube_status"] == "POSTED"
        assert row["tiktok_status"] == "POSTED"

def test_clip_purged_when_one_platform_skipped(temp_dir, monkeypatch):
    """Se o TikTok for SKIPPED e o YouTube for POSTED, o ciclo encerrou e o arquivo deve ser purgado."""
    db_file = _setup_test_db(temp_dir, monkeypatch)

    clip_file = temp_dir / "output" / "clip_skipped.mp4"
    clip_file.write_bytes(b"CLIP_DATA_SKIPPED")

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO long_videos (file_hash, file_name, file_path, status)
            VALUES ('hash_lv3', 'video3.mp4', 'dummy', 'COMPLETED');
        """)
        lv_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score,
                youtube_status, tiktok_status, is_deleted_from_disk
            ) VALUES (?, 'uid_skip_1', ?, 75, 'POSTED', 'SKIPPED', 0);
        """, (lv_id, str(clip_file)))
        clip_id = cursor.lastrowid

    purged = check_and_purge_clip_if_fully_published(clip_id)

    assert purged is True
    assert not clip_file.exists()

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_deleted_from_disk FROM clips WHERE id = ?;", (clip_id,))
        assert cursor.fetchone()["is_deleted_from_disk"] == 1

def test_purge_orphan_temporary_files(temp_dir, monkeypatch):
    """Testa remoção de resíduos .part e .ytdl com mais de 2 horas."""
    _setup_test_db(temp_dir, monkeypatch)

    old_part = temp_dir / "watch" / "download_aborted.mp4.part"
    old_part.write_bytes(b"INCOMPLETE_PART_DATA" * 50)
    # Define mtime para 3 horas atrás
    three_hours_ago = time.time() - (3 * 3600)
    os.utime(str(old_part), (three_hours_ago, three_hours_ago))

    # Arquivo recente (não deve ser deletado)
    recent_file = temp_dir / "watch" / "fresh_download.mp4"
    recent_file.write_bytes(b"FRESH_DATA")

    freed = purge_orphan_temporary_files(hours_threshold=2.0)

    assert freed > 0
    assert not old_part.exists()
    assert recent_file.exists()

def test_run_disk_cleanup_full_cycle(temp_dir, monkeypatch):
    """Testa o ciclo periódico geral de run_disk_cleanup."""
    db_file = _setup_test_db(temp_dir, monkeypatch)

    # Cria vídeo longo COMPLETED
    lv_file = temp_dir / "watch" / "long_done.mp4"
    lv_file.write_bytes(b"BIG_LONG_VIDEO_BYTES_1234")

    # Cria clip já postado em ambas
    clip_file = temp_dir / "output" / "clip_batch.mp4"
    clip_file.write_bytes(b"CLIP_BATCH_BYTES")

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO long_videos (file_hash, file_name, file_path, status, is_deleted_from_disk)
            VALUES ('hash_lv_batch', 'long_done.mp4', ?, 'COMPLETED', 0);
        """, (str(lv_file),))
        lv_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score,
                youtube_status, tiktok_status, is_deleted_from_disk
            ) VALUES (?, 'uid_batch_1', ?, 90, 'POSTED', 'POSTED', 0);
        """, (lv_id, str(clip_file)))

    res = run_disk_cleanup()

    assert res["deleted_long_videos"] == 1
    assert res["deleted_clips"] == 1
    assert res["freed_bytes"] > 0
    assert not lv_file.exists()
    assert not clip_file.exists()
