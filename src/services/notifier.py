"""
Serviço de Notificações via Webhooks (Discord e Telegram) e DLQ.
"""
from typing import Optional, Dict, Any
import requests
import json
import hashlib
import sqlite3
from datetime import datetime, timezone

from src.core.config import settings
from src.core.logger import get_logger
from src.core.database import get_db

logger = get_logger("notifier")

def send_discord_notification(title: str, message: str, color: int = 0x00FF00, fields: Optional[list] = None) -> bool:
    """Envia mensagem formatada com Embed no Discord."""
    webhook_url = settings.DISCORD_WEBHOOK_URL
    if not webhook_url:
        logger.debug(f"[DISCORD DISPENSADO] {title}: {message}")
        return False

    payload = {
        "embeds": [{
            "title": title,
            "description": message,
            "color": color,
            "fields": fields or [],
            "footer": {"text": "Pipeline Autônomo de Cortes • Hermes & Supoclip"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
    }

    try:
        res = requests.post(webhook_url, json=payload, timeout=10)
        return res.status_code in (200, 204)
    except Exception as e:
        logger.error(f"Erro ao enviar webhook Discord: {e}")
        return False

def send_telegram_notification(message: str) -> bool:
    """Envia notificação de texto via Telegram Bot."""
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        logger.error(f"Erro ao enviar notificação Telegram: {e}")
        return False

def notify_published_clip(clip_data: Dict[str, Any], platform_links: Dict[str, str]) -> None:
    """Dispara notificação de publicação comemorativa com métricas de virality score."""
    title = f"🚀 Novo Clip Publicado! ({clip_data.get('title')})"
    score = clip_data.get("virality_score", 0)

    links_text = "\n".join([f"• **{plat.title()}**: {url}" for plat, url in platform_links.items()])
    desc = f"**Virality Score:** `{score}/100`\n\n**Links:**\n{links_text}"

    send_discord_notification(title, desc, color=0x3498DB)
    send_telegram_notification(f"*{title}*\nScore: `{score}/100`\n\n{links_text}")

def notify_alert(severity: str, source: str, title: str, message: str, conn: Optional[sqlite3.Connection] = None) -> None:
    """Registra alerta no banco e envia notificação de incidente com severidade apropriada."""
    import sqlite3
    fingerprint = hashlib.md5(f"{source}_{title}".encode("utf-8")).hexdigest()

    # Cores no Discord: CRITICAL (Vermelho), WARNING (Amarelo), INFO (Azul)
    color_map = {
        "CRITICAL": 0xE74C3C,
        "WARNING": 0xF1C40F,
        "INFO": 0x3498DB
    }
    color = color_map.get(severity.upper(), 0x95A5A6)

    # Persiste na tabela alerts evitando spam duplicado
    sql = """
        INSERT INTO alerts (severity, source, title, message, status, fingerprint)
        VALUES (?, ?, ?, ?, 'OPEN', ?)
        ON CONFLICT(fingerprint) DO UPDATE SET
            status = 'OPEN',
            message = excluded.message;
    """
    try:
        if conn is not None:
            conn.execute(sql, (severity.upper(), source, title, message, fingerprint))
        else:
            with get_db() as local_conn:
                local_conn.execute(sql, (severity.upper(), source, title, message, fingerprint))
    except Exception as e:
        logger.error(f"Erro ao gravar alerta em alerts: {e}")

    formatted_title = f"[{severity.upper()}] {title} ({source})"
    send_discord_notification(formatted_title, message, color=color)
    if severity.upper() == "CRITICAL":
        send_telegram_notification(f"🚨 *{formatted_title}*\n\n{message}")
