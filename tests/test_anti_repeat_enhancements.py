"""
Testes específicos para os aprimoramentos anti-repetição e anti-overlap histórico.
"""
from datetime import datetime, timezone, timedelta
from src.services.overlap_filter import filter_against_database, filter_overlapping_clips
from src.services.scheduler import get_next_available_slot, schedule_pending_clips
from src.core.database import get_db

def test_filter_against_database_blocks_historical_overlap(temp_dir, monkeypatch):
    """Garante que um corte novo que sobrepõe um corte histórico já aprovado no banco seja descartado."""
    db_file = temp_dir / "anti_repeat_test.db"
    from src.database.migrations import run_migrations
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO long_videos (file_hash, file_name, file_path, status) VALUES ('h_anti', 'v.mp4', 'p.mp4', 'COMPLETED');")
        vid_id = cursor.lastrowid

        # Clip 1: Corte antigo já aprovado e postado (00:10 a 00:40)
        cursor.execute("""
            INSERT INTO clips (
                long_video_id, clip_uid, file_path, virality_score,
                start_seconds, end_seconds, duration_seconds,
                title, moderation_status, youtube_status, tiktok_status
            ) VALUES (?, 'hist_01', 'c1.mp4', 85, '00:10', '00:40', 30.0,
                     '🔥 Primeiro Corte', 'APPROVED', 'POSTED', 'POSTED');
        """, (vid_id,))

    # Novo corte candidato com 90% de sobreposição (00:15 a 00:40)
    candidate_clips = [{
        "id": 999,
        "clip_uid": "cand_02",
        "long_video_id": vid_id,
        "start_seconds": "00:15",
        "end_seconds": "00:40",
        "duration_seconds": 25.0,
        "virality_score": 90
    }]

    with get_db(db_file) as conn:
        kept, discarded = filter_against_database(candidate_clips, conn=conn, max_overlap_threshold=0.25)

    assert len(kept) == 0
    assert len(discarded) == 1
    assert "Sobreposição" in discarded[0]["_overlap_reason"]

def test_same_video_slot_spacing(temp_dir, monkeypatch):
    """Testa que cortes do mesmo vídeo longo respeitam o espaçamento mínimo anti-rajada."""
    db_file = temp_dir / "spacing_test.db"
    from src.database.migrations import run_migrations
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)
    monkeypatch.setattr(cfg.settings, "POST_INTERVAL_MINUTES", 15)
    monkeypatch.setattr(cfg.settings, "MIN_SAME_VIDEO_INTERVAL_MINUTES", 120)

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO long_videos (file_hash, file_name, file_path, status) VALUES ('h_sp', 'v.mp4', 'p.mp4', 'COMPLETED');")
        vid_id = cursor.lastrowid

        # Clip A já agendado para as 10:00 UTC
        base_sched = datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc)
        cursor.execute("""
            INSERT INTO clips (id, long_video_id, clip_uid, file_path, virality_score, moderation_status, youtube_status)
            VALUES (101, ?, 'uid_a', 'a.mp4', 80, 'APPROVED', 'SCHEDULED');
        """, (vid_id,))
        cursor.execute("""
            INSERT INTO publications (clip_id, publishing_account_id, platform, status, scheduled_for, idempotency_key)
            VALUES (101, 1, 'youtube', 'SCHEDULED', ?, 'key_a');
        """, (base_sched.isoformat(),))

        # Calcula o próximo slot para outro corte do MESMO vídeo
        slot_same_video = get_next_available_slot(1, "youtube", conn, long_video_id=vid_id)

        # O slot para o mesmo vídeo deve ser de pelo menos 120 minutos após base_sched
        assert slot_same_video >= base_sched + timedelta(minutes=119)
