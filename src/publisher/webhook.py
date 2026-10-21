"""
src/publisher/webhook.py
------------------------
Envia payload de post pronto para webhook externo (n8n, Make, Zapier).
Gera URL pública direta para o arquivo de vídeo para facilitar o nó do Buffer/Instagram/TikTok.
"""
from pathlib import Path
from typing import Any
import requests

from config.settings import (
    WEBHOOK_URL,
    WEBHOOK_SECRET,
    PUBLIC_BASE_URL,
    CLOUDINARY_URL,
    ROOT_DIR,
    OUTPUT_VIDEOS,
    OUTPUT_IMAGES,
)
from src.utils.logger import get_logger

log = get_logger(__name__)


def resolve_public_media_url(media_path: Path) -> str | None:
    """Retorna URL pública para a mídia.
    Prioridade 1: Cloudinary (CDN oficial de mídia, aceita 100% pelo Buffer/Meta).
    Prioridade 2: Servidor local via túnel/domínio (PUBLIC_BASE_URL).
    Prioridade 3: Catbox (fallback temporário).
    """
    if not media_path or not media_path.is_file():
        return None

    import os
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env", override=True)

    # Opção 1: Cloudinary (Padrão ouro para Buffer, Instagram e TikTok)
    cloudinary_env = os.getenv("CLOUDINARY_URL") or CLOUDINARY_URL
    if cloudinary_env and "<your_api_key>" not in cloudinary_env:
        try:
            import cloudinary
            import cloudinary.uploader
            os.environ["CLOUDINARY_URL"] = cloudinary_env

            log.info(f"Fazendo upload de {media_path.name} para o Cloudinary CDN...")
            is_video = media_path.suffix.lower() == ".mp4"
            res = cloudinary.uploader.upload_large(
                str(media_path),
                resource_type="video" if is_video else "image",
                public_id=f"bible_reels/{media_path.stem}",
                overwrite=True,
            )
            secure_url = res.get("secure_url") or res.get("url")
            if secure_url:
                log.info(f"URL Cloudinary gerada com sucesso: {secure_url}")
                return secure_url
        except Exception as exc:
            log.warning(f"Falha ao enviar para Cloudinary: {exc}")

    # Opção 2: Servidor local exposto (ngrok, túnel ou domínio próprio)
    public_base = os.getenv("PUBLIC_BASE_URL") or PUBLIC_BASE_URL
    if public_base:
        subfolder = "videos" if media_path.suffix.lower() == ".mp4" else "images"
        return f"{public_base.rstrip('/')}/media/{subfolder}/{media_path.name}"

    # Opção 3: Catbox (fallback público temporário, apenas se explicitamente autorizado)
    if os.getenv("ALLOW_CATBOX_FALLBACK", "false").strip().lower() in ("1", "true", "yes"):
        try:
            log.info(f"Gerando URL temporária para {media_path.name} via Catbox...")
            with open(media_path, "rb") as f:
                mime = "video/mp4" if media_path.suffix.lower() == ".mp4" else "image/png"
                resp = requests.post(
                    "https://catbox.moe/user/api.php",
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": (media_path.name, f, mime)},
                    timeout=45,
                )
            if resp.status_code == 200 and resp.text.strip().startswith("http"):
                url = resp.text.strip()
                log.info(f"URL pública gerada com sucesso: {url}")
                return url
            log.warning(f"Upload Catbox retornou status {resp.status_code}: {resp.text[:100]}")
        except Exception as exc:
            log.warning(f"Falha ao gerar link público temporário: {exc}")

    return None


def publish_via_webhook(post_data: dict[str, Any]) -> bool:
    """Dispara webhook POST para n8n/Make com dados do post, URL pública de mídia e anexo."""
    import os
    from dotenv import load_dotenv
    from config.settings import ROOT_DIR
    load_dotenv(ROOT_DIR / ".env", override=True)

    webhook_target = os.getenv("WEBHOOK_URL") or WEBHOOK_URL
    if not webhook_target:
        log.warning("WEBHOOK_URL não configurado no .env.")
        return False

    headers = {}
    if WEBHOOK_SECRET:
        headers["X-Webhook-Secret"] = WEBHOOK_SECRET

    video_file = post_data.get("video_path")
    image_file = post_data.get("image_path")
    media_to_send: Path | None = None

    # Encontra mídia válida
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

    # Gera link público acessível pela API do Buffer / Instagram
    public_url = resolve_public_media_url(media_to_send) if media_to_send else None

    raw_caption = post_data.get("caption") or ""
    if raw_caption:
        caption = raw_caption.strip()
    else:
        tags = post_data.get("hashtags", "")
        if isinstance(tags, list):
            tags = " ".join([f"#{t.lstrip('#')}" for t in tags])
        caption = f"{post_data.get('formatted_text', '')}\n\n{tags}".strip()
    is_video = bool(media_to_send and media_to_send.suffix.lower() == ".mp4")

    payload = {
        "post_id": str(post_data.get("id", "")),
        "reference": post_data.get("reference", ""),
        "caption": caption,
        "text": post_data.get("formatted_text", ""),
        "hashtags": post_data.get("hashtags", ""),
        "caption": caption,
        "visual_prompt": post_data.get("visual_prompt", ""),
        "video_url": public_url if is_video else "",
        "image_url": public_url if not is_video and public_url else "",
        "media_url": public_url or "",
        "media_name": media_to_send.name if media_to_send else "",
        "media_type": "video" if is_video else "image",
    }

    try:
        # Se temos URL pública (ex: Cloudinary), envia JSON leve e direto (ideal para Make.com e Buffer)
        if public_url:
            headers["Content-Type"] = "application/json; charset=utf-8"
            resp = requests.post(webhook_target, json=payload, headers=headers, timeout=30)
        elif media_to_send and media_to_send.is_file():
            with open(media_to_send, "rb") as f:
                mime = "video/mp4" if is_video else "image/png"
                files = {"file": (media_to_send.name, f, mime)}
                resp = requests.post(webhook_target, data=payload, files=files, headers=headers, timeout=60)
        else:
            headers["Content-Type"] = "application/json; charset=utf-8"
            resp = requests.post(webhook_target, json=payload, headers=headers, timeout=25)

        resp.raise_for_status()
        log.info(f"Post #{post_data.get('id')} disparado com sucesso para Webhook ({webhook_target}).")
        return True
    except requests.RequestException as exc:
        log.error(f"Falha ao enviar post via Webhook: {exc}")
        return False