"""
Verificador Rápido de Saúde e Sessão das Contas de Publicação (YouTube e TikTok).
Testa em modo headless se cada conta está autenticada ou se requer renovação de login.
"""
import sys
import io
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parent.parent

import json

ACCOUNTS = [
    {
        "name": "YouTube Shorts (Finanças / Raiz do Éden)",
        "platform": "youtube",
        "profile": ROOT / "data" / "youtube_browser_profile_financas",
        "state": ROOT / "config" / "youtube_financas_state.json",
        "url": "https://studio.youtube.com/channel/UC3cuNGcJ39dJ1IbEmIxllfQ/videos/short",
    },
    {
        "name": "YouTube Shorts (Fitness / weslleykebra)",
        "platform": "youtube",
        "profile": ROOT / "data" / "youtube_browser_profile_fitness",
        "state": ROOT / "config" / "youtube_fitness_state.json",
        "url": "https://studio.youtube.com/channel/UCV2JvGLYdsf6s6dDkxIDtWg/videos/short",
    },
    {
        "name": "TikTok (Finanças)",
        "platform": "tiktok",
        "profile": ROOT / "data" / "tiktok_browser_profile_financas",
        "state": ROOT / "config" / "tiktok_financas_state.json",
        "url": "https://www.tiktok.com/tiktokstudio/upload",
    },
    {
        "name": "TikTok (Fitness)",
        "platform": "tiktok",
        "profile": ROOT / "data" / "tiktok_browser_profile_fitness",
        "state": ROOT / "config" / "tiktok_fitness_state.json",
        "url": "https://www.tiktok.com/tiktokstudio/upload",
    },
]

def check_account_health(p, acc):
    name = acc["name"]
    platform = acc["platform"]
    profile = acc["profile"]
    state = acc["state"]
    url = acc["url"]

    if not profile.exists() and not state.exists():
        return False, "Arquivos de sessão ausentes (nunca logado)"

    args = [
        "--start-maximized",
        "--disable-blink-features=AutomationControlled",
        "--window-size=1920,1080",
    ]
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    )

    browser = None
    context = None
    try:
        if platform == "tiktok" and state.exists():
            browser = p.chromium.launch(headless=True, args=args)
            context = browser.new_context(
                storage_state=str(state),
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()
        elif profile.exists():
            ctx_kwargs = {
                "user_data_dir": str(profile),
                "headless": True,
                "args": args,
                "user_agent": user_agent,
                "viewport": {"width": 1920, "height": 1080},
            }
            try:
                context = p.chromium.launch_persistent_context(channel="chrome", **ctx_kwargs)
            except Exception:
                context = p.chromium.launch_persistent_context(**ctx_kwargs)

            if state.exists():
                try:
                    data = json.loads(state.read_text(encoding="utf-8"))
                    cookies = data.get("cookies", [])
                    if cookies:
                        context.add_cookies(cookies)
                except Exception:
                    pass

            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = p.chromium.launch(headless=True, args=args)
            context = browser.new_context(
                storage_state=str(state) if state.exists() else None,
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()

        page.set_default_timeout(25000)
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(4)
        cur_url = page.url.lower()

        if platform == "youtube":
            is_login = any(k in cur_url for k in ["accounts.google.com", "signin", "confirmidentifier", "challenge"])
            if "studio.youtube.com" in cur_url and not is_login:
                return True, "Sessão Ativa no YouTube Studio"
            else:
                return False, f"Exige login (redirecionado para {cur_url[:50]}...)"

        elif platform == "tiktok":
            is_login = any(k in cur_url for k in ["login", "passport.tiktok.com"])
            if ("tiktokstudio" in cur_url or "upload" in cur_url) and not is_login:
                return True, "Sessão Ativa no TikTok Studio"
            else:
                return False, f"Exige login (redirecionado para {cur_url[:50]}...)"

    except Exception as e:
        return False, f"Erro ao testar: {e}"
    finally:
        try:
            if context:
                context.close()
            if browser:
                browser.close()
        except Exception:
            pass

def main():
    print("=" * 65)
    print("  DIAGNÓSTICO DE SAÚDE DAS CONTAS DE PUBLICAÇÃO")
    print("=" * 65)
    results = []
    with sync_playwright() as p:
        for acc in ACCOUNTS:
            print(f"[*] Testando: {acc['name']}...")
            ok, msg = check_account_health(p, acc)
            results.append((acc["name"], ok, msg))

    print("\n" + "=" * 65)
    print("  RESULTADO DO DIAGNÓSTICO:")
    print("=" * 65)
    for name, ok, msg in results:
        status_label = "[ONLINE / LOGADO]" if ok else "[OFFLINE / DESLOGADO]"
        print(f"  {status_label:<24} {name:<42} -> {msg}")
    print("=" * 65)

if __name__ == "__main__":
    main()
