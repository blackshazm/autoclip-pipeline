import subprocess
from pathlib import Path
import pytest
from src.services.video_pacing import optimize_clip_pacing, detect_tail_silence
from src.services.media_validator import inspect_media_file, verify_media_integrity


def test_optimize_clip_pacing_invalid_file(tmp_path):
    fake_path = tmp_path / "nao_existe.mp4"
    assert optimize_clip_pacing(fake_path, speed_factor=1.05) is False


def test_optimize_clip_pacing_neutral_factor(tmp_path):
    dummy = tmp_path / "dummy.mp4"
    dummy.write_text("dummy")
    # Arquivo com tamanho ínfimo e duração <= 0.5 é ignorado e retorna True
    assert optimize_clip_pacing(dummy, speed_factor=1.0, enable_loop=False) is True


def test_optimize_clip_pacing_real_ffmpeg(tmp_path):
    sample_file = tmp_path / "test_sample.mp4"
    
    # Gera um pequeno vídeo de teste de 3 segundos com áudio e vídeo válidos
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(sample_file)
    ]
    res = subprocess.run(cmd, capture_output=True)
    assert res.returncode == 0
    assert sample_file.exists()

    initial_meta = inspect_media_file(sample_file)
    initial_dur = initial_meta["duration_seconds"]
    assert 2.8 <= initial_dur <= 3.2

    # Aplica aceleração de 1.05x com seamless loop
    success = optimize_clip_pacing(sample_file, speed_factor=1.05, enable_loop=True)
    assert success is True
    assert verify_media_integrity(sample_file) is True

    optimized_meta = inspect_media_file(sample_file)
    optimized_dur = optimized_meta["duration_seconds"]

    # Deve ter reduzido a duração (3.0s / 1.05 =~ 2.85s)
    assert optimized_dur < initial_dur
    assert 2.6 <= optimized_dur <= 2.95


def test_detect_tail_silence(tmp_path):
    sample_silence = tmp_path / "silence_sample.mp4"

    # Gera 2.2s de som + 0.8s de silêncio (total 3.0s)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2.2",
        "-filter_complex", "[1:a]apad=whole_dur=3[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-c:a", "aac",
        "-t", "3",
        str(sample_silence)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    assert sample_silence.exists()

    # Detecta cauda de silêncio
    tail_cut = detect_tail_silence(sample_silence, total_duration=3.0, threshold_db=-35, min_silence_sec=0.20)
    assert tail_cut is not None
    assert 2.0 <= tail_cut <= 2.3


def test_seamless_loop_tail_trimming_pipeline(tmp_path):
    sample_clip = tmp_path / "loop_tail_sample.mp4"

    # Gera clipe de 3.5s com os últimos 0.7s em silêncio
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3.5:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2.8",
        "-filter_complex", "[1:a]apad=whole_dur=3.5[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-c:a", "aac",
        "-t", "3.5",
        str(sample_clip)
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    # Executa otimização com seamless loop e velocidade neutra 1.0x para testar o corte da cauda
    success = optimize_clip_pacing(sample_clip, speed_factor=1.0, enable_loop=True)
    assert success is True
    assert verify_media_integrity(sample_clip) is True

    final_meta = inspect_media_file(sample_clip)
    final_dur = final_meta["duration_seconds"]

    # A duração final deve ter cortado o silêncio morto (de 3.5s para ~2.8s)
    assert final_dur < 3.2
    assert 2.6 <= final_dur <= 3.0
