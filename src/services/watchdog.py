"""
Watchdog de Integridade Operacional, Heartbeat e Monitor de DLQ.
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
import time

from src.core.config import settings
from src.core.logger import get_logger
from src.core.database import get_db
from src.services.notifier import notify_alert

logger = get_logger("watchdog")

def record_heartbeat(service_name: str, status: str = "OK", extra_info: str = "") -> None:
    """Registra ping periódico de vida do worker na tabela system_heartbeats."""
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO system_heartbeats (service_name, last_ping, status, extra_info)
                VALUES (?, datetime('now'), ?, ?)
                ON CONFLICT(service_name) DO UPDATE SET
                    last_ping = datetime('now'),
                    status = excluded.status,
                    extra_info = excluded.extra_info;
            """, (service_name, status, extra_info))
    except Exception as e:
        logger.error(f"Erro ao registrar heartbeat para {service_name}: {e}")

def check_heartbeats() -> List[Dict[str, Any]]:
    """Identifica serviços travados ou sem ping há mais de 15 minutos."""
    stale_services = []
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT service_name, last_ping, status FROM system_heartbeats;")
        rows = cursor.fetchall()

        for row in rows:
            last_ping_str = row["last_ping"]
            try:
                dt = datetime.fromisoformat(last_ping_str).replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    stale_services.append({
                        "service": row["service_name"],
                        "last_ping": last_ping_str,
                        "status": row["status"]
                    })
                    notify_alert(
                        "CRITICAL",
                        "watchdog",
                        f"Worker Inativo ({row['service_name']})",
                        f"O serviço {row['service_name']} está sem heartbeat há mais de 15 minutos! Último ping: {last_ping_str}",
                        conn=conn
                    )
            except Exception:
                pass

    return stale_services

def check_dead_letter_queue() -> int:
    """Verifica e alerta sobre novos itens na fila de falhas fatais (DLQ)."""
    fatal_count = 0
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, clip_id, platform, error_code, error_message
            FROM publications
            WHERE status = 'FAILED' AND retry_count >= 3;
        """)
        failed_pubs = cursor.fetchall()

        for pub in failed_pubs:
            fatal_count += 1
            notify_alert(
                "CRITICAL",
                "dlq",
                f"Falha Fatal de Publicação (Clip {pub['clip_id']})",
                f"Publicação na plataforma {pub['platform']} falhou definitivamente após retries. Erro: {pub['error_message']}",
                conn=conn
            )

    return fatal_count

def run_watchdog_check():
    """Executa checagem única de saúde."""
    record_heartbeat("watchdog", "OK", "Watchdog check executed")
    stale = check_heartbeats()
    fatal = check_dead_letter_queue()
    logger.info(f"Watchdog executado: {len(stale)} serviços estagnados, {fatal} itens em DLQ.")

if __name__ == "__main__":
    run_watchdog_check()
