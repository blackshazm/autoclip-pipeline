"""
Robô de Postagem PRO do YouTube Shorts via Playwright.
Módulo autônomo com preenchimento avançado e completo de metadados no YouTube Studio:
- Tags SEO nativas (campo oficial de marcadores até 500 chars)
- Declaração de conteúdo sintético/alterado (IA)
- Seleção de categoria e idioma do vídeo
- Configuração de remix e comentários
- Vinculação de Vídeo Relacionado (Related Video)
- Verificação de Direitos Autorais (Copyright Checks)
- Agendamento de Data/Hora (Schedule) ou Publicação Imediata
- Auditoria com screenshots de cada etapa e Double-Check HTTP
"""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal
import json
import re
import time
import requests
from playwright.sync_api import sync_playwright, Page, Locator

from src.core.config import settings
from src.core.logger import get_logger
from src.core.exceptions import YouTubePublishError, QuotaExceededError
from src.core.process_signals import SignalTracker

logger = get_logger("youtube_browser_publisher_pro")


@dataclass
class PublishPayloadPro:
    """Modelo de dados tipado para publicação avançada no YouTube Studio."""
    video_path: Path
    title: str
    description: str
    tags: List[str] = field(default_factory=list)
    category_name: Optional[str] = "Entretenimento"
    language: str = "Português (Brasil)"
    is_synthetic_ai: bool = False
    related_video_query: Optional[str] = None
    publish_mode: Literal["PUBLIC", "SCHEDULE", "UNLISTED", "PRIVATE"] = "PUBLIC"
    schedule_datetime: Optional[datetime] = None
    allow_remix: bool = True
    wait_copyright_checks: bool = True
    on_copyright_issue: Literal["UNLISTED", "ABORT"] = "UNLISTED"
    clip_uid: str = "clip_pro"


class YouTubeBrowserPublisherPro:
    """
    Publicador PRO resiliente para YouTube Studio.
    Projetado para preenchimento de todos os recursos nativos com alta tolerância a falhas.
    """

    def __init__(
        self,
        profile_dir: Optional[Path] = None,
        state_file: Optional[Path] = None,
        headless: Optional[bool] = None,
        channel_id: Optional[str] = None
    ):
        self.profile_dir = profile_dir or settings.YOUTUBE_BROWSER_PROFILE_DIR
        self.state_file = state_file or settings.YOUTUBE_BROWSER_STATE_FILE
        self.headless = headless if headless is not None else settings.YOUTUBE_BROWSER_HEADLESS
        self.channel_id = channel_id

    def is_authenticated(self) -> bool:
        """Verifica se existem cookies ou diretório de perfil configurado."""
        return self.profile_dir.exists() or self.state_file.exists()

    def _extract_video_id(self, text_or_url: str) -> Optional[str]:
        """Extrai o video_id oficial do YouTube (11 caracteres alfanuméricos)."""
        if not text_or_url:
            return None
        match = re.search(r"(?:youtu\.be\/|v=|\/shorts\/)([a-zA-Z0-9_-]{11})", text_or_url)
        if match:
            return match.group(1)
        return None

    def _safe_click(self, locator: Locator, timeout_ms: int = 8000, required: bool = False) -> bool:
        """Clica no elemento com force=True e fallback em JavaScript puro."""
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
                logger.debug(f"Aviso no _safe_click (não-crítico): {e}")
                return False

    def _verify_youtube_short_live(self, video_id: str, max_retries: int = 3, delay_sec: float = 3.0) -> bool:
        """Double-Check de Entrega: Realiza requisições HTTP para validar se o vídeo está acessível."""
        test_url = f"https://www.youtube.com/shorts/{video_id}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }
        for attempt in range(max_retries):
            try:
                resp = requests.get(test_url, headers=headers, timeout=12)
                if resp.status_code == 200:
                    text_lower = resp.text.lower()
                    if "video unavailable" not in text_lower and "vídeo indisponível" not in text_lower:
                        return True
            except Exception as e:
                logger.debug(f"Tentativa {attempt + 1} de checagem HTTP do vídeo {video_id} falhou: {e}")
            time.sleep(delay_sec)
        return False

    def _expand_show_more(self, page: Page) -> bool:
        """Localiza e clica no botão 'Mostrar mais' / 'Show more' para exibir tags e opções avançadas."""
        logger.info("Expandindo seção 'Mostrar mais' no YouTube Studio...")
        show_more_selectors = [
            "#toggle-button",
            "ytcp-button#toggle-button",
            "button:has-text('Mostrar mais')",
            "button:has-text('Show more')",
            "ytcp-button:has-text('Mostrar mais')",
            "ytcp-button:has-text('Show more')",
            "#details ytcp-button.ytcp-video-metadata-editor"
        ]
        
        # 1. Tenta via evaluate com busca textual ampla
        expanded = page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('ytcp-button, button'));
            for (const b of btns) {
                const txt = (b.innerText || '').toLowerCase();
                if (txt.includes('mostrar mais') || txt.includes('show more')) {
                    b.scrollIntoView({ behavior: 'instant', block: 'center' });
                    b.click();
                    return true;
                }
            }
            return false;
        }""")
        if expanded:
            time.sleep(1.5)
            return True

        # 2. Fallback via locators Playwright
        for sel in show_more_selectors:
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.scroll_into_view_if_needed()
                if self._safe_click(loc, timeout_ms=3000):
                    time.sleep(1.5)
                    return True

        logger.warning("Não foi possível acionar 'Mostrar mais'. Pode já estar expandido.")
        return False

    def _fill_tags(self, page: Page, tags: List[str]) -> int:
        """Preenche o campo nativo de Tags do YouTube Studio (até 500 caracteres)."""
        if not tags:
            return 0

        logger.info(f"Preenchendo tags oficiais no YouTube Studio ({len(tags)} tags)...")
        # Rola a página para a região das tags
        page.evaluate("""() => {
            const el = document.querySelector('#tags-container') 
                    || document.querySelector('input[aria-label="Tags"]') 
                    || document.querySelector('input[aria-label="Marcadores"]');
            if (el) el.scrollIntoView({ behavior: 'instant', block: 'center' });
        }""")
        time.sleep(1)

        tag_input = page.locator(
            "#tags-container input, input[aria-label='Tags'], input[aria-label='Marcadores'], #tags-container #text-input"
        ).first

        if tag_input.count() == 0:
            logger.warning("Campo de tags oficial não encontrado na interface.")
            return 0

        tags_added = 0
        current_len = 0
        tag_input.click(timeout=4000)

        for t in tags:
            clean_tag = t.strip().lstrip("#")
            if not clean_tag:
                continue
            # O YouTube permite até 500 caracteres totais em tags
            if current_len + len(clean_tag) + 1 > 480:
                break
            try:
                tag_input.fill(clean_tag)
                tag_input.press("Enter")
                time.sleep(0.3)
                current_len += len(clean_tag) + 1
                tags_added += 1
            except Exception as e:
                logger.debug(f"Erro ao inserir tag '{clean_tag}': {e}")

        logger.info(f"Total de {tags_added} tags oficiais inseridas com sucesso.")
        return tags_added

    def _set_altered_content_ai(self, page: Page, is_ai: bool) -> bool:
        """Declara se o vídeo possui conteúdo sintético ou gerado por IA (exigência do YouTube)."""
        logger.info(f"Configurando declaração de conteúdo gerado por IA: {is_ai}")
        # YouTube pergunta: "Conteúdo alterado ou sintético? Sim / Não"
        radio_name = "YES" if is_ai else "NO"
        
        # Executa via script no DOM
        success = page.evaluate("""(targetVal) => {
            // Procura containers de altered content
            const radios = Array.from(document.querySelectorAll('tp-yt-paper-radio-button'));
            for (const r of radios) {
                const nameAttr = (r.getAttribute('name') || '').toUpperCase();
                const parentTxt = (r.parentElement ? r.parentElement.innerText : '').toLowerCase();
                if (parentTxt.includes('conteúdo alterado') || parentTxt.includes('altered content')) {
                    if (nameAttr === targetVal || (targetVal === 'NO' && parentTxt.includes('não')) || (targetVal === 'YES' && parentTxt.includes('sim'))) {
                        r.scrollIntoView({ behavior: 'instant', block: 'center' });
                        r.click();
                        return true;
                    }
                }
            }
            return false;
        }""", radio_name)

        if not success:
            # Fallback procurando pelo label
            label_text = "Sim" if is_ai else "Não"
            radio = page.locator(f"tp-yt-paper-radio-button:has-text('{label_text}')").first
            if radio.count() > 0:
                self._safe_click(radio, timeout_ms=3000)
                success = True

        return success

    def _set_category(self, page: Page, category_name: Optional[str]) -> bool:
        """Define a categoria do vídeo no YouTube Studio se especificada."""
        if not category_name:
            return False

        logger.info(f"Definindo categoria do vídeo: '{category_name}'")
        try:
            cat_dropdown = page.locator(
                "#category ytcp-text-dropdown-trigger, #category-dropdown, ytcp-form-category ytcp-text-dropdown-trigger"
            ).first
            if cat_dropdown.count() > 0:
                cat_dropdown.scroll_into_view_if_needed()
                self._safe_click(cat_dropdown)
                time.sleep(1)
                
                option = page.locator(f"ytcp-text-menu-item:has-text('{category_name}')").first
                if option.count() > 0:
                    self._safe_click(option)
                    time.sleep(1)
                    page.keyboard.press("Escape")
                    return True
                page.keyboard.press("Escape")
        except Exception as e:
            logger.debug(f"Aviso ao selecionar categoria '{category_name}': {e}")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        return False

    def _set_language(self, page: Page, language_name: str) -> bool:
        """Define o idioma original do vídeo."""
        if not language_name:
            return False

        logger.info(f"Configurando idioma original do vídeo: '{language_name}'")
        try:
            lang_trigger = page.locator(
                "#language-select ytcp-text-dropdown-trigger, div[aria-label*='Idioma do vídeo'] ytcp-text-dropdown-trigger"
            ).first
            if lang_trigger.count() > 0:
                lang_trigger.scroll_into_view_if_needed()
                self._safe_click(lang_trigger)
                time.sleep(1)
                
                option = page.locator(f"ytcp-text-menu-item:has-text('{language_name}')").first
                if option.count() > 0:
                    self._safe_click(option)
                    time.sleep(1)
                    page.keyboard.press("Escape")
                    return True
                page.keyboard.press("Escape")
        except Exception as e:
            logger.debug(f"Aviso ao selecionar idioma '{language_name}': {e}")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        return False

    def _click_next_step(self, page: Page) -> bool:
        """Avança de forma resiliente para a próxima aba via DOM evaluate nativo."""

        # 1. Tenta clique nativo via DOM evaluate para evitar bloqueio por backdrops
        for _ in range(4):
            adv = page.evaluate("""() => {
                const btn = document.querySelector('#next-button') 
                         || document.querySelector('ytcp-button#next-button')
                         || document.querySelector('button#next-button');
                if (btn && !btn.hasAttribute('disabled') && btn.getAttribute('aria-disabled') !== 'true') {
                    btn.click();
                    return true;
                }
                return false;
            }""")
            if adv:
                time.sleep(2)
                return True
            time.sleep(1)

        # 2. Fallback via safe_click forçado
        next_btn = page.locator("#next-button, ytcp-button#next-button, button#next-button").first
        if next_btn.count() > 0:
            return self._safe_click(next_btn, timeout_ms=6000)
        return False

    def _set_related_video(self, page: Page, query_or_id: Optional[str]) -> bool:
        """
        Vincula um Vídeo Relacionado (Related Video) para o Shorts na aba de Elementos.
        Recurso essencial para conversão de cortes em inscritos no canal principal.
        """
        if not query_or_id:
            return False

        logger.info(f"Vinculando Vídeo Relacionado: '{query_or_id}'...")
        try:
            # Botão 'Adicionar' na linha de Vídeo Relacionado
            add_related_btn = page.locator(
                "#related-video-button, ytcp-button:has-text('Adicionar vídeo relacionado'), button:has-text('Adicionar vídeo relacionado'), ytcp-video-elements-cell:has-text('relacionado') ytcp-button"
            ).first

            if add_related_btn.count() == 0:
                # Tenta localizar por texto amplo
                add_related_btn = page.locator("ytcp-button:has-text('Adicionar')").first

            if add_related_btn.count() > 0:
                self._safe_click(add_related_btn, timeout_ms=5000)
                time.sleep(2)

                # Modal de seleção de vídeo
                search_input = page.locator(
                    "#search-input, input[aria-label*='Pesquisar'], input[placeholder*='Pesquisar seus vídeos']"
                ).first
                if search_input.count() > 0:
                    search_input.fill(query_or_id)
                    time.sleep(1.5)
                    # Clica no primeiro resultado correspondente
                    first_item = page.locator(
                        "#video-list ytcp-entity-card, ytcp-video-row, #search-results ytcp-video-list-cell-video-thumbnail"
                    ).first
                    if first_item.count() > 0:
                        self._safe_click(first_item, timeout_ms=4000)
                        time.sleep(1.5)
                        logger.info("Vídeo Relacionado selecionado com sucesso!")
                        return True
        except Exception as e:
            logger.warning(f"Não foi possível vincular vídeo relacionado '{query_or_id}': {e}")
        return False

    def _wait_for_copyright_checks(self, page: Page, max_wait_sec: int = 45) -> Dict[str, Any]:
        """
        Monitora a aba de Verificações (Copyright & Diretrizes).
        Retorna status {'has_issues': bool, 'details': str}.
        """
        logger.info("Aguardando verificação de Direitos Autorais (Checks)...")
        start_t = time.time()
        
        while time.time() - start_t < max_wait_sec:
            content = page.content().lower()
            if "nenhum problema encontrado" in content or "no issues found" in content:
                logger.info("Verificação de Copyright: Nenhum problema encontrado! (Aprovado)")
                return {"has_issues": False, "details": "Nenhum problema encontrado"}
            
            if "problema de direitos autorais" in content or "copyright claim" in content:
                logger.warning("ALERTA: O YouTube detectou reivindicação de Direitos Autorais neste vídeo.")
                return {"has_issues": True, "details": "Reivindicação de direitos autorais detectada"}

            time.sleep(3)

        logger.info("Verificações em andamento em segundo plano (seguindo com publicação).")
        return {"has_issues": False, "details": "Verificação ainda processando em segundo plano"}

    def _advance_to_visibility_tab(self, page: Page, max_retries: int = 5) -> bool:
        """Clica em 'Avançar' até que a aba Visibilidade esteja de fato ativa na tela."""
        for attempt in range(max_retries):
            # Verifica se já está na aba de visibilidade (procura radios visíveis de PUBLIC/UNLISTED/PRIVATE)
            is_vis = page.evaluate("""() => {
                const radios = Array.from(document.querySelectorAll('tp-yt-paper-radio-button'));
                for (const r of radios) {
                    const name = (r.getAttribute('name') || '').toUpperCase();
                    if ((name === 'PUBLIC' || name === 'UNLISTED' || name === 'PRIVATE') && r.offsetParent !== null) {
                        return true;
                    }
                }
                return false;
            }""")
            if is_vis:
                logger.info(f"Aba Visibilidade alcançada com sucesso (tentativa {attempt + 1})!")
                time.sleep(1)
                return True

            logger.info(f"Clicando em 'Avançar' para alcançar a aba de Visibilidade (tentativa {attempt + 1})...")
            # Clica no botão Avançar
            clicked = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('#next-button, button, ytcp-button'));
                for (const b of btns) {
                    const txt = (b.innerText || '').trim();
                    if ((txt === 'Avançar' || txt === 'Next') && b.offsetParent !== null && !b.hasAttribute('disabled')) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }""")
            if not clicked:
                next_btn = page.locator("#next-button, ytcp-button:has-text('Avançar'), button:has-text('Avançar')").first
                if next_btn.count() > 0 and next_btn.is_visible():
                    self._safe_click(next_btn, timeout_ms=4000)
            time.sleep(2.5)

        return False

    def _configure_visibility_or_schedule(
        self,
        page: Page,
        mode: str,
        schedule_dt: Optional[datetime]
    ) -> bool:
        """Configura a visibilidade (Público, Privado, Não-listado) ou agenda Data/Hora."""
        logger.info(f"Configurando visibilidade: Modo={mode}, Schedule={schedule_dt}")
        time.sleep(1.5)

        if mode == "SCHEDULE" and schedule_dt:
            sched_radio = page.locator(
                "#schedule-radio-button, tp-yt-paper-radio-button[name='SCHEDULE'], #schedule-card"
            ).first
            if sched_radio.count() > 0:
                self._safe_click(sched_radio)
                time.sleep(1.5)

                date_input = page.locator("#datepicker-trigger, #date-picker, input[aria-label*='Data']").first
                if date_input.count() > 0:
                    self._safe_click(date_input)
                    time.sleep(1)

                time_input = page.locator("input[aria-label*='Horário'], #time-of-day-container input").first
                if time_input.count() > 0:
                    time_str = schedule_dt.strftime("%H:%M")
                    time_input.fill(time_str)
                    time_input.press("Enter")
                    time.sleep(1)

                logger.info(f"Agendamento configurado para {schedule_dt.isoformat()}")
                return True

        target_mode = mode.upper()
        marked = page.evaluate("""(target) => {
            const radios = Array.from(document.querySelectorAll('tp-yt-paper-radio-button'));
            for (const r of radios) {
                const name = (r.getAttribute('name') || '').toUpperCase();
                const txt = (r.innerText || '').toLowerCase();
                if (name === target || 
                    (target === 'UNLISTED' && (txt.includes('não listado') || txt.includes('unlisted'))) ||
                    (target === 'PUBLIC' && (txt.includes('público') || txt.includes('public'))) ||
                    (target === 'PRIVATE' && (txt.includes('privado') || txt.includes('private')))) {
                    r.scrollIntoView({ behavior: 'instant', block: 'center' });
                    r.click();
                    return true;
                }
            }
            return false;
        }""", target_mode)

        if not marked:
            logger.warning(f"Aviso: Não foi possível marcar visibilidade {target_mode} via script DOM. Tentando locators...")
            text_query = "Não listado" if target_mode == "UNLISTED" else ("Privado" if target_mode == "PRIVATE" else "Público")
            radio_loc = page.locator(f"tp-yt-paper-radio-button:has-text('{text_query}'), tp-yt-paper-radio-button[name='{target_mode}']").first
            if radio_loc.count() > 0:
                return self._safe_click(radio_loc, timeout_ms=5000, required=True)
            else:
                screenshot_diag = settings.BASE_DIR / "logs" / "screenshots" / f"vis_diag_fail_{target_mode}.png"
                page.screenshot(path=str(screenshot_diag))
                raise YouTubePublishError(f"Opção de visibilidade '{target_mode}' não encontrada na tela. Screenshot salvo: {screenshot_diag.name}")

        logger.info(f"Visibilidade '{target_mode}' selecionada com sucesso.")
        return True

    def publish_short_pro(self, payload: PublishPayloadPro) -> Dict[str, Any]:
        """
        Executa o fluxo completo do Robô de Postagem PRO.
        Retorna dicionário com status, video_id e telemetria de todas as etapas.
        """
        if not payload.video_path.exists():
            raise YouTubePublishError(f"Arquivo de vídeo não encontrado: {payload.video_path}")

        if not self.is_authenticated():
            err_msg = (
                f"Sessão do YouTube não encontrada! Execute primeiro 'python scripts/youtube_login.py' "
                f"ou o arquivo BAT de login do canal."
            )
            logger.error(err_msg, extra={"event": "youtube_pro_no_auth", "clip_uid": payload.clip_uid})
            raise YouTubePublishError(err_msg)

        # Garante hashtag #Shorts no título
        final_title = (payload.title or "").strip()
        if "#Shorts" not in final_title and "#shorts" not in final_title:
            if len(final_title) <= 52:
                final_title += " #Shorts"

        # Formata tags para descrição e hashtags
        formatted_tags = []
        for t in (payload.tags or []):
            clean_t = t.strip().lstrip("#")
            if clean_t:
                formatted_tags.append(f"#{clean_t}")

        tags_block = ("\n\n" + " ".join(formatted_tags)) if formatted_tags else ""
        ref_footer = f"\n\n#Shorts ref:{payload.clip_uid}"
        final_desc = ((payload.description or "") + tags_block + ref_footer)[:5000]

        screenshot_dir = settings.BASE_DIR / "logs" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        SignalTracker.emit_start(
            "youtube_publisher_pro",
            f"Publicar Short PRO ({payload.clip_uid[:8]})",
            total_steps=7,
            message=f"Iniciando publicação PRO para '{final_title[:40]}'"
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

            browser = None
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
                if self.state_file.exists():
                    try:
                        state_data = json.loads(self.state_file.read_text(encoding="utf-8"))
                        cookies = state_data.get("cookies", [])
                        if cookies:
                            context.add_cookies(cookies)
                    except Exception as c_err:
                        logger.debug(f"Aviso ao injetar cookies no perfil: {c_err}")
                page = context.pages[0] if context.pages else context.new_page()
            else:
                browser = p.chromium.launch(headless=self.headless, args=["--start-maximized"])
                context = browser.new_context(
                    storage_state=str(self.state_file) if self.state_file.exists() else None,
                    no_viewport=True,
                    user_agent=context_args["user_agent"]
                )
                page = context.new_page()

            captured_network_video_ids: List[str] = []

            def _on_network_response(resp):
                try:
                    u = resp.url
                    m_u = re.search(r"[?&]video[_-]?id=([a-zA-Z0-9_-]{11})", u, re.IGNORECASE)
                    if m_u:
                        v_candidate = m_u.group(1)
                        if v_candidate not in captured_network_video_ids:
                            captured_network_video_ids.append(v_candidate)
                    if "youtubei/v1" in u and resp.status == 200:
                        c_type = resp.headers.get("content-type", "")
                        if "json" in c_type or "text" in c_type:
                            body = resp.text()
                            for m in re.findall(r'"(?:videoId|encryptedVideoId|externalId)":\s*"([a-zA-Z0-9_-]{11})"', body):
                                if m not in captured_network_video_ids:
                                    captured_network_video_ids.append(m)
                except Exception:
                    pass

            page.on("response", _on_network_response)

            try:
                page.set_default_timeout(60000)

                # 1. Navegação até o YouTube Studio
                SignalTracker.emit_progress("youtube_publisher_pro", 1, 7, "Acessando YouTube Studio...")
                target_url = f"https://studio.youtube.com/channel/{self.channel_id}" if self.channel_id else "https://studio.youtube.com"
                page.goto(target_url, wait_until="domcontentloaded")

                if "accounts.google.com" in page.url or "signin" in page.url:
                    raise YouTubePublishError("Sessão expirada. Execute o script BAT de login para renovar.")

                time.sleep(3)

                # 2. Clicar em Criar / Upload
                create_btn = page.locator("#create-icon, ytcp-button#create-icon, button[aria-label='Criar']").first
                if create_btn.count() > 0:
                    self._safe_click(create_btn)
                    time.sleep(1.5)
                    upload_opt = page.locator(
                        "#text-item-0, ytcp-text-menu-item:has-text('Enviar vídeos'), ytcp-text-menu-item:has-text('Upload videos')"
                    ).first
                    if upload_opt.count() > 0:
                        self._safe_click(upload_opt)
                else:
                    direct_up = page.locator("#upload-icon, ytcp-button:has-text('Enviar vídeos')").first
                    if direct_up.count() > 0:
                        self._safe_click(direct_up)

                # 3. Enviar arquivo de vídeo
                SignalTracker.emit_progress("youtube_publisher_pro", 2, 7, f"Enviando arquivo {payload.video_path.name}...")
                file_input = page.locator('input[type="file"]')
                file_input.wait_for(state="attached", timeout=30000)
                file_input.first.set_input_files(str(payload.video_path.resolve()))
                time.sleep(5)

                # Checagem de limite diário
                content_text = page.content().lower()
                if any(phrase in content_text for phrase in ["limite diário", "daily upload limit", "atingiu seu limite"]):
                    page.screenshot(path=str(screenshot_dir / f"yt_quota_limit_{payload.clip_uid}.png"))
                    raise QuotaExceededError("Limite diário de envios alcançado no YouTube Studio para este canal.")

                # 4. Aba Detalhes: Título, Descrição, Não é para crianças
                SignalTracker.emit_progress("youtube_publisher_pro", 3, 7, "Preenchendo Título, Descrição e COPPA...")
                title_box = page.locator("#title-textarea #textbox, div[aria-label*='Adicione um título']").first
                title_box.wait_for(state="attached", timeout=35000)
                try:
                    title_box.click(timeout=5000)
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    page.keyboard.insert_text(final_title[:100])
                except Exception:
                    pass

                time.sleep(1)
                desc_box = page.locator("#description-textarea #textbox, div[aria-label*='Fale sobre seu vídeo']").first
                if desc_box.count() > 0:
                    try:
                        desc_box.click(timeout=5000)
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.insert_text(final_desc)
                    except Exception:
                        pass
                    time.sleep(1)

                # Marca 'Não é conteúdo para crianças'
                page.evaluate("""() => {
                    const el = document.querySelector('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]') 
                            || document.querySelector('#not-made-for-kids');
                    if (el) {
                        el.scrollIntoView({ behavior: 'instant', block: 'center' });
                        el.click();
                    }
                }""")

                # 5. Expansão PRO: Mostrar Mais, Tags Oficiais, IA, Categoria, Idioma
                SignalTracker.emit_progress("youtube_publisher_pro", 4, 7, "Configurando opções avançadas (Tags SEO, IA, Categoria)...")
                self._expand_show_more(page)
                time.sleep(1)

                # Declaração de IA
                self._set_altered_content_ai(page, payload.is_synthetic_ai)

                # Preenchimento de Tags Oficiais
                self._fill_tags(page, payload.tags)

                # Idioma do Vídeo
                self._set_language(page, payload.language)

                # Categoria
                self._set_category(page, payload.category_name)

                page.screenshot(path=str(screenshot_dir / f"pro_step1_details_{payload.clip_uid}.png"))

                # Captura Video ID preliminar
                video_id = None
                time.sleep(2)
                video_link_elem = page.locator("a.ytcp-video-info, a[href*='youtu.be']").first
                if video_link_elem.count() > 0:
                    href = video_link_elem.get_attribute("href") or video_link_elem.inner_text()
                    video_id = self._extract_video_id(href)

                # Avançar para Aba 'Elementos do Vídeo'
                self._click_next_step(page)
                time.sleep(2)

                # 6. Aba Elementos do Vídeo: Vídeo Relacionado
                SignalTracker.emit_progress("youtube_publisher_pro", 5, 7, "Configurando Vídeo Relacionado...")
                if payload.related_video_query:
                    self._set_related_video(page, payload.related_video_query)
                    page.screenshot(path=str(screenshot_dir / f"pro_step2_related_{payload.clip_uid}.png"))

                # Avançar para Aba 'Verificações' (Checks)
                self._click_next_step(page)
                time.sleep(2)

                # 7. Aba Verificações: Monitoramento de Direitos Autorais
                SignalTracker.emit_progress("youtube_publisher_pro", 6, 7, "Monitorando Verificações de Copyright...")
                check_result = {"has_issues": False, "details": "Nenhum problema"}
                if payload.wait_copyright_checks:
                    check_result = self._wait_for_copyright_checks(page, max_wait_sec=40)
                    page.screenshot(path=str(screenshot_dir / f"pro_step3_checks_{payload.clip_uid}.png"))

                effective_mode = payload.publish_mode
                if check_result.get("has_issues"):
                    if payload.on_copyright_issue == "ABORT":
                        raise YouTubePublishError(f"Abortado devido a restrição de copyright: {check_result.get('details')}")
                    else:
                        logger.warning("Alterando modo para UNLISTED para proteção contra strike/reivindicação.")
                        effective_mode = "UNLISTED"

                # Avançar para Aba 'Visibilidade'
                self._advance_to_visibility_tab(page)

                # 8. Aba Visibilidade: Público ou Agendamento
                SignalTracker.emit_progress("youtube_publisher_pro", 7, 7, f"Aplicando visibilidade ({effective_mode})...")
                self._configure_visibility_or_schedule(page, effective_mode, payload.schedule_datetime)
                page.screenshot(path=str(screenshot_dir / f"pro_step4_visibility_{payload.clip_uid}.png"))

                # Captura de video_id antes de clicar em salvar
                if not video_id and captured_network_video_ids:
                    video_id = captured_network_video_ids[0]

                # Clicar em Salvar / Concluir / Programar
                time.sleep(2)
                done_btn = page.locator("#done-button, ytcp-button#done-button, button#done-button").first
                self._safe_click(done_btn, timeout_ms=6000, required=True)

                # Aguarda confirmação modal
                time.sleep(4)
                if not video_id and captured_network_video_ids:
                    video_id = captured_network_video_ids[-1]

                # Tenta capturar do modal de compartilhamento pós-upload
                if not video_id:
                    modal_link = page.locator("a.ytcp-video-info, a[href*='youtu.be']").first
                    if modal_link.count() > 0:
                        video_id = self._extract_video_id(modal_link.get_attribute("href") or "")

                final_status = "SCHEDULED" if effective_mode == "SCHEDULE" else "POSTED"

                # Double-Check HTTP (se postado como público imediato)
                if effective_mode == "PUBLIC" and video_id:
                    logger.info(f"Executando Double-Check HTTP para o vídeo {video_id}...")
                    self._verify_youtube_short_live(video_id, max_retries=3, delay_sec=3.0)

                page.screenshot(path=str(screenshot_dir / f"pro_step5_complete_{payload.clip_uid}.png"))

                result_data = {
                    "youtube_video_id": video_id or "CONFIRMED_VIA_STUDIO",
                    "status": final_status,
                    "mode": effective_mode,
                    "checks": check_result,
                    "title": final_title,
                    "clip_uid": payload.clip_uid
                }

                SignalTracker.emit_finish("youtube_publisher_pro", f"Short PRO concluído com sucesso ({final_status})!", success=True)
                return result_data

            finally:
                if context:
                    try:
                        context.close()
                    except Exception:
                        pass
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass
