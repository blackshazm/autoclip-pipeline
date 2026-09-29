"""
Gerenciador de Conexão e Transações SQLite com Modo WAL.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional
import shutil

from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger("database")

def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Cria e configura uma conexão SQLite com modo WAL e foreign keys ativas."""
    target_path = db_path or settings.DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(target_path),
        timeout=60.0
    )
    conn.row_factory = sqlite3.Row

    # Pragmas para máxima resiliência e performance em concorrência
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 60000;")
    except Exception:
        pass

    return conn

@contextmanager
def get_db(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager para operações de banco de dados com commit/rollback automático e retry de busy."""
    import time
    conn = get_connection(db_path)
    try:
        yield conn
        # Retry commit se encontrar locked temporário
        for attempt in range(5):
            try:
                conn.commit()
                break
            except sqlite3.OperationalError as oe:
                if "locked" in str(oe).lower() and attempt < 4:
                    time.sleep(0.5 * (attempt + 1))
                else:
                    raise
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.error(
            f"Erro na transação de banco de dados: {e}",
            extra={"event": "db_transaction_error"}
        )
        raise
    finally:
        conn.close()

def create_online_backup(destination_dir: Optional[Path] = None) -> Path:
    """Realiza backup seguro e quente do SQLite via API oficial de backup."""
    dest_dir = destination_dir or settings.BACKUP_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = dest_dir / f"pipeline_{timestamp}.db"

    source_conn = get_connection()
    try:
        dest_conn = sqlite3.connect(str(backup_file))
        try:
            with dest_conn:
                source_conn.backup(dest_conn, pages=250)
            logger.info(
                f"Backup online do banco concluído em {backup_file}",
                extra={"event": "db_backup_success", "backup_path": str(backup_file)}
            )
            return backup_file
        finally:
            dest_conn.close()
    finally:
        source_conn.close()
