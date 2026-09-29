"""
Logging Estruturado em Formato JSON para Operação Lights-Out.
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import re

from src.core.config import settings

# Padrões para mascarar tokens e segredos
SECRET_PATTERNS = [
    re.compile(r"(sk-[a-zA-Z0-9_\-]{20,})"),
    re.compile(r"(AIza[0-9A-Za-z-_]{35})"),
    re.compile(r"(ya29\.[0-9A-Za-z-_]+)"),
    re.compile(r"(act\.[0-9A-Za-z-_]+)")
]

def mask_secrets(text: str) -> str:
    """Mascara chaves e tokens conhecidos em strings de log."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(r"\1"[:6] + "..." + r"\1"[-4:], text)
    return text

class JsonFormatter(logging.Formatter):
    """Formatador que emite eventos em JSON com schema estrito."""

    def __init__(self, service_name: str = "pipeline"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", self.service_name),
            "event": getattr(record, "event", "generic_log"),
            "message": mask_secrets(record.getMessage())
        }

        # Campos contextuais opcionais
        for attr in ("correlation_id", "entity_type", "entity_id", "status", "error_code", "duration_ms"):
            if hasattr(record, attr):
                log_data[attr] = getattr(record, attr)

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)

def get_logger(service_name: str) -> logging.Logger:
    """Retorna um logger configurado para saída em console e arquivo JSON."""
    logger = logging.getLogger(f"pipeline.{service_name}")
    
    if not logger.handlers:
        level_name = settings.LOG_LEVEL.upper()
        level = getattr(logging, level_name, logging.INFO)
        logger.setLevel(level)

        formatter = JsonFormatter(service_name=service_name)

        # Handler de Console com suporte seguro a UTF-8/emojis no Windows
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Handler de Arquivo
        try:
            log_file = settings.LOG_DIR / f"{service_name}.log"
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception:
            pass

        logger.propagate = False

    return logger
