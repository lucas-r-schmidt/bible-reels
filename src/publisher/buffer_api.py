"""
src/publisher/buffer_api.py
---------------------------
Publicação direta no Buffer via nova API GraphQL (https://api.buffer.com).
Elimina o Make.com/n8n do meio: Python -> Buffer -> TikTok (parceiro oficial, sem risco de ban).

.env necessário:
    BUFFER_API_KEY=...                 # https://publish.buffer.com/settings/api
    BUFFER_CHANNEL_IDS=id1,id2         # opcional; se vazio, descobre canais automaticamente
    BUFFER_SERVICES=tiktok             # serviços usados na descoberta automática (ex: tiktok,instagram,youtube)
    BUFFER_MODE=addToQueue             # addToQueue | shareNow
    BUFFER_AI_DISCLOSURE=true          # marca vídeo TikTok como conteúdo gerado por IA
    BUFFER_DRAFT=false                 # true = salva como rascunho (teste sem publicar)

Uso CLI:
    .venv\\Scripts\\python.exe -m src.publisher.buffer_api --channels
    .venv\\Scripts\\python.exe -m src.publisher.buffer_api --post-id 12
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

from config.settings import ROOT_DIR, OUTPUT_VIDEOS, OUTPUT_IMAGES
from src.utils.logger import get_logger

log = get_logger(__name__)

BUFFER_API_URL = "https://api.buffer.com"


def _load_env() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env", override=True)


def _gql(query: str) -> dict[str, Any]:
    """Executa query/mutation GraphQL no Buffer e retorna `data`. Levanta RuntimeError em erro."""
    api_key = os.getenv("BUFFER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("BUFFER_API_KEY ausente no .env (gere em https://publish.buffer.com/settings/api).")

    resp = requests.post(
        BUFFER_API_URL,
        json={"query": query},
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=60,
    )
    try:
        payload = resp.json()
    except ValueError:
        raise RuntimeError(f"Buffer HTTP {resp.status_code}: {resp.text[:300]}")

    if payload.get("errors"):
        raise RuntimeError(f"Buffer GraphQL errors: {payload['errors']}")
    if resp.status_code >= 400:
        raise RuntimeError(f"Buffer HTTP {resp.status_code}: {payload}")
    return payload.get("data") or {}


def list_channels() -> list[dict[str, Any]]:
    """Lista todos os canais de todas as organizações da conta."""
    data = _gql("query { account { organizations { id name } } }")
    orgs = (data.get("account") or {}).get("organizations") or []
    channels: list[dict[str, Any]] = []
    for org in orgs:
        q = (
            "query { channels(input: { organizationId: %s }) "
            "{ id name displayName service isQueuePaused } }" % json.dumps(org["id"])
        )
        for ch in _gql(q).get("channels") or []:
            ch["organizationId"] = org["id"]
            channels.append(ch)
    return channels


def _resolve_channel_ids() -> list[str]:
    explicit = [c.strip() for c in os.getenv("BUFFER_CHANNEL_IDS", "").split(",") if c.strip()]
    if explicit:
        return explicit
    services = {s.strip().lower() for s in os.getenv("BUFFER_SERVICES", "tiktok").split(",") if s.strip()}
    found = [c["id"] for c in list_channels() if str(c.get("service", "")).lower() in services]
    if not found:
        log.error(f"Nenhum canal Buffer encontrado para serviços {services}. Conecte o TikTok em buffer.com.")
    return found


def _find_media(post_data: dict[str, Any]) -> Path | None:
    for candidate in (post_data.get("video_path"), post_data.get("image_path")):
        if not candidate:
            continue
        p = Path(candidate)
        for option in (p, OUTPUT_VIDEOS / p.name, OUTPUT_IMAGES / p.name):
            if option.is_file():
                return option
    return None


def _youtube_title(text: str) -> str:
    """Extrai ou formata título adequado para YouTube Shorts (máx 100 caracteres)."""
    clean = text.strip()
    first_line = clean.splitlines()[0] if clean else "Palavra de Fé"
    first_line = first_line.replace("#", "").strip()
    if len(first_line) > 75:
        first_line = first_line[:72] + "..."
    if "#Shorts" not in first_line:
        first_line = f"{first_line} #Shorts"
    return first_line[:100]


def _build_create_post(channel_id: str, service: str, text: str, media_urls: list[str], is_video: bool,
                       mode: str | None = None, draft: bool | None = None, due_at: str | None = None) -> str:
    mode = mode or os.getenv("BUFFER_MODE", "addToQueue").strip() or "addToQueue"
    if draft is None:
        draft = os.getenv("BUFFER_DRAFT", "false").strip().lower() in ("1", "true", "yes")

    if is_video:
        asset_str = '{ video: { url: %s } }' % json.dumps(media_urls[0])
    else:
        # Suporta múltiplos assets de imagem (Carrossel no Instagram)
        asset_str = ', '.join(['{ image: { url: %s } }' % json.dumps(u) for u in media_urls])

    ai = "true" if os.getenv("BUFFER_AI_DISCLOSURE", "false").strip().lower() in ("1", "true", "yes") else "false"
    metadata = ""
    if service == "tiktok" and is_video:
        metadata = "metadata: { tiktok: { isAiGenerated: %s } }" % ai
    elif service == "instagram":
        ig_type = "reel" if is_video else "post"
        metadata = "metadata: { instagram: { type: %s, shouldShareToFeed: true, isAiGenerated: %s } }" % (ig_type, ai)
    elif service == "youtube":
        category = os.getenv("BUFFER_YT_CATEGORY", "22").strip() or "22"  # 22 = People & Blogs
        metadata = (
            "metadata: { youtube: { title: %s, categoryId: %s, isAiGenerated: %s, madeForKids: false } }"
            % (json.dumps(_youtube_title(text)), json.dumps(category), ai)
        )

    if due_at:
        scheduling_part = f"schedulingType: automatic\n        mode: customScheduled\n        dueAt: {json.dumps(due_at)}"
    else:
        scheduling_part = f"schedulingType: automatic\n        mode: {mode}"

    return """
    mutation {
      createPost(input: {
        text: %s
        channelId: %s
        %s
        saveToDraft: %s
        assets: [%s]
        %s
      }) {
        ... on PostActionSuccess { post { id dueAt } }
        ... on MutationError { message }
      }
    }""" % (json.dumps(text), json.dumps(channel_id), scheduling_part, "true" if draft else "false", asset_str, metadata)


def get_post_status(post_id: str) -> dict[str, Any]:
    """Consulta status de publicação (scheduled/sent/error) e link externo."""
    q = ("query { post(input: { id: %s }) { id status channelService dueAt sentAt externalLink "
         "error { message } } }" % json.dumps(post_id))
    return _gql(q).get("post") or {}


def delete_post(post_id: str) -> bool:
    """Remove post da fila/rascunhos do Buffer."""
    data = _gql("mutation { deletePost(input: { id: %s }) { __typename } }" % json.dumps(post_id))
    log.info(f"Buffer deletePost {post_id}: {data.get('deletePost')}")
    return bool(data.get("deletePost"))


def _publish_via_gateway(
    post_data: dict[str, Any],
    media: Path,
    text: str,
    is_video: bool,
    mode: str | None = None,
    draft: bool | None = None,
    due_at: str | None = None,
) -> bool | None:
    gateway_url = os.getenv("BUFFER_GATEWAY_URL", "http://localhost:8090").strip().rstrip("/")
    if not gateway_url:
        return None

    gateway_api_key = os.getenv("BUFFER_GATEWAY_API_KEY", "gateway_secret_token_123").strip()
    profile = os.getenv("BUFFER_GATEWAY_PROFILE", "bible-reels").strip()
    eff_mode = mode or os.getenv("BUFFER_MODE", "shareNow").strip()
    eff_draft = draft if draft is not None else os.getenv("BUFFER_DRAFT", "false").strip().lower() in ("1", "true", "yes")

    log.info(f"Tentando envio via Buffer Gateway ({gateway_url}) para perfil '{profile}'...")
    headers = {"X-API-Key": gateway_api_key} if gateway_api_key else {}

    try:
        title = post_data.get("reference", "")
        with open(media, "rb") as f:
            files = {"file": (media.name, f, "video/mp4" if is_video else "image/jpeg")}
            data = {
                "profile": profile,
                "text": text,
                "mode": eff_mode,
                "draft": "true" if eff_draft else "false",
            }
            if due_at:
                data["due_at"] = due_at
                data["scheduled_at"] = due_at
            if title:
                data["title"] = title
            resp = requests.post(f"{gateway_url}/api/v1/publish-file", files=files, data=data, headers=headers, timeout=120)

        if resp.status_code == 200:
            res_json = resp.json()
            if res_json.get("success"):
                log.info(f"[OK] Buffer Gateway: post publicado com sucesso no perfil '{profile}'! Canais: {res_json.get('channels_dispatched')}")
                return True
            else:
                log.warning(f"Buffer Gateway falhou: {res_json.get('message')}. Tentando fallback direto...")
        else:
            log.warning(f"Buffer Gateway HTTP {resp.status_code}: {resp.text[:200]}. Tentando fallback direto...")
    except Exception as exc:
        log.warning(f"Falha ao conectar no Buffer Gateway ({exc}). Tentando fallback direto...")
    return None


def _resolve_saint_target_date(ref: str) -> "date":
    """Resolve a data do Santo a partir da referência (ex: 'Santa Teresa (15/10)') ou assume amanhã se for noite."""
    import re
    from datetime import date, timedelta, datetime
    m = re.search(r"\((\d{1,2})/(\d{1,2})\)", ref)
    if m:
        try:
            return date(date.today().year, int(m.group(2)), int(m.group(1)))
        except Exception:
            pass
    if datetime.now().hour >= 18:
        return date.today() + timedelta(days=1)
    return date.today()


def publish_via_buffer(
    post_data: dict[str, Any],
    mode: str | None = None,
    draft: bool | None = None,
    due_at: str | None = None,
    target_service: str | None = None,
) -> bool:
    """Roteia inteligentemente mídias para cada canal no Buffer:
    - Instagram: SEMPRE Vídeo Reel vertical prioritário com áudio/legenda (para Santo do Dia e Versículos).
    - TikTok & YouTube: envia exclusivamente vídeo vertical MP4.
    - Santo do Dia desacoplado: YouTube/TikTok às 20:30 da véspera, Instagram Reel agendado para 06:00 da manhã do dia.
    """
    _load_env()
    from src.publisher.webhook import resolve_public_media_url

    # 1. Identifica todas as mídias disponíveis para o post
    video_path: Path | None = None
    carousel_slides: list[Path] = []
    single_image_path: Path | None = None

    v_cand = post_data.get("video_path")
    if v_cand:
        p_v = Path(v_cand)
        for opt in (p_v, OUTPUT_VIDEOS / p_v.name):
            if opt.is_file():
                video_path = opt
                break

    img_cand = post_data.get("image_path")
    if img_cand:
        p_img = Path(img_cand)
        for opt in (p_img, OUTPUT_IMAGES / p_img.name):
            if opt.is_file():
                # Detecta pasta do carrossel quer seja direto ou subpasta (ex: scenes/)
                c_dir = None
                if "carousel_" in opt.parent.name.lower():
                    c_dir = opt.parent
                elif "carousel_" in opt.parent.parent.name.lower():
                    c_dir = opt.parent.parent

                if c_dir:
                    carousel_slides = sorted([s for s in c_dir.iterdir() if s.is_file() and s.name.startswith("slide_") and s.suffix.lower() in ('.png', '.jpg', '.jpeg')])
                    if not carousel_slides:
                        carousel_slides = sorted([s for s in c_dir.iterdir() if s.is_file() and s.suffix.lower() in ('.png', '.jpg', '.jpeg') and not s.name.startswith(('tts_', 'temp_'))])
                else:
                    single_image_path = opt
                break

    if not video_path and not carousel_slides and not single_image_path:
        log.error(f"Post #{post_data.get('id')}: nenhuma mídia encontrada para enviar ao Buffer.")
        return False

    raw_caption = post_data.get("caption") or ""
    if raw_caption:
        text = raw_caption.strip()
    else:
        tags = post_data.get("hashtags", "")
        if isinstance(tags, list):
            tags = " ".join([f"#{t.lstrip('#')}" for t in tags])
        text = f"{post_data.get('formatted_text', '')}\n\n{tags}".strip()

    try:
        channel_ids = _resolve_channel_ids()
        services = {c["id"]: str(c.get("service", "")).lower() for c in list_channels()}
    except Exception as exc:
        log.error(f"Erro ao consultar canais do Buffer: {exc}")
        return False

    # Cache de URLs públicas do Cloudinary para evitar re-uploads desnecessários
    uploaded_urls_cache: dict[str, str] = {}
    def _get_url(file_path: Path) -> str | None:
        k = str(file_path)
        if k not in uploaded_urls_cache:
            u = resolve_public_media_url(file_path)
            if u:
                uploaded_urls_cache[k] = u
        return uploaded_urls_cache.get(k)

    # Identifica tipo de conteúdo: Santo do Dia vs Versículos/Mensagens
    ref_lower = (post_data.get("reference") or "").lower()
    is_saint = (
        post_data.get("verse_source") == "saint"
        or any(k in ref_lower for k in ("santo", "santa", "são", "sao", "senhora", "nossa senhora"))
        or "carousel_" in str(post_data.get("image_path") or "").lower()
    )

    any_ok = False
    for ch_id in channel_ids:
        service = services.get(ch_id, "")
        if target_service and service != target_service.lower():
            continue

        # Roteamento Inteligente por Plataforma e Tipo de Conteúdo:
        # - Instagram: SEMPRE Vídeo Reel 9:16 vertical (para Santo do Dia e Versículos)
        # - TikTok e YouTube Shorts: SEMPRE Vídeo MP4 vertical 9:16
        if service == "instagram":
            if video_path:
                v_url = _get_url(video_path)
                if not v_url: continue
                log.info(f"Buffer (instagram): enviando Vídeo Reel ({'Santo do Dia' if is_saint else 'Versículo'})...")
                target_urls = [v_url]
                is_vid = True
            elif is_saint and carousel_slides:
                slide_urls = [_get_url(s) for s in carousel_slides]
                slide_urls = [u for u in slide_urls if u]
                if not slide_urls: continue
                log.info(f"Buffer (instagram): Vídeo indisponível, fallback para Carrossel ({len(slide_urls)} slides)...")
                target_urls = slide_urls
                is_vid = False
            elif single_image_path:
                i_url = _get_url(single_image_path)
                if not i_url: continue
                target_urls = [i_url]
                is_vid = False
            else:
                continue

        elif service in ("tiktok", "youtube"):
            # TikTok e YouTube Shorts: SEMPRE VÍDEO MP4 (Santo do Dia e Escrituras)
            if video_path:
                v_url = _get_url(video_path)
                if not v_url:
                    log.warning(f"Buffer ({service}): falha ao gerar URL pública do vídeo MP4.")
                    continue
                log.info(f"Buffer ({service}): enviando Vídeo vertical MP4...")
                target_urls = [v_url]
                is_vid = True
            else:
                log.warning(f"Buffer ({service}): vídeo MP4 não encontrado para o Post #{post_data.get('id')}.")
                continue
        else:
            if video_path:
                v_url = _get_url(video_path)
                if not v_url: continue
                target_urls = [v_url]
                is_vid = True
            elif carousel_slides or single_image_path:
                first_img = carousel_slides[0] if carousel_slides else single_image_path
                i_url = _get_url(first_img)
                if not i_url: continue
                target_urls = [i_url]
                is_vid = False
            else:
                continue

        # Horário Desacoplado:
        # YouTube e TikTok saem às 20:30 da véspera (imediato)
        # Instagram Reel sai às 06:00 da manhã do próprio dia do Santo
        ch_due_at = due_at
        if is_saint and not due_at:
            if service == "instagram":
                target_d = _resolve_saint_target_date(post_data.get("reference") or "")
                try:
                    from datetime import datetime, time, timezone, timedelta
                    tz_br = timezone(timedelta(hours=-3))
                    now_br = datetime.now(tz_br)
                    target_dt = datetime.combine(target_d, time(6, 0), tzinfo=tz_br)
                    if target_dt > now_br:
                        ch_due_at = target_dt.isoformat()
                        log.info(f"Buffer (instagram): Santo do Dia agendado para {ch_due_at} (06:00 da manhã do dia {target_d.strftime('%d/%m')})")
                    else:
                        log.info(f"Buffer (instagram): Horário das 06:00 de {target_d.strftime('%d/%m')} já passou; enviando imediatamente.")
                        ch_due_at = None
                except Exception as e_date:
                    log.warning(f"Erro ao calcular due_at do Instagram para o Santo: {e_date}")
            elif service in ("tiktok", "youtube"):
                ch_due_at = None

        try:
            data = _gql(_build_create_post(ch_id, service, text, target_urls, is_vid, mode, draft, due_at=ch_due_at))
            result = data.get("createPost") or {}
            if result.get("post"):
                kind = "Carrossel" if not is_vid and len(target_urls) > 1 else "Vídeo" if is_vid else "Imagem"
                log.info(f"Buffer ({service or ch_id}): post ({kind}) criado id={result['post']['id']} dueAt={result['post'].get('dueAt')}")
                any_ok = True
            else:
                log.error(f"Buffer ({service or ch_id}) recusou: {result.get('message') or result}")
        except Exception as exc:
            log.error(f"Buffer ({service or ch_id}) falhou: {exc}")

    return any_ok


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Buffer API (GraphQL) helper")
    parser.add_argument("--channels", action="store_true", help="Lista canais conectados")
    parser.add_argument("--post-id", type=int, help="Publica post do banco local")
    parser.add_argument("--now", action="store_true", help="Publica imediatamente (shareNow)")
    parser.add_argument("--draft", action="store_true", help="Salva apenas como rascunho")
    parser.add_argument("--delete", metavar="BUFFER_POST_ID", help="Remove post do Buffer")
    parser.add_argument("--status", metavar="BUFFER_POST_ID", help="Mostra status de publicação")
    parser.add_argument("--service", help="Filtra serviço de destino (ex: instagram, tiktok, youtube)")
    args = parser.parse_args()
    _load_env()

    if args.status:
        print(json.dumps(get_post_status(args.status), indent=2, ensure_ascii=False))
    elif args.channels:
        for ch in list_channels():
            print(f"{ch['service']:<12} {ch['id']}  {ch.get('displayName') or ch.get('name')}  paused={ch.get('isQueuePaused')}")
    elif args.delete:
        print("OK" if delete_post(args.delete) else "FALHOU")
    elif args.post_id:
        from config.settings import DB_PATH
        from src.processor.db_manager import DBManager
        db = DBManager(DB_PATH)
        try:
            row = db.conn.execute("SELECT * FROM posts WHERE id = ?", (args.post_id,)).fetchone()
            if not row:
                print("Post não encontrado.")
            else:
                ok = publish_via_buffer(
                    dict(row),
                    mode="shareNow" if args.now else None,
                    draft=True if args.draft else None,
                    target_service=args.service,
                )
                print("OK" if ok else "FALHOU (ver logs)")
        finally:
            db.close()
    else:
        parser.print_help()
