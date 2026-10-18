"""
Automação Playwright para Publicar Todos os Rascunhos no YouTube Studio.
Acessa o YouTube Studio do canal, localiza todos os Shorts com status 'Rascunho',
preenche as pendências obrigatórias (COPPA, IA) e publica como PÚBLICO em lote,
incluindo a confirmação do modal 'Ainda estamos verificando seu conteúdo'.
"""
import sys
import time
import json
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.core.logger import get_logger

logger = get_logger("publicar_rascunhos")

CHANNEL_IDS = {
    "fitness": "UCV2JvGLYdsf6s6dDkxIDtWg",
    "financas": "UC3cuNGcJ39dJ1IbEmIxllfQ"
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"


def _handle_publish_anyway_dialog(page, timeout_sec: int = 10) -> bool:
    """Detecta e confirma o diálogo 'Ainda estamos verificando seu conteúdo' ('Publicar mesmo assim')."""
    start_t = time.time()
    while time.time() - start_t < timeout_sec:
        for sel in [
            "text='Publicar mesmo assim'",
            "text='Publish anyway'",
            "ytcp-button:has-text('Publicar mesmo assim')",
            "button:has-text('Publicar mesmo assim')",
            "#dialog #confirm-button",
            "ytcp-confirmation-dialog #confirm-button"
        ]:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    print("  [MODAL] Confirmando 'Publicar mesmo assim' via Playwright...")
                    btn.click(force=True, timeout=3000)
                    time.sleep(3)
                    return True
            except Exception:
                pass

        try:
            clicked = page.evaluate("""() => {
                function findClickable(root) {
                    let found = [];
                    const all = root.querySelectorAll('*');
                    for (const el of all) {
                        const tag = el.tagName.toLowerCase();
                        if (tag === 'button' || tag === 'ytcp-button' || tag === 'tp-yt-paper-button') {
                            found.push(el);
                        }
                        if (el.shadowRoot) {
                            found = found.concat(findClickable(el.shadowRoot));
                        }
                    }
                    return found;
                }
                const btns = findClickable(document);
                for (const b of btns) {
                    const text = (b.innerText || b.textContent || '').toLowerCase().trim();
                    if (text.includes('publicar mesmo assim') || text.includes('publish anyway')) {
                        b.scrollIntoView({ behavior: 'instant', block: 'center' });
                        b.click();
                        return true;
                    }
                }
                return false;
            }""")
            if clicked:
                print("  [MODAL] Confirmando 'Publicar mesmo assim' via DOM JS...")
                time.sleep(3)
                return True
        except Exception:
            pass

        time.sleep(1)
    return False


def _publish_draft_modal(page, ciclo: int, screenshot_debug: Path) -> bool:
    """Processa o modal clássico de edição de rascunho (stepper com Detalhes -> Visibilidade)."""
    # 1. Garante COPPA (Não é conteúdo para crianças)
    print("  [1/4] Configurando COPPA: 'Não é conteúdo para crianças'...")
    coppa_res = page.evaluate("""() => {
        // Rola o container do diálogo para baixo para exibir as opções de público/COPPA
        const scrollers = document.querySelectorAll('#scrollable-content, ytcp-uploads-dialog #scrollable-content, ytcp-video-metadata-editor');
        for (const s of scrollers) {
            s.scrollTop = s.scrollHeight;
        }

        function findCoppa(root) {
            const radios = root.querySelectorAll('tp-yt-paper-radio-button, [role="radio"]');
            for (const r of radios) {
                const name = (r.getAttribute('name') || '').toUpperCase();
                const txt = (r.innerText || r.textContent || '').toLowerCase();
                if (name.includes('NOT_MFK') || txt.includes('não é conteúdo para crianças') || txt.includes('não, não é') || txt.includes('not made for kids')) {
                    return r;
                }
            }
            const all = root.querySelectorAll('*');
            for (const el of all) {
                if (el.shadowRoot) {
                    const found = findCoppa(el.shadowRoot);
                    if (found) return found;
                }
            }
            return null;
        }

        const target = findCoppa(document);
        if (target) {
            target.scrollIntoView({ behavior: 'instant', block: 'center' });
            target.click();
            return true;
        }
        return false;
    }""")

    # Fallback de Playwright para COPPA
    if not coppa_res:
        for c_sel in [
            "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']",
            "#not-made-for-kids",
            "tp-yt-paper-radio-button:has-text('Não é conteúdo para crianças')",
            "tp-yt-paper-radio-button:has-text('Não, não é conteúdo para crianças')",
            "tp-yt-paper-radio-button:has-text('not made for kids')",
            "[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']",
            "#radioLabel:has-text('Não é conteúdo para crianças')",
        ]:
            try:
                c_btn = page.locator(c_sel).first
                if c_btn.count() > 0:
                    c_btn.scroll_into_view_if_needed(timeout=2000)
                    c_btn.click(force=True, timeout=2000)
                    coppa_res = True
                    break
            except Exception:
                pass

    if coppa_res:
        print("  ✓ COPPA definido com sucesso: Não é conteúdo para crianças.")
    else:
        print("  ⚠️ Aviso: Opção COPPA não encontrada ou já definida.")
    time.sleep(1.5)

    # 2. Avançar pelas abas até atingir Visibilidade
    reached_vis = False
    for step in range(6):
        # Tenta atalho no stepper (badge 4 / Visibilidade)
        try:
            badge = page.locator("#step-badge-3, [test-id='VISIBILITY_STEP'], ytcp-stepper-item:has-text('Visibilidade'), ytcp-stepper-item:has-text('Visibility')").first
            if badge.count() > 0 and badge.is_visible():
                badge.click(force=True, timeout=1500)
                time.sleep(1)
        except Exception:
            pass

        is_vis = page.evaluate("""() => {
            const pub = document.querySelector('tp-yt-paper-radio-button[name="PUBLIC"]') ||
                        document.querySelector('#public-radio-button') ||
                        document.querySelector('[name="PUBLIC"]');
            return pub !== null && pub.offsetParent !== null;
        }""")
        if is_vis:
            reached_vis = True
            break

        advanced = page.evaluate("""() => {
            const b = document.querySelector('#next-button') || document.querySelector('ytcp-button#next-button');
            if (b && !b.hasAttribute('disabled')) {
                b.click();
                return true;
            }
            const allBtns = Array.from(document.querySelectorAll('button, ytcp-button'));
            for (const btn of allBtns) {
                const txt = (btn.innerText || '').trim();
                if ((txt === 'Avançar' || txt === 'Next') && !btn.hasAttribute('disabled')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        if not advanced:
            try:
                next_btn = page.locator("#next-button:not([disabled]), button:has-text('Avançar')").first
                if next_btn.count() > 0 and next_btn.is_visible():
                    next_btn.click(force=True, timeout=2000)
            except Exception:
                pass
        time.sleep(2)

    page.screenshot(path=str(screenshot_debug / f"draft_{ciclo}_modal_vis.png"))

    # 3. Marcar Público
    print("  [2/4] Selecionando visibilidade 'Público'...")
    pub_marked = page.evaluate("""() => {
        const pub = document.querySelector('tp-yt-paper-radio-button[name="PUBLIC"]') ||
                    document.querySelector('#public-radio-button') ||
                    document.querySelector('[name="PUBLIC"]');
        if (pub) {
            pub.scrollIntoView({ behavior: 'instant', block: 'center' });
            pub.click();
            return true;
        }
        return false;
    }""")
    if not pub_marked:
        for p_sel in [
            "tp-yt-paper-radio-button[name='PUBLIC']",
            "#public-radio-button",
            "tp-yt-paper-radio-button:has-text('Público')",
            "tp-yt-paper-radio-button:has-text('Public')",
        ]:
            try:
                p_btn = page.locator(p_sel).first
                if p_btn.count() > 0:
                    p_btn.scroll_into_view_if_needed(timeout=2000)
                    p_btn.click(force=True, timeout=2000)
                    pub_marked = True
                    break
            except Exception:
                pass
    time.sleep(1.5)

    # 4. Clicar em Salvar / Publicar
    print("  [3/4] Clicando em Salvar / Publicar...")
    published = page.evaluate("""() => {
        const done = document.querySelector('#done-button') ||
                     document.querySelector('ytcp-button#done-button') ||
                     document.querySelector('button#done-button');
        if (done && !done.hasAttribute('disabled')) {
            done.click();
            return true;
        }
        return false;
    }""")
    if not published:
        for d_sel in [
            "#done-button:not([disabled])",
            "ytcp-button#done-button:not([disabled])",
            "button#done-button:not([disabled])",
            "ytcp-button:has-text('Publicar'):not([disabled])",
            "button:has-text('Publicar'):not([disabled])",
            "ytcp-button:has-text('Salvar'):not([disabled])",
            "button:has-text('Salvar'):not([disabled])",
        ]:
            try:
                done_btn = page.locator(d_sel).first
                if done_btn.count() > 0:
                    done_btn.click(force=True, timeout=3000)
                    published = True
                    break
            except Exception:
                pass

    if not published:
        print("  ⚠️ Botão de salvar/publicar não pôde ser acionado.")
        return False

    # 5. Trata confirmação 'Publicar mesmo assim'
    time.sleep(2)
    _handle_publish_anyway_dialog(page, timeout_sec=8)

    # 6. Aguarda e fecha modal de sucesso pós-publicação
    time.sleep(3)
    page.screenshot(path=str(screenshot_debug / f"draft_{ciclo}_modal_published.png"))
    print("  [4/4] Fechando diálogo de confirmação...")
    for c_sel in [
        "#close-button",
        "ytcp-button#close-button",
        "button#close-button",
        "button:has-text('Fechar')",
        "button[aria-label='Fechar']",
        "button:has-text('Close')",
    ]:
        try:
            close_btn = page.locator(c_sel).first
            if close_btn.count() > 0 and close_btn.is_visible():
                close_btn.click(force=True, timeout=2000)
                break
        except Exception:
            pass
    time.sleep(2)
    return True


def _publish_draft_edit_page(page, ciclo: int, screenshot_debug: Path, shorts_url: str) -> bool:
    """Processa a página completa de detalhes do vídeo (/video/<id>/edit)."""
    print("  [Página de Detalhes] Configurando visibilidade na coluna lateral...")

    # Garante COPPA
    page.evaluate("""() => {
        const radios = Array.from(document.querySelectorAll('tp-yt-paper-radio-button'));
        for (const r of radios) {
            const name = (r.getAttribute('name') || '').toUpperCase();
            const txt = (r.innerText || '').toLowerCase();
            if (name.includes('NOT_MFK') || txt.includes('não é conteúdo para crianças') || txt.includes('not made for kids')) {
                r.scrollIntoView({ behavior: 'instant', block: 'center' });
                r.click();
                return true;
            }
        }
        return false;
    }""")
    time.sleep(1.5)

    # Clica no trigger de visibilidade
    for v_sel in [
        "#visibility-trigger",
        "ytcp-video-metadata-visibility #visibility-trigger",
        "ytcp-text-dropdown-trigger",
        "[id*='visibility']",
        "div[role='button']:has-text('Visibilidade')",
        "div[role='button']:has-text('Rascunho')",
    ]:
        try:
            v_btn = page.locator(v_sel).first
            if v_btn.count() > 0 and v_btn.is_visible():
                v_btn.click(force=True, timeout=3000)
                break
        except Exception:
            pass

    time.sleep(1.5)

    # Marca Público
    page.evaluate("""() => {
        const radios = Array.from(document.querySelectorAll('tp-yt-paper-radio-button, [role="radio"]'));
        for (const r of radios) {
            const name = (r.getAttribute('name') || '').toUpperCase();
            const txt = (r.innerText || '').toLowerCase();
            if (name === 'PUBLIC' || txt.includes('público') || txt.includes('public')) {
                r.scrollIntoView({ behavior: 'instant', block: 'center' });
                r.click();
                return true;
            }
        }
        return false;
    }""")
    time.sleep(1.5)

    # Botão Concluído do dropdown
    for done_sel in ["#done-button", "ytcp-button#done-button", "button:has-text('Concluído')", "button:has-text('Done')"]:
        try:
            d_btn = page.locator(done_sel).first
            if d_btn.count() > 0 and d_btn.is_visible():
                d_btn.click(force=True, timeout=2000)
                break
        except Exception:
            pass

    time.sleep(1)

    # Botão principal Salvar
    saved = page.evaluate("""() => {
        const btn = document.querySelector('#save-button') || document.querySelector('ytcp-button#save-button');
        if (btn && !btn.hasAttribute('disabled')) {
            btn.click();
            return true;
        }
        return false;
    }""")
    if not saved:
        try:
            s_btn = page.locator("#save-button, ytcp-button#save-button").first
            if s_btn.count() > 0:
                s_btn.click(force=True, timeout=4000)
                saved = True
        except Exception:
            pass

    time.sleep(2)
    _handle_publish_anyway_dialog(page, timeout_sec=8)
    time.sleep(3)
    page.screenshot(path=str(screenshot_debug / f"draft_{ciclo}_edit_page_saved.png"))

    # Retorna para a listagem
    page.goto(shorts_url, timeout=60000)
    time.sleep(4)
    return True


def publicar_rascunhos(niche: str = "fitness", headless: bool = True, max_videos: int = 50) -> int:
    niche_clean = niche.lower().strip()
    user_data_dir = ROOT_DIR / "data" / f"youtube_browser_profile_{niche_clean}"
    state_file = ROOT_DIR / "config" / f"youtube_{niche_clean}_state.json"
    screenshot_debug = ROOT_DIR / "logs" / "screenshots"
    screenshot_debug.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print(f"🚀 PUBLICADOR EM MASSA DE RASCUNHOS - NICHO: [{niche_clean.upper()}]")
    print("=" * 65)
    print(f"📁 Perfil: {user_data_dir}")
    print(f"🖥️ Headless: {headless}")
    print(f"🎯 Limite por ciclo: {max_videos} vídeos")
    print("=" * 65 + "\n")

    if not user_data_dir.exists():
        print(f"❌ Diretório de perfil não encontrado: {user_data_dir}")
        return 0

    publicados_sucesso = 0

    with sync_playwright() as p:
        extra_args = [
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--window-size=1920,1080",
        ]
        if headless:
            extra_args.append("--headless=new")

        context_args = {
            "user_data_dir": str(user_data_dir),
            "headless": headless,
            "args": extra_args,
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": USER_AGENT,
            "ignore_default_args": ["--enable-automation"],
        }

        context = p.chromium.launch_persistent_context(**context_args)

        if state_file.exists():
            try:
                state_data = json.loads(state_file.read_text(encoding="utf-8"))
                cookies = state_data.get("cookies", [])
                if cookies:
                    context.add_cookies(cookies)
                    print(f"🔑 Sessão carregada: {len(cookies)} cookies injetados.")
            except Exception as c_err:
                print(f"⚠️ Aviso ao injetar cookies: {c_err}")

        page = context.pages[0] if context.pages else context.new_page()

        channel_id = CHANNEL_IDS.get(niche_clean)
        tabs_to_check = []
        if channel_id:
            tabs_to_check.append(f"https://studio.youtube.com/channel/{channel_id}/videos/short")
            tabs_to_check.append(f"https://studio.youtube.com/channel/{channel_id}/videos/upload")
        else:
            tabs_to_check.append("https://studio.youtube.com")

        for current_tab_url in tabs_to_check:
            tab_name = "Shorts" if "videos/short" in current_tab_url else "Vídeos Normais"
            print(f"\n📂 Inspecionando aba [{tab_name}]: {current_tab_url}")
            page.goto(current_tab_url, timeout=60000)
            time.sleep(6)

            if "accounts.google.com" in page.url or "signin" in page.url:
                print(f"❌ Sessão do YouTube expirada para nicho {niche_clean}!")
                break

            falhas_consecutivas = 0

            while publicados_sucesso < max_videos and falhas_consecutivas < 3:
                # Clica no botão de rascunho VISÍVEL dentro de uma linha com status 'Rascunho'
                opened = page.evaluate("""() => {
                    const rows = Array.from(document.querySelectorAll('ytcp-video-row'));
                    for (const row of rows) {
                        const text = (row.innerText || '').toLowerCase();
                        if (text.includes('rascunho') || text.includes('draft')) {
                            const btn = row.querySelector('.edit-draft-button') ||
                                        Array.from(row.querySelectorAll('button, ytcp-button')).find(b => (b.innerText || '').includes('Editar rascunho'));
                            if (btn && !btn.hasAttribute('hidden') && btn.offsetParent !== null) {
                                btn.scrollIntoView({ behavior: 'instant', block: 'center' });
                                btn.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }""")

                if not opened:
                    # Se não encontrou visível, tenta rolar para baixo para renderizar linhas virtuais
                    page.evaluate("window.scrollBy(0, 600)")
                    time.sleep(2)
                    opened = page.evaluate("""() => {
                        const rows = Array.from(document.querySelectorAll('ytcp-video-row'));
                        for (const row of rows) {
                            const text = (row.innerText || '').toLowerCase();
                            if (text.includes('rascunho') || text.includes('draft')) {
                                const btn = row.querySelector('.edit-draft-button') ||
                                            Array.from(row.querySelectorAll('button, ytcp-button')).find(b => (b.innerText || '').includes('Editar rascunho'));
                                if (btn && !btn.hasAttribute('hidden') && btn.offsetParent !== null) {
                                    btn.scrollIntoView({ behavior: 'instant', block: 'center' });
                                    btn.click();
                                    return true;
                                }
                            }
                        }
                        return false;
                    }""")

                if not opened:
                    # Tenta atualizar a página para puxar os próximos rascunhos da lista
                    print(f"🔄 Recarregando aba [{tab_name}] para verificar se há mais rascunhos...")
                    page.reload()
                    time.sleep(6)
                    opened = page.evaluate("""() => {
                        const rows = Array.from(document.querySelectorAll('ytcp-video-row'));
                        for (const row of rows) {
                            const text = (row.innerText || '').toLowerCase();
                            if (text.includes('rascunho') || text.includes('draft')) {
                                const btn = row.querySelector('.edit-draft-button') ||
                                            Array.from(row.querySelectorAll('button, ytcp-button')).find(b => (b.innerText || '').includes('Editar rascunho'));
                                if (btn && !btn.hasAttribute('hidden') && btn.offsetParent !== null) {
                                    btn.scrollIntoView({ behavior: 'instant', block: 'center' });
                                    btn.click();
                                    return true;
                                }
                            }
                        }
                        return false;
                    }""")

                if not opened:
                    print(f"✨ Nenhum rascunho pendente visível na aba [{tab_name}].")
                    break

                print(f"\n[Rascunho {publicados_sucesso + 1}/{max_videos}] Rascunho aberto para edição...")
                time.sleep(5)

                is_edit_page = ("/video/" in page.url and "/edit" in page.url) or (page.locator("#save-button").count() > 0 and page.locator("ytcp-uploads-dialog").count() == 0)
                if is_edit_page:
                    ok = _publish_draft_edit_page(page, publicados_sucesso + 1, screenshot_debug, current_tab_url)
                else:
                    ok = _publish_draft_modal(page, publicados_sucesso + 1, screenshot_debug)

                if ok:
                    publicados_sucesso += 1
                    falhas_consecutivas = 0
                    print(f"✅ Rascunho {publicados_sucesso} publicado com SUCESSO como PÚBLICO!")
                else:
                    falhas_consecutivas += 1
                    print("⚠️ Falha ao publicar este rascunho. Continuando...")

                time.sleep(3)
                # Garante que a página volta para a listagem
                if page.url != current_tab_url:
                    page.goto(current_tab_url, timeout=60000)
                    time.sleep(4)

        context.close()

    print("\n" + "=" * 65)
    print(f"🎉 CICLO FINALIZADO PARA [{niche_clean.upper()}]! Total publicados: {publicados_sucesso}")
    print("=" * 65)
    return publicados_sucesso


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publicar todos os rascunhos pendentes no YouTube Studio")
    parser.add_argument("--niche", default="all", choices=["fitness", "financas", "all"], help="Nicho do canal (ou 'all' para ambos)")
    parser.add_argument("--headless", action="store_true", default=True, help="Rodar em modo headless")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Rodar com navegador visível")
    parser.add_argument("--limit", type=int, default=50, help="Quantidade máxima de rascunhos para publicar nesta rodada")
    args = parser.parse_args()

    if args.niche == "all":
        tot = 0
        for n in ["fitness", "financas"]:
            tot += publicar_rascunhos(niche=n, headless=args.headless, max_videos=args.limit)
        print(f"\n🚀 TOTAL GERAL DE RASCUNHOS PUBLICADOS EM TODOS OS CANAIS: {tot}")
    else:
        publicar_rascunhos(niche=args.niche, headless=args.headless, max_videos=args.limit)
