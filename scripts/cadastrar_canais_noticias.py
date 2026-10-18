"""
Script de Cadastro e Ativação de Canais de Notícias (Globo, SBT, Record, Band, CNN).
Cadastra canais oficiais de notícias e jornalismo voltados para o nicho de negócios e atualidades.
"""

import sys
import sqlite3
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.core.config import settings
DB_PATH = settings.DB_PATH

CANAIS_NOTICIAS = [
    {
        "youtube_channel_id": "UCvdwhh_fDyWccR42-rReZLw",
        "name": "CNN Brasil",
        "handle": "@CNNbrasil",
        "min_duration": 8,
        "vph_threshold": 2000,
        "multiplier_threshold": 1.8,
        "median_vph": 1500.0,
        "niche": "financas",
        "description": "Notícias ao vivo, economia, negócios, política e debates aprofundados."
    },
    {
        "youtube_channel_id": "UCoa-D_VfMkFrCYodrOC9-mA",
        "name": "Band Jornalismo",
        "handle": "@BandJornalismo",
        "min_duration": 8,
        "vph_threshold": 2000,
        "multiplier_threshold": 1.8,
        "median_vph": 1500.0,
        "niche": "financas",
        "description": "Jornalismo da Band, Jornal da Band, Linha de Frente e análises de economia."
    },
    {
        "youtube_channel_id": "UC376n347Ob5Lwzq2WGzF1AA",
        "name": "SBT News",
        "handle": "@SBTNews",
        "min_duration": 8,
        "vph_threshold": 2000,
        "multiplier_threshold": 1.8,
        "median_vph": 1200.0,
        "niche": "financas",
        "description": "Cobertura jornalística 24 horas do SBT, política, mercado e reportagens."
    },
    {
        "youtube_channel_id": "UCuiLR4p6wQ3xLEm15pEn1Xw",
        "name": "Record News",
        "handle": "@recordnews",
        "min_duration": 8,
        "vph_threshold": 2000,
        "multiplier_threshold": 1.8,
        "median_vph": 1500.0,
        "niche": "financas",
        "description": "Canal de notícias 24 horas da Record, entrevistas e boletins de negócios."
    },
    {
        "youtube_channel_id": "UCmpHPgeCBgvk_fDXZQKsnAA",
        "name": "Jornal da Record",
        "handle": "@jornaldarecord",
        "min_duration": 10,
        "vph_threshold": 2500,
        "multiplier_threshold": 1.8,
        "median_vph": 2000.0,
        "niche": "financas",
        "description": "Edições e reportagens investigativas principais da Record."
    },
    {
        "youtube_channel_id": "UCp6RRaz93Pt2xYZoEye_rLA",
        "name": "GloboNews",
        "handle": "@globonews",
        "min_duration": 8,
        "vph_threshold": 2000,
        "multiplier_threshold": 1.8,
        "median_vph": 1800.0,
        "niche": "financas",
        "description": "Canal 24 horas da Globo, cobertura de mercado, política e entrevistas."
    },
    {
        "youtube_channel_id": "UCaGmdJSSiR7fkh2A-c6emsA",
        "name": "g1",
        "handle": "@g1globo",
        "min_duration": 6,
        "vph_threshold": 2500,
        "multiplier_threshold": 1.8,
        "median_vph": 2000.0,
        "niche": "financas",
        "description": "Portal de notícias e reportagens em vídeo do Grupo Globo."
    },
]


def cadastrar_canais(niche_override: str = None, dry_run: bool = False, db_path: Path = None):
    active_db = Path(db_path) if db_path else settings.DB_PATH
    print("=" * 70)
    print("📺 CADASTRO DE CANAIS DE NOTÍCIAS NO RADAR")
    print(f"Banco de dados: {active_db}")
    print(f"Modo: {'[SIMULAÇÃO / DRY-RUN]' if dry_run else '[EXECUÇÃO REAL]'}")
    print("=" * 70)

    if not active_db.exists():
        print(f"❌ Banco {active_db} não encontrado!")
        sys.exit(1)

    conn = sqlite3.connect(str(active_db))
    cursor = conn.cursor()

    try:
        # Garante colunas necessárias
        cursor.execute("PRAGMA table_info(source_channels);")
        cols = [c[1] for c in cursor.fetchall()]
        if "niche" not in cols:
            cursor.execute("ALTER TABLE source_channels ADD COLUMN niche TEXT DEFAULT 'general';")
        if "max_videos_per_cycle" not in cols:
            cursor.execute("ALTER TABLE source_channels ADD COLUMN max_videos_per_cycle INTEGER DEFAULT 3;")

        cadastrados = 0
        for ch in CANAIS_NOTICIAS:
            target_niche = niche_override or ch["niche"]
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['youtube_channel_id']}"
            
            print(f"[+] Canal: {ch['name']:<18} ({ch['handle']}) -> Nicho: {target_niche}")
            print(f"    ID: {ch['youtube_channel_id']} | Min Dur: {ch['min_duration']}m | VPH Threshold: {ch['vph_threshold']}")
            
            if not dry_run:
                cursor.execute("""
                    INSERT INTO source_channels (
                        youtube_channel_id, name, rss_url, active,
                        min_duration_minutes, vph_absolute_threshold,
                        vph_multiplier_threshold, median_vph, license_mode,
                        max_videos_per_cycle, niche
                    ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, 'owned', 3, ?)
                    ON CONFLICT(youtube_channel_id) DO UPDATE SET
                        name = excluded.name,
                        rss_url = excluded.rss_url,
                        active = 1,
                        min_duration_minutes = excluded.min_duration_minutes,
                        vph_absolute_threshold = excluded.vph_absolute_threshold,
                        vph_multiplier_threshold = excluded.vph_multiplier_threshold,
                        median_vph = excluded.median_vph,
                        max_videos_per_cycle = excluded.max_videos_per_cycle,
                        niche = excluded.niche,
                        updated_at = datetime('now');
                """, (
                    ch["youtube_channel_id"],
                    ch["name"],
                    rss_url,
                    ch["min_duration"],
                    ch["vph_threshold"],
                    ch["multiplier_threshold"],
                    ch["median_vph"],
                    target_niche,
                ))
                cadastrados += 1

        if not dry_run:
            conn.commit()

        print("=" * 70)
        print(f"✅ {cadastrados if not dry_run else len(CANAIS_NOTICIAS)} canais de notícias {'salvos' if not dry_run else 'analisados'} com sucesso!")
        print("=" * 70)

        # Exibe lista de todos os canais ativos no Radar
        cursor.execute("SELECT id, name, youtube_channel_id, niche, min_duration_minutes, vph_absolute_threshold, active FROM source_channels WHERE active = 1 ORDER BY niche ASC, id ASC;")
        ativos = cursor.fetchall()
        print("\n📋 Canais Ativos Atualmente no Radar:")
        for row in ativos:
            print(f"  - [{row[3].upper()}] #{row[0]} {row[1]:<20} (ID: {row[2]}) | Min: {row[4]}m | VPH: {row[5]}")

    except Exception as e:
        conn.rollback()
        print(f"❌ Erro ao cadastrar canais: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cadastra canais de notícias oficiais no Radar")
    parser.add_argument("--niche", type=str, default=None, help="Sobrescrever nicho dos canais (ex: financas, noticias)")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem gravar no banco de dados")
    args = parser.parse_args()

    cadastrar_canais(niche_override=args.niche, dry_run=args.dry_run)
