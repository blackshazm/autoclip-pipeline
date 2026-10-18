"""
Script de Login Interativo no TikTok Studio via Playwright com Perfil Persistente.
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

SESSION_COOKIE_NAMES = {"sessionid", "sessionid_ss", "sid_tt", "sessionid_tt", "sid_guard", "sid_ucp_v1"}


def _is_authenticated_tiktok(context) -> tuple[bool, str]:
    """Verifica se o usuário já está autenticado no TikTok via cookies de sessão ou URLs ativas."""
    try:
        # 1. Verifica presença de cookies de autenticação do TikTok
        cookies = context.cookies()
        cookie_names = {c.get("name", "") for c in cookies}
        if cookie_names.intersection(SESSION_COOKIE_NAMES):
            return True, "Sessão autenticada detectada (cookies de sessão presentes)!"

        # 2. Verifica URLs de todas as abas abertas no navegador
        for p in context.pages:
            try:
                if p.is_closed():
                    continue
                u = p.url.lower()
                if "tiktokstudio" in u or "upload" in u or "creator-center" in u:
                    return True, "Painel do TikTok Studio detectado na tela!"
                if "/@" in u and "tiktok.com" in u:
                    return True, "Perfil do TikTok carregado com sucesso!"
            except Exception:
                pass

        return False, "Aguardando login no TikTok..."
    except Exception as e:
        return False, f"Erro ao verificar: {e}"


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
    target_url = "https://www.tiktok.com/tiktokstudio/upload"

    print("=" * 65)
    print(f"🚀 CONEXÃO TIKTOK STUDIO - CANAL: [{niche_clean.upper()}]")
    print("=" * 65)
    print(f"• Perfil:  {user_data_dir}")
    print(f"• Sessão:  {state_file}")
    print("1. O Google Chrome abrirá ajustado ao tamanho normal da sua tela.")
    print("2. Faça o login na conta do TikTok (QR Code ou E-mail/Senha).")
    print("3. O script detecta automaticamente o login ou você pode teclar [ENTER].")
    print("=" * 65 + "\n")

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

    with sync_playwright() as p:
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

        print(f"\n👉 Conclua o login para o canal [{niche_clean.upper()}] no navegador aberto.")
        print("💡 O salvamento dos cookies ocorrerá automaticamente assim que logar.")
        print("   (Você também pode pressionar [ENTER] neste terminal a qualquer momento).")
        print("=" * 65 + "\n")

        max_wait = 600  # 10 minutos
        start_time = time.time()
        logged_in = False
        user_confirmed_input = threading.Event()
        stop_input = threading.Event()

        def _wait_input():
            while not stop_input.is_set():
                try:
                    input("\n👉 [OPCIONAL] Pressione ENTER aqui assim que terminar de logar no navegador: ")
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
                    ok, reason = _is_authenticated_tiktok(context)
                    if not ok:
                        # Tenta navegar para o studio para puxar os cookies caso o usuário já esteja logado
                        try:
                            page.goto(target_url, timeout=15000, wait_until="domcontentloaded")
                            time.sleep(2)
                            ok, reason = _is_authenticated_tiktok(context)
                        except Exception:
                            pass
                    if ok:
                        logged_in = True
                        break
                    else:
                        print(f"⚠️ Atenção: {reason}")
                except Exception as e_chk:
                    print(f"⚠️ Erro ao verificar sessão: {e_chk}")

            try:
                ok, _ = _is_authenticated_tiktok(context)
                if ok:
                    print("\n✨ Login no TikTok Studio detectado automaticamente!")
                    logged_in = True
                    break
            except Exception:
                # Caso o usuário tenha fechado a página
                break

            time.sleep(2)

        stop_input.set()

        if logged_in:
            print(f"\n🎉 Login no TikTok [{niche_clean.upper()}] confirmado!")
            print("Garantindo registro completo dos cookies de criador...")
            try:
                page.goto("https://www.tiktok.com/tiktokstudio/upload", timeout=20000, wait_until="domcontentloaded")
                time.sleep(3)
            except Exception:
                pass

            try:
                if state_file.exists():
                    backup_file = state_file.with_suffix(".json.bak")
                    shutil.copy2(state_file, backup_file)
                    print(f"🛡️ Backup de segurança criado em: {backup_file.name}")

                context.storage_state(path=str(state_file))
                print(f"✅ Sessão salva com sucesso em: {state_file}")
                print(f"✅ Perfil persistente salvo em: {user_data_dir}")
                print(f"🚀 Conta de TikTok [{niche_clean.upper()}] 100% pronta para publicações!")
                success = True
            except Exception as s_err:
                print(f"⚠️ Erro ao salvar estado de sessão: {s_err}")
                success = False
        else:
            print("\n⏰ Tempo limite esgotado ou janela encerrada sem confirmação de login.")
            success = False

        try:
            context.close()
        except Exception:
            pass

        return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Login no TikTok com isolamento por nicho.")
    parser.add_argument("--niche", type=str, default="fitness", help="Nicho da conta (ex: fitness, financas)")
    args = parser.parse_args()
    ok = login_tiktok(niche=args.niche)
    sys.exit(0 if ok else 1)
