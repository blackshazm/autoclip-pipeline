"""
Testes unitários para o módulo de utilitários centrais (src/core/utils.py).
"""
import pytest
from pathlib import Path
from src.core.utils import compute_sha256, ensure_directory, safe_unlink, mask_secret

def test_compute_sha256(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("Hello World", encoding="utf-8")
    h = compute_sha256(f)
    assert len(h) == 64
    assert isinstance(h, str)

def test_ensure_directory(tmp_path):
    sub = tmp_path / "deep" / "nested" / "dir"
    res = ensure_directory(sub)
    assert res.exists()
    assert res.is_dir()

def test_safe_unlink(tmp_path):
    f = tmp_path / "temp.txt"
    f.write_text("delete me", encoding="utf-8")
    assert safe_unlink(f) is True
    assert not f.exists()

    # Segunda chamada não falha e retorna False
    assert safe_unlink(f) is False

def test_mask_secret():
    assert mask_secret("sk-1234567890abcdef", show_last=4) == "***************cdef"
    assert mask_secret("1234", show_last=4) == "****"
    assert mask_secret("12", show_last=4) == "**"
    assert mask_secret(None) == ""
    assert mask_secret("") == ""
