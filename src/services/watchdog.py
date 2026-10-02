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

_last_cleanup_timestamp: float = 0.0
CLEANUP_INTERVAL_SECONDS: int = 3600  # 1 hora

def run_watchdog_check():
    """Executa checagem única de saúde e rotina periódica de limpeza de disco."""
    global _last_cleanup_timestamp
    record_heartbeat("watchdog", "OK", "Watchdog ativo e monitorando")
    stale = check_heartbeats()
    fatal = check_dead_letter_queue()
    logger.info(f"Watchdog executado: {len(stale)} serviços estagnados, {fatal} itens em DLQ.")

    # Rotina automática de retenção e limpeza de disco a cada 1 hora
    now = time.time()
    if now - _last_cleanup_timestamp >= CLEANUP_INTERVAL_SECONDS:
        try:
            from src.services.cleanup import run_disk_cleanup
            cleanup_res = run_disk_cleanup()
            _last_cleanup_timestamp = now
            logger.info(f"Limpeza de retenção de disco executada com sucesso: {cleanup_res}")
        except Exception as ce:
            logger.error(f"Erro ao executar limpeza de retenção de disco: {ce}", exc_info=True)

def run_watchdog_loop(interval_seconds: int = 60):
    """Executa monitoramento contínuo em loop com tolerância a falhas."""
    logger.info(f"Iniciando Watchdog Guardião contínuo (intervalo: {interval_seconds}s)...")
    while True:
        try:
            run_watchdog_check()
        except Exception as e:
            logger.error(f"Erro na execução do ciclo de watchdog: {e}")
            record_heartbeat("watchdog", "ERROR", f"Erro: {str(e)[:100]}")
        time.sleep(interval_seconds)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Watchdog Guardião de Integridade Operacional")
    parser.add_argument("--once", action="store_true", help="Executa checagem única e encerra")
    parser.add_argument("--interval", type=int, default=60, help="Intervalo em segundos entre checagens (padrão: 60s)")
    args = parser.parse_args()

    if args.once:
        run_watchdog_check()
    else:
        run_watchdog_loop(interval_seconds=args.interval)
