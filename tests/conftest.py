"""
Fixtures compartilhadas para testes automatizados com banco isolado e mocks.
"""
import pytest
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import sqlite3
from pathlib import Path
import tempfile
import shutil
import sys, os
# Adiciona diretório raiz ao sys.path para permitir importação de pacotes src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database.migrations import run_migrations
from src.core.config import settings

@pytest.fixture
def temp_dir():
    """Diretório temporário isolado para testes com arquivos e mídias."""
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)

@pytest.fixture(autouse=True)
def isolate_db_for_all_tests(temp_dir, monkeypatch):
    """Garante isolamento absoluto: todo teste roda em banco temporário com migrações aplicadas."""
    db_file = temp_dir / "isolated_test_pipeline.db"
    run_migrations(db_file)
    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)
    yield db_file

@pytest.fixture
def test_db(isolate_db_for_all_tests):
    """Retorna o caminho do banco SQLite isolado."""
    return isolate_db_for_all_tests
