"""
Módulo de Controle Central de Execução, Pausa e Gestão de Memória da Pipeline.
Permite pausar/retomar robôs individualmente ou em conjunto via SQLite WAL mode,
e fornece o Escudo de Memória RAM (RAM Conflict Shield) entre Supoclip e LLM Copywriter.
"""
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import psutil
except ImportError:
    psutil = None

from src.core.logger import get_logger
from src.core.database import get_db
from src.core.config import settings

logger = get_logger("pipeline_control")

SERVICES = [
    "all",
    "radar_youtube",
    "robot1_ingest",
    "media_processor",
    "pub_yt_financas",
    "pub_yt_fitness",
    "pub_tk_financas",
    "pub_tk_fitness",
    "llm_copywriter",
]

SERVICE_LABELS = {
    "all": "Pipeline Completa",
    "radar_youtube": "Radar de Hype",
    "robot1_ingest": "Robô Ingestor",
    "media_processor": "Fábrica de Cortes",
    "pub_yt_financas": "YouTube Raiz do Éden",
    "pub_yt_fitness": "YouTube Fitness",
    "pub_tk_financas": "TikTok Finanças",
    "pub_tk_fitness": "TikTok Fitness",
    "llm_copywriter": "Copywriter LLM",
}

def init_controls_table():
    """Garante que a tabela de controles de execução existe no banco."""
    try:
        with get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_controls (
                    service_name TEXT PRIMARY KEY,
                    is_paused INTEGER DEFAULT 0,
                    paused_at TEXT,
                    pause_reason TEXT,
                    updated_at TEXT
                );
            """)
            now_iso = datetime.now(timezone.utc).isoformat()
            for s in SERVICES:
                conn.execute("""
                    INSERT OR IGNORE INTO pipeline_controls (service_name, is_paused, updated_at)
                    VALUES (?, 0, ?);
                """, (s, now_iso))
    except Exception as e:
        logger.debug(f"Aviso ao inicializar pipeline_controls: {e}")

class PipelineController:
    """Gerenciador central de pausa, retomada e proteção de recursos."""

    @classmethod
    def is_paused(cls, service_name: str) -> bool:
        """
        Retorna True se o serviço específico OU o interruptor geral ('all') estiver pausado.
        """
        init_controls_table()
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT service_name, is_paused
                    FROM pipeline_controls
                    WHERE service_name IN (?, 'all');
                """, (service_name,))
                rows = {r["service_name"]: bool(r["is_paused"]) for r in cur.fetchall()}
                return rows.get("all", False) or rows.get(service_name, False)
        except Exception as e:
            logger.error(f"Erro ao verificar status de pausa para '{service_name}': {e}")
            return False

    @classmethod
    def set_paused(cls, service_name: str, paused: bool, reason: str = "manual") -> bool:
        """
        Define o status de pausa para um serviço ou para 'all'.
        """
        init_controls_table()
        if service_name not in SERVICES:
            raise ValueError(f"Serviço desconhecido: {service_name}. Válidos: {SERVICES}")

        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO pipeline_controls (service_name, is_paused, paused_at, pause_reason, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(service_name) DO UPDATE SET
                        is_paused = excluded.is_paused,
                        paused_at = CASE WHEN excluded.is_paused = 1 THEN excluded.paused_at ELSE NULL END,
                        pause_reason = CASE WHEN excluded.is_paused = 1 THEN excluded.pause_reason ELSE NULL END,
                        updated_at = excluded.updated_at;
                """, (service_name, 1 if paused else 0, now_iso if paused else None, reason if paused else None, now_iso))

            action = "PAUSADO" if paused else "RETOMADO"
            label = SERVICE_LABELS.get(service_name, service_name)
            logger.info(f"[CONTROLE] {label} foi {action} (Motivo: {reason})")
            return True
        except Exception as e:
            logger.error(f"Erro ao atualizar status de pausa para '{service_name}': {e}")
            return False

    @classmethod
    def toggle_pause(cls, service_name: str, reason: str = "manual") -> bool:
        """Alterna entre pausado e ativo para um serviço."""
        init_controls_table()
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT is_paused FROM pipeline_controls WHERE service_name = ?;", (service_name,))
                row = cur.fetchone()
                current = bool(row["is_paused"]) if row else False
            new_state = not current
            cls.set_paused(service_name, new_state, reason=reason)
            return new_state
        except Exception as e:
            logger.error(f"Erro ao alternar pausa para '{service_name}': {e}")
            return False

    @classmethod
    def pause_all(cls, reason: str = "manual") -> bool:
        """Pausa todos os robôs simultaneamente."""
        return cls.set_paused("all", True, reason=reason)

    @classmethod
    def resume_all(cls) -> bool:
        """Retoma todos os robôs simultaneamente."""
        init_controls_table()
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with get_db() as conn:
                conn.execute("""
                    UPDATE pipeline_controls
                    SET is_paused = 0, paused_at = NULL, pause_reason = NULL, updated_at = ?;
                """, (now_iso,))
            logger.info("[CONTROLE] Todos os robôs da pipeline foram RETOMADOS com sucesso.")
            return True
        except Exception as e:
            logger.error(f"Erro ao retomar todos os serviços: {e}")
            return False

    @classmethod
    def get_all_statuses(cls) -> Dict[str, Any]:
        """Retorna o estado detalhado de cada robô e a telemetria do sistema."""
        init_controls_table()
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT service_name, is_paused, paused_at, pause_reason, updated_at FROM pipeline_controls;")
            rows = [dict(r) for r in cur.fetchall()]

        statuses = {}
        for r in rows:
            s_name = r["service_name"]
            statuses[s_name] = {
                "service_name": s_name,
                "label": SERVICE_LABELS.get(s_name, s_name),
                "is_paused": bool(r["is_paused"]),
                "paused_at": r["paused_at"],
                "pause_reason": r["pause_reason"],
            }

        # Checagem se algum corte está ativo no Supoclip
        clip_cutting_active = cls.is_clip_processing_active()

        # Telemetria de Memória RAM
        mem_info = cls.get_system_memory_info()

        return {
            "controls": statuses,
            "all_paused": statuses.get("all", {}).get("is_paused", False),
            "clip_cutting_active": clip_cutting_active,
            "system_memory": mem_info,
        }

    @classmethod
    def is_clip_processing_active(cls) -> bool:
        """
        Retorna True se houver tarefas de fatiamento/clipamento ativas no Supoclip
        (Whisper + FFmpeg). Usado pelo RAM Shield para evitar colisão com a LLM.
        """
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT COUNT(*) as active_count
                    FROM supoclip_jobs
                    WHERE status IN ('SUBMITTED', 'PROCESSING');
                """)
                row = cur.fetchone()
                return (row["active_count"] if row else 0) > 0
        except Exception as e:
            logger.debug(f"Aviso ao consultar jobs ativos no Supoclip: {e}")
            return False

    @classmethod
    def set_copywriter_active(cls, active: bool) -> None:
        """Sinaliza que o serviço de Copywriting LLM (Ollama) está utilizando RAM ativamente."""
        init_controls_table()
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO pipeline_controls (service_name, is_paused, updated_at, pause_reason)
                    VALUES ('copywriter_running', ?, ?, ?)
                    ON CONFLICT(service_name) DO UPDATE SET
                        is_paused = excluded.is_paused,
                        updated_at = excluded.updated_at,
                        pause_reason = excluded.pause_reason;
                """, (1 if active else 0, now_iso, "LLM copywriter active" if active else "idle"))
        except Exception as e:
            logger.debug(f"Aviso ao atualizar copywriter_running: {e}")

    @classmethod
    def is_copywriter_active(cls) -> bool:
        """Verifica se o Copywriter LLM está rodando no momento com expiração de segurança (5 min)."""
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT is_paused, updated_at FROM pipeline_controls WHERE service_name = 'copywriter_running';")
                row = cur.fetchone()
                if not row or not row["is_paused"]:
                    return False
                if row["updated_at"]:
                    try:
                        up_dt = datetime.fromisoformat(row["updated_at"])
                        if (datetime.now(timezone.utc) - up_dt).total_seconds() > 300:
                            return False
                    except Exception:
                        pass
                return bool(row["is_paused"])
        except Exception as e:
            logger.debug(f"Aviso ao consultar copywriter_running: {e}")
            return False

    @classmethod
    def is_local_llm(cls) -> bool:
        """Retorna True se o Copywriter estiver configurado para LLM local (Ollama/localhost)."""
        base_url = str(getattr(settings, "OPENAI_BASE_URL", "")).lower()
        return "localhost" in base_url or "127.0.0.1" in base_url

    @classmethod
    def can_ingest_new_video(cls) -> tuple[bool, str]:
        """
        Valida se o Robô 1 pode despachar um NOVO vídeo longo para o Supoclip:
        1. Robô 1 não pode estar pausado.
        2. Supoclip deve estar ocioso (0 jobs em SUBMITTED ou PROCESSING).
        3. Se for LLM local (Ollama), aguarda o copywriter liberar a RAM/VRAM local.
        4. Memória RAM física mínima de segurança (apenas proteção contra colapso do SO < 0.35 GB livres).
        """
        if cls.is_paused("robot1_ingest"):
            return False, "⏸️ Robô 1 pausado pelo usuário."

        if cls.is_clip_processing_active():
            return False, "🛡️ Supoclip ocupado: Já existe corte em andamento. Aguardando conclusão (Um por vez)."

        # Só bloqueia concorrência se a LLM for local no host
        if cls.is_local_llm() and cls.is_copywriter_active():
            return False, "🛡️ Canal Crítico (RAM Shield): Copywriter LLM local ativo. Aguardando liberação da RAM/VRAM."

        mem = cls.get_system_memory_info()
        if mem.get("available") and mem.get("free_gb", 1.0) < 0.35:
            return False, f"⚠️ Memória RAM crítica (< 350 MB livres: {mem.get('free_gb')} GB). Postergando envio para evitar travamento do SO."

        return True, "Pronto para ingestão"

    @classmethod
    def can_run_copywriter(cls) -> tuple[bool, str]:
        """
        Valida se o Copywriter LLM pode gerar copy para um corte:
        1. Copywriter não pode estar pausado.
        2. Se for LLM local (Ollama), evita rodar enquanto o Supoclip usa VRAM/Whisper.
           Se for LLM remota (NVIDIA NIM / Nuvem), roda 100% livre em paralelo sem travar!
        3. Memória RAM física mínima de segurança (apenas proteção contra colapso do SO < 0.35 GB livres).
        """
        if cls.is_paused("llm_copywriter"):
            return False, "⏸️ Copywriter LLM pausado pelo usuário."

        # Só suspende se a LLM for local
        if cls.is_local_llm() and cls.is_clip_processing_active():
            return False, "🛡️ Canal Crítico (RAM Shield): Supoclip fatiando vídeo. Suspendendo LLM local para evitar sobrecarga simultânea."

        mem = cls.get_system_memory_info()
        if mem.get("available") and mem.get("free_gb", 1.0) < 0.35:
            return False, f"⚠️ Memória RAM crítica (< 350 MB livres). Postergando chamada da LLM."

        return True, "Pronto para copywriting"

    @classmethod
    def get_system_memory_info(cls) -> Dict[str, Any]:
        """Obtém métricas em tempo real de uso da memória RAM física."""
        if psutil is None:
            return {
                "percent": 0.0,
                "used_gb": 0.0,
                "total_gb": 0.0,
                "free_gb": 0.0,
                "available": False
            }
        try:
            mem = psutil.virtual_memory()
            total_gb = round(mem.total / (1024 ** 3), 1)
            used_gb = round(mem.used / (1024 ** 3), 1)
            free_gb = round(mem.available / (1024 ** 3), 1)
            return {
                "percent": round(mem.percent, 1),
                "used_gb": used_gb,
                "total_gb": total_gb,
                "free_gb": free_gb,
                "available": True,
                "is_high_pressure": mem.percent >= 80.0
            }
        except Exception as e:
            logger.debug(f"Erro ao coletar memória via psutil: {e}")
            return {
                "percent": 0.0,
                "used_gb": 0.0,
                "total_gb": 0.0,
                "free_gb": 0.0,
                "available": False
            }
