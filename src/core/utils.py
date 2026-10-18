"""
Utilitários de suporte compartilhados para o AutoClip Pipeline.
Funções puras e operações idempotentes de sistema de arquivos e mascaramento.
"""

import hashlib
from pathlib import Path
from typing import Optional


def compute_sha256(file_path: Path) -> str:
    """Calcula hash SHA-256 em blocos de 64KB para evitar sobrecarga de memória RAM."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def ensure_directory(path: Path) -> Path:
    """Garante que o diretório especificado existe no disco e o retorna."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_unlink(path: Path) -> bool:
    """Remove um arquivo com segurança, ignorando se o arquivo não existir ou se estiver em uso transitório."""
    try:
        if path.exists():
            path.unlink(missing_ok=True)
            return True
    except (OSError, PermissionError):
        return False
    return False


def mask_secret(secret: Optional[str], show_last: int = 4) -> str:
    """Mascara strings sensíveis (chaves de API, senhas, tokens) preservando os últimos N caracteres para depuração."""
    if not secret:
        return ""
    if len(secret) <= show_last:
        return "*" * len(secret)
    return f"{'*' * (len(secret) - show_last)}{secret[-show_last:]}"
