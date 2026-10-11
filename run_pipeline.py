"""
Executor Unificado da Pipeline Autonoma de Cortes.
Inicia e gerencia todos os robos (Radar, Ingestor e Publicador) em paralelo.
"""
import time
import sys
import subprocess
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent

PIPELINE_MODULES = [
    ("Robô Ingestor", "src.robot1_ingest", "robot1_ingest.log"),
    ("Fábrica de Cortes", "src.services.media_pipeline_worker", "media_processor.log"),
    ("YouTube Raiz do Éden", "src.services.publish_worker --platform youtube --niche financas", "pub_yt_financas.log"),
    ("YouTube Fitness", "src.services.publish_worker --platform youtube --niche fitness", "pub_yt_fitness.log"),
    ("TikTok Finanças", "src.services.publish_worker --platform tiktok --niche financas", "pub_tk_financas.log"),
    ("TikTok Fitness", "src.services.publish_worker --platform tiktok --niche fitness", "pub_tk_fitness.log"),
    ("Radar de Hype", "src.radar_youtube", "radar_youtube.log"),
    ("Painel Web", "src.dashboard", "dashboard.log"),
    ("Watchdog Guardião", "src.services.watchdog", "watchdog.log"),
]

def get_running_pipeline_processes():
    """Identifica processos Python ativos relacionados à esteira."""
    import os
    matches = []
    try:
        # PowerShell query compatível com Windows
        cmd = [
            "powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | Select-Object ProcessId, CommandLine | ConvertTo-Json"
        ]
        out = subprocess.check_output(cmd, text=True, errors="replace").strip()
        if not out:
            return []
        import json
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        curr_pid = os.getpid()
        for item in data:
            pid = item.get("ProcessId")
            cline = item.get("CommandLine") or ""
            if pid and pid != curr_pid:
                for name, mod, _ in PIPELINE_MODULES:
                    mod_tokens = mod.split()
                    if all(t in cline for t in mod_tokens):
                        matches.append((pid, name, mod, cline))
                        break
    except Exception as e:
        print(f"[!] Erro ao listar processos: {e}")
    return matches

def stop_pipeline():
    """Encerra com segurança todos os processos ativos da esteira."""
    print("=" * 65)
    print(" PARANDO SERVIÇOS DA PIPELINE")
    print("=" * 65)
    procs = get_running_pipeline_processes()
    if not procs:
        print("[OK] Nenhum processo da pipeline está em execução no momento.")
        return
    for pid, name, mod, _ in procs:
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"], check=False)
            print(f"[OK] Encerrado: {name} (PID {pid})")
        except Exception as e:
            print(f"[!] Falha ao encerrar {name} (PID {pid}): {e}")
    print("[OK] Todos os serviços foram finalizados.")

def status_pipeline():
    """Exibe o status dos módulos da esteira."""
    print("=" * 65)
    print(" STATUS DOS MÓDULOS DA PIPELINE")
    print("=" * 65)
    procs = get_running_pipeline_processes()
    running_mods = {mod: (pid, name) for pid, name, mod, _ in procs}
    for name, mod, logf in PIPELINE_MODULES:
        if mod in running_mods:
            pid, _ = running_mods[mod]
            print(f"  [ON]  {name:<22} [ONLINE]  PID: {pid:<7} (Log: logs/{logf})")
        else:
            print(f"  [OFF] {name:<22} [OFFLINE]           (Log: logs/{logf})")
    print("=" * 65)
    print("  Painel Web:   http://localhost:8085")
    print("  Supoclip API: http://localhost:8000")
    print("=" * 65)

def start_worker(module_name: str, log_file_name: str) -> subprocess.Popen:
    log_path = BASE_DIR / "logs" / log_file_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(log_path, "a", encoding="utf-8")
    cmd = [sys.executable, "-m"] + module_name.split()
    proc = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        stdout=f,
        stderr=subprocess.STDOUT
    )
    print(f"[*] {module_name} iniciado com PID {proc.pid} (Log: logs/{log_file_name})")
    return proc

def main():
    parser = argparse.ArgumentParser(description="Gerenciador da Pipeline Autônoma de Cortes")
    parser.add_argument("--stop", action="store_true", help="Para todos os processos da pipeline em execução")
    parser.add_argument("--status", action="store_true", help="Mostra o status de cada módulo da pipeline")
    args = parser.parse_args()

    if args.stop:
        stop_pipeline()
        return

    if args.status:
        status_pipeline()
        return

    print("=" * 65)
    print(" INICIANDO PIPELINE AUTONOMA DE CORTES (MODO REAL)")
    print("=" * 65)

    # Verifica se já há processos rodando
    existing = get_running_pipeline_processes()
    if existing:
        print(f"[!] AVISO: Foram detectados {len(existing)} processo(s) da pipeline já ativos:")
        for pid, name, _, _ in existing:
            print(f"    - {name} (PID {pid})")
        print("[!] Recomenda-se rodar 'python run_pipeline.py --stop' antes de iniciar novamente.")
        print("")

    processes = []
    try:
        for name, mod, logf in PIPELINE_MODULES:
            p = start_worker(mod, logf)
            processes.append((name, mod, logf, p))

        print("")
        print("[OK] Todos os módulos da pipeline estão em execução contínua!")
        print("[*] Painel de Controle ativo em: http://localhost:8085")
        print("[*] Supoclip Engine ativo em: http://localhost:8000")
        print("[*] Pressione Ctrl+C para encerrar todos os processos.")
        print("")

        while True:
            for idx, (name, mod, logf, proc) in enumerate(processes):
                if proc.poll() is not None:
                    print(f"[!] AVISO: Processo {name} (PID {proc.pid}) finalizou com código {proc.returncode}. Reiniciando em 5s...")
                    time.sleep(5)
                    new_proc = start_worker(mod, logf)
                    processes[idx] = (name, mod, logf, new_proc)
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n[*] Encerrando processos da pipeline...")
        for item in processes:
            proc = item[3]
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        print("[OK] Todos os serviços foram encerrados.")

if __name__ == "__main__":
    main()
