"""
Script de Login Interativo no YouTube Studio via Playwright com Perfil Persistente.
Abre o navegador visível para autenticação segura e salva os cookies/sessão.
"""
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
USER_DATA_DIR = ROOT_DIR / "data" / "youtube_browser_profile"
STATE_FILE = CONFIG_DIR / "youtube_state.json"

def login_youtube():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("🚀 INICIANDO LOGIN NO YOUTUBE STUDIO (PERFIL PERSISTENTE)")
    print("=" * 65)
    print("1. Uma janela visível do navegador será aberta.")
    print("2. Faça seu login na sua conta Google / YouTube Studio normalmente.")
    print("3. Conclua qualquer verificação em duas etapas (2FA/SMS/Prompt).")
    print("4. O script aguardará até 10 minutos até você acessar o painel do Studio.")
    print("=" * 65 + "\n")

    with sync_playwright() as p:
        # Tenta abrir com o Chrome do sistema ou Chromium bundled
        context_args = {
            "user_data_dir": str(USER_DATA_DIR),
            "headless": False,
            "args": ["--start-maximized", "--disable-blink-features=AutomationControlled"],
            "no_viewport": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

        try:
            context = p.chromium.launch_persistent_context(**context_args, channel="chrome")
        except Exception:
            # Fallback para Chromium bundled se Chrome não estiver no path padrão
            context = p.chromium.launch_persistent_context(**context_args)

        page = context.pages[0] if context.pages else context.new_page()

        print("Acessando https://studio.youtube.com...")
        try:
            page.goto("https://studio.youtube.com", wait_until="domcontentloaded")
        except Exception as e:
            print(f"Aviso ao carregar URL inicial: {e}")

        print("👉 Por favor, realize o login na janela aberta do navegador...")

        max_wait = 600  # 10 minutos
        start_time = time.time()
        logged_in = False

        while time.time() - start_time < max_wait:
            current_url = page.url.lower()

            # Detecta se já está dentro do YouTube Studio (não mais na tela de signin da Google)
            if "studio.youtube.com" in current_url and "accounts.google.com" not in current_url and "signin" not in current_url:
                cookies = context.cookies()
                cookie_names = [c["name"] for c in cookies]

                # Google authentication cookies essenciais
                has_google_session = any(k in cookie_names for k in ["SID", "SSID", "HSID", "LOGIN_INFO"])

                # Verifica se elementos do painel estão presentes
                is_dashboard = page.locator("#create-icon, #avatar-btn, ytcp-button#create-icon").count() > 0

                if has_google_session or is_dashboard:
                    logged_in = True
                    break

            time.sleep(3)

        if logged_in:
            print("\n🎉 Login no YouTube Studio detectado com sucesso!")
            print("Gravando cookies e sessão persistente...")
            time.sleep(4)
            context.storage_state(path=str(STATE_FILE))
            print(f"✅ Arquivo de estado salvo em: {STATE_FILE}")
            print(f"✅ Diretório de perfil salvo em: {USER_DATA_DIR}")

            # Exporta cookies no formato Netscape para o yt-dlp (downloader)
            cookies_file = CONFIG_DIR / "cookies.txt"
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
            print(f"✅ Arquivo de cookies Netscape para downloads salvo em: {cookies_file}")
            print("🚀 Agora você pode usar o modo de publicação por navegador e downloads automáticos!")
        else:
            print("\n⏰ Tempo limite esgotado sem confirmação do YouTube Studio.")

        context.close()

if __name__ == "__main__":
    login_youtube()
