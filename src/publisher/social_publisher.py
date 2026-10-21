"""
src/publisher/social_publisher.py
---------------------------------
Publicador integrado que conecta o Bible Reels ao microsserviço central Social Publisher (porta 8000).
Permite publicar simultaneamente no TikTok, Instagram Reels e YouTube Shorts.
"""
from pathlib import Path
from typing import Any
import requests
import os
from dotenv import load_dotenv

from config.settings import ROOT_DIR, OUTPUT_VIDEOS
from src.publisher.webhook import resolve_public_media_url
from src.utils.logger import get_logger

log = get_logger(__name__)

SOCIAL_PUBLISHER_URL = os.getenv("SOCIAL_PUBLISHER_URL", "http://localhost:8000")

def publish_via_social_publisher(post_data: dict[str, Any], platforms: list[str] = None) -> bool:
    """Envia o post pronto para o Social Publisher Hub."""
    load_dotenv(ROOT_DIR / ".env", override=True)
    publisher_url = os.getenv("SOCIAL_PUBLISHER_URL", SOCIAL_PUBLISHER_URL).rstrip("/")

    video_file = post_data.get("video_path")
    media_path: Path | None = None

    if video_file and Path(video_file).is_file():
        media_path = Path(video_file)
    elif video_file and (OUTPUT_VIDEOS / Path(video_file).name).is_file():
        media_path = OUTPUT_VIDEOS / Path(video_file).name
    else:
        post_id = post_data.get("id")
        candidate = OUTPUT_VIDEOS / f"post_{int(post_id):04d}.mp4"
        if candidate.is_file():
            media_path = candidate

    if not media_path or not media_path.is_file():
        log.error(f"Arquivo .mp4 não encontrado para o Post #{post_data.get('id')}.")
        return False

    # 1. Resolve URL pública via Cloudinary
    video_url = resolve_public_media_url(media_path)
    if not video_url:
        video_url = str(media_path)

    raw_caption = post_data.get("caption", "").strip()
    if raw_caption:
        caption = raw_caption
    else:
        hook_hdr = f"✨ {post_data.get('hook_title')}\n\n" if post_data.get("hook_title") else ""
        caption = (
            f"{hook_hdr}"
            f"📖 {post_data.get('formatted_text', '')}\n\n"
            f"👇 Escreva seu AMÉM nos comentários e compartilhe esta bênção! 🙏\n\n"
            f"{post_data.get('hashtags', '')}"
        ).strip()

    hook_prefix = f"{post_data.get('hook_title')} | " if post_data.get("hook_title") else ""
    title = f"{hook_prefix}{post_data.get('reference', '')} #Shorts".strip()

    if not platforms:
        env_plats = os.getenv("SOCIAL_PUBLISHER_PLATFORMS", "tiktok")
        platforms = [p.strip() for p in env_plats.split(",") if p.strip()]

    payload = {
        "platforms": platforms,
        "video_url": video_url,
        "caption": caption,
        "title": title,
    }

    endpoint = f"{publisher_url}/api/publish"
    log.info(f"Enviando Post #{post_data.get('id')} para Social Publisher ({endpoint}) - Plataformas: {platforms}...")

    try:
        res = requests.post(endpoint, json=payload, timeout=90)
        res.raise_for_status()
        data = res.json()
        if data.get("success"):
            log.info(f"🎉 Post #{post_data.get('id')} publicado com sucesso via Social Publisher: {data.get('results')}")
            return True
        else:
            log.error(f"Social Publisher retornou falha: {data.get('results')}")
            return False
    except Exception as exc:
        log.error(f"Erro ao comunicar com Social Publisher Hub ({endpoint}): {exc}")
        return False
