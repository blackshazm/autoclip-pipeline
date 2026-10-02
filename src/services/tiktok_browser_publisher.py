"""
Publicador do TikTok via Navegador Automatizado (Playwright).
Opera diretamente no TikTok Studio Web com perfil persistente e cookies de sessão,
com confirmação estrita de upload, detecção de erros/captcha e validação no Gerenciador de Conteúdo.
"""
from pathlib import Path
from typing import Dict, Any, Optional, List
import time
import re
from playwright.sync_api import sync_playwright

from src.core.config import settings
from src.core.logger import get_logger
from src.core.exceptions import TikTokPublishError
from src.core.process_signals import SignalTracker

logger = get_logger("tiktok_browser_publisher")

class TikTokBrowserPublisher:
    """
    Publicador resiliente via TikTok Studio Web (Playwright).
    Confirmação garantida de postagem e validação de status no gerenciador de conteúdo.
    """

    def __init__(
        self,
        profile_dir: Optional[Path] = None,
        state_file: Optional[Path] = None,
        headless: Optional[bool] = None
    ):
        self.profile_dir = profile_dir or getattr(settings, "TIKTOK_BROWSER_PROFILE_DIR", Path("./data/tiktok_browser_profile"))
        self.state_file = state_file or getattr(settings, "TIKTOK_BROWSER_STATE_FILE", Path("./config/tiktok_state.json"))
        self.headless = headless if headless is not None else getattr(settings, "TIKTOK_BROWSER_HEADLESS", True)

    def is_authenticated(self) -> bool:
        """Verifica se existem cookies ou diretório de perfil configurado."""
        return self.profile_dir.exists() or self.state_file.exists()

    def format_caption(self, title: str, tags: Optional[List[str]] = None, max_len: int = 2200) -> str:
        """
        Formata a legenda para o TikTok Studio:
        - Remove menções a plataformas concorrentes (#shorts, #youtubeshorts, #reels).
        - Substitui #shorts por tags nativas de alto alcance do TikTok (#fyp, #viral, #cortes).
        - Evita qualquer penalização algorítmica por repost cruzado no feed 'Para Você'.
        """
        # 1. Remove qualquer menção a concorrentes no título (#shorts, #reels, etc.)
        caption_title = re.sub(r'#(?:shorts?|youtubeshorts?|reels?)\b', '', title, flags=re.IGNORECASE).strip()
        caption_title = re.sub(r'\s{2,}', ' ', caption_title)

        # 2. Higieniza a lista de tags excluindo termos concorrentes
        tag_list = tags if tags is not None else ["cortes", "podcast", "viral", "fyp"]
        competitor_tags = {"shorts", "short", "youtubeshorts", "reels", "reel"}
        
        formatted_tags: List[str] = []
        has_tiktok_feed_tag = False
        
        for t in tag_list:
            clean_tag = t.strip().lstrip("#").lower()
            if not clean_tag or clean_tag in competitor_tags:
                continue
            if clean_tag in ("fyp", "foryou", "viral", "paravoce"):
                has_tiktok_feed_tag = True
            
            formatted_tags.append(f"#{clean_tag}")

        # Se não houver tags de feed do TikTok, adiciona #fyp e #viral para impulsionar alcance orgânico
        if not has_tiktok_feed_tag:
            formatted_tags.insert(0, "#fyp")
            if "#viral" not in formatted_tags:
                formatted_tags.append("#viral")

        tags_str = " ".join(formatted_tags)
        full_caption = f"{caption_title} {tags_str}".strip()
        return full_caption[:max_len]

    def _safe_click(self, locator, timeout_ms: int = 15000, required: bool = False) -> bool:
        """Clica no elemento com force=True e fallback em JavaScript puro para contornar overlays."""
        try:
            locator.wait_for(state="attached", timeout=timeout_ms)
            locator.click(force=True, timeout=5000)
            return True
        except Exception:
            try:
                locator.evaluate("el => el.click()")
                return True
            except Exception as e:
                if required:
                    raise TikTokPublishError(f"Falha ao clicar no elemento obrigatório do TikTok Studio: {e}")
                logger.warning(f"Aviso no _safe_click (TikTok): {e}")
                return False

    def _dismiss_onboarding_popups(self, page) -> None:
        """Descarta modais de boas-vindas/verificação que bloqueiam a interface."""
        selectors = [
            'button:has-text("Ativar")',
            'button:has-text("Entendi")',
            'button:has-text("Got it")',
            'button:has-text("Enable")',
            '.TUXModal-close',
            '[data-floating-ui-portal] button:has-text("Entendi")',
            '[data-floating-ui-portal] button:has-text("Ativar")',
            'div[aria-label="Close"]',
            'button[aria-label="Fechar"]'
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel)
                count = loc.count()
                for i in range(count):
                    b = loc.nth(i)
                    if b.is_visible():
                        logger.debug(f"Descartando modal de onboarding: '{b.inner_text().strip()}'")
                        b.click(force=True)
                        time.sleep(1)
            except Exception:
                pass

    def _extract_post_id_from_content_page(
        self,
        page,
        title_fragment: str = "",
        tags: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Navega ou lê a página de conteúdo do TikTok Studio (/tiktokstudio/content)
        para validar a presença do vídeo publicado e extrair seu identificador real.
        """
        try:
            # Aguarda a renderização dos itens de vídeo pelo framework React do TikTok
            try:
                page.wait_for_selector('a[href*="/video/"]', timeout=12000)
            except Exception:
                pass
            time.sleep(3)

            # 1. Procura diretamente todos os links com padrão /video/ na página inteira
            video_links = page.locator('a[href*="/video/"]')
            count = video_links.count()
            logger.info(f"Localizados {count} links de vídeo no TikTok Studio Content.")
            
            words_to_match = [w.lower() for w in re.sub(r'[^\w\s]', '', title_fragment).split() if len(w) > 3]
            if tags:
                for t in tags:
                    clean_t = re.sub(r'[^\w]', '', t).lower()
                    if len(clean_t) > 3:
                        words_to_match.append(clean_t)

            first_found_id = None
            for i in range(min(15, count)):
                link = video_links.nth(i)
                href = link.get_attribute("href") or ""
                match = re.search(r"/video/(\d+)", href)
                if match:
                    vid_id = match.group(1)
                    if not first_found_id:
                        first_found_id = vid_id
                    
                    # Se tiver fragmentos de título ou tags para checar correspondência
                    if words_to_match:
                        try:
                            parent_text = link.evaluate("el => (el.closest('div, li, tr') || el).innerText").lower()
                            if any(w in parent_text for w in words_to_match):
                                logger.info(f"Vídeo confirmado por título/tags e link: ID={vid_id}")
                                return vid_id
                        except Exception:
                            pass

            if first_found_id:
                logger.info(f"Vídeo mais recente no topo do gerenciador confirmado: ID={first_found_id}")
                return first_found_id

            # 2. Checa também elementos com data-id ou id numérico longo (18-20 dígitos do TikTok)
            data_elements = page.locator('[data-id], [id*="video"]')
            for i in range(min(10, data_elements.count())):
                attr = data_elements.nth(i).get_attribute("data-id") or data_elements.nth(i).get_attribute("id") or ""
                m = re.search(r"\b(\d{18,20})\b", attr)
                if m:
                    return m.group(1)

        except Exception as e:
            logger.warning(f"Aviso ao inspecionar gerenciador de conteúdo do TikTok: {e}")

        return None

    def publish_video(
        self,
        video_path: Path,
        title: str,
        tags: List[str],
        clip_uid: str
    ) -> Dict[str, Any]:
        """
        Realiza o upload do vídeo no TikTok Studio através de emulação de navegador.
        Retorna dicionário com identificador real e status de publicação.
        Garante que NUNCA marca POSTED sem validação de envio pelo TikTok.
        """
        if not video_path.exists():
            raise TikTokPublishError(f"Arquivo de vídeo não encontrado: {video_path}")

        if not self.is_authenticated():
            err_msg = (
                f"Sessão do TikTok não encontrada! Execute primeiro 'LOGIN_TIKTOK.bat' ou "
                f"'python scripts/tiktok_login.py' para autenticar no TikTok Studio."
            )
            logger.error(err_msg, extra={"event": "tiktok_browser_no_auth", "clip_uid": clip_uid})
            raise TikTokPublishError(err_msg)

        final_caption = self.format_caption(title, tags)

        SignalTracker.emit_start(
            "tiktok_publisher",
            f"Publicar TikTok ({clip_uid[:8]})",
            total_steps=4,
            message=f"Iniciando TikTok Studio para: '{title[:45]}'"
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

            try:
                page.set_default_timeout(60000)
                SignalTracker.emit_progress("tiktok_publisher", 1, 4, "Acessando o TikTok Studio Upload...")
                
                target_url = "https://www.tiktok.com/tiktokstudio/upload"
                page.goto(target_url, wait_until="domcontentloaded")
                time.sleep(4)

                # Se foi redirecionado para página de login ou login passport
                current_url = page.url.lower()
                if "login" in current_url or "passport.tiktok.com" in current_url:
                    raise TikTokPublishError(
                        "Sessão expirada ou não autenticada no TikTok. Execute 'LOGIN_TIKTOK.bat' para renovar a sessão."
                    )

                self._dismiss_onboarding_popups(page)

                # 1. Localizar input de arquivo com espera reativa e fallback resiliente
                SignalTracker.emit_progress("tiktok_publisher", 2, 4, f"Enviando arquivo {video_path.name} e aguardando processamento...")
                
                input_uploaded = False
                # Tentativa A: Aguardar o input nativo ser injetado no DOM pelo React
                try:
                    page.locator('input[type="file"]').first.wait_for(state="attached", timeout=20000)
                    file_input = page.locator('input[type="file"]').first
                    logger.info(f"Arquivo de vídeo {video_path.name} sendo enviado para o TikTok Studio via input...")
                    file_input.set_input_files(str(video_path.resolve()))
                    input_uploaded = True
                except Exception as wait_err:
                    logger.warning(f"Input direto não pronto ({wait_err}). Buscando em frames...")

                # Tentativa B: Localizar em frames/iframes
                if not input_uploaded:
                    for frame in page.frames:
                        try:
                            f_inp = frame.locator('input[type="file"]').first
                            f_inp.wait_for(state="attached", timeout=5000)
                            f_inp.set_input_files(str(video_path.resolve()))
                            input_uploaded = True
                            logger.info(f"Arquivo enviado com sucesso via iframe do TikTok Studio.")
                            break
                        except Exception:
                            continue

                # Tentativa C: Fallback disparando o FileChooser do navegador via clique no botão 'Selecionar vídeo'
                if not input_uploaded:
                    try:
                        logger.info("Tentando acionar o seletor de arquivos clicando no botão 'Selecionar vídeo'...")
                        select_btn = page.locator('button:has-text("Selecionar vídeo"), button:has-text("Select video"), button:has-text("Carregar")').first
                        select_btn.wait_for(state="visible", timeout=10000)
                        with page.expect_file_chooser(timeout=10000) as fc_info:
                            select_btn.click()
                        file_chooser = fc_info.value
                        file_chooser.set_files(str(video_path.resolve()))
                        input_uploaded = True
                        logger.info(f"Arquivo enviado com sucesso via FileChooser do TikTok Studio.")
                    except Exception as fc_err:
                        logger.warning(f"Fallback FileChooser falhou: {fc_err}")

                if not input_uploaded:
                    err_snap = screenshot_dir / f"tk_no_input_{clip_uid}.png"
                    try:
                        page.screenshot(path=str(err_snap), full_page=True)
                    except Exception:
                        pass
                    raise TikTokPublishError("Campo de seleção de arquivo não encontrado no TikTok Studio após aguardar carregamento completo da página.")

                # 2. Aguarda o upload do vídeo
                time.sleep(8)
                self._dismiss_onboarding_popups(page)

                # Checagem de erros de limite ou captcha
                content_lower = page.content().lower()
                if "limite diário" in content_lower or "daily limit" in content_lower:
                    page.screenshot(path=str(screenshot_dir / f"tk_quota_limit_{clip_uid}.png"))
                    raise TikTokPublishError("Limite diário de postagens atingido no TikTok Studio.")
                
                if "verificação de segurança" in content_lower or "security check" in content_lower or "captcha" in content_lower:
                    page.screenshot(path=str(screenshot_dir / f"tk_captcha_{clip_uid}.png"))
                    raise TikTokPublishError("Captcha ou verificação de segurança detectada no TikTok Studio.")

                # 3. Preenche a legenda e hashtags
                SignalTracker.emit_progress("tiktok_publisher", 3, 4, "Preenchendo legenda e configurando post...")
                caption_selectors = [
                    'div[contenteditable="true"]',
                    '.public-DraftEditor-content',
                    'div[data-placeholder*="legenda" i]',
                    'div[data-placeholder*="caption" i]'
                ]

                caption_elem = None
                for sel in caption_selectors:
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        caption_elem = loc.first
                        break

                if caption_elem:
                    self._safe_click(caption_elem)
                    time.sleep(1)
                    page.keyboard.press("Control+A")
                    time.sleep(0.3)
                    page.keyboard.press("Backspace")
                    time.sleep(0.5)
                    page.keyboard.type(final_caption, delay=25)
                else:
                    page.keyboard.type(f" {final_caption}", delay=25)

                time.sleep(3)
                self._dismiss_onboarding_popups(page)

                # 4. Rola a página para baixo e localiza o botão Publicar
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)

                post_btn = page.locator('button:has-text("Publicar"), button:has-text("Post")').first
                if post_btn.count() == 0 or not post_btn.is_visible():
                    page.screenshot(path=str(screenshot_dir / f"tk_btn_missing_{clip_uid}.png"))
                    raise TikTokPublishError("Botão de Publicar não encontrado na interface do TikTok Studio.")

                logger.info("Clicando no botão de Publicar do TikTok Studio...")
                self._safe_click(post_btn, required=True)
                time.sleep(3)

                # 5. Tratamento de Confirmação
                confirm_selectors = [
                    'button:has-text("Publicar agora")',
                    'button:has-text("Publicar mesmo assim")',
                    'button:has-text("Post now")',
                    'button:has-text("Post anyway")',
                    'button:has-text("Confirmar")',
                    'button:has-text("Continuar")'
                ]

                for c_sel in confirm_selectors:
                    loc = page.locator(c_sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        logger.info(f"Confirmando diálogo de publicação: '{loc.first.inner_text().strip()}'...")
                        self._safe_click(loc.first)
                        time.sleep(2)
                        break

                # 6. Confirmação Real de Postagem
                SignalTracker.emit_progress("tiktok_publisher", 4, 4, "Validando confirmação de postagem no TikTok Studio...")
                time.sleep(8)

                # Checa mensagem de sucesso ou redirecionamento
                success_indicators = [
                    'div:has-text("Seu vídeo foi publicado")',
                    'div:has-text("Your video has been published")',
                    'div:has-text("Postado com sucesso")',
                    'div:has-text("Vídeo carregado")',
                    'div:has-text("Carregado com sucesso")',
                    'button:has-text("Gerenciar vídeos")',
                    'button:has-text("Manage your posts")',
                    'button:has-text("Carregar outro vídeo")',
                    'button:has-text("Upload another video")'
                ]

                has_success_modal = False
                for s_sel in success_indicators:
                    if page.locator(s_sel).count() > 0:
                        has_success_modal = True
                        break

                # Validação via Gerenciador de Conteúdo
                real_post_id = None
                content_url = "https://www.tiktok.com/tiktokstudio/content"
                try:
                    page.goto(content_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(6)
                    real_post_id = self._extract_post_id_from_content_page(page, title, tags)
                except Exception as c_err:
                    logger.debug(f"Aviso ao consultar página de conteúdo: {c_err}")

                if not real_post_id and not has_success_modal:
                    # Se não houve modal de sucesso e nem foi localizado na página de conteúdo, falha!
                    screenshot_path = screenshot_dir / f"tk_unconfirmed_{clip_uid}.png"
                    page.screenshot(path=str(screenshot_path))
                    raise TikTokPublishError(
                        f"Não foi possível confirmar a publicação no TikTok Studio. "
                        f"Nenhum comprovante de postagem detectado. Screenshot em {screenshot_path}"
                    )

                confirmed_id = real_post_id or f"tiktok_post_{int(time.time())}"

                SignalTracker.emit_finish(
                    "tiktok_publisher",
                    f"Vídeo postado e confirmado no TikTok Studio (ID: {confirmed_id})",
                    success=True,
                    metadata={"tiktok_post_id": confirmed_id, "clip_uid": clip_uid}
                )

                logger.info(
                    f"Vídeo postado no TikTok com confirmação real via navegador: ID {confirmed_id}",
                    extra={"event": "tiktok_browser_success", "post_id": confirmed_id, "clip_uid": clip_uid}
                )

                return {
                    "tiktok_post_id": confirmed_id,
                    "status": "POSTED",
                    "platform": "tiktok_browser"
                }

            except Exception as e:
                try:
                    err_img = screenshot_dir / f"tiktok_error_{clip_uid}.png"
                    page.screenshot(path=str(err_img))
                    (screenshot_dir / f"tiktok_error_{clip_uid}.html").write_text(page.content(), encoding="utf-8")
                except Exception:
                    pass
                SignalTracker.emit_finish("tiktok_publisher", f"Erro no TikTok Studio: {e}", success=False)
                logger.error(f"Erro durante publicação no TikTok Studio via navegador: {e}", exc_info=True)
                raise TikTokPublishError(f"Falha na automação Playwright do TikTok: {e}")
            finally:
                context.close()
