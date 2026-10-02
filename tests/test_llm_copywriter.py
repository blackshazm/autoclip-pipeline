"""
Testes para copywriting LLM, validação de schema, sanitização e fallback.
"""
from src.services.llm_copywriter import (
    ClipMetadataOutput,
    sanitize_transcription,
    generate_clip_copy,
    DETERMINISTIC_FALLBACK
)

def test_clip_metadata_schema_valid():
    valid_data = {
        "title": "🔥 O Segredo que Ninguém Te Contou #Shorts",
        "description": "Veja como a IA está transformando o mercado de forma rápida.",
        "tags": ["#shorts", "#ia", "#tecnologia", "#cortes"]
    }
    obj = ClipMetadataOutput(**valid_data)
    assert obj.title.startswith("🔥")
    assert len(obj.tags) == 4

def test_sanitize_transcription_limits_length():
    huge_text = "Palavra " * 500
    cleaned = sanitize_transcription(huge_text)
    assert len(cleaned) <= 2020
    assert cleaned.endswith("... [truncado]")

def test_llm_fallback_on_invalid_endpoint(monkeypatch, temp_dir):
    """Quando o endpoint LLM está offline/inválido, o fallback determinístico deve ser ativado."""
    db_file = temp_dir / "llm_test.db"
    from src.database.migrations import run_migrations
    run_migrations(db_file)

    import src.core.config as cfg
    monkeypatch.setattr(cfg.settings, "DB_PATH", db_file)
    monkeypatch.setattr(cfg.settings, "OPENAI_BASE_URL", "http://localhost:9999/v1") # Porta inexistente
    monkeypatch.setattr(cfg.settings, "LLM_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(cfg.settings, "LLM_MAX_RETRIES", 0)

    result = generate_clip_copy(clip_id=999, transcription="Texto de teste da transcrição")

    assert result["is_fallback"] is True
    assert result["status"] == "FALLBACK"
    assert "title" in result["metadata"]
    assert len(result["metadata"]["tags"]) >= 3
