"""
Testes unitários isolados com mocks para o serviço de download (src/services/downloader.py).
Garante que arquivos válidos são renomeados, IDs inválidos são rejeitados e resíduos .temp.* são expurgados.
"""
import subprocess
from pathlib import Path
from src.services.downloader import download_youtube_video


def test_download_youtube_video_success(tmp_path, monkeypatch):
    """Cenário de sucesso: subprocess retorna 0, arquivo .temp.* é movido e validado."""
    yt_id = "test_vid_12"  # exatamente 11 caracteres
    temp_file = tmp_path / f"{yt_id}.temp.mp4"
    temp_file.write_bytes(b"FAKE_VALID_MP4_CONTENT")

    class MockProcessResult:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: MockProcessResult())
    monkeypatch.setattr("src.services.downloader.verify_media_integrity", lambda p: True)

    final_path = download_youtube_video(yt_id, output_dir=tmp_path)
    assert final_path is not None
    assert final_path == tmp_path / f"{yt_id}.mp4"
    assert final_path.exists()
    assert not temp_file.exists()


def test_download_youtube_video_failure_no_placeholder(tmp_path, monkeypatch):
    """Cenário de erro: subprocess falha com código != 0; deve retornar None sem criar arquivo vazio."""
    yt_id = "test_vid_er"  # 11 caracteres
    final_file = tmp_path / f"{yt_id}.mp4"

    class MockErrorResult:
        returncode = 1
        stdout = ""
        stderr = "HTTP 403 Forbidden"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: MockErrorResult())

    result = download_youtube_video(yt_id, output_dir=tmp_path)
    assert result is None
    assert not final_file.exists()


def test_download_youtube_video_file_not_found(tmp_path, monkeypatch):
    """Cenário onde yt-dlp não é encontrado: deve retornar None sem criar arquivo vazio."""
    yt_id = "test_vid_no"  # 11 caracteres
    final_file = tmp_path / f"{yt_id}.mp4"

    def mock_run_fn(*a, **k):
        raise FileNotFoundError("yt-dlp binary not found")

    monkeypatch.setattr(subprocess, "run", mock_run_fn)

    result = download_youtube_video(yt_id, output_dir=tmp_path)
    assert result is None
    assert not final_file.exists()


def test_download_youtube_video_timeout(tmp_path, monkeypatch):
    """Cenário de timeout: deve retornar None de forma limpa."""
    yt_id = "test_vid_to"  # 11 caracteres

    def mock_run_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd=["yt_dlp"], timeout=10)

    monkeypatch.setattr(subprocess, "run", mock_run_timeout)

    result = download_youtube_video(yt_id, output_dir=tmp_path)
    assert result is None


def test_download_youtube_video_already_exists(tmp_path, monkeypatch):
    """Cenário onde o vídeo já existe com tamanho > 0: retorna o arquivo existente sem rodar subprocess."""
    yt_id = "test_vid_cc"  # 11 caracteres
    existing_file = tmp_path / f"{yt_id}.mp4"
    existing_file.write_bytes(b"PRE_EXISTING_VIDEO_BYTES")

    def mock_fail_if_called(*a, **k):
        raise AssertionError("subprocess.run não deveria ser chamado quando o vídeo já existe")

    monkeypatch.setattr(subprocess, "run", mock_fail_if_called)

    result = download_youtube_video(yt_id, output_dir=tmp_path)
    assert result == existing_file
    assert result.stat().st_size > 0


def test_download_youtube_video_invalid_id_rejected(tmp_path, monkeypatch):
    """Garante que IDs com tamanhos inválidos ou caracteres perigosos são rejeitados de imediato."""
    invalid_ids = [
        "",
        "short_id",
        "too_long_youtube_identifier_12345",
        "https://www.youtube.com/watch?v=12345678901",
        "../traversal",
        "vid;rm -rf /",
        "vid$HOME1234",
    ]

    for bad_id in invalid_ids:
        res = download_youtube_video(bad_id, output_dir=tmp_path)
        assert res is None, f"ID inválido '{bad_id}' deveria ter sido rejeitado"


def test_download_youtube_video_cleans_up_temp_files_on_failure(tmp_path, monkeypatch):
    """Garante que resíduos temporários .temp.* são removidos após falhas ou timeouts."""
    yt_id = "test_vid_cl"  # 11 caracteres
    temp_file1 = tmp_path / f"{yt_id}.temp.mp4"
    temp_file1.write_bytes(b"PARTIAL_BYTES")
    temp_file2 = tmp_path / f"{yt_id}.temp.part"
    temp_file2.write_bytes(b"PARTIAL_PART_BYTES")

    def mock_run_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd=["yt_dlp"], timeout=10)

    monkeypatch.setattr(subprocess, "run", mock_run_timeout)

    res = download_youtube_video(yt_id, output_dir=tmp_path)
    assert res is None
    assert not temp_file1.exists()
    assert not temp_file2.exists()
