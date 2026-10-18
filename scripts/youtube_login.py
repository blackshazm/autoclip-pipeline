"""
Script de Login Interativo no YouTube Studio via Playwright com Perfil Persistente.
Suporta isolamento multi-nicho (Fitness, Finanças ou Geral).
"""
import sys
import time
import argparse
import shutil
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)


def _is_on_studio(page) -> tuple[bool, str]:
    """Verifica se o navegador já saiu da tela de login do Google e está no YouTube Studio."""
    try:
        cur_url = page.url.lower()
        # Se ainda estiver no fluxo de login ou autenticação do Google
        if any(x in cur_url for x in ["accounts.google.com", "/signin", "identifier", "/challenge", "rejected"]):
            return False, "Tela de login do Google ainda aberta. Conclua o login na janela primeiro."

        # Se já estiver no YouTube Studio
        if "studio.youtube.com" in cur_url or "youtube.com/upload" in cur_url:
            return True, "Painel do YouTube Studio carregado com sucesso!"

        return False, f"Aguardando acesso ao YouTube Studio (URL atual: {cur_url[:45]}...)"
    except Exception as e:
        return False, f"Erro ao inspecionar navegador: {e}"


def login_youtube(niche: str = "fitness"):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    niche_clean = niche.lower().strip()
    if niche_clean and niche_clean not in ("default", "general"):
        user_data_dir = ROOT_DIR / "data" / f"youtube_browser_profile_{niche_clean}"
        state_file = CONFIG_DIR / f"youtube_{niche_clean}_state.json"
    else:
        user_data_dir = ROOT_DIR / "data" / "youtube_browser_profile"
        state_file = CONFIG_DIR / "youtube_state.json"

    user_data_dir.mkdir(parents=True, exist_ok=True)
    target_url = "https://studio.youtube.com"

    print("=" * 65)
    print(f"🚀 CONEXÃO YOUTUBE STUDIO - CANAL: [{niche_clean.upper()}]")
    print("=" * 65)
    print(f"• Perfil:  {user_data_dir}")
    print(f"• Sessão:  {state_file}")
    print("1. O Google Chrome abrirá ajustado ao tamanho normal da sua tela.")
    print("2. Faça seu login com a conta Google do canal.")
    print("3. O robô detecta automaticamente o Studio e salva os cookies com segurança.")
    print("=" * 65 + "\n")

    with sync_playwright() as p:
        # Abre no tamanho nativo da tela do usuário, maximizado
        context_args = {
            "user_data_dir": str(user_data_dir),
            "headless": False,
            "args": [
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
            "no_viewport": True,
            "user_agent": USER_AGENT,
            "ignore_default_args": ["--enable-automation"],
        }

        try:
            context = p.chromium.launch_persistent_context(**context_args, channel="chrome")
        except Exception:
            context = p.chromium.launch_persistent_context(**context_args)

        page = context.pages[0] if context.pages else context.new_page()

        print(f"Acessando {target_url}...")
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"Aviso ao carregar URL inicial: {e}")

        print(f"\n👉 Faça o login no navegador aberto.")
        print("💡 Quando o YouTube Studio carregar, o salvamento ocorrerá automaticamente.")
        print("   (Você também pode pressionar [ENTER] neste terminal se preferir).")
        print("=" * 65 + "\n")

        max_wait = 600  # 10 minutos
        start_time = time.time()
        logged_in = False
        user_confirmed_input = threading.Event()
        stop_input = threading.Event()

        def _wait_input():
            while not stop_input.is_set():
                try:
                    input("\n👉 [OPCIONAL] Pressione ENTER aqui assim que estiver vendo o painel do YouTube Studio: ")
                    if stop_input.is_set():
                        break
                    user_confirmed_input.set()
                    break
                except Exception:
                    break

        inp_thread = threading.Thread(target=_wait_input, daemon=True)
        inp_thread.start()

        while time.time() - start_time < max_wait:
            if user_confirmed_input.is_set():
                user_confirmed_input.clear()
                try:
                    ok, reason = _is_on_studio(page)
                    if ok:
                        logged_in = True
                        break
                    else:
                        print(f"⚠️ Atenção: {reason}")
                except Exception as e_chk:
                    print(f"⚠️ Erro ao verificar painel: {e_chk}")

            try:
                ok, _ = _is_on_studio(page)
                if ok:
                    print("\n✨ Painel do YouTube Studio detectado automaticamente!")
                    logged_in = True
                    break
            except Exception:
                # Janela fechada pelo usuário
                break

            time.sleep(2)

        stop_input.set()

        if logged_in:
            print(f"\n🎉 Login no YouTube Studio [{niche_clean.upper()}] confirmado!")
            print("Gravando cookies e sessão persistente de forma segura...")
            time.sleep(3)
            try:
                if state_file.exists():
                    backup_file = state_file.with_suffix(".json.bak")
                    shutil.copy2(state_file, backup_file)
                    print(f"🛡️ Backup de segurança criado em: {backup_file.name}")

                context.storage_state(path=str(state_file))
                print(f"✅ Arquivo de estado salvo com sucesso em: {state_file}")
                print(f"✅ Diretório de perfil atualizado em: {user_data_dir}")

                cookies_file = CONFIG_DIR / f"cookies_{niche_clean}.txt" if niche_clean != "general" else CONFIG_DIR / "cookies.txt"
                all_cookies = context.cookies()
                with open(cookies_file, "w", encoding="utf-8") as f_cook:
                    f_cook.write("# Netscape HTTP Cookie File\n")
                    for c in all_cookies:
                        domain = c.get("domain", "")
                        include_sub = "TRUE" if domain.startswith(".") else "FALSE"
                        path = c.get("path", "/")
                        secure = "TRUE" if c.get("secure", False) else "FALSE"
                        expires = int(c.get("expires", -1))
                        if expires <= 0:
                            expires = 2147483647
                        name = c.get("name", "")
                        val = c.get("value", "")
                        f_cook.write(f"{domain}\t{include_sub}\t{path}\t{secure}\t{expires}\t{name}\t{val}\n")
                print(f"✅ Arquivo de cookies Netscape salvo em: {cookies_file}")
                print(f"🚀 Conta de YouTube [{niche_clean.upper()}] conectada com sucesso e pronta para publicações!")
                success = True
            except Exception as s_err:
                print(f"⚠️ Erro ao salvar estado de sessão: {s_err}")
                success = False
        else:
            print("\n⏰ Tempo limite esgotado ou janela encerrada antes de carregar o YouTube Studio.")
            success = False

        try:
            context.close()
        except Exception:
            pass

        return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Login no YouTube Studio com isolamento por nicho.")
    parser.add_argument("--niche", type=str, default="fitness", help="Nicho da conta (ex: fitness, financas)")
    args = parser.parse_args()
    ok = login_youtube(niche=args.niche)
    sys.exit(0 if ok else 1)
