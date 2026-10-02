"""
MÓDULO 0: Radar de Hype do YouTube (radar_youtube.py).
Monitoramento contínuo de canais via RSS, cálculo de VPH e download seletivo de virais.
"""
import argparse
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import requests
import json

from src.core.config import settings
from src.core.logger import get_logger
from src.core.database import get_db
from src.services.youtube_metrics import (
    calculate_vph,
    calculate_median_factor,
    calculate_engagement_ratio,
    fetch_video_metrics,
    extract_video_heatmap_and_chapters,
)
from src.services.downloader import download_youtube_video
from src.services.watchdog import record_heartbeat
from src.core.process_signals import SignalTracker

logger = get_logger("radar_youtube")

def fetch_channel_feed(rss_url: str, channel_ref: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Lê feed RSS do YouTube e extrai IDs dos vídeos recentes sem consumir quota de API.
    Em caso de falha do RSS (ex: HTTP 404 ou formato indisponível), utiliza fallback resiliente via yt-dlp.
    """
    try:
        response = requests.get(rss_url, timeout=15)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "yt": "http://www.youtube.com/xml/schemas/2015"
            }

            entries = []
            for entry in root.findall("atom:entry", ns):
                video_id_elem = entry.find("yt:videoId", ns)
                title_elem = entry.find("atom:title", ns)
                published_elem = entry.find("atom:published", ns)

                if video_id_elem is not None and video_id_elem.text:
                    entries.append({
                        "youtube_id": video_id_elem.text,
                        "title": title_elem.text if title_elem is not None else "",
                        "published_at": published_elem.text if published_elem is not None else ""
                    })
            if entries:
                return entries
        else:
            logger.warning(f"Feed RSS indisponível ({rss_url}): HTTP {response.status_code}. Tentando fallback...")
    except Exception as e:
        logger.warning(f"Falha ao ler feed RSS {rss_url}: {e}. Acionando fallback...")

    # Fallback via yt-dlp flat-playlist
    target_channel = channel_ref
    if not target_channel:
        if "channel_id=" in rss_url:
            target_channel = rss_url.split("channel_id=")[-1].split("&")[0]
        else:
            target_channel = rss_url

    if target_channel:
        channel_url = f"https://www.youtube.com/channel/{target_channel}/videos" if target_channel.startswith("UC") else f"https://www.youtube.com/{target_channel}/videos"
        try:
            import subprocess
            import sys
            import json
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--flat-playlist",
                "--dump-single-json",
                "--playlist-items", "1:10",
                "--no-warnings",
                channel_url
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                fallback_entries = []
                for item in data.get("entries", []):
                    v_id = item.get("id")
                    if v_id:
                        fallback_entries.append({
                            "youtube_id": v_id,
                            "title": item.get("title", ""),
                            "published_at": ""
                        })
                if fallback_entries:
                    logger.info(f"Fallback yt-dlp obteve {len(fallback_entries)} vídeos para {target_channel}")
                    return fallback_entries
        except Exception as e:
            logger.error(f"Fallback yt-dlp para canal {target_channel} falhou: {e}")

    return []

def run_radar_cycle(dry_run: bool = False) -> int:
    """Executa um ciclo completo de varredura nos canais monitorados."""
    record_heartbeat("radar_youtube", "RUNNING", f"Ciclo iniciado (dry_run={dry_run})")
    downloads_count = 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM source_channels WHERE active = 1;")
        channels = [dict(r) for r in cursor.fetchall()]

    if not channels:
        logger.warning("Nenhum canal ativo configurado em source_channels.")
        SignalTracker.emit_finish("radar_youtube", "Nenhum canal ativo para monitorar", success=True)
        return 0

    SignalTracker.emit_start(
        "radar_youtube",
        "Varredura de Canais",
        total_steps=len(channels),
        message=f"Monitorando {len(channels)} canais ativos"
    )

    for ch_idx, channel in enumerate(channels, 1):
        channel_id = channel["id"]
        channel_name = channel["name"]
        rss_url = channel["rss_url"]
        min_duration = channel["min_duration_minutes"] * 60
        vph_threshold = channel["vph_absolute_threshold"]
        multiplier_threshold = channel["vph_multiplier_threshold"]
        median_vph = channel["median_vph"] or 1500.0

        SignalTracker.emit_progress(
            "radar_youtube",
            ch_idx,
            len(channels),
            f"Canal {ch_idx}/{len(channels)}: Analisando '{channel_name}'"
        )
        logger.info(f"Varrendo canal '{channel_name}'...", extra={"event": "radar_scan_channel", "channel": channel_name})
        feed_entries = fetch_channel_feed(rss_url, channel_ref=channel["youtube_channel_id"])

        for entry in feed_entries:
            yt_id = entry["youtube_id"]

            # 1. Checa se o vídeo já foi ingerido ou baixado ou rejeitado (transação pontual)
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT status, downloaded_at FROM radar_candidates WHERE youtube_id = ?;", (yt_id,))
                row_cand = cursor.fetchone()
                existing_candidate = dict(row_cand) if row_cand else None
                cursor.execute("SELECT id FROM long_videos WHERE youtube_id = ?;", (yt_id,))
                already_in_long_videos = cursor.fetchone() is not None

            if existing_candidate:
                cand_status = existing_candidate["status"]
                # Se foi rejeitado ou já baixado com sucesso, pula
                if cand_status in ("DOWNLOADED", "REJECTED"):
                    continue
                # Se já está em long_videos, pula
                if already_in_long_videos:
                    continue
                # Se já está QUALIFICADO mas ainda não foi baixado, realiza o download
                if cand_status == "QUALIFIED" and not existing_candidate.get("downloaded_at"):
                    if not dry_run and downloads_count < settings.MAX_DOWNLOADS_PER_CYCLE:
                        downloaded_path = download_youtube_video(yt_id)
                        if downloaded_path and downloaded_path.exists():
                            with get_db() as conn:
                                conn.cursor().execute("""
                                    UPDATE radar_candidates
                                    SET status = 'DOWNLOADED', downloaded_at = datetime('now')
                                    WHERE youtube_id = ?;
                                """, (yt_id,))
                            downloads_count += 1
                    continue

            # 2. Coleta métricas analíticas
            metrics = fetch_video_metrics(yt_id)
            if not metrics:
                continue

            pub_dt = metrics["published_at"]
            now_utc = datetime.now(timezone.utc)
            age_hours = (now_utc - pub_dt).total_seconds() / 3600.0

            # Regra de amostragem temporal: ignora temporariamente vídeos com menos de 2h
            if age_hours < settings.RADAR_MIN_AGE_HOURS:
                logger.debug(f"Vídeo {yt_id} muito recente ({age_hours:.1f}h). Aguardando maturação de métricas.")
                with get_db() as conn:
                    conn.cursor().execute("""
                        INSERT INTO radar_candidates (source_channel_id, youtube_id, title, published_at, status, last_checked_at)
                        VALUES (?, ?, ?, ?, 'MONITORING', datetime('now'))
                        ON CONFLICT(youtube_id) DO UPDATE SET last_checked_at = datetime('now');
                    """, (channel_id, yt_id, metrics["title"], pub_dt.isoformat()))
                continue

            # Ignora vídeos excessivamente antigos (> 48h)
            if age_hours > settings.RADAR_MAX_AGE_HOURS:
                with get_db() as conn:
                    conn.cursor().execute("""
                        INSERT INTO radar_candidates (source_channel_id, youtube_id, title, published_at, status, reject_reason)
                        VALUES (?, ?, ?, ?, 'REJECTED', 'Vídeo com idade acima de 48h')
                        ON CONFLICT(youtube_id) DO UPDATE SET status = 'REJECTED', reject_reason = 'Idade > 48h';
                    """, (channel_id, yt_id, metrics["title"], pub_dt.isoformat()))
                continue

            vph = calculate_vph(metrics["view_count"], pub_dt, reference_time=now_utc)
            median_factor = calculate_median_factor(vph, median_vph)
            duration = metrics["duration_seconds"]
            engagement_ratio = calculate_engagement_ratio(
                metrics["view_count"],
                metrics["like_count"],
                metrics["comment_count"]
            )

            # 3. Gatilhos de Decisão
            # Condição 1: Duração mínima (ignora Shorts e vídeos curtos)
            is_long_enough = duration >= min_duration
            # Condição 2: Hype (VPH alto ou multiplicador acima da mediana)
            is_viral = (vph >= vph_threshold) or (median_factor >= multiplier_threshold)

            if is_long_enough and is_viral:
                logger.info(
                    f"🔥 VÍDEO VIRAL QUALIFICADO: '{metrics['title']}' (VPH: {vph}, Fator: {median_factor}x, Engajamento: {engagement_ratio}%, Duração: {duration // 60}m)",
                    extra={"event": "video_qualified", "youtube_id": yt_id, "vph": vph, "factor": median_factor, "engagement": engagement_ratio}
                )
                with get_db() as conn:
                    conn.cursor().execute("""
                        INSERT INTO radar_candidates (
                            source_channel_id, youtube_id, title, published_at, duration_seconds,
                            view_count, like_count, comment_count, vph, median_factor,
                            status, qualified_at, last_checked_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUALIFIED', datetime('now'), datetime('now'))
                        ON CONFLICT(youtube_id) DO UPDATE SET
                            vph = excluded.vph,
                            median_factor = excluded.median_factor,
                            status = 'QUALIFIED',
                            qualified_at = datetime('now');
                    """, (channel_id, yt_id, metrics["title"], pub_dt.isoformat(), duration,
                          metrics["view_count"], metrics["like_count"], metrics["comment_count"],
                          vph, median_factor))

                # 4. Ação: Download seletivo e Extração de Inteligência
                if not dry_run:
                    if downloads_count < settings.MAX_DOWNLOADS_PER_CYCLE:
                        downloaded_path = download_youtube_video(yt_id)
                        if downloaded_path and downloaded_path.exists():
                            # Salva heatmap e capítulos no arquivo companion .meta.json
                            try:
                                meta_info = extract_video_heatmap_and_chapters(yt_id)
                                meta_info["engagement_ratio"] = engagement_ratio
                                meta_info["vph"] = vph
                                meta_info["title"] = metrics["title"]
                                meta_file = downloaded_path.with_suffix(".meta.json")
                                with open(meta_file, "w", encoding="utf-8") as f_meta:
                                    json.dump(meta_info, f_meta, indent=2, ensure_ascii=False)
                                logger.info(f"Metadados de retenção/heatmap salvos em {meta_file.name}")
                            except Exception as e_meta:
                                logger.warning(f"Falha ao salvar meta.json para {yt_id}: {e_meta}")

                            with get_db() as conn:
                                conn.cursor().execute("""
                                    UPDATE radar_candidates
                                    SET status = 'DOWNLOADED', downloaded_at = datetime('now')
                                    WHERE youtube_id = ?;
                                """, (yt_id,))
                            downloads_count += 1
                    else:
                        logger.info(f"Limite de downloads por ciclo atingido ({settings.MAX_DOWNLOADS_PER_CYCLE}).")
            else:
                reject_reason = []
                if not is_long_enough:
                    reject_reason.append(f"Duração insuficiente ({duration // 60}m < {min_duration // 60}m)")
                if not is_viral:
                    reject_reason.append(f"Abaixo do threshold de hype (VPH: {vph} < {vph_threshold})")

                with get_db() as conn:
                    conn.cursor().execute("""
                        INSERT INTO radar_candidates (
                            source_channel_id, youtube_id, title, published_at, duration_seconds,
                            view_count, vph, median_factor, status, reject_reason, last_checked_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'REJECTED', ?, datetime('now'))
                        ON CONFLICT(youtube_id) DO UPDATE SET
                            vph = excluded.vph,
                            status = 'REJECTED',
                            reject_reason = excluded.reject_reason,
                            last_checked_at = datetime('now');
                    """, (channel_id, yt_id, metrics["title"], pub_dt.isoformat(), duration,
                          metrics["view_count"], vph, median_factor, "; ".join(reject_reason)))

    msg_finish = f"Ciclo finalizado. Vídeos baixados para corte: {downloads_count}"
    record_heartbeat("radar_youtube", "OK", msg_finish)
    SignalTracker.emit_finish("radar_youtube", msg_finish, success=True, metadata={"downloads": downloads_count})
    return downloads_count

def main():
    parser = argparse.ArgumentParser(description="Radar de Hype YouTube")
    parser.add_argument("--dry-run", action="store_true", help="Analisa feeds sem baixar vídeos")
    parser.add_argument("--once", action="store_true", help="Executa apenas um ciclo e encerra")
    parser.add_argument("--add-channel", type=str, help="Adiciona canal por @handle, URL ou channel_id")
    parser.add_argument("--name", type=str, default=None, help="Nome amigável para o canal")
    parser.add_argument("--vph", type=int, default=2000, help="VPH mínimo absoluto para qualificação")
    parser.add_argument("--min-duration", type=int, default=15, help="Duração mínima em minutos")
    parser.add_argument("--list-channels", action="store_true", help="Lista os canais monitorados")
    parser.add_argument("--delete-channel", type=int, help="Remove canal por ID do banco")
    args = parser.parse_args()

    from src.services.channel_manager import add_source_channel, list_source_channels, delete_source_channel

    if args.list_channels:
        channels = list_source_channels()
        print(f"\n=== CANAIS MONITORADOS PELO RADAR ({len(channels)}) ===")
        for ch in channels:
            status_icon = "🟢" if ch["active"] else "🔴"
            print(f"{status_icon} [ID {ch['id']}] {ch['name']} (Channel ID: {ch['youtube_channel_id']})")
            print(f"   VPH Mínimo: {ch['vph_absolute_threshold']} | Duração Mínima: {ch['min_duration_minutes']} min | Licença: {ch['license_mode']}")
            print(f"   Feed: {ch['rss_url']}\n")
        return

    if args.add_channel:
        print(f"Resolvendo e adicionando canal '{args.add_channel}'...")
        try:
            ch = add_source_channel(
                args.add_channel,
                name=args.name,
                min_duration_minutes=args.min_duration,
                vph_threshold=args.vph
            )
            print(f"✅ Canal adicionado com sucesso! [ID {ch['id']}] {ch['name']} ({ch['youtube_channel_id']})")
        except Exception as e:
            print(f"❌ Erro ao adicionar canal: {e}")
        return

    if args.delete_channel:
        ok = delete_source_channel(args.delete_channel)
        if ok:
            print(f"✅ Canal ID {args.delete_channel} removido do monitoramento.")
        else:
            print(f"❌ Canal ID {args.delete_channel} não encontrado.")
        return

    logger.info("Radar de Hype iniciado.")
    while True:
        try:
            run_radar_cycle(dry_run=args.dry_run)
        except Exception as e:
            logger.error(f"Erro no ciclo do radar: {e}", exc_info=True)

        if args.once or args.dry_run:
            break

        time.sleep(settings.RADAR_INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()
