"""
Gerenciador de Migrações e Inicialização do Banco de Dados.
"""
from pathlib import Path
from typing import Optional
import sqlite3

from src.core.config import settings
from src.core.database import get_db
from src.core.logger import get_logger

logger = get_logger("migrations")

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

def run_migrations(db_path: Optional[Path] = None) -> None:
    """Aplica o schema DDL e registra a migração se ainda não aplicada."""
    logger.info("Iniciando verificação e aplicação de migrações...", extra={"event": "migration_start"})
    
    with get_db(db_path) as conn:
        # 1. Executa o DDL completo
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            ddl_script = f.read()

        conn.executescript(ddl_script)

        # 2. Registra na tabela schema_migrations
        migration_version = "v1.0.0_initial_consolidated_schema"
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM schema_migrations WHERE version = ?", (migration_version,))
        row = cursor.fetchone()

        if not row:
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (?)", (migration_version,))
            logger.info(
                f"Migração {migration_version} registrada com sucesso.",
                extra={"event": "migration_applied", "version": migration_version}
            )
        else:
            logger.info(
                f"Migração {migration_version} já se encontra aplicada.",
                extra={"event": "migration_already_applied", "version": migration_version}
            )

        # 3. Seed inicial de Contas de Publicação (YouTube e TikTok default)
        cursor.execute("SELECT COUNT(*) as cnt FROM publishing_accounts")
        if cursor.fetchone()["cnt"] == 0:
            cursor.execute("""
                INSERT INTO publishing_accounts (platform, profile_name, display_name, credentials_ref, timezone, min_interval_minutes, max_daily_posts)
                VALUES 
                ('youtube', 'default_youtube', 'Canal Principal YouTube', 'config/youtube_token.json', 'America/Sao_Paulo', 180, 6),
                ('tiktok', 'default_tiktok', 'Perfil Principal TikTok', 'config/tiktok_token.json', 'America/Sao_Paulo', 180, 6);
            """)
            logger.info("Contas de publicação padrão semeadas.", extra={"event": "seed_publishing_accounts"})

        # 4. Seed de Canal Monitorado de Demonstração (caso tabela esteja vazia)
        cursor.execute("SELECT COUNT(*) as cnt FROM source_channels")
        if cursor.fetchone()["cnt"] == 0:
            cursor.execute("""
                INSERT INTO source_channels (youtube_channel_id, name, rss_url, min_duration_minutes, vph_absolute_threshold, vph_multiplier_threshold, median_vph, license_mode)
                VALUES 
                ('UC_x5XG1OV2P6uZZ5FSM9Ttw', 'Google Developers (Exemplo)', 'https://www.youtube.com/feeds/videos.xml?channel_id=UC_x5XG1OV2P6uZZ5FSM9Ttw', 10, 1000, 1.5, 500, 'owned');
            """)
            logger.info("Canal de exemplo semeado em source_channels.", extra={"event": "seed_source_channels"})

    logger.info("Migrações concluídas com sucesso.", extra={"event": "migration_completed"})

if __name__ == "__main__":
    run_migrations()
