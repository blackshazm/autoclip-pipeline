"""
MÓDULO 2: Inteligência, Agendamento e Publicação Multiplataforma (robot2_publish.py).

NOTA ARQUITETURAL / RETROCOMPATIBILIDADE:
Este módulo atua como o orquestrador unificado monolítico (all-in-one) mantido para retrocompatibilidade
e execuções manuais (--once). Para escalabilidade e isolamento por nicho/plataforma em produção,
utilize os workers desacoplados em 'src.services.publish_worker' e 'src.services.media_pipeline_worker'.
"""

import argparse
import gc
import json
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict

from src.core.config import settings
from src.core.logger import get_logger
from src.core.database import get_db
from src.services.supoclip_client import SupoclipClient
from src.services.llm_copywriter import generate_clip_copy
from src.services.scheduler import schedule_pending_clips
from src.services.youtube_publisher import YouTubePublisher
from src.services.youtube_browser_publisher import YouTubeBrowserPublisher
from src.services.youtube_browser_publisher_pro import YouTubeBrowserPublisherPro, PublishPayloadPro
from src.services.tiktok_publisher import TikTokPublisher
from src.services.tiktok_browser_publisher import TikTokBrowserPublisher
from src.services.notifier import notify_published_clip, notify_alert, notify_supoclip_job_completed
from src.services.media_validator import verify_media_integrity, inspect_media_file
from src.services.watchdog import record_heartbeat
from src.services.cleanup import check_and_purge_clip_if_fully_published
from src.core.exceptions import QuotaExceededError
from src.core.process_signals import SignalTracker
from src.core.pipeline_control import PipelineController

logger = get_logger("robot2_publish")

WORKER_ID = f"worker-{uuid.uuid4().hex[:6]}"


def sync_supoclip_jobs(client: SupoclipClient) -> int:
    """Consulta o Supoclip sobre o status de jobs pendentes e processa clips gerados."""
    completed_jobs = 0

    # --- Leitura atômica (transação curta) ---
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT j.id, j.long_video_id, j.supoclip_job_id, v.file_path as original_file_path, v.file_name, v.youtube_id
            FROM supoclip_jobs j
            JOIN long_videos v ON j.long_video_id = v.id
            WHERE j.status IN ('SUBMITTED', 'PROCESSING');
        """
        )
        pending_jobs = [dict(r) for r in cursor.fetchall()]

    # --- Chamadas de rede FORA de qualquer transação ---
    for idx, job in enumerate(pending_jobs, 1):
        job_db_id = job["id"]
        long_video_id = job["long_video_id"]
        supo_id = job["supoclip_job_id"]
        original_path = Path(job["original_file_path"])

        record_heartbeat("robot2_publish", "RUNNING", f"Sincronizando Supoclip {idx}/{len(pending_jobs)}")

        status_data = client.get_job_status(supo_id, original_path)
        current_status = status_data.get("status", "PROCESSING")

        if current_status == "COMPLETED":
            clips_list = status_data.get("clips", [])
            logger.info(
                f"Job {supo_id} CONCLUÍDO no Supoclip. {len(clips_list)} clips gerados.",
                extra={"event": "supoclip_job_completed", "job_id": supo_id, "clips_count": len(clips_list)},
            )

            from src.services.overlap_filter import filter_overlapping_clips

            for c in clips_list:
                c["long_video_id"] = long_video_id
            kept_clips, discarded_clips = filter_overlapping_clips(clips_list, max_overlap_threshold=0.25)
            discarded_uids = {
                d["clip_uid"]: d.get("_overlap_reason", "Sobreposição temporal detectada") for d in discarded_clips
            }

            # --- Escrita atômica por job (transação curta) ---
            with get_db() as conn:
                cursor = conn.cursor()
                for c in clips_list:
                    clip_uid = c["clip_uid"]
                    virality_score = int(c.get("virality_score", 0))
                    is_overlap = clip_uid in discarded_uids
                    is_qualified = (virality_score >= settings.MIN_VIRALITY_SCORE) and not is_overlap

                    clip_file = Path(c["file_path"])
                    clip_duration = float(c.get("duration_seconds") or 0)

                    # Aplica Enquadramento Facial Inteligente (Modo Híbrido: Smart Headroom / Blurred Fit) se habilitado
                    if is_qualified and getattr(settings, "ENABLE_SMART_REFRAME", True) and clip_file.exists():
                        try:
                            from src.services.smart_reframe import apply_smart_reframe

                            apply_smart_reframe(clip_file)
                        except Exception as e_reframe:
                            logger.warning(f"Smart reframe ignorado para clip {clip_uid}: {e_reframe}")

                    # Aplica Otimização Audiovisual (Pacing 1.05x, Loudnorm e Seamless Loop) se habilitado
                    if (
                        is_qualified
                        and (
                            getattr(settings, "ENABLE_VIDEO_PACING", True)
                            or getattr(settings, "ENABLE_SEAMLESS_LOOP", True)
                        )
                        and clip_file.exists()
                    ):
                        try:
                            from src.services.video_pacing import optimize_clip_pacing

                            if optimize_clip_pacing(
                                clip_file, speed_factor=getattr(settings, "VIDEO_SPEED_FACTOR", 1.05)
                            ):
                                media_meta = inspect_media_file(clip_file)
                                clip_duration = round(float(media_meta.get("duration_seconds") or clip_duration), 2)
                        except Exception as e_pacing:
                            logger.warning(f"Otimização de retenção/loop ignorada para clip {clip_uid}: {e_pacing}")

                    mod_status = "APPROVED" if is_qualified else "MODERATION_BLOCKED"
                    pub_status = "PENDING" if is_qualified else "SKIPPED"
                    err_msg = discarded_uids.get(clip_uid) if is_overlap else None

                    cursor.execute(
                        """
                        INSERT INTO clips (
                            long_video_id, clip_uid, file_path, virality_score,
                            start_seconds, end_seconds, duration_seconds,
                            width, height, fps, transcription_path,
                            moderation_status, youtube_status, tiktok_status,
                            series_id, part_number, total_parts, error_log
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(clip_uid) DO NOTHING;
                    """,
                        (
                            long_video_id,
                            clip_uid,
                            str(clip_file),
                            virality_score,
                            c.get("start_seconds"),
                            c.get("end_seconds"),
                            clip_duration,
                            c.get("width"),
                            c.get("height"),
                            c.get("fps"),
                            c.get("transcription_path"),
                            mod_status,
                            pub_status,
                            pub_status,
                            c.get("series_id"),
                            c.get("part_number", 1),
                            c.get("total_parts", 1),
                            err_msg,
                        ),
                    )

                cursor.execute(
                    "UPDATE supoclip_jobs SET status = 'COMPLETED', completed_at = datetime('now') WHERE id = ?;",
                    (job_db_id,),
                )

                # Auto-cleanup imediato do vídeo longo bruto original pós-fatiamento
                is_del = 0
                if getattr(settings, "AUTO_DELETE_LONG_VIDEOS_ON_COMPLETION", True):
                    if original_path and original_path.exists():
                        try:
                            orig_size = original_path.stat().st_size
                            original_path.unlink()
                            is_del = 1
                            logger.info(
                                f"Auto-cleanup: Vídeo longo bruto purgado ({orig_size / (1024*1024):.2f} MB): {original_path.name}",
                                extra={"event": "purge_long_video_on_sync", "video_id": long_video_id},
                            )
                        except Exception as e:
                            logger.error(f"Erro ao purgar vídeo longo bruto {original_path}: {e}")

                cursor.execute(
                    "UPDATE long_videos SET status = 'COMPLETED', completed_at = datetime('now'), is_deleted_from_disk = ? WHERE id = ?;",
                    (is_del, long_video_id),
                )
            completed_jobs += 1

            # Dispara notificação comemorativa de cortes prontos
            try:
                video_name = job.get("file_name") or original_path.name
                total_c = len(clips_list)
                qual_c = len([c for c in prepared_clips if c[11] == "APPROVED"])
                top_sc = max([c[3] for c in prepared_clips], default=0)
                notify_supoclip_job_completed(
                    job_id=supo_id,
                    video_title=video_name,
                    total_clips=total_c,
                    qualified_clips=qual_c,
                    top_score=top_sc,
                )
            except Exception as e_notif:
                logger.warning(f"Aviso ao enviar notificação de conclusão do Supoclip: {e_notif}")

        elif current_status == "FAILED":
            error_msg = status_data.get("error", "Erro não especificado no Supoclip")
            logger.error(f"Job {supo_id} FALHOU no Supoclip: {error_msg}")
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE supoclip_jobs SET status = 'FAILED', error_message = ? WHERE id = ?;",
                    (error_msg, job_db_id),
                )
                cursor.execute(
                    "UPDATE long_videos SET status = 'FAILED', error_message = ? WHERE id = ?;",
                    (error_msg, long_video_id),
                )

    return completed_jobs


def enrich_clips_with_copywriting() -> int:
    """Gera metadados (título, descrição, tags) via LLM para clips aprovados sem cópia (cadenciado)."""
    # 1. Checa condições de segurança de memória e concorrência via PipelineController
    can_run, reason = PipelineController.can_run_copywriter()
    if not can_run:
        logger.info(reason)
        SignalTracker.emit_progress("llm_copywriter", 0, 1, reason)
        return 0

    enriched_count = 0
    max_copies_per_cycle = getattr(settings, "MAX_COPIES_PER_CYCLE", 2)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.id, c.clip_uid, c.transcription_path, c.virality_score, c.series_id, c.part_number, c.total_parts,
                   COALESCE(sc.niche, 'general') as clip_niche
            FROM clips c
            LEFT JOIN long_videos lv ON c.long_video_id = lv.id
            LEFT JOIN source_channels sc ON lv.source_channel_id = sc.id
            WHERE c.virality_score >= ? 
              AND c.moderation_status = 'APPROVED'
              AND c.title IS NULL
            ORDER BY c.id ASC
            LIMIT ?;
        """,
            (settings.MIN_VIRALITY_SCORE, max_copies_per_cycle),
        )
        clips = [dict(row) for row in cursor.fetchall()]

    for idx, clip in enumerate(clips, 1):
        # Reavalia condições de memória antes de cada clip
        can_run_next, reason_next = PipelineController.can_run_copywriter()
        if not can_run_next:
            logger.info(f"Interrompendo lote de copywriting: {reason_next}")
            break

        record_heartbeat("robot2_publish", "RUNNING", f"Gerando copy {idx}/{len(clips)} (clip {clip['clip_uid']})")

        clip_id = clip["id"]
        clip_niche = clip.get("clip_niche") or "general"
        trans_path = Path(clip["transcription_path"]) if clip["transcription_path"] else None

        transcript_text = ""
        if trans_path and trans_path.exists():
            with open(trans_path, "r", encoding="utf-8") as f:
                transcript_text = f.read()

        if not transcript_text:
            transcript_text = f"Corte de alta retenção {clip['clip_uid']} com score {clip['virality_score']}."

        result = generate_clip_copy(
            clip_id,
            transcript_text,
            conn=None,
            part_number=clip["part_number"] or 1,
            total_parts=clip["total_parts"] or 1,
            niche=clip_niche,
        )
        meta = result["metadata"]

        with get_db() as update_conn:
            update_cursor = update_conn.cursor()
            update_cursor.execute(
                """
                UPDATE clips
                SET title = ?,
                    description = ?,
                    tags = ?,
                    metadata_json = ?,
                    llm_fallback_used = ?
                WHERE id = ?;
            """,
                (
                    meta["title"],
                    meta["description"],
                    json.dumps(meta["tags"]),
                    json.dumps(meta),
                    1 if result["is_fallback"] else 0,
                    clip_id,
                ),
            )

        enriched_count += 1
        logger.info(
            f"Copywriting gerado para clip {clip['clip_uid']}: '{meta['title']}'",
            extra={"event": "copywriting_done", "clip_id": clip_id, "title": meta["title"]},
        )

        # Pausa de estabilização e coleta de lixo entre cada corte
        time.sleep(1.0)
        gc.collect()

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
        cursor.execute(
            """
            UPDATE publications
            SET status = 'RECONCILING'
            WHERE status = 'UPLOADING' AND (lease_expires_at < ? OR lease_expires_at < datetime('now'));
        """,
            (now_iso,),
        )
        reconciled = cursor.rowcount
        if reconciled > 0:
            logger.warning(
                f"{reconciled} publicações marcadas para reconciliação pós-crash/timeout.",
                extra={"event": "reconciliation_marked"},
            )
        conn.commit()

        # 2. Busca publicações prontas para envio com dados de conta e nicho
        max_pubs = getattr(settings, "MAX_PUBLICATIONS_PER_CYCLE", 5)
        cursor.execute(
            """
            SELECT p.id, p.clip_id, p.platform, p.publishing_account_id,
                   c.clip_uid, c.file_path, c.title, c.description, c.tags, c.virality_score,
                   pa.profile_name, pa.credentials_ref, pa.external_channel_id, pa.niche as account_niche
            FROM publications p
            JOIN clips c ON p.clip_id = c.id
            LEFT JOIN publishing_accounts pa ON p.publishing_account_id = pa.id
            WHERE p.status = 'SCHEDULED' AND p.scheduled_for <= ?
            ORDER BY p.scheduled_for ASC
            LIMIT ?;
        """,
            (now_iso, max_pubs),
        )
        due_pubs = cursor.fetchall()

        exhausted_account_ids = set()
        for idx, pub_row in enumerate(due_pubs, 1):
            pub = dict(pub_row)
            pub_id = pub["id"]
            clip_id = pub["clip_id"]
            platform = pub["platform"]
            clip_uid = pub["clip_uid"]
            file_path = Path(pub["file_path"])
            title = pub["title"] or "Corte #Shorts"
            description = pub["description"] or ""
            tags = json.loads(pub["tags"]) if pub["tags"] else ["#shorts", "#cortes"]

            record_heartbeat("robot2_publish", "RUNNING", f"Publicando {idx}/{len(due_pubs)} ({platform})", conn=conn)

            if pub.get("publishing_account_id") in exhausted_account_ids:
                logger.info(
                    f"Pulando publicação {pub_id} ({platform}) pois a conta {pub.get('publishing_account_id')} já atingiu cota hoje."
                )
                continue

            # 3. Tenta adquirir Lease Lock atômico
            lease_exp_iso = (now_dt + timedelta(minutes=25)).isoformat()
            cursor.execute(
                """
                UPDATE publications
                SET status = 'UPLOADING',
                    lease_owner = ?,
                    lease_expires_at = ?
                WHERE id = ? AND status = 'SCHEDULED';
            """,
                (WORKER_ID, lease_exp_iso, pub_id),
            )

            if cursor.rowcount == 0:
                continue  # Outro worker adquiriu o lease

            conn.commit()  # Libera o lock de escrita do SQLite imediatamente para outros processos!
            logger.info(
                f"Lease adquirido para publicação {pub_id} ({platform}). Disparando upload...",
                extra={"event": "lease_acquired", "pub_id": pub_id},
            )

            # Valida que o vídeo é íntegro e não é tela preta/vazia
            if not verify_media_integrity(file_path):
                logger.error(
                    f"Publicação {pub_id} abortada: o arquivo {file_path.name} está corrompido ou é tela preta."
                )
                cursor.execute(
                    """
                    UPDATE publications SET status = 'FAILED', error_message = 'Arquivo inválido ou tela preta detectada' WHERE id = ?;
                """,
                    (pub_id,),
                )
                cursor.execute(
                    """
                    UPDATE clips SET moderation_status = 'MODERATION_BLOCKED', error_log = 'Arquivo inválido ou tela preta detectada' WHERE id = ?;
                """,
                    (clip_id,),
                )
                try:
                    notify_alert(
                        "WARNING",
                        "robot2_publish",
                        f"Arquivo Inválido ({platform})",
                        f"O arquivo {file_path.name} está corrompido ou é tela preta.",
                        conn=conn,
                    )
                except Exception:
                    pass
                conn.commit()
                continue

            try:
                if platform == "youtube":
                    yt_res = None
                    if getattr(settings, "YOUTUBE_PUBLISHER_MODE", "api") == "browser":
                        try:
                            acc_niche = pub.get("account_niche") or "general"
                            cred_ref = pub.get("credentials_ref")
                            ext_ch_id = pub.get("external_channel_id")
                            yt_pdir = (
                                Path(f"./data/youtube_browser_profile_{acc_niche}")
                                if acc_niche not in ("general", "default")
                                else settings.YOUTUBE_BROWSER_PROFILE_DIR
                            )
                            yt_sfile = (
                                Path(cred_ref)
                                if cred_ref
                                else (
                                    Path(f"./config/youtube_{acc_niche}_state.json")
                                    if acc_niche not in ("general", "default")
                                    else settings.YOUTUBE_BROWSER_STATE_FILE
                                )
                            )

                            niche_categories = {
                                "financas": "Educação",
                                "fitness": "Esportes",
                                "general": "Entretenimento",
                                "default": "Entretenimento",
                            }
                            category_name = niche_categories.get(str(acc_niche).lower(), "Entretenimento")

                            if getattr(settings, "YOUTUBE_BROWSER_ENGINE", "pro") == "pro":
                                browser_pub = YouTubeBrowserPublisherPro(
                                    profile_dir=yt_pdir,
                                    state_file=yt_sfile,
                                    channel_id=ext_ch_id,
                                    headless=settings.YOUTUBE_BROWSER_HEADLESS,
                                )
                                payload = PublishPayloadPro(
                                    video_path=file_path,
                                    title=title,
                                    description=description,
                                    tags=tags or [],
                                    category_name=category_name,
                                    language="Português (Brasil)",
                                    is_synthetic_ai=getattr(settings, "YOUTUBE_DEFAULT_AI_DISCLOSURE", True),
                                    publish_mode="PUBLIC",
                                    clip_uid=clip_uid,
                                )
                                yt_res = browser_pub.publish_short_pro(payload)
                            else:
                                browser_pub = YouTubeBrowserPublisher(
                                    profile_dir=yt_pdir, state_file=yt_sfile, channel_id=ext_ch_id
                                )
                                yt_res = browser_pub.publish_short(file_path, title, description, tags, clip_uid)
                        except Exception as browser_err:
                            if getattr(settings, "YOUTUBE_BROWSER_FALLBACK_TO_API", True):
                                logger.warning(
                                    f"Falha no YouTube Browser Publisher ({acc_niche}): {browser_err}. Acionando fallback automático para API oficial..."
                                )
                                yt_res = yt_publisher.publish_short(file_path, title, description, tags, clip_uid)
                            else:
                                raise browser_err
                    else:
                        yt_res = yt_publisher.publish_short(file_path, title, description, tags, clip_uid)

                    yt_id = yt_res.get("youtube_video_id")

                    cursor.execute(
                        """
                        UPDATE publications
                        SET status = 'POSTED', published_at = datetime('now'), external_id = ?, response_json = ?
                        WHERE id = ?;
                    """,
                        (yt_id, json.dumps(yt_res), pub_id),
                    )

                    cursor.execute(
                        """
                        UPDATE clips
                        SET youtube_status = 'POSTED', youtube_video_id = ?, published_at = datetime('now')
                        WHERE id = ?;
                    """,
                        (yt_id, clip_id),
                    )

                    conn.commit()
                    published_count += 1
                    try:
                        notify_published_clip(
                            {"title": title, "virality_score": pub["virality_score"]},
                            {"youtube": f"https://youtube.com/shorts/{yt_id}"},
                        )
                    except Exception as e_notif:
                        logger.warning(f"Falha ao enviar notificação de publicação ({platform}): {e_notif}")

                    try:
                        # Hook de Auto-Cleanup reativo imediato (se publicado em ambas as plataformas)
                        check_and_purge_clip_if_fully_published(clip_id, conn=conn)
                    except Exception as e_purge:
                        logger.warning(f"Aviso ao verificar auto-cleanup do clipe {clip_id}: {e_purge}")

                elif platform == "tiktok":
                    tk_res = None
                    if getattr(settings, "TIKTOK_PUBLISHER_MODE", "browser") == "browser":
                        try:
                            acc_niche = pub.get("account_niche") or "general"
                            cred_ref = pub.get("credentials_ref")
                            tk_pdir = (
                                Path(f"./data/tiktok_browser_profile_{acc_niche}")
                                if acc_niche not in ("general", "default")
                                else getattr(
                                    settings, "TIKTOK_BROWSER_PROFILE_DIR", Path("./data/tiktok_browser_profile")
                                )
                            )
                            tk_sfile = (
                                Path(cred_ref)
                                if cred_ref
                                else (
                                    Path(f"./config/tiktok_{acc_niche}_state.json")
                                    if acc_niche not in ("general", "default")
                                    else getattr(
                                        settings, "TIKTOK_BROWSER_STATE_FILE", Path("./config/tiktok_state.json")
                                    )
                                )
                            )

                            browser_tk = TikTokBrowserPublisher(profile_dir=tk_pdir, state_file=tk_sfile)
                            tk_res = browser_tk.publish_video(file_path, title, tags, clip_uid)
                        except Exception as tk_browser_err:
                            if getattr(settings, "TIKTOK_BROWSER_FALLBACK_TO_API", False):
                                logger.warning(
                                    f"Falha no TikTokBrowserPublisher ({acc_niche}): {tk_browser_err}. Acionando fallback para API oficial..."
                                )
                                tk_res = tk_publisher.publish_video(file_path, title, tags, clip_uid)
                            else:
                                raise tk_browser_err
                    else:
                        tk_res = tk_publisher.publish_video(file_path, title, tags, clip_uid)

                    tk_id = tk_res.get("tiktok_post_id")

                    cursor.execute(
                        """
                        UPDATE publications
                        SET status = 'POSTED', published_at = datetime('now'), external_id = ?, response_json = ?
                        WHERE id = ?;
                    """,
                        (tk_id, json.dumps(tk_res), pub_id),
                    )

                    cursor.execute(
                        """
                        UPDATE clips
                        SET tiktok_status = 'POSTED', tiktok_post_id = ?
                        WHERE id = ?;
                    """,
                        (tk_id, clip_id),
                    )

                    conn.commit()
                    published_count += 1
                    try:
                        notify_published_clip(
                            {"title": title, "virality_score": pub["virality_score"]},
                            {"tiktok": f"https://www.tiktok.com/@post/{tk_id}"},
                        )
                    except Exception as e_notif:
                        logger.warning(f"Falha ao enviar notificação de publicação ({platform}): {e_notif}")

                    try:
                        # Hook de Auto-Cleanup reativo imediato (se publicado em ambas as plataformas)
                        check_and_purge_clip_if_fully_published(clip_id, conn=conn)
                    except Exception as e_purge:
                        logger.warning(f"Aviso ao verificar auto-cleanup do clipe {clip_id}: {e_purge}")

            except QuotaExceededError:
                logger.error(
                    f"Limite diário de upload atingido no YouTube ao processar {pub_id}. Pausando fila do YouTube por 24h."
                )
                exhausted_account_ids.add(pub.get("publishing_account_id"))
                cool_24h = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
                cursor.execute(
                    """
                    UPDATE publications
                    SET status = 'FAILED_QUOTA',
                        error_message = 'Limite diário do YouTube atingido (24h)',
                        scheduled_for = ?,
                        lease_owner = NULL,
                        lease_expires_at = NULL
                    WHERE id = ?;
                """,
                    (cool_24h, pub_id),
                )
                cursor.execute("UPDATE clips SET youtube_status = 'FAILED_QUOTA' WHERE id = ?;", (clip_id,))

                # Adia apenas as publicações pendentes da CONTA ESPECÍFICA para daqui a 24 horas
                cursor.execute(
                    """
                    UPDATE publications
                    SET scheduled_for = ?, lease_owner = NULL, lease_expires_at = NULL
                    WHERE platform = 'youtube' AND publishing_account_id = ? AND status = 'SCHEDULED';
                """,
                    (cool_24h, pub["publishing_account_id"]),
                )
                conn.commit()
                SignalTracker.emit_finish(
                    "youtube_publisher",
                    "Limite diário de envios atingido no YouTube (24h). Publicações do YouTube pausadas até amanhã.",
                    success=False,
                    metadata={"error": "quota_limit_exceeded"},
                )
                notify_alert(
                    "WARNING",
                    "robot2_publish",
                    "Limite Diário YouTube",
                    "Limite diário de vídeos atingido no YouTube Studio. Fila do YouTube reprogramada para amanhã.",
                    conn=conn,
                )

            except Exception as e:
                logger.error(f"Falha ao publicar {pub_id} no {platform}: {e}", exc_info=True)
                cursor.execute("SELECT status, retry_count FROM publications WHERE id = ?;", (pub_id,))
                row_pub = cursor.fetchone()
                # Blindagem: se a publicação já estiver como POSTED, NUNCA reverter para SCHEDULED
                if row_pub and row_pub["status"] == "POSTED":
                    logger.warning(
                        f"Publicação {pub_id} já confirmada como POSTED. Reversão bloqueada para evitar republicação."
                    )
                    continue

                current_retries = row_pub["retry_count"] if row_pub else 0

                if current_retries + 1 < 3:
                    # Reprograma para tentar novamente em 5 minutos
                    retry_time_iso = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
                    cursor.execute(
                        """
                        UPDATE publications
                        SET status = 'SCHEDULED',
                            retry_count = retry_count + 1,
                            scheduled_for = ?,
                            error_message = ?
                        WHERE id = ?;
                    """,
                        (retry_time_iso, str(e), pub_id),
                    )
                    logger.info(
                        f"Publicação {pub_id} ({platform}) reprogramada para retry em 5 minutos (tentativa {current_retries + 1}/3)."
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE publications
                        SET status = 'FAILED',
                            retry_count = retry_count + 1,
                            error_message = ?
                        WHERE id = ?;
                    """,
                        (str(e), pub_id),
                    )
                    if platform == "youtube":
                        cursor.execute(
                            "UPDATE clips SET youtube_status = 'FAILED', error_log = ? WHERE id = ?;", (str(e), clip_id)
                        )
                    elif platform == "tiktok":
                        cursor.execute(
                            "UPDATE clips SET tiktok_status = 'FAILED', error_log = ? WHERE id = ?;", (str(e), clip_id)
                        )
                    logger.warning(f"Publicação {pub_id} ({platform}) falhou definitivamente após 3 tentativas.")
                conn.commit()
                try:
                    notify_alert("WARNING", "robot2_publish", f"Erro Upload ({platform})", str(e), conn=conn)
                except Exception as alert_err:
                    logger.debug(f"Erro ao disparar notify_alert pós-falha de publicação: {alert_err}")

    return published_count


def run_publisher_cycle() -> Dict[str, int]:
    """Executa um ciclo completo de inteligência, agendamento e postagem."""
    if PipelineController.is_paused("robot2_publish"):
        msg = "⏸️ Robô 2 (Publicador) pausado pelo usuário. Em espera..."
        record_heartbeat("robot2_publish", "PAUSED", msg)
        SignalTracker.emit_progress("robot2_publish", 0, 1, msg)
        logger.info(msg)
        return {"jobs_synced": 0, "copies_generated": 0, "clips_scheduled": 0, "pubs_done": 0}

    record_heartbeat("robot2_publish", "RUNNING", f"Worker {WORKER_ID} ativo")
    SignalTracker.emit_start(
        "robot2_publish",
        "Ciclo de Publicação & Inteligência",
        total_steps=4,
        message=f"Iniciando ciclo (Worker {WORKER_ID})",
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
            "clips_scheduled": clips_scheduled,
        },
    )
    return {
        "jobs_synced": jobs_synced,
        "copies_generated": copies_generated,
        "clips_scheduled": clips_scheduled,
        "pubs_done": pubs_done,
    }


def main():
    parser = argparse.ArgumentParser(description="Módulo 2: Inteligência e Publicador")
    parser.add_argument("--once", action="store_true", help="Executa um ciclo e encerra")
    args = parser.parse_args()

    logger.info(
        f"Robô 2 (Orquestrador Unificado) iniciado com ID {WORKER_ID}. (Para isolamento por nicho/plataforma em produção, utilize 'src.services.publish_worker')."
    )
    while True:
        try:
            run_publisher_cycle()
        except Exception as e:
            logger.error(f"Erro no ciclo do publicador: {e}", exc_info=True)

        if args.once:
            break

        if PipelineController.is_paused("robot2_publish"):
            time.sleep(5)
        else:
            time.sleep(30)


if __name__ == "__main__":
    main()
