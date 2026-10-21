"""
src/publisher/postproxy.py
--------------------------
Gerencia a publicação de posts e vídeos em múltiplas redes sociais
(Instagram Reels, TikTok, YouTube Shorts, Facebook, etc.) via Postproxy API.
"""
import json
import mimetypes
import os
from typing import Any
import requests

from pathlib import Path
from config.settings import (
    POSTPROXY_API_KEY,
    POSTPROXY_BASE_URL,
    POSTPROXY_PROFILE_IDS,
    OUTPUT_IMAGES,
    OUTPUT_VIDEOS,
)
from src.utils.logger import get_logger

log = get_logger(__name__)


class PostproxyPublisher:
    """
    Cliente para gerenciar publicação via API oficial do Postproxy (postproxy.dev).
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or POSTPROXY_API_KEY or os.environ.get("POSTPROXY_API_KEY", "")
        base = base_url or POSTPROXY_BASE_URL or os.environ.get("POSTPROXY_BASE_URL", "https://api.postproxy.dev/api")
        if base.endswith("/v1"):
            base = base[:-3] + "/api"
        elif not base.endswith("/api") and "postproxy.dev" in base:
            base = base.rstrip("/") + "/api"
        self.base_url = base.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    def _format_error(self, res: requests.Response) -> str:
        try:
            data = res.json()
            if isinstance(data, dict):
                msg = data.get("error") or data.get("message")
                detalhes = data.get("errors") or data.get("details") or data.get("detail")
                if msg and detalhes:
                    return f"{msg} - {detalhes}"
                if detalhes:
                    return f"Bad Request: {detalhes}"
                if msg and msg != "Bad Request":
                    return str(msg)
                return json.dumps(data, ensure_ascii=False)
            elif isinstance(data, list):
                return json.dumps(data, ensure_ascii=False)
            return res.text or getattr(res, "reason", "Erro desconhecido")
        except Exception:
            return getattr(res, "text", "") or f"HTTP {getattr(res, 'status_code', 'Desconhecido')}"

    def listar_perfis(self) -> list[dict[str, Any]]:
        endpoint = f"{self.base_url}/profiles"
        res = requests.get(endpoint, headers=self.headers, timeout=20)
        if not res.ok:
            raise RuntimeError(f"Erro ao buscar perfis ({res.status_code}): {self._format_error(res)}")
        data = res.json()
        return data.get("data", []) if isinstance(data, dict) else data

    def publicar_post(
        self,
        video_source: str,
        legenda: str,
        profile_ids: list[str],
        platforms_config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not profile_ids:
            raise ValueError("Pelo menos um ID de perfil deve ser fornecido.")

        endpoint = f"{self.base_url}/posts"
        platforms = platforms_config or {}

        if os.path.isfile(video_source):
            data = [("post[body]", legenda)]
            for pid in profile_ids:
                data.append(("profiles[]", str(pid)))
            for plat, params in platforms.items():
                if isinstance(params, dict):
                    for k, v in params.items():
                        data.append((f"platforms[{plat}][{k}]", str(v)))

            headers_multipart = {
                "Authorization": f"Bearer {self.api_key}",
                "x-api-key": self.api_key
            }

            mime_type, _ = mimetypes.guess_type(video_source)
            if not mime_type:
                mime_type = "video/mp4" if video_source.lower().endswith(".mp4") else "image/png"

            with open(video_source, "rb") as f:
                filename = os.path.basename(video_source)
                files = [("media[]", (filename, f, mime_type))]
                res = requests.post(endpoint, headers=headers_multipart, data=data, files=files, timeout=60)
                if not res.ok:
                    raise RuntimeError(f"Erro {res.status_code} na API do Postproxy ({endpoint}): {self._format_error(res)}")
                return res.json()
        else:
            payload: dict[str, Any] = {
                "post": {"body": legenda},
                "profiles": [str(pid) for pid in profile_ids],
                "media": [video_source]
            }
            if platforms:
                payload["platforms"] = platforms

            res = requests.post(endpoint, headers=self.headers, json=payload, timeout=60)
            if not res.ok:
                raise RuntimeError(f"Erro {res.status_code} na API do Postproxy ({endpoint}): {self._format_error(res)}")
            return res.json()

    def publicar_reels(self, video_source: str, legenda: str, account_id: str) -> dict[str, Any]:
        return self.publicar_post(
            video_source=video_source,
            legenda=legenda,
            profile_ids=[account_id],
            platforms_config={"instagram": {"format": "reel"}}
        )

    def publicar_multiplos_canais(self, video_source: str, legenda: str, contas: list[dict[str, Any]]) -> dict[str, Any]:
        final_profiles: list[str] = []
        final_platforms: dict[str, Any] = {}
        for c in contas:
            pid = c.get("accountId") or c.get("id") or c.get("profileId")
            plat = str(c.get("platform", "")).lower()
            if pid and str(pid) not in final_profiles:
                final_profiles.append(str(pid))
            if plat and plat not in final_platforms:
                if plat == "instagram":
                    final_platforms["instagram"] = {"format": "reel"}
                elif plat == "tiktok":
                    final_platforms["tiktok"] = {"format": "video"}
                elif plat == "youtube":
                    final_platforms["youtube"] = {"format": "post"}

        return self.publicar_post(
            video_source=video_source,
            legenda=legenda,
            profile_ids=final_profiles,
            platforms_config=final_platforms
        )

    def verificar_status_post(self, post_id: str) -> dict[str, Any]:
        endpoint = f"{self.base_url}/posts/{post_id}"
        try:
            res = requests.get(endpoint, headers=self.headers, timeout=20)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            log.error(f"Erro ao consultar status do post {post_id}: {e}")
            return {}


def publish_via_postproxy(post_data: dict[str, Any]) -> bool:
    """Dispara publicação para redes sociais via Postproxy API."""
    if not POSTPROXY_API_KEY:
        log.warning("POSTPROXY_API_KEY não configurado no .env.")
        return False

    video_path = post_data.get("video_path")
    image_path = post_data.get("image_path")
    media_path = ""

    def _resolve(p: str | None, default_dir: Path) -> str | None:
        if not p:
            return None
        if os.path.isfile(p):
            return str(p)
        filename = Path(p).name
        candidate = default_dir / filename
        if candidate.is_file():
            return str(candidate)
        return None

    resolved_vid = _resolve(video_path, OUTPUT_VIDEOS)
    resolved_img = _resolve(image_path, OUTPUT_IMAGES)

    if resolved_vid:
        media_path = resolved_vid
    elif resolved_img:
        media_path = resolved_img

    if not media_path:
        log.error(f"Post {post_data.get('id')} sem arquivo de mídia válido para envio (video={video_path}, image={image_path}).")
        return False

    raw_caption = post_data.get("caption") or ""
    if raw_caption:
        caption = raw_caption.strip()
    else:
        caption = post_data.get("formatted_text", "")
        hashtags = post_data.get("hashtags")
        if isinstance(hashtags, str):
            try:
                hashtags = json.loads(hashtags)
            except Exception:
                hashtags = []
        if isinstance(hashtags, list) and hashtags:
            tags_str = " ".join([f"#{t.lstrip('#')}" for t in hashtags])
            caption = f"{caption}\n\n{tags_str}".strip()

    publisher = PostproxyPublisher(api_key=POSTPROXY_API_KEY, base_url=POSTPROXY_BASE_URL)

    profile_ids = list(POSTPROXY_PROFILE_IDS)
    if not profile_ids:
        try:
            perfis = publisher.listar_perfis()
            profile_ids = [str(p.get("id")) for p in perfis if p.get("id")]
            log.info(f"Nenhum POSTPROXY_PROFILE_IDS no .env. Detectados {len(profile_ids)} perfis da conta.")
        except Exception as exc:
            log.error(f"Falha ao listar perfis do Postproxy: {exc}")
            return False

    if not profile_ids:
        log.error("Nenhum perfil configurado ou encontrado no Postproxy.")
        return False

    is_video = media_path.lower().endswith((".mp4", ".mov", ".mkv", ".avi", ".webm"))
    platforms_config: dict[str, Any] = {}
    if is_video:
        platforms_config = {
            "instagram": {"format": "reel"},
            "tiktok": {"format": "video"},
            "youtube": {"format": "post"}
        }

    try:
        res = publisher.publicar_post(
            video_source=media_path,
            legenda=caption,
            profile_ids=profile_ids,
            platforms_config=platforms_config
        )
        post_id = res.get("id") or (res.get("data", {}).get("id") if isinstance(res.get("data"), dict) else None)
        log.info(f"Post {post_data.get('id')} enviado com sucesso via Postproxy! (Postproxy ID: {post_id})")
        return True
    except Exception as exc:
        log.error(f"Falha ao publicar via Postproxy: {exc}")
        return False
