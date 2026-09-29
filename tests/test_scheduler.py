"""
Testes para o agendador de postagens com buffer anti-spam e janelas horárias.
"""
from datetime import datetime, timezone, timedelta
from src.services.scheduler import generate_idempotency_key, get_next_available_slot, schedule_pending_clips
from src.core.database import get_db

def test_generate_idempotency_key():
    k1 = generate_idempotency_key("clip_001", "youtube", 1)
    k2 = generate_idempotency_key("clip_001", "youtube", 1)
    k3 = generate_idempotency_key("clip_001", "tiktok", 1)

    assert k1 == k2
    assert k1 != k3
    assert len(k1) == 64

def test_scheduler_enqueues_qualified_clips(temp_dir, monkeypatch):
    """Testa enfileiramento de clips aprovados nas janelas corretas."""
    db_file = temp_dir / "sched_test.db"
    from src.database.migrations import run_migrations
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        # Cria vídeo longo fictício
        cursor.execute("INSERT INTO long_videos (file_hash, file_name, file_path, status) VALUES ('h1', 'v.mp4', 'p.mp4', 'COMPLETED');")
        vid_id = cursor.lastrowid

        # Cria clip aprovado com virality_score 85
        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score,
                title, moderation_status, youtube_status, tiktok_status
            ) VALUES (?, 'uid_85', 'c.mp4', 85, '🔥 Titulo Teste #Shorts', 'APPROVED', 'PENDING', 'PENDING');
        """, (vid_id,))

    # Executa o agendador
    count = schedule_pending_clips()
    # Deve agendar para as 2 contas semeadas (1 YouTube e 1 TikTok)
    assert count == 2

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, scheduled_for, idempotency_key FROM publications WHERE clip_id = 1;")
        rows = cursor.fetchall()
        assert len(rows) == 2
        for r in rows:
            assert r["status"] == "SCHEDULED"
            assert r["scheduled_for"] is not None
