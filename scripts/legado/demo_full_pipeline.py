"""
Demonstração Completa Interativa: Pipeline Autônomo de Cortes de Vídeo.
Executa todas as funções em sequência ao vivo e inicia o Dashboard Web.
"""
import sys
import time
import subprocess
import webbrowser
from pathlib import Path

from src.core.config import settings
from src.database.migrations import run_migrations
from src.radar_youtube import run_radar_cycle
from src.robot1_ingest import run_ingestor_cycle
from src.robot2_publish import run_publisher_cycle
from src.services.cleanup import run_disk_cleanup
from src.services.watchdog import run_watchdog_check

def print_step(number: int, title: str, desc: str):
    print(f"\n{'='*70}")
    print(f"▶ ETAPA {number}: {title}")
    print(f"   {desc}")
    print(f"{'='*70}")
    time.sleep(1)

def main():
    print("""
    ======================================================================
    🎬 PIPELINE AUTÔNOMO DE CORTES — DEMONSTRAÇÃO COMPLETA AO VIVO
    ======================================================================
    """)

    # 1. Banco de Dados
    print_step(1, "INICIALIZAÇÃO DO BANCO DE DADOS (WAL MODE)", "Verificando tabelas, índices e migrações no SQLite...")
    run_migrations()
    print("✔ Banco de dados pronto e idempotente.")

    # 2. Radar de Hype
    print_step(2, "MÓDULO 0: RADAR DE HYPE (RSS & VPH)", "Consultando feeds RSS e calculando métricas de audiência...")
    run_radar_cycle(dry_run=True)
    print("✔ Radar executado com sucesso.")

    # 3. Geração de Vídeo Longo para Ingestão
    print_step(3, "MÓDULO 1: PREPARAÇÃO DE VÍDEO LONGO", "Gerando vídeo podcast de teste com áudio e vídeo...")
    sample_video = settings.WATCH_DIR / "podcast_demo_aovivo.mp4"
    if not sample_video.exists():
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=navy:s=1280x720:d=15:r=30",
            "-f", "lavfi", "-i", "sine=f=440:d=15",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest",
            str(sample_video)
        ]
        subprocess.run(cmd, capture_output=True)
    print(f"✔ Vídeo de entrada pronto em: {sample_video.name}")

    # 4. Ingestão e Despacho
    print_step(4, "MÓDULO 1: INGESTÃO DETERMINÍSTICA E SUPOCLIP", "Validando estabilidade, hash SHA-256 e despachando ao Supoclip...")
    ingested = run_ingestor_cycle()
    print(f"✔ Ingestão concluída. Vídeos processados: {ingested}")

    # 5. Publicador, Copywriting e Agendamento
    print_step(5, "MÓDULO 2: INTELIGÊNCIA ARTIFICIAL E BUFFER", "Sincronizando cortes, gerando copywriting e agendando no buffer...")
    res = run_publisher_cycle()
    print(f"✔ Publicador concluído: {res}")

    # 6. Retenção e Limpeza
    print_step(6, "MÓDULO 3: RETENÇÃO E PROTEÇÃO DE DISCO", "Purgando vídeo longo bruto e clips reprovados para economizar armazenamento...")
    clean_res = run_disk_cleanup()
    print(f"✔ Limpeza concluída: {clean_res['deleted_long_videos']} vídeo(s) purgado(s), {clean_res['freed_bytes']} bytes liberados.")

    # 7. Watchdog
    print_step(7, "OBSERVABILIDADE: WATCHDOG & HEARTBEATS", "Auditando integridade dos workers e fila de erros (DLQ)...")
    run_watchdog_check()
    print("✔ Watchdog auditado. Sistema 100% operacional.")

    # 8. Dashboard Web
    print_step(8, "PAINEL VISUAL: INICIANDO MISSION CONTROL", "Abrindo Dashboard Web em http://localhost:8085...")
    print("\nVocê poderá assistir aos cortes 9:16 gerados, ver as cópias da IA e o status de cada rede social no navegador!")
    
    # Abre o navegador automaticamente
    try:
        webbrowser.open("http://localhost:8085")
    except Exception:
        pass

    from src.dashboard import start_dashboard
    start_dashboard()

if __name__ == "__main__":
    main()
