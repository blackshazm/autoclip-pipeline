"""
Fixtures compartilhadas para testes automatizados com banco isolado e mocks.
"""
import pytest
import sqlite3
from pathlib import Path
import tempfile
import shutil

from src.database.migrations import run_migrations
from src.core.config import settings

@pytest.fixture
def temp_dir():
    """Diretório temporário isolado para testes com arquivos e mídias."""
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def test_db(temp_dir):
    """Cria um banco SQLite temporário com schema e seeds aplicados."""
    db_file = temp_dir / "test_pipeline.db"
    run_migrations(db_file)
    return db_file
