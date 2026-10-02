"""
Testes unitários para a garantia de confirmação real de postagem no YouTube e TikTok.
Garante que IDs falsos são rejeitados e que a extração e validação do link é estrita.
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.services.youtube_browser_publisher import YouTubeBrowserPublisher
from src.services.tiktok_browser_publisher import TikTokBrowserPublisher
from src.core.exceptions import YouTubePublishError, TikTokPublishError

def test_youtube_video_id_strict_extraction():
    pub = YouTubeBrowserPublisher()

    # IDs válidos de 11 caracteres
    assert pub._extract_video_id("https://youtu.be/kX3vW3m1234") == "kX3vW3m1234"
    assert pub._extract_video_id("https://www.youtube.com/shorts/abcdef12345") == "abcdef12345"
    assert pub._extract_video_id("https://www.youtube.com/watch?v=0123456789A") == "0123456789A"

    # IDs inválidos ou textos truncados
    assert pub._extract_video_id("") is None
    assert pub._extract_video_id("yt_curto") is None
    assert pub._extract_video_id("https://youtube.com/shorts/") is None

def test_youtube_double_check_live_mock():
    pub = YouTubeBrowserPublisher()

    with patch("requests.get") as mock_get:
        # Mock de vídeo disponível
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>Vídeo oficial em reprodução</body></html>"
        mock_get.return_value = mock_resp

        assert pub._verify_youtube_short_live("abcdef12345") is True

        # Mock de vídeo indisponível
        mock_resp.text = "<html><body>Video unavailable - Este vídeo não está disponível</body></html>"
        assert pub._verify_youtube_short_live("abcdef12345", max_retries=1, delay_sec=0.1) is False

def test_tiktok_caption_formatting():
    pub = TikTokBrowserPublisher()
    caption = pub.format_caption("Corte Viral de Podcasts", ["cortes", "podcast", "viral"])
    assert "Corte Viral de Podcasts" in caption
    assert "#cortes" in caption
    assert "#podcast" in caption
    assert "#viral" in caption
