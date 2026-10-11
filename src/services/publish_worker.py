"""
Worker Especializado de Publicação Autônoma (src/services/publish_worker.py).
Responsabilidade Única:
- Atende com exclusividade uma única plataforma (YouTube Shorts ou TikTok) e nicho (Finanças ou Fitness);
- Mantém seu próprio perfil do navegador e cookies persistentes;
- Trata limites de cota de upload de forma estritamente isolada (não contamina outros canais);
- Reporta telemetria dedicada em tempo real para o Painel Web.
"""
import argparse
import gc
import json
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from src.core.config import settings
from src.core.logger import get_logger
from src.core.database import get_db
from src.services.youtube_publisher import YouTubePublisher
from src.services.youtube_browser_publisher import YouTubeBrowserPublisher
from src.services.tiktok_publisher import TikTokPublisher
from src.services.tiktok_browser_publisher import TikTokBrowserPublisher
from src.services.notifier import notify_published_clip, notify_alert
from src.services.media_validator import verify_media_integrity
from src.services.cleanup import check_and_purge_clip_if_fully_published
from src.services.watchdog import record_heartbeat
from src.core.exceptions import QuotaExceededError
from src.core.process_signals import SignalTracker
from src.core.pipeline_control import PipelineController

logger = get_logger("publish_worker")


def run_single_publish_cycle(platform: str, niche: str, worker_id: str, process_name: str) -> int:
    """Executa um ciclo de despacho para o canal e nicho específicos."""
    if PipelineController.is_paused(process_name):
        msg = f"⏸️ Robô ({platform.upper()} - {niche.capitalize()}) pausado pelo usuário."
        record_heartbeat(process_name, "PAUSED", msg)
        SignalTracker.emit_progress(process_name, 0, 1, msg)
        return 0

    record_heartbeat(process_name, "RUNNING", f"Worker {worker_id} ativo")
    
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    published_count = 0

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Reconciliação atômica pós-crash/timeout deste worker/canal
        cursor.execute("""
            UPDATE publications
            SET status = 'SCHEDULED', lease_owner = NULL, lease_expires_at = NULL
            WHERE status = 'UPLOADING'
              AND platform = ?
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at < ?
              AND publishing_account_id IN (
                  SELECT id FROM publishing_accounts WHERE platform = ? AND niche = ?
              );
        """, (platform, now_iso, platform, niche))
        conn.commit()

        # 2. Busca próxima publicação elegível exclusivamente para esta plataforma e nicho
        cursor.execute("""
            SELECT p.id, p.clip_id, p.platform, p.publishing_account_id,
                   c.clip_uid, c.file_path, c.title, c.description, c.tags, c.virality_score,
                   pa.profile_name, pa.credentials_ref, pa.external_channel_id, pa.niche as account_niche
            FROM publications p
            JOIN clips c ON p.clip_id = c.id
            JOIN publishing_accounts pa ON p.publishing_account_id = pa.id
            WHERE p.status = 'SCHEDULED' 
              AND p.platform = ? 
              AND pa.niche = ?
              AND p.scheduled_for <= ?
            ORDER BY p.scheduled_for ASC
            LIMIT 1;
        """, (platform, niche, now_iso))
        row = cursor.fetchone()

        if not row:
            # Sem publicações pendentes neste instante
            record_heartbeat(process_name, "OK", "Aguardando próximo horário de publicação...")
            return 0

        pub = dict(row)
        pub_id = pub["id"]
        clip_id = pub["clip_id"]
        clip_uid = pub["clip_uid"]
        file_path = Path(pub["file_path"])
        title = pub["title"] or "Corte #Shorts"
        description = pub["description"] or ""
        tags = json.loads(pub["tags"]) if pub["tags"] else ["#shorts", "#cortes"]
        ext_channel_id = pub.get("external_channel_id")
        account_id = pub.get("publishing_account_id")

        # 3. Adquire Lease Lock atômico
        lease_exp_iso = (now_dt + timedelta(minutes=15)).isoformat()
        cursor.execute("""
            UPDATE publications
            SET status = 'UPLOADING',
                lease_owner = ?,
                lease_expires_at = ?
            WHERE id = ? AND status = 'SCHEDULED';
        """, (worker_id, lease_exp_iso, pub_id))

        if cursor.rowcount == 0:
            return 0  # Outro worker assumiu

        conn.commit()

    # Log e Telemetria
    display_title = (title or "").strip()[:40]
    SignalTracker.emit_start(
        process_name,
        f"Publicar ({platform.upper()} - {niche.capitalize()})",
        total_steps=4,
        message=f"Iniciando despacho de: '{display_title}'"
    )

    # 4. Validação de integridade do arquivo em disco
    if not file_path.exists() or not verify_media_integrity(file_path):
        err_msg = f"Arquivo de vídeo inválido ou ausente: {file_path.name}"
        logger.error(err_msg)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE publications SET status = 'FAILED', error_message = ? WHERE id = ?;", (err_msg, pub_id))
            cursor.execute("UPDATE clips SET moderation_status = 'MODERATION_BLOCKED', error_log = ? WHERE id = ?;", (err_msg, clip_id))
            conn.commit()
        SignalTracker.emit_finish(process_name, err_msg, success=False)
        return 0

    # 5. Execução do Upload Isolado
    try:
        if platform == "youtube":
            yt_pdir = Path(f"./data/youtube_browser_profile_{niche}")
            yt_sfile = Path(f"./config/youtube_{niche}_state.json")
            
            SignalTracker.emit_progress(process_name, 1, 4, f"Abrindo YouTube Studio ({niche})...")
            browser_pub = YouTubeBrowserPublisher(
                profile_dir=yt_pdir,
                state_file=yt_sfile,
                channel_id=ext_channel_id
            )
            
            SignalTracker.emit_progress(process_name, 2, 4, f"Fazendo upload de {file_path.name}...")
            yt_res = browser_pub.publish_short(file_path, title, description, tags, clip_uid)
            yt_id = yt_res.get("youtube_video_id")

            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE publications
                    SET status = 'POSTED', published_at = datetime('now'), external_id = ?, response_json = ?
                    WHERE id = ?;
                """, (yt_id, json.dumps(yt_res), pub_id))
                cursor.execute("""
                    UPDATE clips
                    SET youtube_status = 'POSTED', youtube_video_id = ?, published_at = datetime('now')
                    WHERE id = ?;
                """, (yt_id, clip_id))
                conn.commit()
                check_and_purge_clip_if_fully_published(clip_id, conn=conn)

            published_count += 1
            pub_url = f"https://youtube.com/shorts/{yt_id}"
            notify_published_clip(
                {"title": title, "virality_score": pub.get("virality_score", 0)},
                {"youtube": pub_url}
            )
            SignalTracker.emit_finish(
                process_name,
                f"Vídeo postado no YouTube Shorts: {pub_url}",
                success=True,
                metadata={"video_id": yt_id}
            )

        elif platform == "tiktok":
            tk_pdir = Path(f"./data/tiktok_browser_profile_{niche}")
            tk_sfile = Path(f"./config/tiktok_{niche}_state.json")

            SignalTracker.emit_progress(process_name, 1, 4, f"Abrindo TikTok Studio ({niche})...")
            browser_tk = TikTokBrowserPublisher(
                profile_dir=tk_pdir,
                state_file=tk_sfile
            )

            SignalTracker.emit_progress(process_name, 2, 4, f"Fazendo upload de {file_path.name}...")
            tk_res = browser_tk.publish_video(file_path, title, tags, clip_uid)
            tk_id = tk_res.get("tiktok_post_id")

            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE publications
                    SET status = 'POSTED', published_at = datetime('now'), external_id = ?, response_json = ?
                    WHERE id = ?;
                """, (tk_id, json.dumps(tk_res), pub_id))
                cursor.execute("""
                    UPDATE clips
                    SET tiktok_status = 'POSTED', tiktok_post_id = ?, published_at = datetime('now')
                    WHERE id = ?;
                """, (tk_id, clip_id))
                conn.commit()
                check_and_purge_clip_if_fully_published(clip_id, conn=conn)

            published_count += 1
            pub_url = f"https://www.tiktok.com/@post/{tk_id}"
            notify_published_clip(
                {"title": title, "virality_score": pub.get("virality_score", 0)},
                {"tiktok": pub_url}
            )
            SignalTracker.emit_finish(
                process_name,
                f"Vídeo postado no TikTok: {pub_url}",
                success=True,
                metadata={"post_id": tk_id}
            )

    except QuotaExceededError as q_err:
        err_msg = f"Limite diário de upload alcançado no canal ({niche}). Pausando apenas esta conta por 24h."
        logger.warning(err_msg)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE publications
                SET status = 'FAILED_QUOTA', error_message = ?, scheduled_for = datetime('now', '+24 hours')
                WHERE id = ?;
            """, (str(q_err), pub_id))
            # Adia APENAS as publicações desta conta específica!
            cursor.execute("""
                UPDATE publications
                SET scheduled_for = datetime('now', '+24 hours')
                WHERE platform = ? AND publishing_account_id = ? AND status = 'SCHEDULED';
            """, (platform, account_id))
            conn.commit()
        SignalTracker.emit_finish(process_name, err_msg, success=False)

    except Exception as e:
        err_msg = f"Falha ao publicar {pub_id} no {platform} ({niche}): {e}"
        logger.error(err_msg, exc_info=True)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT retry_count FROM publications WHERE id = ?;", (pub_id,))
            retries = (cursor.fetchone() or [0])[0]
            if retries + 1 < 3:
                retry_time = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
                cursor.execute("""
                    UPDATE publications
                    SET status = 'SCHEDULED', retry_count = retry_count + 1, scheduled_for = ?, error_message = ?
                    WHERE id = ?;
                """, (retry_time, str(e), pub_id))
            else:
                cursor.execute("""
                    UPDATE publications
                    SET status = 'FAILED', retry_count = retry_count + 1, error_message = ?
                    WHERE id = ?;
                """, (str(e), pub_id))
            conn.commit()
        SignalTracker.emit_finish(process_name, f"Falha: {str(e)[:80]}", success=False)

    return published_count


def main():
    parser = argparse.ArgumentParser(description="Worker Especializado de Publicação Autônoma")
    parser.add_argument("--platform", required=True, choices=["youtube", "tiktok"], help="Plataforma de publicação")
    parser.add_argument("--niche", required=True, choices=["financas", "fitness"], help="Nicho da conta")
    parser.add_argument("--once", action="store_true", help="Executa um único ciclo e encerra")
    args = parser.parse_args()

    platform = args.platform
    niche = args.niche
    worker_id = f"pub-{platform[:2]}-{niche[:3]}-{uuid.uuid4().hex[:4]}"
    process_name = f"pub_{'yt' if platform == 'youtube' else 'tk'}_{niche}"

    logger.info(f"Worker de Publicação [{platform.upper()} - {niche.capitalize()}] iniciado com ID {worker_id}.")

    while True:
        try:
            run_single_publish_cycle(platform, niche, worker_id, process_name)
        except Exception as e:
            logger.error(f"Erro no ciclo do worker {process_name}: {e}", exc_info=True)

        if args.once:
            break

        # Ciclo de verificação a cada 20 segundos
        time.sleep(20)


if __name__ == "__main__":
    main()
