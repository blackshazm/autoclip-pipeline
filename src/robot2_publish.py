"""
MÓDULO 2: Inteligência, Agendamento e Publicação Multiplataforma (robot2_publish.py).
Sincronização com Supoclip, Copywriting LLM, Lease-Lock e Publicação Resiliente.
"""
import argparse
import json
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from src.core.config import settings
from src.core.logger import get_logger
from src.core.database import get_db
from src.services.supoclip_client import SupoclipClient
from src.services.llm_copywriter import generate_clip_copy
from src.services.scheduler import schedule_pending_clips
from src.services.youtube_publisher import YouTubePublisher
from src.services.youtube_browser_publisher import YouTubeBrowserPublisher
from src.services.tiktok_publisher import TikTokPublisher
from src.services.tiktok_browser_publisher import TikTokBrowserPublisher
from src.services.notifier import notify_published_clip, notify_alert
from src.services.media_validator import verify_media_integrity
from src.services.watchdog import record_heartbeat
from src.core.exceptions import QuotaExceededError
from src.core.process_signals import SignalTracker

logger = get_logger("robot2_publish")

WORKER_ID = f"worker-{uuid.uuid4().hex[:6]}"

def sync_supoclip_jobs(client: SupoclipClient) -> int:
    """Consulta o Supoclip sobre o status de jobs pendentes e processa clips gerados."""
    completed_jobs = 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT j.id, j.long_video_id, j.supoclip_job_id, v.file_path as original_file_path
            FROM supoclip_jobs j
            JOIN long_videos v ON j.long_video_id = v.id
            WHERE j.status IN ('SUBMITTED', 'PROCESSING');
        """)
        pending_jobs = cursor.fetchall()

        for job in pending_jobs:
            job_db_id = job["id"]
            long_video_id = job["long_video_id"]
            supo_id = job["supoclip_job_id"]
            original_path = Path(job["original_file_path"])

            status_data = client.get_job_status(supo_id, original_path)
            current_status = status_data.get("status", "PROCESSING")

            if current_status == "COMPLETED":
                clips_list = status_data.get("clips", [])
                logger.info(
                    f"Job {supo_id} CONCLUÍDO no Supoclip. {len(clips_list)} clips gerados.",
                    extra={"event": "supoclip_job_completed", "job_id": supo_id, "clips_count": len(clips_list)}
                )

                # Persiste os clips gerados
                for c in clips_list:
                    clip_uid = c["clip_uid"]
                    virality_score = int(c.get("virality_score", 0))
                    is_qualified = virality_score >= settings.MIN_VIRALITY_SCORE

                    cursor.execute("""
                        INSERT INTO clips (
                            long_video_id, clip_uid, file_path, virality_score,
                            start_seconds, end_seconds, duration_seconds,
                            width, height, fps, transcription_path,
                            moderation_status, youtube_status, tiktok_status,
                            series_id, part_number, total_parts
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(clip_uid) DO NOTHING;
                    """, (
                        long_video_id, clip_uid, c["file_path"], virality_score,
                        c.get("start_seconds"), c.get("end_seconds"), c.get("duration_seconds"),
                        c.get("width"), c.get("height"), c.get("fps"), c.get("transcription_path"),
                        'APPROVED' if is_qualified else 'MODERATION_BLOCKED',
                        'PENDING' if is_qualified else 'SKIPPED',
                        'PENDING' if is_qualified else 'SKIPPED',
                        c.get("series_id"),
                        c.get("part_number", 1),
                        c.get("total_parts", 1)
                    ))

                # Atualiza status do job e do vídeo longo
                cursor.execute("UPDATE supoclip_jobs SET status = 'COMPLETED', completed_at = datetime('now') WHERE id = ?;", (job_db_id,))
                cursor.execute("UPDATE long_videos SET status = 'COMPLETED', completed_at = datetime('now') WHERE id = ?;", (long_video_id,))
                completed_jobs += 1

            elif current_status == "FAILED":
                error_msg = status_data.get("error", "Erro não especificado no Supoclip")
                logger.error(f"Job {supo_id} FALHOU no Supoclip: {error_msg}")
                cursor.execute("UPDATE supoclip_jobs SET status = 'FAILED', error_message = ? WHERE id = ?;", (error_msg, job_db_id))
                cursor.execute("UPDATE long_videos SET status = 'FAILED', error_message = ? WHERE id = ?;", (error_msg, long_video_id))

    return completed_jobs

def enrich_clips_with_copywriting() -> int:
    """Gera metadados (título, descrição, tags) via LLM para clips aprovados sem cópia."""
    enriched_count = 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, clip_uid, transcription_path, virality_score, series_id, part_number, total_parts
            FROM clips
            WHERE virality_score >= ? 
              AND moderation_status = 'APPROVED'
              AND title IS NULL;
        """, (settings.MIN_VIRALITY_SCORE,))
        clips = cursor.fetchall()

        for clip in clips:
            clip_id = clip["id"]
            trans_path = Path(clip["transcription_path"]) if clip["transcription_path"] else None
            
            transcript_text = ""
            if trans_path and trans_path.exists():
                with open(trans_path, "r", encoding="utf-8") as f:
                    transcript_text = f.read()

            if not transcript_text:
                transcript_text = f"Corte de alta retenção {clip['clip_uid']} com score {clip['virality_score']}."

            result = generate_clip_copy(clip_id, transcript_text, conn=conn, part_number=clip["part_number"] or 1, total_parts=clip["total_parts"] or 1)
            meta = result["metadata"]

            cursor.execute("""
                UPDATE clips
                SET title = ?,
                    description = ?,
                    tags = ?,
                    metadata_json = ?,
                    llm_fallback_used = ?
                WHERE id = ?;
            """, (
                meta["title"],
                meta["description"],
                json.dumps(meta["tags"]),
                json.dumps(meta),
                1 if result["is_fallback"] else 0,
                clip_id
            ))
            enriched_count += 1
            logger.info(
                f"Copywriting gerado para clip {clip['clip_uid']}: '{meta['title']}'",
                extra={"event": "copywriting_done", "clip_id": clip_id, "title": meta["title"]}
            )

    return enriched_count

def process_due_publications() -> int:
    """
    Executa os uploads de clips com agendamento vencido utilizando trava atômica de lease-lock.
    """
    yt_publisher = YouTubePublisher()
    tk_publisher = TikTokPublisher()
    published_count = 0

    with get_db() as conn:
        cursor = conn.cursor()
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        # 1. Reconciliação: Publicações em UPLOADING cujo lease expirou
        cursor.execute("""
            UPDATE publications
            SET status = 'RECONCILING'
            WHERE status = 'UPLOADING' AND (lease_expires_at < ? OR lease_expires_at < datetime('now'));
        """, (now_iso,))
        reconciled = cursor.rowcount
        if reconciled > 0:
            logger.warning(f"{reconciled} publicações marcadas para reconciliação pós-crash/timeout.", extra={"event": "reconciliation_marked"})

        # 2. Busca publicações prontas para envio
        cursor.execute("""
            SELECT p.id, p.clip_id, p.platform, p.publishing_account_id,
                   c.clip_uid, c.file_path, c.title, c.description, c.tags, c.virality_score
            FROM publications p
            JOIN clips c ON p.clip_id = c.id
            WHERE p.status = 'SCHEDULED' AND p.scheduled_for <= ?
            ORDER BY p.scheduled_for ASC;
        """, (now_iso,))
        due_pubs = cursor.fetchall()

        youtube_quota_exhausted = False
        for pub in due_pubs:
            pub_id = pub["id"]
            clip_id = pub["clip_id"]
            platform = pub["platform"]
            clip_uid = pub["clip_uid"]
            file_path = Path(pub["file_path"])
            title = pub["title"]
            description = pub["description"]
            tags = json.loads(pub["tags"]) if pub["tags"] else ["#shorts", "#cortes"]

            if platform == "youtube" and youtube_quota_exhausted:
                logger.info(f"Pulando publicação {pub_id} (YouTube) pois o limite diário de upload já foi atingido hoje.")
                continue

            # 3. Tenta adquirir Lease Lock atômico
            lease_exp_iso = (now_dt + timedelta(minutes=15)).isoformat()
            cursor.execute("""
                UPDATE publications
                SET status = 'UPLOADING',
                    lease_owner = ?,
                    lease_expires_at = ?
                WHERE id = ? AND status = 'SCHEDULED';
            """, (WORKER_ID, lease_exp_iso, pub_id))

            if cursor.rowcount == 0:
                continue # Outro worker adquiriu o lease

            conn.commit() # Libera o lock de escrita do SQLite imediatamente para outros processos!
            logger.info(f"Lease adquirido para publicação {pub_id} ({platform}). Disparando upload...", extra={"event": "lease_acquired", "pub_id": pub_id})

            # Valida que o vídeo é íntegro e não é tela preta/vazia
            if not verify_media_integrity(file_path):
                logger.error(f"Publicação {pub_id} abortada: o arquivo {file_path.name} está corrompido ou é tela preta.")
                cursor.execute("""
                    UPDATE publications SET status = 'FAILED', error_message = 'Arquivo inválido ou tela preta detectada' WHERE id = ?;
                """, (pub_id,))
                cursor.execute("""
                    UPDATE clips SET moderation_status = 'MODERATION_BLOCKED', error_log = 'Arquivo inválido ou tela preta detectada' WHERE id = ?;
                """, (clip_id,))
                continue

            try:
                if platform == "youtube":
                    yt_res = None
                    if getattr(settings, "YOUTUBE_PUBLISHER_MODE", "api") == "browser":
                        try:
                            browser_pub = YouTubeBrowserPublisher()
                            yt_res = browser_pub.publish_short(file_path, title, description, tags, clip_uid)
                        except Exception as browser_err:
                            if getattr(settings, "YOUTUBE_BROWSER_FALLBACK_TO_API", True):
                                logger.warning(
                                    f"Falha no YouTubeBrowserPublisher: {browser_err}. Acionando fallback automático para API oficial..."
                                )
                                yt_res = yt_publisher.publish_short(file_path, title, description, tags, clip_uid)
                            else:
                                raise browser_err
                    else:
                        yt_res = yt_publisher.publish_short(file_path, title, description, tags, clip_uid)

                    yt_id = yt_res.get("youtube_video_id")

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
                    published_count += 1
                    notify_published_clip(
                        {"title": title, "virality_score": pub["virality_score"]},
                        {"youtube": f"https://youtube.com/shorts/{yt_id}"}
                    )

                elif platform == "tiktok":
                    tk_res = None
                    if getattr(settings, "TIKTOK_PUBLISHER_MODE", "browser") == "browser":
                        try:
                            browser_tk = TikTokBrowserPublisher()
                            tk_res = browser_tk.publish_video(file_path, title, tags, clip_uid)
                        except Exception as tk_browser_err:
                            if getattr(settings, "TIKTOK_BROWSER_FALLBACK_TO_API", False):
                                logger.warning(
                                    f"Falha no TikTokBrowserPublisher: {tk_browser_err}. Acionando fallback para API oficial..."
                                )
                                tk_res = tk_publisher.publish_video(file_path, title, tags, clip_uid)
                            else:
                                raise tk_browser_err
                    else:
                        tk_res = tk_publisher.publish_video(file_path, title, tags, clip_uid)

                    tk_id = tk_res.get("tiktok_post_id")

                    cursor.execute("""
                        UPDATE publications
                        SET status = 'POSTED', published_at = datetime('now'), external_id = ?, response_json = ?
                        WHERE id = ?;
                    """, (tk_id, json.dumps(tk_res), pub_id))

                    cursor.execute("""
                        UPDATE clips
                        SET tiktok_status = 'POSTED', tiktok_post_id = ?
                        WHERE id = ?;
                    """, (tk_id, clip_id))

                    conn.commit()
                    published_count += 1
                    notify_published_clip(
                        {"title": title, "virality_score": pub["virality_score"]},
                        {"tiktok": f"https://www.tiktok.com/@post/{tk_id}"}
                    )

            except QuotaExceededError as q_err:
                logger.error(f"Limite diário de upload atingido no YouTube ao processar {pub_id}. Pausando fila do YouTube por 24h.")
                youtube_quota_exhausted = True
                cursor.execute("""
                    UPDATE publications
                    SET status = 'FAILED_QUOTA',
                        error_message = 'Limite diário do YouTube atingido (24h)',
                        scheduled_for = datetime('now', '+24 hours')
                    WHERE id = ?;
                """, (pub_id,))
                cursor.execute("UPDATE clips SET youtube_status = 'FAILED_QUOTA' WHERE id = ?;", (clip_id,))
                
                # Adia todas as publicações pendentes do YouTube para daqui a 24 horas
                cursor.execute("""
                    UPDATE publications
                    SET scheduled_for = datetime('now', '+24 hours')
                    WHERE platform = 'youtube' AND status = 'SCHEDULED';
                """)
                conn.commit()
                SignalTracker.emit_finish(
                    "youtube_publisher",
                    "Limite diário de envios atingido no YouTube (24h). Publicações do YouTube pausadas até amanhã.",
                    success=False,
                    metadata={"error": "quota_limit_exceeded"}
                )
                notify_alert("WARNING", "robot2_publish", "Limite Diário YouTube", "Limite diário de vídeos atingido no YouTube Studio. Fila do YouTube reprogramada para amanhã.", conn=conn)

            except Exception as e:
                logger.error(f"Falha ao publicar {pub_id} no {platform}: {e}", exc_info=True)
                cursor.execute("SELECT retry_count FROM publications WHERE id = ?;", (pub_id,))
                row_retries = cursor.fetchone()
                current_retries = row_retries[0] if row_retries else 0

                if current_retries + 1 < 3:
                    # Reprograma para tentar novamente em 5 minutos
                    retry_time_iso = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
                    cursor.execute("""
                        UPDATE publications
                        SET status = 'SCHEDULED',
                            retry_count = retry_count + 1,
                            scheduled_for = ?,
                            error_message = ?
                        WHERE id = ?;
                    """, (retry_time_iso, str(e), pub_id))
                    logger.info(f"Publicação {pub_id} ({platform}) reprogramada para retry em 5 minutos (tentativa {current_retries + 1}/3).")
                else:
                    cursor.execute("""
                        UPDATE publications
                        SET status = 'FAILED',
                            retry_count = retry_count + 1,
                            error_message = ?
                        WHERE id = ?;
                    """, (str(e), pub_id))
                    logger.warning(f"Publicação {pub_id} ({platform}) falhou definitivamente após 3 tentativas.")
                conn.commit()
                notify_alert("WARNING", "robot2_publish", f"Erro Upload ({platform})", str(e), conn=conn)

    return published_count

def run_publisher_cycle() -> Dict[str, int]:
    """Executa um ciclo completo de inteligência, agendamento e postagem."""
    record_heartbeat("robot2_publish", "RUNNING", f"Worker {WORKER_ID} ativo")
    SignalTracker.emit_start(
        "robot2_publish",
        "Ciclo de Publicação & Inteligência",
        total_steps=4,
        message=f"Iniciando ciclo (Worker {WORKER_ID})"
    )
    client = SupoclipClient()

    # Prioridade 1: Despacha imediatamente vídeos cujo horário de publicação já chegou
    pubs_done = process_due_publications()
    SignalTracker.emit_progress("robot2_publish", 1, 4, f"Publicações despachadas com confirmação: {pubs_done}")

    jobs_synced = sync_supoclip_jobs(client)
    SignalTracker.emit_progress("robot2_publish", 2, 4, f"Jobs do Supoclip sincronizados: {jobs_synced}")

    copies_generated = enrich_clips_with_copywriting()
    SignalTracker.emit_progress("robot2_publish", 3, 4, f"Copywritings de clips gerados: {copies_generated}")

    clips_scheduled = schedule_pending_clips()
    SignalTracker.emit_progress("robot2_publish", 4, 4, f"Clips agendados na fila: {clips_scheduled}")

    msg_done = f"Ciclo finalizado. Postagens confirmadas: {pubs_done}, Agendados: {clips_scheduled}"
    record_heartbeat("robot2_publish", "OK", msg_done)
    SignalTracker.emit_finish(
        "robot2_publish",
        msg_done,
        success=True,
        metadata={
            "pubs_done": pubs_done,
            "jobs_synced": jobs_synced,
            "copies_generated": copies_generated,
            "clips_scheduled": clips_scheduled
        }
    )
    return {
        "jobs_synced": jobs_synced,
        "copies_generated": copies_generated,
        "clips_scheduled": clips_scheduled,
        "pubs_done": pubs_done
    }

def main():
    parser = argparse.ArgumentParser(description="Módulo 2: Inteligência e Publicador")
    parser.add_argument("--once", action="store_true", help="Executa um ciclo e encerra")
    args = parser.parse_args()

    logger.info(f"Robô 2 (Publicador) iniciado com ID {WORKER_ID}.")
    while True:
        try:
            run_publisher_cycle()
        except Exception as e:
            logger.error(f"Erro no ciclo do publicador: {e}", exc_info=True)

        if args.once:
            break

        time.sleep(30)

if __name__ == "__main__":
    main()
