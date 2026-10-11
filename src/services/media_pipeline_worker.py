"""
Fábrica Autônoma de Mídia & Inteligência (src/services/media_pipeline_worker.py).
Responsabilidade Única:
- Sincronização contínua de jobs do Supoclip;
- Smart Reframe Facial Híbrido (1080x1920) & Otimização Audiovisual (Pacing 1.05x);
- Copywriting Magnético via LLM;
- Agendamento atômico de cortes na fila de publicações.

Este módulo NÃO realiza uploads nem abre navegadores web, eliminando concorrência de CPU com os publicadores.
"""
import argparse
import gc
import json
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List

from src.core.config import settings
from src.core.logger import get_logger
from src.core.database import get_db
from src.services.supoclip_client import SupoclipClient
from src.services.llm_copywriter import generate_clip_copy
from src.services.scheduler import schedule_pending_clips
from src.services.media_validator import inspect_media_file, verify_media_integrity
from src.services.watchdog import record_heartbeat
from src.core.process_signals import SignalTracker
from src.core.pipeline_control import PipelineController

logger = get_logger("media_processor")
WORKER_ID = f"media-{uuid.uuid4().hex[:6]}"


def sync_supoclip_jobs(client: SupoclipClient) -> int:
    """Consulta o Supoclip sobre jobs pendentes e processa os clipes gerados."""
    completed_jobs = 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT j.id, j.long_video_id, j.supoclip_job_id, v.file_path as original_file_path
            FROM supoclip_jobs j
            JOIN long_videos v ON j.long_video_id = v.id
            WHERE j.status IN ('SUBMITTED', 'PROCESSING');
        """)
        pending_jobs = [dict(r) for r in cursor.fetchall()]

    for idx, job in enumerate(pending_jobs, 1):
        job_db_id = job["id"]
        long_video_id = job["long_video_id"]
        supo_id = job["supoclip_job_id"]
        original_path = Path(job["original_file_path"])

        record_heartbeat("media_processor", "RUNNING", f"Sincronizando Supoclip {idx}/{len(pending_jobs)}")

        status_data = client.get_job_status(supo_id, original_path)
        current_status = status_data.get("status", "PROCESSING")

        if current_status == "COMPLETED":
            clips_list = status_data.get("clips", [])
            logger.info(
                f"Job {supo_id} CONCLUÍDO no Supoclip. {len(clips_list)} clips gerados.",
                extra={"event": "supoclip_job_completed", "job_id": supo_id, "clips_count": len(clips_list)}
            )

            from src.services.overlap_filter import filter_overlapping_clips

            for c in clips_list:
                c["long_video_id"] = long_video_id
            kept_clips, discarded_clips = filter_overlapping_clips(clips_list, max_overlap_threshold=0.25)
            discarded_uids = {d["clip_uid"]: d.get("_overlap_reason", "Sobreposição temporal detectada") for d in discarded_clips}

            with get_db() as conn:
                cursor = conn.cursor()
                for c in clips_list:
                    clip_uid = c["clip_uid"]
                    virality_score = int(c.get("virality_score", 0))
                    is_overlap = clip_uid in discarded_uids
                    is_qualified = (virality_score >= settings.MIN_VIRALITY_SCORE) and not is_overlap

                    clip_file = Path(c["file_path"])
                    clip_duration = float(c.get("duration_seconds") or 0)

                    # Smart Reframe (Headroom / Blurred Fit)
                    if is_qualified and getattr(settings, "ENABLE_SMART_REFRAME", True) and clip_file.exists():
                        try:
                            from src.services.smart_reframe import apply_smart_reframe
                            apply_smart_reframe(clip_file)
                        except Exception as e_reframe:
                            logger.warning(f"Smart reframe ignorado para clip {clip_uid}: {e_reframe}")

                    # Video Pacing & Retention Loop
                    if is_qualified and (getattr(settings, "ENABLE_VIDEO_PACING", True) or getattr(settings, "ENABLE_SEAMLESS_LOOP", True)) and clip_file.exists():
                        try:
                            from src.services.video_pacing import optimize_clip_pacing
                            if optimize_clip_pacing(clip_file, speed_factor=getattr(settings, "VIDEO_SPEED_FACTOR", 1.05)):
                                media_meta = inspect_media_file(clip_file)
                                clip_duration = round(float(media_meta.get("duration_seconds") or clip_duration), 2)
                        except Exception as e_pacing:
                            logger.warning(f"Otimização de retenção/loop ignorada para clip {clip_uid}: {e_pacing}")

                    mod_status = 'APPROVED' if is_qualified else 'MODERATION_BLOCKED'
                    pub_status = 'PENDING' if is_qualified else 'SKIPPED'
                    err_msg = discarded_uids.get(clip_uid) if is_overlap else None

                    cursor.execute("""
                        INSERT INTO clips (
                            long_video_id, clip_uid, file_path, virality_score,
                            start_seconds, end_seconds, duration_seconds,
                            width, height, fps, transcription_path,
                            moderation_status, youtube_status, tiktok_status,
                            series_id, part_number, total_parts, error_log
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(clip_uid) DO NOTHING;
                    """, (
                        long_video_id, clip_uid, str(clip_file), virality_score,
                        c.get("start_seconds"), c.get("end_seconds"), clip_duration,
                        c.get("width"), c.get("height"), c.get("fps"), c.get("transcription_path"),
                        mod_status, pub_status, pub_status,
                        c.get("series_id"),
                        c.get("part_number", 1),
                        c.get("total_parts", 1),
                        err_msg
                    ))

                cursor.execute("UPDATE supoclip_jobs SET status = 'COMPLETED', completed_at = datetime('now') WHERE id = ?;", (job_db_id,))
                
                # Auto-cleanup de vídeo bruto longo
                is_del = 0
                if getattr(settings, "AUTO_DELETE_LONG_VIDEOS_ON_COMPLETION", True):
                    if original_path and original_path.exists():
                        try:
                            orig_size = original_path.stat().st_size
                            original_path.unlink()
                            is_del = 1
                            logger.info(f"Auto-cleanup: Vídeo longo purgado ({orig_size / (1024*1024):.2f} MB): {original_path.name}")
                        except Exception as e:
                            logger.error(f"Erro ao purgar vídeo longo bruto {original_path}: {e}")

                cursor.execute("UPDATE long_videos SET status = 'COMPLETED', completed_at = datetime('now'), is_deleted_from_disk = ? WHERE id = ?;", (is_del, long_video_id))
            completed_jobs += 1

        elif current_status == "FAILED":
            error_msg = status_data.get("error", "Erro não especificado no Supoclip")
            logger.error(f"Job {supo_id} FALHOU no Supoclip: {error_msg}")
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE supoclip_jobs SET status = 'FAILED', error_message = ? WHERE id = ?;", (error_msg, job_db_id))
                cursor.execute("UPDATE long_videos SET status = 'FAILED', error_message = ? WHERE id = ?;", (error_msg, long_video_id))

    return completed_jobs


def enrich_clips_with_copywriting() -> int:
    """Gera metadados (título, descrição, tags) via LLM para clipes aprovados sem cópia."""
    can_run, reason = PipelineController.can_run_copywriter()
    if not can_run:
        logger.info(reason)
        SignalTracker.emit_progress("media_processor", 0, 1, reason)
        return 0

    enriched_count = 0
    max_copies_per_cycle = getattr(settings, "MAX_COPIES_PER_CYCLE", 2)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
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
        """, (settings.MIN_VIRALITY_SCORE, max_copies_per_cycle))
        clips = [dict(row) for row in cursor.fetchall()]

    for idx, clip in enumerate(clips, 1):
        can_run_next, reason_next = PipelineController.can_run_copywriter()
        if not can_run_next:
            logger.info(f"Interrompendo lote de copywriting: {reason_next}")
            break

        record_heartbeat("media_processor", "RUNNING", f"Gerando copy {idx}/{len(clips)} (clip {clip['clip_uid']})")

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
            niche=clip_niche
        )
        meta = result["metadata"]

        with get_db() as update_conn:
            update_cursor = update_conn.cursor()
            update_cursor.execute("""
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

        time.sleep(1.0)
        gc.collect()

    return enriched_count


def run_media_cycle() -> Dict[str, int]:
    """Executa um ciclo completo de ingestão e preparação de mídia."""
    if PipelineController.is_paused("media_processor"):
        msg = "⏸️ Fábrica de Mídia pausada pelo usuário. Em espera..."
        record_heartbeat("media_processor", "PAUSED", msg)
        SignalTracker.emit_progress("media_processor", 0, 1, msg)
        logger.info(msg)
        return {"jobs_synced": 0, "copies_generated": 0, "clips_scheduled": 0}

    record_heartbeat("media_processor", "RUNNING", f"Worker {WORKER_ID} ativo")
    SignalTracker.emit_start(
        "media_processor",
        "Fábrica de Mídia & Cortes",
        total_steps=3,
        message=f"Iniciando ciclo de processamento (Worker {WORKER_ID})"
    )
    client = SupoclipClient()

    # 1. Sincroniza Supoclip e aplica Smart Reframe + Pacing
    jobs_synced = sync_supoclip_jobs(client)
    SignalTracker.emit_progress("media_processor", 1, 3, f"Jobs do Supoclip sincronizados: {jobs_synced}")

    # 2. Enriquecimento de Copywriting com LLM
    copies_generated = enrich_clips_with_copywriting()
    SignalTracker.emit_progress("media_processor", 2, 3, f"Copywritings de clips gerados: {copies_generated}")

    # 3. Agendamento atômico de cortes prontos na fila
    clips_scheduled = schedule_pending_clips()
    SignalTracker.emit_progress("media_processor", 3, 3, f"Clips agendados na fila: {clips_scheduled}")

    msg_done = f"Ciclo finalizado. Jobs: {jobs_synced}, Copies: {copies_generated}, Agendados: {clips_scheduled}"
    record_heartbeat("media_processor", "OK", msg_done)
    SignalTracker.emit_finish(
        "media_processor",
        msg_done,
        success=True,
        metadata={
            "jobs_synced": jobs_synced,
            "copies_generated": copies_generated,
            "clips_scheduled": clips_scheduled
        }
    )
    return {
        "jobs_synced": jobs_synced,
        "copies_generated": copies_generated,
        "clips_scheduled": clips_scheduled
    }


def main():
    parser = argparse.ArgumentParser(description="Fábrica de Mídia e IA (Processamento de Cortes)")
    parser.add_argument("--once", action="store_true", help="Executa um único ciclo e encerra")
    args = parser.parse_args()

    logger.info(f"Fábrica de Mídia iniciada com ID {WORKER_ID}.")
    while True:
        try:
            run_media_cycle()
        except Exception as e:
            logger.error(f"Erro no ciclo da fábrica de mídia: {e}", exc_info=True)

        if args.once:
            break

        if PipelineController.is_paused("media_processor"):
            time.sleep(5)
        else:
            time.sleep(15)


if __name__ == "__main__":
    main()
