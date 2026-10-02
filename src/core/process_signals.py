"""
Módulo de Sinais e Telemetria de Processos em Tempo Real.
Registra o estado, progresso e sinais de conclusão de cada componente da pipeline,
com saída estruturada no console e persistência para o Dashboard Web.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.core.logger import get_logger
from src.core.database import get_db

logger = get_logger("process_signals")

# Cores ANSI para o terminal
COLOR_RESET = "\033[0m"
COLOR_CYAN = "\033[36m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_RED = "\033[31m"
COLOR_MAGENTA = "\033[35m"
COLOR_BOLD = "\033[1m"

def init_signals_table():
    """Garante que a tabela process_signals existe no banco de dados."""
    try:
        with get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS process_signals (
                    process_name TEXT PRIMARY KEY,
                    display_name TEXT,
                    task_name TEXT,
                    current_step INTEGER DEFAULT 0,
                    total_steps INTEGER DEFAULT 0,
                    status TEXT, -- 'IDLE', 'RUNNING', 'COMPLETED', 'FAILED'
                    message TEXT,
                    last_updated TEXT,
                    extra_json TEXT
                );
            """)
    except Exception as e:
        logger.debug(f"Aviso ao inicializar tabela process_signals: {e}")

class SignalTracker:
    """Gerenciador centralizado de sinais de ciclo e progresso."""

    NAME_MAP = {
        "radar_youtube": "📡 Radar de Hype",
        "robot1_ingest": "📥 Robô 1: Ingestor",
        "supoclip": "✂️ Supoclip (Cortes)",
        "llm_copywriter": "✍️ Copywriter LLM",
        "scheduler": "⏱️ Agendador",
        "robot2_publish": "🚀 Robô 2: Publicador",
        "youtube_publisher": "🔴 YouTube Shorts",
        "tiktok_publisher": "🎵 TikTok Studio",
        "watchdog": "🛡️ Watchdog Guardião"
    }

    @classmethod
    def emit_start(
        cls,
        process_name: str,
        task_name: str,
        total_steps: int = 1,
        message: str = "Iniciado",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Emite sinal de início de processo ou tarefa."""
        display = cls.NAME_MAP.get(process_name, process_name)
        now_iso = datetime.now(timezone.utc).isoformat()
        extra_str = json.dumps(metadata or {})

        print(f"{COLOR_BOLD}{COLOR_CYAN}[SINAL: INÍCIO]{COLOR_RESET} {COLOR_BOLD}{display}{COLOR_RESET} » {task_name}: {message}")

        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO process_signals (
                        process_name, display_name, task_name, current_step, total_steps, status, message, last_updated, extra_json
                    ) VALUES (?, ?, ?, 0, ?, 'RUNNING', ?, ?, ?)
                    ON CONFLICT(process_name) DO UPDATE SET
                        display_name = excluded.display_name,
                        task_name = excluded.task_name,
                        current_step = 0,
                        total_steps = excluded.total_steps,
                        status = 'RUNNING',
                        message = excluded.message,
                        last_updated = excluded.last_updated,
                        extra_json = excluded.extra_json;
                """, (process_name, display, task_name, total_steps, message, now_iso, extra_str))
        except Exception as e:
            logger.debug(f"Falha ao persistir sinal de início ({process_name}): {e}")

    @classmethod
    def emit_progress(
        cls,
        process_name: str,
        current_step: int,
        total_steps: int,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Emite sinal de progresso com passo e mensagem."""
        display = cls.NAME_MAP.get(process_name, process_name)
        now_iso = datetime.now(timezone.utc).isoformat()
        extra_str = json.dumps(metadata or {})

        pct = int((current_step / max(1, total_steps)) * 100)
        print(f"{COLOR_YELLOW}[SINAL: ETAPA {current_step}/{total_steps} ({pct}%)] {COLOR_RESET}{COLOR_BOLD}{display}{COLOR_RESET} » {message}")

        try:
            with get_db() as conn:
                conn.execute("""
                    UPDATE process_signals
                    SET current_step = ?,
                        total_steps = ?,
                        status = 'RUNNING',
                        message = ?,
                        last_updated = ?,
                        extra_json = ?
                    WHERE process_name = ?;
                """, (current_step, total_steps, message, now_iso, extra_str, process_name))
        except Exception as e:
            logger.debug(f"Falha ao persistir sinal de progresso ({process_name}): {e}")

    @classmethod
    def emit_finish(
        cls,
        process_name: str,
        message: str = "Concluído com sucesso",
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Emite sinal de término com status e detalhes."""
        display = cls.NAME_MAP.get(process_name, process_name)
        now_iso = datetime.now(timezone.utc).isoformat()
        extra_str = json.dumps(metadata or {})
        status = "COMPLETED" if success else "FAILED"

        if success:
            print(f"{COLOR_BOLD}{COLOR_GREEN}[SINAL: CONCLUÍDO ✅]{COLOR_RESET} {COLOR_BOLD}{display}{COLOR_RESET} » {message}")
        else:
            print(f"{COLOR_BOLD}{COLOR_RED}[SINAL: FALHOU ❌]{COLOR_RESET} {COLOR_BOLD}{display}{COLOR_RESET} » {message}")

        try:
            with get_db() as conn:
                conn.execute("""
                    UPDATE process_signals
                    SET status = ?,
                        message = ?,
                        last_updated = ?,
                        extra_json = ?
                    WHERE process_name = ?;
                """, (status, message, now_iso, extra_str, process_name))
        except Exception as e:
            logger.debug(f"Falha ao persistir sinal de término ({process_name}): {e}")

    @classmethod
    def get_all_signals(cls) -> List[Dict[str, Any]]:
        """Recupera o estado mais recente de todos os processos."""
        init_signals_table()
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT process_name, display_name, task_name, current_step, total_steps, status, message, last_updated, extra_json
                FROM process_signals
                ORDER BY last_updated DESC;
            """)
            rows = cursor.fetchall()
            signals = []
            for r in rows:
                extra = {}
                if r["extra_json"]:
                    try:
                        extra = json.loads(r["extra_json"])
                    except Exception:
                        pass
                signals.append({
                    "process_name": r["process_name"],
                    "display_name": r["display_name"] or r["process_name"],
                    "task_name": r["task_name"] or "",
                    "current_step": r["current_step"],
                    "total_steps": r["total_steps"],
                    "status": r["status"] or "IDLE",
                    "message": r["message"] or "",
                    "last_updated": r["last_updated"] or "",
                    "extra": extra
                })
            return signals

# Inicializa tabela ao carregar o módulo
init_signals_table()
