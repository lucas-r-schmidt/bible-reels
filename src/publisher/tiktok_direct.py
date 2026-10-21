"""
src/publisher/tiktok_direct.py
------------------------------
Publicação direta no TikTok via Playwright (Navegador com sessão salva).
Funciona em qualquer conta pessoal do TikTok. Não requer empresa, CNPJ nem aprovação de API.
"""
from pathlib import Path
from typing import Any
import json
import time

from config.settings import ROOT_DIR, OUTPUT_VIDEOS
from src.utils.logger import get_logger

log = get_logger(__name__)

SESSION_FILE = ROOT_DIR / "data" / "tiktok_session.json"
TIKTOK_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?from=creator_center"


def ensure_tiktok_session() -> bool:
    """Gera o arquivo de sessão a partir do TIKTOK_SESSION_ID se necessário."""
    if SESSION_FILE.is_file() and SESSION_FILE.stat().st_size > 50:
        return True
    from config.settings import TIKTOK_SESSION_ID
    if TIKTOK_SESSION_ID:
        cookies = [
            {"name": "sessionid", "value": TIKTOK_SESSION_ID, "domain": ".tiktok.com", "path": "/", "expires": -1, "httpOnly": True, "secure": True, "sameSite": "None"},
            {"name": "sessionid_ss", "value": TIKTOK_SESSION_ID, "domain": ".tiktok.com", "path": "/", "expires": -1, "httpOnly": True, "secure": True, "sameSite": "None"},
            {"name": "sid_tt", "value": TIKTOK_SESSION_ID, "domain": ".tiktok.com", "path": "/", "expires": -1, "httpOnly": True, "secure": True, "sameSite": "None"}
        ]
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(json.dumps({"cookies": cookies, "origins": []}, indent=2), encoding="utf-8")
        log.info("Sessão do TikTok gerada automaticamente a partir de TIKTOK_SESSION_ID.")
        return True
    return False


def is_tiktok_authenticated() -> bool:
    """Verifica se existe arquivo de sessão válido do TikTok."""
    return ensure_tiktok_session()


def setup_tiktok_session() -> bool:
    """Abre o Chrome real sem marcas de automação para o usuário fazer login no TikTok."""
    from playwright.sync_api import sync_playwright

    log.info("Abrindo Google Chrome real para login no TikTok...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 850},
            locale="pt-BR",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Oculta propriedades de automação
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")

        log.info("Aguardando login no TikTok (QR Code, Google ou E-mail)...")
        logged_in = False
        for _ in range(120):  # Espera até 4 minutos
            time.sleep(2)
            try:
                cookies = context.cookies()
                has_session = any(c["name"] in ("sessionid", "sessionid_ss") for c in cookies)
                if has_session:
                    logged_in = True
                    break
            except Exception:
                pass

        if logged_in:
            time.sleep(3)
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(SESSION_FILE))
            log.info("Sessão do TikTok salva com sucesso em data/tiktok_session.json!")
            browser.close()
            return True
        else:
            log.warning("Tempo limite de login no TikTok esgotado.")
            browser.close()
            return False


def dismiss_tiktok_modals(page) -> None:
    """Fecha avisos, modais de análise de direitos autorais ou tutoriais que sobrepõem a tela."""
    try:
        page.keyboard.press("Escape")
        time.sleep(0.5)

        dismiss_selectors = [
            "button:has-text('Entendi')",
            "button:has-text('Got it')",
            "button:has-text('OK')",
            "button:has-text('Fechar')",
            "button:has-text('Continuar')",
            "button:has-text('Not now')",
            "button:has-text('Agora não')",
            "div[data-floating-ui-portal] button",
            ".TUXModal button",
            "div[role='dialog'] button",
        ]
        for sel in dismiss_selectors:
            matches = page.locator(sel)
            count = matches.count()
            for i in range(min(count, 3)):
                btn = matches.nth(i)
                if btn.is_visible():
                    btn.click(timeout=1000, force=True)
                    time.sleep(0.5)
    except Exception:
        pass


def publish_via_tiktok_direct(post_data: dict[str, Any]) -> bool:
    """Publica vídeo diretamente no TikTok Studio via Playwright."""
    from playwright.sync_api import sync_playwright

    if not is_tiktok_authenticated():
        log.warning("Sessão do TikTok não encontrada. Iniciando login interativo...")
        if not setup_tiktok_session():
            return False

    video_file = post_data.get("video_path")
    media_to_send: Path | None = None

    if video_file and Path(video_file).is_file():
        media_to_send = Path(video_file)
    elif video_file and (OUTPUT_VIDEOS / Path(video_file).name).is_file():
        media_to_send = OUTPUT_VIDEOS / Path(video_file).name

    if not media_to_send or not media_to_send.is_file():
        log.error(f"Nenhum arquivo de vídeo encontrado para o TikTok no Post #{post_data.get('id')}.")
        return False

    caption = f"{post_data.get('formatted_text', '')}\n\n{post_data.get('hashtags', '')}".strip()

    log.info(f"Iniciando publicação do Post #{post_data.get('id')} no TikTok em segundo plano...")

    try:
        with sync_playwright() as p:
            launch_opts = {
                "headless": True,
                "ignore_default_args": ["--enable-automation"],
                "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            }
            try:
                browser = p.chromium.launch(channel="chrome", **launch_opts)
            except Exception:
                browser = p.chromium.launch(**launch_opts)
            context = browser.new_context(
                storage_state=str(SESSION_FILE),
                viewport={"width": 1280, "height": 900},
                locale="pt-BR",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            # Navega até o Studio de Upload do TikTok
            page.goto(TIKTOK_UPLOAD_URL, timeout=45000, wait_until="domcontentloaded")
            time.sleep(4)

            # Verifica se foi deslogado
            if "login" in page.url:
                log.warning("Sessão do TikTok expirou. Necessário novo login.")
                browser.close()
                SESSION_FILE.unlink(missing_ok=True)
                return setup_tiktok_session()

            # Envia o arquivo no input de arquivo
            file_input = page.locator("input[type='file']")
            if not file_input.count():
                # Tenta dentro de iframes se houver
                for frame in page.frames:
                    fi = frame.locator("input[type='file']")
                    if fi.count():
                        file_input = fi
                        break

            if not file_input.count():
                log.error("Campo de upload de vídeo não encontrado no TikTok Studio.")
                browser.close()
                return False

            log.info(f"Fazendo upload de {media_to_send.name} para o TikTok...")
            file_input.set_input_files(str(media_to_send.resolve()))

            # Aguarda o vídeo carregar (aparece preview ou campo de legenda)
            time.sleep(8)
            dismiss_tiktok_modals(page)

            # Preenche legenda / título
            caption_input = page.locator("div[contenteditable='true']").first
            if caption_input.count():
                try:
                    caption_input.click(timeout=4000)
                except Exception:
                    dismiss_tiktok_modals(page)
                    try:
                        caption_input.click(force=True, timeout=3000)
                    except Exception:
                        pass

                try:
                    caption_input.fill("")
                except Exception:
                    caption_input.press("Control+A")
                    caption_input.press("Backspace")

                # Digita a legenda com quebras de linha
                caption_input.type(caption[:2000], delay=10)
                log.info("Legenda preenchida no TikTok com sucesso.")

            time.sleep(3)
            dismiss_tiktok_modals(page)

            # Localiza botão de publicar
            publish_btn = page.locator("button:has-text('Publicar'), button:has-text('Post')").first
            if publish_btn.count():
                try:
                    publish_btn.click(timeout=5000)
                except Exception:
                    dismiss_tiktok_modals(page)
                    publish_btn.click(force=True)

                log.info("Botão Publicar clicado no TikTok. Aguardando confirmação...")
                time.sleep(8)
                dismiss_tiktok_modals(page)

                # Salva sessão atualizada
                context.storage_state(path=str(SESSION_FILE))
                log.info(f"Post #{post_data.get('id')} publicado com sucesso no TikTok!")
                browser.close()
                return True
            else:
                log.warning("Botão Publicar não localizado no TikTok Studio.")
                browser.close()
                return False

    except Exception as exc:
        log.error(f"Erro ao publicar no TikTok via Playwright: {exc}")
        return False
