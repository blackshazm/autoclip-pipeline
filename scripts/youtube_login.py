"""
Script de Login Interativo no YouTube Studio via Playwright com Perfil Persistente.
Suporta isolamento multi-nicho (Fitness, Finanças ou Geral).
"""
import sys
import time
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"

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

    print("=" * 65)
    print(f"🚀 INICIANDO LOGIN NO YOUTUBE STUDIO - NICHO: [{niche_clean.upper()}]")
    print("=" * 65)
    print(f"• Perfil do Navegador: {user_data_dir}")
    print(f"• Arquivo de Sessão:    {state_file}")
    print("1. Uma janela visível do navegador será aberta.")
    print("2. Faça o login na conta Google do seu canal do YouTube Studio.")
    print("3. Conclua qualquer verificação em duas etapas (2FA/SMS/Prompt).")
    print("4. O script aguardará até 10 minutos até você acessar o painel do Studio.")
    print("=" * 65 + "\n")

    with sync_playwright() as p:
        context_args = {
            "user_data_dir": str(user_data_dir),
            "headless": False,
            "args": ["--start-maximized", "--disable-blink-features=AutomationControlled"],
            "no_viewport": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

        try:
            context = p.chromium.launch_persistent_context(**context_args, channel="chrome")
        except Exception:
            context = p.chromium.launch_persistent_context(**context_args)

        page = context.pages[0] if context.pages else context.new_page()

        print("Acessando https://studio.youtube.com...")
        try:
            page.goto("https://studio.youtube.com", wait_until="domcontentloaded")
        except Exception as e:
            print(f"Aviso ao carregar URL inicial: {e}")

        print(f"👉 Realize o login para o canal [{niche_clean.upper()}] no navegador aberto.")
        print("💡 DICA: Quando você estiver vendo o painel do YouTube Studio do canal desejado,")
        print("         pressione [ENTER] neste terminal para confirmar e salvar a sessão permanentemente.")
        print("         (O script também detectará automaticamente ao carregar o Studio).")
        print("=" * 65 + "\n")

        max_wait = 600  # 10 minutos
        start_time = time.time()
        logged_in = False

        import threading
        user_confirmed = threading.Event()

        def _wait_input():
            try:
                input("\n👉 [OPCIONAL] Pressione ENTER aqui assim que estiver vendo o YouTube Studio: ")
                user_confirmed.set()
            except Exception:
                pass

        inp_thread = threading.Thread(target=_wait_input, daemon=True)
        inp_thread.start()

        while time.time() - start_time < max_wait:
            if user_confirmed.is_set():
                logged_in = True
                break

            try:
                current_url = page.url.lower()
                is_studio_url = current_url.startswith("https://studio.youtube.com")
                is_login_flow = any(x in current_url for x in ["accounts.google.com", "signin", "confirmidentifier", "challenge"])

                if is_studio_url and not is_login_flow:
                    dashboard_el = page.locator("#create-icon, #avatar-btn, ytcp-button#create-icon, ytcp-entity-page, #entity-name")
                    if dashboard_el.first.is_visible():
                        logged_in = True
                        break
            except Exception:
                break

            time.sleep(2)

        if logged_in:
            print(f"\n🎉 Login no YouTube Studio [{niche_clean.upper()}] confirmado!")
            print("Gravando cookies e sessão persistente...")
            time.sleep(3)
            try:
                context.storage_state(path=str(state_file))
                print(f"✅ Arquivo de estado salvo em: {state_file}")
                print(f"✅ Diretório de perfil salvo em: {user_data_dir}")

                # Exporta cookies no formato Netscape para downloads seguros
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
                print(f"🚀 Conta de YouTube [{niche_clean.upper()}] 100% pronta para publicações!")
            except Exception as s_err:
                print(f"⚠️ Erro ao salvar estado de sessão: {s_err}")
        else:
            print("\n⏰ Tempo limite esgotado ou janela encerrada sem confirmação do YouTube Studio.")

        try:
            context.close()
        except Exception:
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Login no YouTube Studio com isolamento por nicho.")
    parser.add_argument("--niche", type=str, default="fitness", help="Nicho da conta (ex: fitness, financas)")
    args = parser.parse_args()
    login_youtube(niche=args.niche)
