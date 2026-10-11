"""
Script de migração para suporte à arquitetura multi-nicho (Fitness & Finanças).
Adiciona colunas 'niche' e cadastra canais de origem e contas de publicação isoladas.
"""
import sys
import sqlite3
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "pipeline.db"

def migrate():
    print("=" * 65)
    print("🚀 INICIANDO MIGRAÇÃO MULTI-NICHO (FITNESS & FINANÇAS)")
    print(f"Banco: {DB_PATH}")
    print("=" * 65)

    if not DB_PATH.exists():
        print(f"❌ Banco {DB_PATH} não encontrado!")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        # 1. Adicionar coluna niche em source_channels se não existir
        cursor.execute("PRAGMA table_info(source_channels);")
        sc_cols = [c[1] for c in cursor.fetchall()]
        if "niche" not in sc_cols:
            print("[+] Adicionando coluna 'niche' em source_channels...")
            cursor.execute("ALTER TABLE source_channels ADD COLUMN niche TEXT DEFAULT 'general';")
        else:
            print("[✓] Coluna 'niche' já existe em source_channels.")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_channels_niche ON source_channels(niche);")

        # 2. Adicionar coluna niche em publishing_accounts se não existir
        cursor.execute("PRAGMA table_info(publishing_accounts);")
        pa_cols = [c[1] for c in cursor.fetchall()]
        if "niche" not in pa_cols:
            print("[+] Adicionando coluna 'niche' em publishing_accounts...")
            cursor.execute("ALTER TABLE publishing_accounts ADD COLUMN niche TEXT DEFAULT 'general';")
        else:
            print("[✓] Coluna 'niche' já existe em publishing_accounts.")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_publishing_accounts_niche ON publishing_accounts(niche);")

        # 3. Categorizar canais existentes
        print("[+] Atualizando classificação dos canais existentes...")
        cursor.execute("UPDATE source_channels SET niche = 'fitness', active = 1 WHERE name LIKE '%Ironberg%';")
        cursor.execute("UPDATE source_channels SET niche = 'financas', active = 1 WHERE name LIKE '%PrimoCast%';")
        cursor.execute("""
            UPDATE source_channels 
            SET niche = 'entretenimento', active = 0 
            WHERE name NOT LIKE '%Ironberg%' AND name NOT LIKE '%PrimoCast%';
        """)

        # 4. Inserir novos canais de Fitness e Finanças
        novos_canais = [
            # Fitness
            (
                "UCW8w8qOEKr_f1N6fEF13vxQ",
                "Monster Cast",
                "https://www.youtube.com/feeds/videos.xml?channel_id=UCW8w8qOEKr_f1N6fEF13vxQ",
                1, 20, 3000, 1.8, 1200.0, "owned", 3, "fitness"
            ),
            (
                "UCPX0gLduKAfgr-HJENa7CFw",
                "Renato Cariani",
                "https://www.youtube.com/feeds/videos.xml?channel_id=UCPX0gLduKAfgr-HJENa7CFw",
                1, 15, 6000, 2.0, 2500.0, "owned", 3, "fitness"
            ),
            # Finanças / Negócios / Mentalidade
            (
                "UCK8ahNLOL8APKU9zDM4Wa3w",
                "KIWIcast",
                "https://www.youtube.com/feeds/videos.xml?channel_id=UCK8ahNLOL8APKU9zDM4Wa3w",
                1, 20, 3500, 2.0, 1500.0, "owned", 3, "financas"
            ),
            (
                "UCzJPdSTGj7KPZLjaOatWS4A",
                "Os Sócios Podcast",
                "https://www.youtube.com/feeds/videos.xml?channel_id=UCzJPdSTGj7KPZLjaOatWS4A",
                1, 25, 4000, 2.0, 1800.0, "owned", 3, "financas"
            ),
            (
                "UCH66qm2YR85-_7BBzvsI5Ig",
                "Jota Jota Podcast",
                "https://www.youtube.com/feeds/videos.xml?channel_id=UCH66qm2YR85-_7BBzvsI5Ig",
                1, 20, 3000, 1.8, 1400.0, "owned", 3, "financas"
            ),
        ]

        for yt_id, name, rss, active, min_dur, vph_abs, vph_mult, med_vph, lic, max_v, niche in novos_canais:
            cursor.execute("""
                INSERT INTO source_channels (
                    youtube_channel_id, name, rss_url, active, min_duration_minutes,
                    vph_absolute_threshold, vph_multiplier_threshold, median_vph,
                    license_mode, max_videos_per_cycle, niche
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(youtube_channel_id) DO UPDATE SET
                    name = excluded.name,
                    rss_url = excluded.rss_url,
                    niche = excluded.niche,
                    active = excluded.active;
            """, (yt_id, name, rss, active, min_dur, vph_abs, vph_mult, med_vph, lic, max_v, niche))
            print(f"[✓] Canal configurado: {name} ({niche})")

        # 5. Configurar contas de destino em publishing_accounts
        print("[+] Configurando contas de destino por nicho...")
        cursor.execute("UPDATE publishing_accounts SET active = 0 WHERE profile_name IN ('default_youtube', 'default_tiktok');")

        contas = [
            # Fitness
            (
                "youtube", "yt_fitness", "YouTube Shorts - Fitness",
                "config/youtube_fitness_state.json", '["11:30","15:00","18:30","21:30"]', 180, 6, "fitness", 1
            ),
            (
                "tiktok", "tk_fitness", "TikTok - Fitness",
                "config/tiktok_fitness_state.json", '["12:00","15:30","19:00","22:00"]', 180, 6, "fitness", 1
            ),
            # Finanças
            (
                "youtube", "yt_financas", "YouTube Shorts - Finanças",
                "config/youtube_financas_state.json", '["11:30","15:00","18:30","21:30"]', 180, 6, "financas", 1
            ),
            (
                "tiktok", "tk_financas", "TikTok - Finanças",
                "config/tiktok_financas_state.json", '["12:00","15:30","19:00","22:00"]', 180, 6, "financas", 1
            ),
        ]

        for plat, prof, disp, cred, win, min_int, max_posts, niche, active in contas:
            cursor.execute("""
                INSERT INTO publishing_accounts (
                    platform, profile_name, display_name, credentials_ref,
                    posting_windows, min_interval_minutes, max_daily_posts, niche, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_name) DO UPDATE SET
                    display_name = excluded.display_name,
                    credentials_ref = excluded.credentials_ref,
                    niche = excluded.niche,
                    active = excluded.active;
            """, (plat, prof, disp, cred, win, min_int, max_posts, niche, active))
            print(f"[✓] Conta configurada: {prof} ({plat} - {niche})")

        conn.commit()
        print("=" * 65)
        print("✅ MIGRAÇÃO MULTI-NICHO CONCLUÍDA COM SUCESSO!")
        print("=" * 65)

    except Exception as e:
        conn.rollback()
        print(f"❌ Erro durante a migração: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
