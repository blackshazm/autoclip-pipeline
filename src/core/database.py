"""
Gerenciador de Conexão e Transações SQLite com Modo WAL.
"""
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional
import shutil

from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger("database")

# Número máximo de tentativas e backoff para operações com database locked
_LOCK_MAX_RETRIES = 8
_LOCK_BASE_DELAY = 0.25  # segundos

def _execute_with_retry(fn, label: str = ""):
    """Executa fn() com backoff exponencial em caso de OperationalError: database is locked."""
    for attempt in range(_LOCK_MAX_RETRIES):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < _LOCK_MAX_RETRIES - 1:
                delay = _LOCK_BASE_DELAY * (2 ** attempt)
                logger.debug(f"DB locked ({label}), aguardando {delay:.2f}s (tentativa {attempt + 1}/{_LOCK_MAX_RETRIES})")
                time.sleep(delay)
            else:
                raise

def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Cria e configura uma conexão SQLite com modo WAL e foreign keys ativas."""
    target_path = db_path or settings.DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # timeout=120s: Python aguarda lock em nível de API antes de lançar exceção
    conn = sqlite3.connect(
        str(target_path),
        timeout=120.0,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row

    # Pragmas para máxima resiliência e performance em concorrência
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 120000;")  # 2 min timeout no nível SQLite
        conn.execute("PRAGMA wal_autocheckpoint = 1000;")
    except Exception:
        pass

    return conn

@contextmanager
def get_db(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager para operações de banco de dados com commit/rollback automático e retry de busy."""
    conn = get_connection(db_path)
    try:
        yield conn
        # Retry commit com backoff exponencial
        _execute_with_retry(conn.commit, label="commit")
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
