import subprocess
from pathlib import Path
import pytest
from src.services.smart_reframe import (
    detect_speaker_count,
    build_reframe_filter,
    apply_smart_reframe,
)
from src.services.media_validator import inspect_media_file, verify_media_integrity


def test_detect_speaker_count_invalid_file(tmp_path):
    fake = tmp_path / "nao_existe.mp4"
    assert detect_speaker_count(fake) == 1


def test_build_reframe_filter_modes():
    filter_fit = build_reframe_filter("blurred_fit", 1920, 1080)
    assert "boxblur=25:5" in filter_fit
    assert "scale=1080:608" in filter_fit

    filter_headroom = build_reframe_filter("headroom", 1920, 1080, headroom_ratio=0.20)
    assert "boxblur=25:5" in filter_headroom
    assert "overlay=(W-w)/2:220" in filter_headroom


def test_apply_smart_reframe_synthetic_video(tmp_path):
    sample = tmp_path / "sample_16_9.mp4"

    # Gera vídeo horizontal 16:9 (640x360, 2 segundos)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(sample)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    assert sample.exists()

    # Aplica Smart Reframe modo blurred_fit
    success = apply_smart_reframe(sample, mode_override="blurred_fit")
    assert success is True
    assert verify_media_integrity(sample) is True

    meta = inspect_media_file(sample)
    assert meta["width"] == 1080
    assert meta["height"] == 1920


def test_apply_smart_reframe_headroom_mode(tmp_path):
    sample = tmp_path / "sample_headroom.mp4"

    # Gera vídeo horizontal 16:9 (640x360, 2 segundos)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(sample)
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    # Aplica Smart Reframe modo headroom
    success = apply_smart_reframe(sample, mode_override="headroom")
    assert success is True
    assert verify_media_integrity(sample) is True

    meta = inspect_media_file(sample)
    assert meta["width"] == 1080
    assert meta["height"] == 1920
