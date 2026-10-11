"""
Script de Login Interativo no TikTok Studio via Playwright com Perfil Persistente.
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

def login_tiktok(niche: str = "fitness"):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    niche_clean = niche.lower().strip()
    if niche_clean and niche_clean not in ("default", "general"):
        user_data_dir = ROOT_DIR / "data" / f"tiktok_browser_profile_{niche_clean}"
        state_file = CONFIG_DIR / f"tiktok_{niche_clean}_state.json"
    else:
        user_data_dir = ROOT_DIR / "data" / "tiktok_browser_profile"
        state_file = CONFIG_DIR / "tiktok_state.json"

    user_data_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print(f"🚀 INICIANDO LOGIN NO TIKTOK STUDIO - NICHO: [{niche_clean.upper()}]")
    print("=" * 65)
    print(f"• Perfil do Navegador: {user_data_dir}")
    print(f"• Arquivo de Sessão:    {state_file}")
    print("1. Uma janela visível do navegador será aberta.")
    print("2. Faça seu login no TikTok normalmente (QR Code ou E-mail/Senha).")
    print("3. O script aguardará até 10 minutos para você concluir com calma.")
    print("=" * 65 + "\n")

    context_args = {
        "headless": False,
        "args": ["--start-maximized", "--disable-blink-features=AutomationControlled"],
        "no_viewport": True,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                channel="chrome",
                **context_args
            )
        except Exception:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                **context_args
            )

        page = context.pages[0] if context.pages else context.new_page()

        print("Acessando https://www.tiktok.com/login...")
        page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")

        print(f"👉 Faça o login para o canal [{niche_clean.upper()}] no navegador aberto.")
        print("💡 DICA: Quando você estiver vendo o painel do TikTok Studio (tela de Upload de Vídeo),")
        print("         pressione [ENTER] neste terminal para confirmar e salvar os cookies permanentemente.")
        print("         (O script também detectará automaticamente caso você acesse o Studio).")
        print("=" * 65 + "\n")

        max_wait = 600  # 10 minutos
        start_time = time.time()
        logged_in = False

        # Permite detecção automática E confirmação via ENTER
        import threading
        user_confirmed = threading.Event()

        def _wait_input():
            try:
                input("\n👉 [OPCIONAL] Pressione ENTER aqui assim que terminar de logar no navegador: ")
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
                cookies = context.cookies()
                cookie_names = [c["name"] for c in cookies]

                # Validação real: precisa ter cookie de sessão do TikTok
                if any(k in cookie_names for k in ["sessionid", "sessionid_ss", "sid_tt"]):
                    current_url = page.url.lower()
                    if "tiktokstudio" in current_url:
                        logged_in = True
                        break
            except Exception:
                # Caso o usuário tenha fechado a página
                break

            time.sleep(2)

        if logged_in:
            print(f"\n🎉 Login no TikTok [{niche_clean.upper()}] confirmado!")
            print("Garantindo registro completo dos cookies de criador no TikTok Studio...")
            try:
                page.goto("https://www.tiktok.com/tiktokstudio/upload", timeout=30000, wait_until="domcontentloaded")
                time.sleep(4)
            except Exception:
                pass

            try:
                context.storage_state(path=str(state_file))
                print(f"✅ Sessão salva com sucesso em: {state_file}")
                print(f"✅ Perfil persistente salvo em: {user_data_dir}")
                print(f"🚀 Conta de TikTok [{niche_clean.upper()}] 100% pronta para publicações!")
            except Exception as s_err:
                print(f"⚠️ Erro ao salvar estado de sessão: {s_err}")
        else:
            print("\n⏰ Tempo limite esgotado ou janela encerrada sem confirmação de login.")

        try:
            context.close()
        except Exception:
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Login no TikTok com isolamento por nicho.")
    parser.add_argument("--niche", type=str, default="fitness", help="Nicho da conta (ex: fitness, financas)")
    args = parser.parse_args()
    login_tiktok(niche=args.niche)
