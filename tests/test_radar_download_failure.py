"""
Testes de resiliência do Radar do YouTube contra falhas de download.
"""
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from src.core.database import get_db
import src.radar_youtube as radar

def test_radar_marks_candidate_as_error_on_download_failure(temp_dir, monkeypatch):
    """Testa se candidato qualificado cujo download retorna None é marcado com status ERROR."""
    db_file = temp_dir / "radar_dl_fail_test.db"
    from src.database.migrations import run_migrations
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)
    monkeypatch.setattr(cfg.settings, "RADAR_DISABLE_HYPE_FILTERS", True)

    with get_db(db_file) as conn:
        cursor = conn.cursor()
        # Canal ativo
        cursor.execute("SELECT id, youtube_channel_id FROM source_channels LIMIT 1;")
        ch_row = cursor.fetchone()
        channel_id = ch_row["id"]
        ch_yt_id = ch_row["youtube_channel_id"]

        # Insere candidato qualificado sem download
        cursor.execute("""
            INSERT INTO radar_candidates (
                source_channel_id, youtube_id, title, published_at, status, qualified_at
            ) VALUES (?, 'yt_fail_01', 'Vídeo com Download Falhado', datetime('now'), 'QUALIFIED', datetime('now'));
        """, (channel_id,))

    # Mock do feed e do download retornando None (falha)
    fake_entries = [{"youtube_id": "yt_fail_01", "title": "Vídeo com Download Falhado", "published_at": ""}]
    
    with patch("src.radar_youtube.fetch_channel_feed", return_value=fake_entries):
        with patch("src.radar_youtube.download_youtube_video", return_value=None):
            result = radar.run_radar_cycle(dry_run=False)

    # Verifica se o candidato foi marcado como ERROR e não ficou preso em QUALIFIED
    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, reject_reason FROM radar_candidates WHERE youtube_id = 'yt_fail_01';")
        cand_row = cursor.fetchone()
        assert cand_row["status"] == "ERROR"
        assert "Falha no download" in cand_row["reject_reason"]
