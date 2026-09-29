"""
Testes de concorrência com lease-lock no SQLite e reconciliação pós-crash.
"""
from datetime import datetime, timezone, timedelta
from src.core.database import get_db
import src.robot2_publish as r2

def test_publisher_lease_lock_concurrency(temp_dir, monkeypatch):
    """Simula dois workers tentando publicar o mesmo item simultaneamente."""
    db_file = temp_dir / "lease_test.db"
    from src.database.migrations import run_migrations
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)

    now_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO long_videos (file_hash, file_name, file_path, status) VALUES ('h2', 'v2.mp4', 'p2.mp4', 'COMPLETED');")
        vid_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO clips (long_video_id, clip_uid, file_path, virality_score, title, moderation_status)
            VALUES (?, 'uid_concurrency', 'c.mp4', 90, '🔥 Clip Concorrente #Shorts', 'APPROVED');
        """, (vid_id,))
        clip_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO publications (
                clip_id, publishing_account_id, platform, status, scheduled_for, idempotency_key
            ) VALUES (?, 1, 'youtube', 'SCHEDULED', ?, 'key_conc_1');
        """, (clip_id, now_iso))
        pub_id = cursor.lastrowid

    # Worker A tenta pegar lease
    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE publications
            SET status = 'UPLOADING', lease_owner = 'worker-A', lease_expires_at = datetime('now', '+10 minutes')
            WHERE id = ? AND status = 'SCHEDULED';
        """, (pub_id,))
        acquired_a = cursor.rowcount

    # Worker B tenta pegar lease no mesmo registro
    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE publications
            SET status = 'UPLOADING', lease_owner = 'worker-B', lease_expires_at = datetime('now', '+10 minutes')
            WHERE id = ? AND status = 'SCHEDULED';
        """, (pub_id,))
        acquired_b = cursor.rowcount

    # Apenas o Worker A deve ter adquirido o lock!
    assert acquired_a == 1
    assert acquired_b == 0

def test_reconciliation_marks_expired_lease(temp_dir, monkeypatch):
    """Testa se publicações abandonadas em UPLOADING com lease vencido entram em RECONCILING."""
    db_file = temp_dir / "reconcile_test.db"
    from src.database.migrations import run_migrations
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)

    past_lease = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO long_videos (file_hash, file_name, file_path, status) VALUES ('h3', 'v3.mp4', 'p3.mp4', 'COMPLETED');")
        vid_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO clips (long_video_id, clip_uid, file_path, virality_score, title, moderation_status)
            VALUES (?, 'uid_reconcile', 'c.mp4', 80, '🔥 Clip Reconcile #Shorts', 'APPROVED');
        """, (vid_id,))
        clip_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO publications (
                clip_id, publishing_account_id, platform, status, scheduled_for, idempotency_key,
                lease_owner, lease_expires_at
            ) VALUES (?, 1, 'youtube', 'UPLOADING', datetime('now'), 'key_rec_1', 'dead_worker', ?);
        """, (clip_id, past_lease))
        pub_id = cursor.lastrowid

    # Dispara a rotina de processamento
    r2.process_due_publications()

    # Valida que o item passou para RECONCILING
    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM publications WHERE id = ?;", (pub_id,))
        assert cursor.fetchone()["status"] == "RECONCILING"
