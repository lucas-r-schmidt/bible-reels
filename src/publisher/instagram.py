"""
src/publisher/instagram.py
--------------------------
Publicação no Instagram Graph API (Reels / Carrossel).
Requer URL pública acessível da mídia.
"""
from typing import Any
import requests

from config.settings import INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_ACCOUNT_ID
from src.utils.logger import get_logger

log = get_logger(__name__)

def publish_to_instagram(caption: str, media_url: str) -> bool:
    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        log.warning("Credenciais de Instagram não preenchidas no .env.")
        return False

    url_container = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media"
    payload = {
        "media_type": "REELS",
        "video_url": media_url,
        "caption": caption,
        "access_token": INSTAGRAM_ACCESS_TOKEN
    }

    try:
        res = requests.post(url_container, data=payload, timeout=30)
        res.raise_for_status()
        creation_id = res.json().get("id")

        url_publish = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        res_pub = requests.post(url_publish, data={"creation_id": creation_id, "access_token": INSTAGRAM_ACCESS_TOKEN}, timeout=30)
        res_pub.raise_for_status()
        log.info(f"Publicado no Instagram com sucesso: ID {creation_id}")
        return True
    except requests.RequestException as err:
        log.error(f"Erro ao publicar no Instagram: {err}")
        return False