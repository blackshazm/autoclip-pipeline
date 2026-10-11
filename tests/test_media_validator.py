"""
Testes unitários para o validador de mídia (src/services/media_validator.py).
"""
import pytest
from pathlib import Path
from src.services.media_validator import inspect_media_file, is_video_entirely_black, verify_media_integrity
from src.core.exceptions import MediaValidationError

def test_verify_media_integrity_nonexistent_or_empty(tmp_path):
    # Arquivo não existente
    assert verify_media_integrity(tmp_path / "non_existent.mp4") is False

    # Arquivo de 0 bytes
    empty_file = tmp_path / "empty.mp4"
    empty_file.touch()
    assert verify_media_integrity(empty_file) is False

def test_inspect_media_file_nonexistent_or_empty(tmp_path):
    with pytest.raises(MediaValidationError, match="não existe ou está vazio"):
        inspect_media_file(tmp_path / "missing.mp4")

    empty = tmp_path / "empty.mp4"
    empty.touch()
    with pytest.raises(MediaValidationError, match="não existe ou está vazio"):
        inspect_media_file(empty)

def test_is_video_entirely_black_empty(tmp_path):
    assert is_video_entirely_black(tmp_path / "missing.mp4") is True
    empty = tmp_path / "empty.mp4"
    empty.touch()
    assert is_video_entirely_black(empty) is True

def test_verify_media_integrity_missing_binary(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"DUMMY_DATA")

    import subprocess
    def mock_missing_ffmpeg(*a, **k):
        raise FileNotFoundError("ffmpeg not installed")

    monkeypatch.setattr(subprocess, "run", mock_missing_ffmpeg)
    assert verify_media_integrity(video) is False
