"""
src/publisher/tiktok.py
-----------------------
Publicação oficial no TikTok via Content Posting API v2 (Direct File Upload).
100% oficial, sem risco de ban, sem necessidade de domínio verificado ou navegador.
"""
from pathlib import Path
from typing import Any
import os
import time
import requests

from config.settings import ROOT_DIR, OUTPUT_VIDEOS
from src.utils.logger import get_logger

log = get_logger(__name__)

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"


def _refresh_access_token() -> str | None:
    """Renova o TIKTOK_ACCESS_TOKEN usando o TIKTOK_REFRESH_TOKEN."""
    from dotenv import load_dotenv, set_key
    load_dotenv(ROOT_DIR / ".env", override=True)

    client_key = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("TIKTOK_REFRESH_TOKEN", "").strip()

    if not client_key or not client_secret or not refresh_token:
        log.error("Credenciais de refresh do TikTok ausentes no .env.")
        return None

    try:
        url = f"{TIKTOK_API_BASE}/oauth/token/"
        data = {
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        res = requests.post(url, data=data, headers=headers, timeout=30)
        res.raise_for_status()
        payload = res.json()
        new_token = payload.get("access_token")
        new_refresh = payload.get("refresh_token")

        if new_token:
            env_path = str(ROOT_DIR / ".env")
            set_key(env_path, "TIKTOK_ACCESS_TOKEN", new_token)
            if new_refresh:
                set_key(env_path, "TIKTOK_REFRESH_TOKEN", new_refresh)
            os.environ["TIKTOK_ACCESS_TOKEN"] = new_token
            log.info("Token de acesso do TikTok renovado com sucesso!")
            return new_token
        else:
            log.error(f"Erro ao renovar token do TikTok: {payload}")
            return None
    except Exception as exc:
        log.error(f"Exceção ao renovar token do TikTok: {exc}")
        return None


def get_valid_access_token() -> str | None:
    """Retorna um access token válido, renovando se necessário."""
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env", override=True)
    token = os.getenv("TIKTOK_ACCESS_TOKEN", "").strip()
    if not token:
        token = _refresh_access_token()
    return token


def upload_video_file_to_tiktok(file_path: Path, caption: str, privacy_level: str | None = None) -> bool:
    """
    Publica um arquivo local de vídeo (.mp4) diretamente no TikTok via FILE_UPLOAD.
    Dispensa verificação de domínio ou URLs externas.
    Apps em desenvolvimento/sandbox exigem SELF_ONLY (vídeo privado no perfil).
    """
    if not file_path or not file_path.is_file():
        log.error(f"Arquivo de vídeo não encontrado em: {file_path}")
        return False

    token = get_valid_access_token()
    if not token:
        log.error("TIKTOK_ACCESS_TOKEN não disponível.")
        return False

    if not privacy_level:
        privacy_level = os.getenv("TIKTOK_PRIVACY_LEVEL", "PUBLIC_TO_EVERYONE").strip()

    file_size = file_path.stat().st_size
    log.info(f"Preparando envio direto de {file_path.name} ({file_size / 1024 / 1024:.2f} MB) para o TikTok (Privacidade: {privacy_level})...")

    url_init = f"{TIKTOK_API_BASE}/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    clean_caption = caption[:2200].strip()

    body = {
        "post_info": {
            "title": clean_caption,
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": file_size,
            "total_chunk_count": 1,
        }
    }

    try:
        res = requests.post(url_init, json=body, headers=headers, timeout=30)
        
        # Se token expirou, renova e repete
        if res.status_code == 401:
            log.warning("Token expirado no init. Renovando...")
            token = _refresh_access_token()
            if not token:
                return False
            headers["Authorization"] = f"Bearer {token}"
            res = requests.post(url_init, json=body, headers=headers, timeout=30)

        # Trata apps em sandbox/não auditados pelo TikTok que só aceitam vídeos privados (SELF_ONLY)
        if res.status_code == 403 or (res.status_code == 200 and res.json().get("error", {}).get("code") == "unaudited_client_can_only_post_to_private_accounts"):
            err_json = {}
            try:
                err_json = res.json().get("error", {})
            except Exception:
                pass
            if err_json.get("code") == "unaudited_client_can_only_post_to_private_accounts":
                log.warning("⚠️ App TikTok em modo de desenvolvimento (Sandbox). Exige 'SELF_ONLY' (privado). Reenviando automaticamente como privado...")
                body["post_info"]["privacy_level"] = "SELF_ONLY"
                res = requests.post(url_init, json=body, headers=headers, timeout=30)

        res.raise_for_status()
        data = res.json()
        error_info = data.get("error", {})
        if error_info.get("code") != "ok":
            log.error(f"Erro retornado no init do TikTok: {data}")
            return False

        publish_id = data.get("data", {}).get("publish_id")
        upload_url = data.get("data", {}).get("upload_url")

        if not upload_url:
            log.error(f"Upload URL não fornecida pelo TikTok: {data}")
            return False

        log.info(f"Sessão de upload criada (ID: {publish_id}). Enviando binário do vídeo...")

        # Faz upload dos bytes do vídeo via PUT
        with open(file_path, "rb") as vf:
            video_bytes = vf.read()

        put_headers = {
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
        }
        put_res = requests.put(upload_url, data=video_bytes, headers=put_headers, timeout=120)
        if put_res.status_code not in (200, 201, 206):
            log.error(f"Falha ao enviar arquivo de vídeo para o TikTok: {put_res.status_code} {put_res.text}")
            return False

        log.info(f"Upload de {file_path.name} concluído com sucesso! Aguardando processamento...")

        # Monitora status
        status_url = f"{TIKTOK_API_BASE}/post/publish/status/fetch/"
        for attempt in range(12):
            time.sleep(3)
            try:
                res_st = requests.post(status_url, json={"publish_id": publish_id}, headers=headers, timeout=15)
                if res_st.status_code == 200:
                    st_data = res_st.json().get("data", {})
                    status = st_data.get("status")
                    log.info(f"Status do processamento TikTok: {status}")
                    if status in ("SUCCESS", "PUBLISH_COMPLETE"):
                        log.info(f"🎉 Vídeo {file_path.name} publicado com sucesso no TikTok!")
                        return True
                    elif status == "FAILED":
                        fail_reason = st_data.get("fail_reason", "Desconhecido")
                        log.error(f"Falha no processamento do TikTok: {fail_reason}")
                        return False
            except Exception as e:
                log.debug(f"Aguardando status ({e})...")

        log.info(f"Vídeo {file_path.name} recebido e em processamento final pelo TikTok.")
        return True

    except requests.RequestException as err:
        log.error(f"Erro na requisição para API do TikTok: {err}")
        if hasattr(err, "response") and err.response is not None:
            try:
                log.error(f"Detalhes do erro TikTok: {err.response.json()}")
            except Exception:
                log.error(f"Resposta bruta: {err.response.text}")
        return False


def publish_via_tiktok(post_data: dict[str, Any]) -> bool:
    """
    Publicador integrado para ser chamado pelo servidor web ou CLI.
    Localiza o arquivo .mp4 local e realiza o upload binário direto.
    """
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
        log.error(f"Nenhum arquivo .mp4 encontrado em disco para o Post #{post_data.get('id')}.")
        return False

    caption = f"{post_data.get('formatted_text', '')}\n\n{post_data.get('hashtags', '')}".strip()
    return upload_video_file_to_tiktok(file_path=media_path, caption=caption)


# Alias para compatibilidade
publish_to_tiktok = upload_video_file_to_tiktok