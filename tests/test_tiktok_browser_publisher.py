"""
Testes unitários para o TikTokBrowserPublisher e chaveamento no robot2_publish.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.services.tiktok_browser_publisher import TikTokBrowserPublisher
from src.core.exceptions import TikTokPublishError

def test_format_caption():
    """Valida a formatação de legendas e tags para o TikTok sem termos concorrentes (#shorts)."""
    pub = TikTokBrowserPublisher()
    
    caption = pub.format_caption("Dicas de Produtividade #Shorts", ["foco", "#disciplina", "shorts", "#reels"])
    assert "Dicas de Produtividade" in caption
    assert "#shorts" not in caption.lower()
    assert "#reels" not in caption.lower()
    assert "#foco" in caption
    assert "#disciplina" in caption
    assert "#fyp" in caption  # Injetado automaticamente para alcance orgânico

    # Limite máximo de caracteres
    long_title = "A" * 3000
    trimmed = pub.format_caption(long_title, ["tag1"], max_len=100)
    assert len(trimmed) <= 100

def test_is_authenticated_logic(tmp_path):
    """Verifica detecção de autenticação com base no diretório ou arquivo de estado."""
    fake_profile = tmp_path / "fake_profile"
    fake_state = tmp_path / "fake_state.json"

    pub = TikTokBrowserPublisher(profile_dir=fake_profile, state_file=fake_state)
    assert pub.is_authenticated() is False

    fake_state.write_text("{}", encoding="utf-8")
    assert pub.is_authenticated() is True

def test_publish_video_missing_file(tmp_path):
    """Garante que erro é levantado se o arquivo de vídeo não existir."""
    fake_video = tmp_path / "inexistente.mp4"
    pub = TikTokBrowserPublisher()
    with pytest.raises(TikTokPublishError, match="não encontrado"):
        pub.publish_video(fake_video, "Titulo", ["tag"], "clip_1")

def test_publish_video_not_authenticated(tmp_path):
    """Garante que erro é levantado se não houver autenticação ou sessão."""
    fake_video = tmp_path / "video.mp4"
    fake_video.write_text("fake video content", encoding="utf-8")

    empty_profile = tmp_path / "no_profile"
    empty_state = tmp_path / "no_state.json"

    pub = TikTokBrowserPublisher(profile_dir=empty_profile, state_file=empty_state)
    with pytest.raises(TikTokPublishError, match="Sessão do TikTok não encontrada"):
        pub.publish_video(fake_video, "Titulo", ["tag"], "clip_1")
