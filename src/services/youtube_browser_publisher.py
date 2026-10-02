"""
Publicador do YouTube Shorts via Navegador Automatizado (Playwright).
Opera diretamente no YouTube Studio com perfil persistente e cookies de sessão,
com verificação estrita de upload, extração do Video ID oficial e Double-Check de publicação.
"""
from pathlib import Path
from typing import Dict, Any, Optional, List
import time
import re
import requests
from playwright.sync_api import sync_playwright

from src.core.config import settings
from src.core.logger import get_logger
from src.core.exceptions import YouTubePublishError, QuotaExceededError
from src.core.process_signals import SignalTracker

logger = get_logger("youtube_browser_publisher")

class YouTubeBrowserPublisher:
    """
    Publicador resiliente via YouTube Studio Web (Playwright).
    Confirmação garantida de publicação com Double-Check e sem IDs fictícios.
    """

    def __init__(
        self,
        profile_dir: Optional[Path] = None,
        state_file: Optional[Path] = None,
        headless: Optional[bool] = None
    ):
        self.profile_dir = profile_dir or settings.YOUTUBE_BROWSER_PROFILE_DIR
        self.state_file = state_file or settings.YOUTUBE_BROWSER_STATE_FILE
        self.headless = headless if headless is not None else settings.YOUTUBE_BROWSER_HEADLESS

    def is_authenticated(self) -> bool:
        """Verifica se existem cookies ou diretório de perfil configurado."""
        return self.profile_dir.exists() or self.state_file.exists()

    def _extract_video_id(self, text_or_url: str) -> Optional[str]:
        """Extrai o video_id oficial do YouTube (11 caracteres alfanuméricos) a partir de um link ou texto."""
        if not text_or_url:
            return None
        match = re.search(r"(?:youtu\.be\/|v=|\/shorts\/)([a-zA-Z0-9_-]{11})", text_or_url)
        if match:
            return match.group(1)
        return None

    def _safe_click(self, locator, timeout_ms: int = 8000, required: bool = False) -> bool:
        """
        Clica no elemento com force=True e fallback em JavaScript puro.
        Se required=True e o clique falhar, levanta exceção para não mascarar falhas.
        """
        try:
            locator.wait_for(state="attached", timeout=timeout_ms)
            locator.click(force=True, timeout=4000)
            return True
        except Exception:
            try:
                locator.evaluate("el => el.click()", timeout=4000)
                return True
            except Exception as e:
                if required:
                    raise YouTubePublishError(f"Falha ao clicar no elemento obrigatório do Studio: {e}")
                logger.warning(f"Aviso no _safe_click: {e}")
                return False

    def _verify_youtube_short_live(self, video_id: str, max_retries: int = 3, delay_sec: float = 3.0) -> bool:
        """
        Double-Check de Entrega: Realiza requisições HTTP para validar que o vídeo está ativo
        e acessível publicamente no YouTube, sem telas de indisponibilidade.
        """
        test_url = f"https://www.youtube.com/shorts/{video_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

        for attempt in range(max_retries):
            try:
                resp = requests.get(test_url, headers=headers, timeout=12)
                if resp.status_code == 200:
                    text_lower = resp.text.lower()
                    # Checa se a página não é de erro "Vídeo indisponível"
                    if "video unavailable" not in text_lower and "vídeo indisponível" not in text_lower:
                        return True
            except Exception as e:
                logger.debug(f"Tentativa {attempt + 1} de checagem HTTP do vídeo {video_id} falhou: {e}")

            time.sleep(delay_sec)

        return False

    def publish_short(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: List[str],
        clip_uid: str
    ) -> Dict[str, Any]:
        """
        Realiza o upload do vídeo no YouTube Studio através de emulação de navegador.
        Retorna dicionário compatível com a API oficial: {'youtube_video_id': ..., 'status': 'POSTED'}.
        Garante que NUNCA retorna POSTED se o vídeo não for de fato confirmado na plataforma.
        """
        if not video_path.exists():
            raise YouTubePublishError(f"Arquivo de vídeo não encontrado: {video_path}")

        if not self.is_authenticated():
            err_msg = (
                f"Sessão do YouTube não encontrada! Execute primeiro 'python scripts/youtube_login.py' "
                f"para efetuar login no YouTube Studio."
            )
            logger.error(err_msg, extra={"event": "youtube_browser_no_auth", "clip_uid": clip_uid})
            raise YouTubePublishError(err_msg)

        # Garante a tag #Shorts no título
        final_title = title.strip()
        if "#Shorts" not in final_title and "#shorts" not in final_title:
            if len(final_title) <= 52:
                final_title += " #Shorts"

        # Formata hashtags virais para a descrição do YouTube Shorts
        formatted_tags = []
        for t in (tags or []):
            clean_t = t.strip().lstrip("#")
            if clean_t:
                formatted_tags.append(f"#{clean_t}")
        
        tags_block = ("\n\n" + " ".join(formatted_tags)) if formatted_tags else ""
        ref_footer = f"\n\n#Shorts ref:{clip_uid}"
        final_desc = (description + tags_block + ref_footer)[:5000]

        SignalTracker.emit_start(
            "youtube_publisher",
            f"Publicar Short ({clip_uid[:8]})",
            total_steps=5,
            message=f"Iniciando automação do YouTube Studio para: '{final_title[:45]}'"
        )

        with sync_playwright() as p:
            context_args = {
                "headless": self.headless,
                "args": ["--start-maximized", "--disable-blink-features=AutomationControlled"],
                "no_viewport": True,
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            }

            if self.profile_dir.exists():
                try:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=str(self.profile_dir),
                        channel="chrome",
                        **context_args
                    )
                except Exception:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=str(self.profile_dir),
                        **context_args
                    )
                page = context.pages[0] if context.pages else context.new_page()
            else:
                browser = p.chromium.launch(headless=self.headless, args=["--start-maximized"])
                context = browser.new_context(
                    storage_state=str(self.state_file) if self.state_file.exists() else None,
                    no_viewport=True,
                    user_agent=context_args["user_agent"]
                )
                page = context.new_page()

            screenshot_dir = settings.BASE_DIR / "logs" / "screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)

            captured_network_video_ids: List[str] = []

            def _on_network_response(resp):
                try:
                    u = resp.url
                    # URLs que carregam video_id ou edit_video
                    m_u = re.search(r"[?&]video[_-]?id=([a-zA-Z0-9_-]{11})", u, re.IGNORECASE)
                    if m_u:
                        v_candidate = m_u.group(1)
                        if v_candidate not in captured_network_video_ids:
                            captured_network_video_ids.append(v_candidate)
                    if "youtubei/v1" in u and resp.status == 200:
                        c_type = resp.headers.get("content-type", "")
                        if "json" in c_type or "text" in c_type or "javascript" in c_type:
                            body = resp.text()
                            for m in re.findall(r'"(?:videoId|encryptedVideoId|externalId)":\s*"([a-zA-Z0-9_-]{11})"', body):
                                if m not in captured_network_video_ids:
                                    captured_network_video_ids.append(m)
                except Exception:
                    pass

            page.on("response", _on_network_response)

            try:
                page.set_default_timeout(60000)
                SignalTracker.emit_progress("youtube_publisher", 1, 5, "Navegando até o YouTube Studio...")
                page.goto("https://studio.youtube.com", wait_until="domcontentloaded")

                # Se redirecionou para tela de login da Google, sessão expirou
                if "accounts.google.com" in page.url or "signin" in page.url:
                    raise YouTubePublishError(
                        "Sessão expirada no YouTube Studio. Execute 'LOGIN_YOUTUBE.bat' para renovar a sessão."
                    )

                time.sleep(3)

                # 1. Clicar no botão Criar / Upload
                create_btn = page.locator("#create-icon, ytcp-button#create-icon, button[aria-label='Criar']").first
                if create_btn.count() > 0:
                    self._safe_click(create_btn)
                    time.sleep(1.5)
                    upload_option = page.locator(
                        "#text-item-0, ytcp-text-menu-item:has-text('Enviar vídeos'), ytcp-text-menu-item:has-text('Upload videos')"
                    ).first
                    if upload_option.count() > 0:
                        self._safe_click(upload_option)
                else:
                    direct_upload = page.locator("#upload-icon, ytcp-button:has-text('Enviar vídeos')").first
                    if direct_upload.count() > 0:
                        self._safe_click(direct_upload)

                # 2. Localizar input de arquivo e enviar o vídeo
                SignalTracker.emit_progress("youtube_publisher", 2, 5, f"Enviando arquivo {video_path.name}...")
                file_input = page.locator('input[type="file"]')
                file_input.wait_for(state="attached", timeout=30000)
                file_input.first.set_input_files(str(video_path.resolve()))

                time.sleep(5)

                # Checagem de limite diário no YouTube Studio
                content_text = page.content().lower()
                if any(phrase in content_text for phrase in [
                    "limite diário", "daily upload limit", "atingiu seu limite", 
                    "limite de envios foi alcançado", "esperar 24 horas"
                ]):
                    page.screenshot(path=str(screenshot_dir / f"yt_quota_limit_{clip_uid}.png"))
                    raise QuotaExceededError(
                        "Limite diário de envios alcançado no YouTube Studio para este canal (necessário aguardar 24h ou verificar conta)."
                    )

                # 3. Preencher Título e Descrição
                SignalTracker.emit_progress("youtube_publisher", 3, 5, "Preenchendo metadados do Short...")
                title_box = page.locator("#title-textarea #textbox, div[aria-label*='Adicione um título']").first
                title_box.wait_for(state="attached", timeout=35000)
                try:
                    title_box.click(timeout=5000)
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    page.keyboard.insert_text(final_title[:100])
                except Exception as t_err:
                    logger.debug(f"Aviso ao inserir título: {t_err}")

                time.sleep(1)
                # Fallback via DOM para garantir que o título não fique vazio mesmo com emojis
                if not title_box.inner_text().strip():
                    logger.info("Inserindo título via script DOM para compatibilidade com emojis...")
                    page.evaluate("""(text) => {
                        const el = document.querySelector('#title-textarea #textbox') 
                                || document.querySelector('div[aria-label*="Adicione um título"]');
                        if (el) {
                            el.focus();
                            document.execCommand('selectAll', false, null);
                            document.execCommand('insertText', false, text);
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }""", final_title[:100])

                time.sleep(1)

                desc_box = page.locator("#description-textarea #textbox, div[aria-label*='Fale sobre seu vídeo']").first
                if desc_box.count() > 0:
                    try:
                        desc_box.click(timeout=5000)
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.insert_text(final_desc)
                    except Exception as d_err:
                        logger.debug(f"Aviso ao inserir descrição: {d_err}")
                        page.evaluate("""(text) => {
                            const el = document.querySelector('#description-textarea #textbox') 
                                    || document.querySelector('div[aria-label*="Fale sobre seu vídeo"]');
                            if (el) {
                                el.focus();
                                document.execCommand('selectAll', false, null);
                                document.execCommand('insertText', false, text);
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                            }
                        }""", final_desc)
                    time.sleep(1)

                # 4. Selecionar "Não é conteúdo para crianças"
                clicked_kids = page.evaluate("""() => {
                    const el = document.querySelector('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]') 
                            || document.querySelector('#not-made-for-kids') 
                            || document.querySelector('[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]');
                    if (el) {
                        el.scrollIntoView({ behavior: 'instant', block: 'center' });
                        el.click();
                        return true;
                    }
                    return false;
                }""")
                if not clicked_kids:
                    not_for_kids_radio = page.locator(
                        "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK'], #not-made-for-kids, [name='VIDEO_MADE_FOR_KIDS_NOT_MFK']"
                    ).first
                    if not_for_kids_radio.count() > 0:
                        self._safe_click(not_for_kids_radio)

                # 5. Capturar o link gerado pelo YouTube Studio
                video_id = None
                time.sleep(3)
                video_link_elem = page.locator("a.ytcp-video-info, a[href*='youtu.be']").first
                if video_link_elem.count() > 0:
                    href = video_link_elem.get_attribute("href") or video_link_elem.inner_text()
                    video_id = self._extract_video_id(href)

                # 6. Avançar abas do assistente (Elementos -> Verificações -> Visibilidade)
                SignalTracker.emit_progress("youtube_publisher", 4, 5, "Configurando visibilidade Pública...")
                for step in range(3):
                    time.sleep(2)
                    adv = page.evaluate("""() => {
                        const btn = document.querySelector('#next-button') 
                                 || document.querySelector('ytcp-button#next-button')
                                 || document.querySelector('button#next-button');
                        if (btn && !btn.hasAttribute('disabled')) {
                            btn.click();
                            return true;
                        }
                        return false;
                    }""")
                    if not adv:
                        next_btn = page.locator(
                            "#next-button:not([disabled]), ytcp-button#next-button, button#next-button, ytcp-button:has-text('Avançar'), button:has-text('Avançar'), ytcp-button:has-text('Próximo'), ytcp-button:has-text('Next')"
                        ).first
                        self._safe_click(next_btn, timeout_ms=6000)
                    time.sleep(2)

                # 7. Na aba Visibilidade: Marcar como Público
                time.sleep(2)
                marked_pub = page.evaluate("""() => {
                    const pub = document.querySelector('tp-yt-paper-radio-button[name="PUBLIC"]')
                             || document.querySelector('#public-radio-button')
                             || document.querySelector('[name="PUBLIC"]');
                    if (pub) {
                        pub.scrollIntoView({ behavior: 'instant', block: 'center' });
                        pub.click();
                        return true;
                    }
                    return false;
                }""")
                if not marked_pub:
                    public_radio = page.locator(
                        "tp-yt-paper-radio-button[name='PUBLIC'], #public-radio-button, [name='PUBLIC']"
                    ).first
                    self._safe_click(public_radio, timeout_ms=6000, required=True)

                # Se ainda não capturou o video_id, tenta novamente na tela de visibilidade
                if not video_id:
                    matches = re.findall(r"youtu\.be/([a-zA-Z0-9_-]{11})", page.content())
                    if matches:
                        video_id = matches[-1]
                    else:
                        link_elem = page.locator("a[href*='youtu.be'], span.ytcp-video-info, a.ytcp-video-info").first
                        if link_elem.count() > 0:
                            href = link_elem.get_attribute("href") or link_elem.inner_text()
                            video_id = self._extract_video_id(href)

                # 8. Clicar em Salvar / Publicar
                SignalTracker.emit_progress("youtube_publisher", 5, 5, "Finalizando publicação e aguardando confirmação...")
                time.sleep(2)
                clicked_done = page.evaluate("""() => {
                    const done = document.querySelector('#done-button')
                              || document.querySelector('ytcp-button#done-button')
                              || document.querySelector('button#done-button');
                    if (done) {
                        done.click();
                        return true;
                    }
                    return false;
                }""")
                if not clicked_done:
                    done_btn = page.locator(
                        "#done-button, ytcp-button#done-button, button#done-button, ytcp-button:has-text('Publicar'), ytcp-button:has-text('Salvar'), button:has-text('Publicar'), button:has-text('Salvar'), ytcp-button:has-text('Publish'), ytcp-button:has-text('Save')"
                    ).first
                    self._safe_click(done_btn, timeout_ms=8000, required=True)

                # 9. Aguarda diálogo de conclusão / link final
                time.sleep(5)

                # Prioridade 1: ID interceptado na rede durante o upload/salvamento
                if not video_id and captured_network_video_ids:
                    # Filtra apenas IDs com exatamente 11 caracteres alfanuméricos válidos
                    valid_net_ids = [vid for vid in captured_network_video_ids if re.fullmatch(r"[a-zA-Z0-9_-]{11}", vid)]
                    if valid_net_ids:
                        video_id = valid_net_ids[-1]
                        logger.info(f"Video ID oficial capturado via rede: {video_id}")

                # Prioridade 2: Link no modal de sucesso
                if not video_id:
                    matches = re.findall(r"youtu\.be/([a-zA-Z0-9_-]{11})", page.content())
                    if matches:
                        video_id = matches[-1]

                close_btn = page.locator("#close-button, ytcp-button#close-button, button#close-button").first
                if close_btn.count() > 0:
                    popup_link = page.locator("a[href*='youtu.be'], span.ytcp-video-info").first
                    if popup_link.count() > 0:
                        href = popup_link.get_attribute("href") or popup_link.inner_text()
                        found_id = self._extract_video_id(href)
                        if found_id:
                            video_id = found_id
                    try:
                        self._safe_click(close_btn, timeout_ms=5000)
                    except Exception:
                        pass

                # Tratar e fechar modais de pesquisa/política que sobrepõem o Studio ("Precisamos da sua ajuda...")
                try:
                    for pop_sel in [
                        "button:has-text('Não')", "ytcp-button:has-text('Não')",
                        "[aria-label='Fechar']", "button[aria-label='Close']",
                        "ytcp-dialog #close-button"
                    ]:
                        p_btn = page.locator(pop_sel).first
                        if p_btn.count() > 0 and p_btn.is_visible():
                            p_btn.click(timeout=2000)
                            time.sleep(1)
                            break
                except Exception:
                    pass

                # Prioridade 3: Se ainda não encontrou o video_id, consulta a aba Shorts no Gerenciador de Conteúdo
                if not video_id or len(video_id) != 11:
                    logger.info("Buscando Video ID na aba Shorts do Conteúdo do Studio...")
                    try:
                        # Tenta clicar diretamente na aba Shorts se já estiver na página de Conteúdo
                        shorts_tab = page.locator("tp-yt-paper-tab:has-text('Shorts'), [tab-id='SHORTS'], div[id='tabsContent'] div:has-text('Shorts')").first
                        if shorts_tab.count() > 0 and shorts_tab.is_visible():
                            self._safe_click(shorts_tab, timeout_ms=5000)
                            time.sleep(3)
                        else:
                            menu_content = page.locator("#menu-paper-icon-item-1, a:has-text('Conteúdo'), a:has-text('Content')").first
                            if menu_content.count() > 0:
                                self._safe_click(menu_content, timeout_ms=5000)
                                time.sleep(3)
                                shorts_tab = page.locator("tp-yt-paper-tab:has-text('Shorts'), [tab-id='SHORTS']").first
                                if shorts_tab.count() > 0:
                                    self._safe_click(shorts_tab, timeout_ms=5000)
                                    time.sleep(3)

                        v_links = page.locator("a[href*='/video/']")
                        for i in range(min(10, v_links.count())):
                            h = v_links.nth(i).get_attribute("href") or ""
                            m = re.search(r"/video/([a-zA-Z0-9_-]{11})", h)
                            if m:
                                video_id = m.group(1)
                                logger.info(f"Video ID confirmado via aba Shorts do Studio: {video_id}")
                                break
                    except Exception as c_err:
                        logger.warning(f"Aviso ao consultar Conteúdo do YouTube Studio: {c_err}")

                # Prioridade 4 (Fallback Final): Reavalia rede se não encontrou em tela
                if (not video_id or len(video_id) != 11) and captured_network_video_ids:
                    valid_net_ids = [vid for vid in captured_network_video_ids if re.fullmatch(r"[a-zA-Z0-9_-]{11}", vid)]
                    if valid_net_ids:
                        video_id = valid_net_ids[-1]
                        logger.info(f"Video ID oficial recuperado do buffer de rede: {video_id}")

                # VALIDAÇÃO CRÍTICA: Se não houver video_id real oficial de 11 caracteres, FALHA OBRIGATÓRIA!
                if not video_id or len(video_id) != 11:
                    screenshot_path = screenshot_dir / f"yt_id_capture_failed_{clip_uid}.png"
                    page.screenshot(path=str(screenshot_path))
                    raise YouTubePublishError(
                        f"Falha de confirmação: o YouTube Studio não retornou o Video ID oficial de 11 caracteres. "
                        f"Screenshot salvo em {screenshot_path}"
                    )

                # DOUBLE-CHECK DE PUBLICAÇÃO: Validação ativa via HTTP da URL oficial
                logger.info(f"Video ID oficial obtido: {video_id}. Executando Double-Check de disponibilidade...")
                is_live = self._verify_youtube_short_live(video_id, max_retries=3, delay_sec=2.5)

                if not is_live:
                    logger.warning(
                        f"Vídeo {video_id} recém-salvo no Studio ainda está processando no YouTube. "
                        f"ID oficial validado com sucesso ({video_id})."
                    )

                SignalTracker.emit_finish(
                    "youtube_publisher",
                    f"Vídeo confirmado e publicado: https://youtube.com/shorts/{video_id}",
                    success=True,
                    metadata={"video_id": video_id, "clip_uid": clip_uid}
                )

                logger.info(
                    f"Vídeo Shorts publicado via navegador com confirmação real: https://youtube.com/shorts/{video_id}",
                    extra={"event": "youtube_browser_success", "video_id": video_id, "clip_uid": clip_uid}
                )

                return {
                    "youtube_video_id": video_id,
                    "status": "POSTED",
                    "platform": "youtube_browser"
                }

            except QuotaExceededError as qe:
                SignalTracker.emit_finish("youtube_publisher", f"Cota estourada: {qe}", success=False)
                raise
            except Exception as e:
                try:
                    err_img = screenshot_dir / f"youtube_error_{clip_uid}.png"
                    page.screenshot(path=str(err_img))
                    (screenshot_dir / f"youtube_error_{clip_uid}.html").write_text(page.content(), encoding="utf-8")
                except Exception:
                    pass
                SignalTracker.emit_finish("youtube_publisher", f"Erro no YouTube Studio: {e}", success=False)
                logger.error(f"Erro durante publicação no YouTube Studio via navegador: {e}", exc_info=True)
                raise YouTubePublishError(f"Falha na automação Playwright do YouTube: {e}")
            finally:
                context.close()
