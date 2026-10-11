"""
Testes unitários para validação do roteamento estrito por nicho no agendador de publicações.
"""
import sqlite3
import json
from unittest.mock import patch
from datetime import datetime, timezone

from src.services.scheduler import schedule_pending_clips

def setup_test_db(conn: sqlite3.Connection):
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE source_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            niche TEXT,
            active INTEGER DEFAULT 1
        );

        CREATE TABLE long_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_channel_id INTEGER REFERENCES source_channels(id)
        );

        CREATE TABLE clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            long_video_id INTEGER REFERENCES long_videos(id),
            clip_uid TEXT UNIQUE,
            virality_score INTEGER,
            moderation_status TEXT DEFAULT 'APPROVED',
            title TEXT,
            start_seconds REAL DEFAULT 0.0,
            end_seconds REAL DEFAULT 30.0,
            duration_seconds REAL DEFAULT 30.0,
            series_id TEXT,
            part_number INTEGER DEFAULT 1,
            total_parts INTEGER DEFAULT 1,
            youtube_status TEXT DEFAULT 'PENDING',
            tiktok_status TEXT DEFAULT 'PENDING',
            scheduled_for TEXT,
            error_log TEXT,
            created_at TEXT DEFAULT '2026-10-08T12:00:00Z'
        );

        CREATE TABLE publishing_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,
            profile_name TEXT UNIQUE,
            niche TEXT,
            timezone TEXT DEFAULT 'America/Sao_Paulo',
            posting_windows TEXT DEFAULT '["12:00","18:00"]',
            min_interval_minutes INTEGER DEFAULT 60,
            max_daily_posts INTEGER DEFAULT 6,
            active INTEGER DEFAULT 1
        );

        CREATE TABLE publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clip_id INTEGER REFERENCES clips(id),
            publishing_account_id INTEGER REFERENCES publishing_accounts(id),
            platform TEXT,
            status TEXT DEFAULT 'SCHEDULED',
            scheduled_for TEXT,
            idempotency_key TEXT UNIQUE
        );
    """)

    # 1. Configura Canais Fontes (Fitness e Finanças)
    cursor.execute("INSERT INTO source_channels (id, name, niche) VALUES (1, 'Ironberg Podcast', 'fitness');")
    cursor.execute("INSERT INTO source_channels (id, name, niche) VALUES (2, 'PrimoCast', 'financas');")

    # 2. Configura Vídeos Longos
    cursor.execute("INSERT INTO long_videos (id, source_channel_id) VALUES (10, 1);")
    cursor.execute("INSERT INTO long_videos (id, source_channel_id) VALUES (20, 2);")

    # 3. Configura Contas de Publicação
    cursor.execute("INSERT INTO publishing_accounts (id, platform, profile_name, niche) VALUES (1, 'youtube', 'yt_fitness', 'fitness');")
    cursor.execute("INSERT INTO publishing_accounts (id, platform, profile_name, niche) VALUES (2, 'tiktok', 'tk_fitness', 'fitness');")
    cursor.execute("INSERT INTO publishing_accounts (id, platform, profile_name, niche) VALUES (3, 'youtube', 'yt_financas', 'financas');")
    cursor.execute("INSERT INTO publishing_accounts (id, platform, profile_name, niche) VALUES (4, 'tiktok', 'tk_financas', 'financas');")

    # 4. Configura Clips Aprovados
    cursor.execute("""
        INSERT INTO clips (id, long_video_id, clip_uid, virality_score, moderation_status, title)
        VALUES (101, 10, 'clip_fit_01', 85, 'APPROVED', '🔥 Segredo do Shape');
    """)
    cursor.execute("""
        INSERT INTO clips (id, long_video_id, clip_uid, virality_score, moderation_status, title)
        VALUES (201, 20, 'clip_fin_01', 90, 'APPROVED', '💵 Como Investir em 2026');
    """)

    conn.commit()

def test_scheduler_strictly_routes_by_niche():
    conn = sqlite3.connect(":memory:")
    setup_test_db(conn)

    with patch("src.services.scheduler.get_db") as mock_get_db:
        # Context manager mock para reutilizar a mesma conexão em memória
        from contextlib import contextmanager
        @contextmanager
        def _get_mock_db():
            yield conn
        mock_get_db.side_effect = _get_mock_db

        enqueued = schedule_pending_clips()
        assert enqueued == 4, f"Esperado 4 publicações agendadas (2 fitness + 2 finanças), obtido {enqueued}"

        cursor = conn.cursor()
        
        # Publicações do Clip de Fitness (ID 101)
        cursor.execute("""
            SELECT p.platform, pa.profile_name, pa.niche
            FROM publications p
            JOIN publishing_accounts pa ON p.publishing_account_id = pa.id
            WHERE p.clip_id = 101;
        """)
        fit_pubs = [dict(r) for r in cursor.fetchall()]
        assert len(fit_pubs) == 2
        for pub in fit_pubs:
            assert pub["niche"] == "fitness", f"Corte de fitness agendado para nicho incorreto: {pub}"
            assert pub["profile_name"] in ("yt_fitness", "tk_fitness")

        # Publicações do Clip de Finanças (ID 201)
        cursor.execute("""
            SELECT p.platform, pa.profile_name, pa.niche
            FROM publications p
            JOIN publishing_accounts pa ON p.publishing_account_id = pa.id
            WHERE p.clip_id = 201;
        """)
        fin_pubs = [dict(r) for r in cursor.fetchall()]
        assert len(fin_pubs) == 2
        for pub in fin_pubs:
            assert pub["niche"] == "financas", f"Corte de finanças agendado para nicho incorreto: {pub}"
            assert pub["profile_name"] in ("yt_financas", "tk_financas")
