"""
Testes unitários automatizados para o YouTubeBrowserPublisherPro e validações de Payload.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.services.youtube_browser_publisher_pro import YouTubeBrowserPublisherPro, PublishPayloadPro
from src.core.exceptions import YouTubePublishError


def test_extract_video_id():
    """Valida a extração de ID de vídeo a partir de URLs e textos."""
    publisher = YouTubeBrowserPublisherPro()
    assert publisher._extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert publisher._extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert publisher._extract_video_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert publisher._extract_video_id("Texto sem link") is None


def test_payload_pro_defaults(tmp_path):
    """Valida valores padrão e integridade do PublishPayloadPro."""
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_text("dummy", encoding="utf-8")

    payload = PublishPayloadPro(
        video_path=dummy_video,
        title="Meu Short PRO",
        description="Descrição PRO"
    )

    assert payload.category_name == "Entretenimento"
    assert payload.language == "Português (Brasil)"
    assert payload.is_synthetic_ai is False
    assert payload.publish_mode == "PUBLIC"
    assert payload.wait_copyright_checks is True
    assert payload.on_copyright_issue == "UNLISTED"


def test_is_authenticated_pro_logic(tmp_path):
    """Valida verificação de credenciais/perfil no publicador PRO."""
    fake_profile = tmp_path / "fake_profile"
    fake_state = tmp_path / "fake_state.json"

    pub = YouTubeBrowserPublisherPro(profile_dir=fake_profile, state_file=fake_state)
    assert pub.is_authenticated() is False

    fake_state.write_text("{}", encoding="utf-8")
    assert pub.is_authenticated() is True


def test_publish_pro_missing_video(tmp_path):
    """Garante que erro é levantado se o arquivo de vídeo não existir."""
    fake_video = tmp_path / "nao_existe.mp4"
    pub = YouTubeBrowserPublisherPro()
    payload = PublishPayloadPro(
        video_path=fake_video,
        title="Título",
        description="Desc"
    )
    with pytest.raises(YouTubePublishError, match="não encontrado"):
        pub.publish_short_pro(payload)


def test_publish_pro_not_authenticated(tmp_path):
    """Garante erro explicativo se não houver sessão ou perfil autenticado."""
    fake_video = tmp_path / "video.mp4"
    fake_video.write_text("video content", encoding="utf-8")

    empty_profile = tmp_path / "no_profile"
    empty_state = tmp_path / "no_state.json"

    pub = YouTubeBrowserPublisherPro(profile_dir=empty_profile, state_file=empty_state)
    payload = PublishPayloadPro(
        video_path=fake_video,
        title="Título",
        description="Desc"
    )
    with pytest.raises(YouTubePublishError, match="Sessão do YouTube não encontrada"):
        pub.publish_short_pro(payload)


def test_fill_tags_character_limit():
    """Valida que o inseridor de tags respeita o limite seguro de caracteres."""
    publisher = YouTubeBrowserPublisherPro()
    mock_page = MagicMock()
    mock_locator = MagicMock()
    mock_locator.count.return_value = 1
    mock_page.locator.return_value.first = mock_locator

    # Gera 100 tags longas que juntas excederiam 500 caracteres
    tags_longas = [f"taglonga_{i}_{'x'*15}" for i in range(100)]
    added_count = publisher._fill_tags(mock_page, tags_longas)

    # Não deve tentar adicionar todas as 100 tags, pois para antes dos 480 caracteres
    assert added_count < len(tags_longas)
    assert added_count > 0
