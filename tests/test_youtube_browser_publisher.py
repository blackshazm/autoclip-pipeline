"""
Testes unitários para o YouTubeBrowserPublisher e o chaveamento em robot2_publish.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.services.youtube_browser_publisher import YouTubeBrowserPublisher
from src.core.exceptions import YouTubePublishError

def test_extract_video_id():
    """Valida a extração de ID de vídeo a partir de URLs ou textos."""
    publisher = YouTubeBrowserPublisher()
    
    assert publisher._extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert publisher._extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert publisher._extract_video_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert publisher._extract_video_id("Texto sem link") is None

def test_is_authenticated_logic(tmp_path):
    """Verifica detecção de autenticação com base no diretório ou arquivo de estado."""
    fake_profile = tmp_path / "fake_profile"
    fake_state = tmp_path / "fake_state.json"

    pub = YouTubeBrowserPublisher(profile_dir=fake_profile, state_file=fake_state)
    assert pub.is_authenticated() is False

    fake_state.write_text("{}", encoding="utf-8")
    assert pub.is_authenticated() is True

def test_publish_short_missing_video(tmp_path):
    """Garante que erro é levantado se arquivo de vídeo não existir."""
    fake_video = tmp_path / "inexistente.mp4"
    pub = YouTubeBrowserPublisher()
    with pytest.raises(YouTubePublishError, match="não encontrado"):
        pub.publish_short(fake_video, "Titulo", "Desc", ["tag"], "clip_1")

def test_publish_short_not_authenticated(tmp_path):
    """Garante que erro é levantado se não houver autenticação/sessão."""
    fake_video = tmp_path / "video.mp4"
    fake_video.write_text("fake video content", encoding="utf-8")

    empty_profile = tmp_path / "no_profile"
    empty_state = tmp_path / "no_state.json"

    pub = YouTubeBrowserPublisher(profile_dir=empty_profile, state_file=empty_state)
    with pytest.raises(YouTubePublishError, match="Sessão do YouTube não encontrada"):
        pub.publish_short(fake_video, "Titulo", "Desc", ["tag"], "clip_1")
