"""
src/publisher/instagram_direct.py
---------------------------------
Publicação direta no Instagram (Reels e Fotos) via instagrapi (Mobile API).
Não requer Meta Developer Portal, Facebook Page ou aprovação da Meta.
Funciona em qualquer conta (pessoal ou profissional).
"""
from pathlib import Path
from typing import Any
import os

from config.settings import ROOT_DIR, OUTPUT_VIDEOS, OUTPUT_IMAGES
from src.utils.logger import get_logger

log = get_logger(__name__)

SESSION_FILE = ROOT_DIR / "data" / "instagram_session.json"
_CLIENT_CACHE: Any = None


def get_instagram_client() -> Any:
    """Inicializa cliente do Instagram com persistência de sessão e cache em memória."""
    global _CLIENT_CACHE
    if _CLIENT_CACHE is not None:
        try:
            # Verifica se sessão em memória ainda é válida
            if getattr(_CLIENT_CACHE, "user_id", None):
                return _CLIENT_CACHE
        except Exception:
            _CLIENT_CACHE = None

    from instagrapi import Client
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env", override=True)
    sessionid = os.getenv("INSTAGRAM_SESSIONID", "").strip()
    username = os.getenv("INSTAGRAM_USERNAME", "").strip()
    password = os.getenv("INSTAGRAM_PASSWORD", "").strip()

    cl = Client()
    cl.delay_range = [0, 1]  # Delay mínimo para upload rápido sem travas

    # Método 1: Login por SessionID (Instantâneo)
    if sessionid:
        try:
            log.info("Autenticando via SessionID...")
            cl.login_by_sessionid(sessionid)
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            cl.dump_settings(SESSION_FILE)
            log.info("Autenticação no Instagram via SessionID realizada com sucesso!")
            _CLIENT_CACHE = cl
            return cl
        except Exception as exc:
            log.warning(f"Falha ao autenticar por SessionID: {exc}")

    # Método 2: Sessão salva anterior
    if SESSION_FILE.is_file():
        try:
            cl.load_settings(SESSION_FILE)
            if cl.user_id:
                log.info("Sessão salva do Instagram reutilizada com sucesso.")
                _CLIENT_CACHE = cl
                return cl
        except Exception as exc:
            log.warning(f"Falha ao carregar sessão anterior: {exc}")

    # Método 3: Login tradicional por usuário e senha
    if not username or not password:
        log.warning("INSTAGRAM_SESSIONID ou (INSTAGRAM_USERNAME + PASSWORD) não configurados no .env.")
        return None

    try:
        logged_in = cl.login(username, password)
        if logged_in:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            cl.dump_settings(SESSION_FILE)
            log.info(f"Login no Instagram efetuado com sucesso como @{username}.")
            _CLIENT_CACHE = cl
            return cl
    except Exception as exc:
        log.error(f"Erro ao autenticar no Instagram (@{username}): {exc}")
        return None

    return None


def publish_via_instagram_direct(post_data: dict[str, Any], prefer_carousel: bool = False) -> bool:
    """Publica Reel diretamente no Instagram sem passar por Meta ou Buffer em alta velocidade."""
    cl = get_instagram_client()
    if not cl:
        return False

    video_file = post_data.get("video_path")
    image_file = post_data.get("image_path")
    media_to_send: Path | None = None
    thumb_path: Path | None = None

    for candidate in [video_file, image_file]:
        if candidate and Path(candidate).is_file():
            media_to_send = Path(candidate)
            break
        elif candidate and (OUTPUT_VIDEOS / Path(candidate).name).is_file():
            media_to_send = OUTPUT_VIDEOS / Path(candidate).name
            break
        elif candidate and (OUTPUT_IMAGES / Path(candidate).name).is_file():
            media_to_send = OUTPUT_IMAGES / Path(candidate).name
            break

    # Localiza imagem gerada para usar como thumbnail sem reprocessar vídeo
    if image_file and Path(image_file).is_file():
        thumb_path = Path(image_file)
    elif media_to_send and (OUTPUT_IMAGES / f"{media_to_send.stem}.png").is_file():
        thumb_path = OUTPUT_IMAGES / f"{media_to_send.stem}.png"

    # Suporte a Carrossel (álbum com áudio em micro-vídeos MP4 ou fotos sequenciais PNG)
    carousel_slides: list[Path] = []
    if image_file and Path(image_file).is_file():
        p_img = Path(image_file)
        if "carousel_" in p_img.parent.name.lower():
            # Prioriza lâminas em micro-vídeo com áudio se existirem
            v_slides_dir = p_img.parent / "video_slides"
            if v_slides_dir.is_dir():
                v_slides = sorted([s for s in v_slides_dir.iterdir() if s.is_file() and s.suffix.lower() == ".mp4"])
                if v_slides:
                    carousel_slides = v_slides
            if not carousel_slides:
                carousel_slides = sorted([s for s in p_img.parent.iterdir() if s.is_file() and s.suffix.lower() in ('.png', '.jpg', '.jpeg')])

    raw_caption = post_data.get("caption") or ""
    if raw_caption:
        caption = raw_caption.strip()
    else:
        tags = post_data.get("hashtags", "")
        if isinstance(tags, list):
            tags = " ".join([f"#{t.lstrip('#')}" for t in tags])
        caption = f"{post_data.get('formatted_text', '')}\n\n{tags}".strip()
    is_video = media_to_send and media_to_send.suffix.lower() == ".mp4"

    explicit_carousel = bool(prefer_carousel or post_data.get("prefer_carousel"))

    try:
        log.info(f"Enviando post #{post_data.get('id')} para o Instagram...")
        if (explicit_carousel and carousel_slides) or (not is_video and carousel_slides):
            is_v_album = carousel_slides[0].suffix.lower() == ".mp4"
            tipo_album = "vídeos com áudio" if is_v_album else "fotos"
            log.info(f"Instagram: enviando Carrossel ({tipo_album}) com {len(carousel_slides)} lâminas para o feed...")
            media = cl.album_upload(carousel_slides, caption=caption)
        elif is_video:
            # Vídeo vertical 1080x1920 (Reel)
            log.info(f"Instagram: enviando Reel de vídeo MP4 vertical...")
            media = cl.clip_upload(media_to_send, caption=caption, thumbnail=thumb_path)
        else:
            media = cl.photo_upload(media_to_send, caption=caption)

        code = getattr(media, "code", None)
        post_link = f"https://www.instagram.com/p/{code}/" if carousel_slides or not is_video else f"https://www.instagram.com/reel/{code}/"
        log.info(f"Publicado com sucesso no Instagram! Link: {post_link if code else media.id}")
        return True
    except Exception as exc:
        log.error(f"Falha ao publicar Reel no Instagram via instagrapi: {exc}")
        return False
