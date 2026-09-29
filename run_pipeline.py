"""
Executor Unificado da Pipeline Autonoma de Cortes.
Inicia e gerencia todos os robos (Radar, Ingestor e Publicador) em paralelo.
"""
import time
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def start_worker(module_name: str, log_file_name: str) -> subprocess.Popen:
    log_path = BASE_DIR / "logs" / log_file_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(log_path, "a", encoding="utf-8")
    cmd = [sys.executable, "-m", module_name]
    proc = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        stdout=f,
        stderr=subprocess.STDOUT
    )
    print(f"[*] {module_name} iniciado com PID {proc.pid} (Log: logs/{log_file_name})")
    return proc

def main():
    print("=" * 65)
    print(" INICIANDO PIPELINE AUTONOMA DE CORTES (MODO REAL)")
    print("=" * 65)

    processes = []
    try:
        p1 = start_worker("src.robot1_ingest", "robot1_ingest.log")
        processes.append(("Robo 1 (Ingestor)", "src.robot1_ingest", "robot1_ingest.log", p1))

        p2 = start_worker("src.robot2_publish", "robot2_publish.log")
        processes.append(("Robo 2 (Publicador)", "src.robot2_publish", "robot2_publish.log", p2))

        p0 = start_worker("src.radar_youtube", "radar_youtube.log")
        processes.append(("Radar de Hype", "src.radar_youtube", "radar_youtube.log", p0))

        p_dash = start_worker("src.dashboard", "dashboard.log")
        processes.append(("Painel Web", "src.dashboard", "dashboard.log", p_dash))

        print("")
        print("[OK] Todos os modulos da pipeline estao em execucao continua!")
        print("[*] Painel de Controle ativo em: http://localhost:8085")
        print("[*] Supoclip Engine ativo em: http://localhost:8000")
        print("[*] Pressione Ctrl+C para encerrar todos os processos.")
        print("")

        while True:
            for idx, (name, mod, logf, proc) in enumerate(processes):
                if proc.poll() is not None:
                    print(f"[!] AVISO: Processo {name} (PID {proc.pid}) finalizou com codigo {proc.returncode}. Reiniciando em 5s...")
                    time.sleep(5)
                    new_proc = start_worker(mod, logf)
                    processes[idx] = (name, mod, logf, new_proc)
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n[*] Encerrando processos da pipeline...")
        for item in processes:
            proc = item[3] if len(item) == 4 else item[1]
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        print("[OK] Todos os servicos foram encerrados.")

if __name__ == "__main__":
    main()
