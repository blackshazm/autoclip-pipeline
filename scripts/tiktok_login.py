import time
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
USER_DATA_DIR = ROOT_DIR / "data" / "tiktok_browser_profile"
STATE_FILE = CONFIG_DIR / "tiktok_state.json"

def login_tiktok():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("🚀 INICIANDO LOGIN NO TIKTOK STUDIO (PERFIL PERSISTENTE)")
    print("=" * 65)
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
                user_data_dir=str(USER_DATA_DIR),
                channel="chrome",
                **context_args
            )
        except Exception:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(USER_DATA_DIR),
                **context_args
            )
        
        page = context.pages[0] if context.pages else context.new_page()

        print("Acessando https://www.tiktok.com/login...")
        page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")

        print("👉 Faça o login no navegador aberto...")
        
        max_wait = 600  # 10 minutos
        start_time = time.time()
        logged_in = False

        while time.time() - start_time < max_wait:
            cookies = context.cookies()
            cookie_names = [c["name"] for c in cookies]

            # Detecta cookies essenciais de autenticação do TikTok
            if any(k in cookie_names for k in ["sessionid", "sessionid_ss", "sid_tt"]):
                logged_in = True
                break

            # Detecta redirecionamento para o feed ou upload
            current_url = page.url.lower()
            if "tiktok.com" in current_url and "login" not in current_url and current_url != "https://www.tiktok.com/":
                logged_in = True
                break

            time.sleep(3)

        if logged_in:
            print("\n🎉 Login detectado com sucesso!")
            print("Navegando até o TikTok Studio para registrar os cookies de criador...")
            try:
                page.goto("https://www.tiktok.com/tiktokstudio/upload", timeout=30000, wait_until="domcontentloaded")
                time.sleep(5)
            except Exception:
                pass

            context.storage_state(path=str(STATE_FILE))
            print(f"✅ Sessão salva com sucesso em: {STATE_FILE}")
            print(f"✅ Perfil persistente salvo em: {USER_DATA_DIR}")
        else:
            print("\n⏰ Tempo limite esgotado sem detecção de login.")

        context.close()

if __name__ == "__main__":
    login_tiktok()
