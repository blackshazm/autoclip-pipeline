"""
Testes para as rotas e serviços de Gerenciamento de Canais do Radar.
"""

import pytest
from fastapi.testclient import TestClient
from src.web.app import app
from src.core.database import get_db
from src.services.channel_manager import list_source_channels, toggle_channel_status, add_source_channel
from scripts.cadastrar_canais_noticias import cadastrar_canais

@pytest.fixture
def client():
    return TestClient(app)

def test_list_and_seed_news_channels(client):
    """Testa cadastro e listagem de canais de notícias via script e API."""
    # Executa o cadastro dos canais de notícias no banco isolado de teste
    cadastrar_canais()

    res = client.get("/api/channels")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert isinstance(data["channels"], list)
    assert len(data["channels"]) >= 7

    names = [c["name"] for c in data["channels"]]
    assert any("CNN Brasil" in n for n in names)
    assert any("Band Jornalismo" in n for n in names)
    assert any("SBT News" in n for n in names)
    assert any("Record News" in n for n in names)
    assert any("GloboNews" in n or "g1" in n for n in names)

    # Verifica nicho atribuído
    cnn = next(c for c in data["channels"] if "CNN" in c["name"])
    assert cnn["niche"] == "financas"
    assert cnn["active"] == 1
    assert cnn["min_duration_minutes"] == 8

def test_toggle_channel(client):
    """Testa alternar o status ativo/pausado de um canal."""
    cadastrar_canais()
    channels = list_source_channels()
    assert len(channels) > 0
    test_ch = channels[0]
    initial_active = test_ch["active"]

    # Toggle via API
    res = client.post(f"/api/channels/{test_ch['id']}/toggle")
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Verifica se inverteu
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT active FROM source_channels WHERE id = ?;", (test_ch["id"],))
        updated_active = cur.fetchone()["active"]
    assert updated_active != initial_active

def test_create_channel_validation(client):
    """Testa rota de adicionar canal com validação."""
    # Identifier inválido
    res = client.post("/api/channels", json={"identifier": "", "niche": "financas"})
    assert res.status_code == 400
