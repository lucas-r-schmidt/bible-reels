"""
src/web/server.py
-----------------
Servidor web nativo (sem dependências extras) para a interface visual do Bible Reels.
Serve a UI moderna, arquivos estáticos, mídias geradas e endpoints de API.
"""
import json
import mimetypes
import os
import sqlite3
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import (
    DB_PATH,
    DEFAULT_PUBLISHER,
    OUTPUT_IMAGES,
    OUTPUT_VIDEOS,
    POSTPROXY_API_KEY,
    POSTPROXY_PROFILE_IDS,
    ROOT_DIR,
    WEBHOOK_URL,
)
from src.collector.bible_api import collect_verses
from src.collector.local_quotes import collect_quotes, collect_classic_prayers
from src.collector.liturgy import collect_gospel_of_day, collect_psalm_of_day
from src.collector.saints import collect_saint_of_day, get_saint_for_date, get_saint_image
from src.media_gen.image_builder import generate_post_image
from src.media_gen.video_builder import generate_video_from_image
from src.processor.ai_formatter import format_verse, format_saint_post, format_gospel_post, format_community_prayer_post
from src.processor.db_manager import DBManager
from src.publisher.buffer_api import publish_via_buffer
from src.publisher.postproxy import PostproxyPublisher, publish_via_postproxy
from src.publisher.webhook import publish_via_webhook
from src.publisher.instagram_direct import publish_via_instagram_direct
from src.publisher.tiktok_direct import publish_via_tiktok_direct, is_tiktok_authenticated
from src.utils.logger import get_logger
from src.web.auth import (
    ADMIN_EMAIL,
    SESSION_COOKIE_NAME,
    authenticate_email_password,
    check_rate_limit,
    clear_login_failures,
    create_session,
    delete_user,
    get_session_user,
    get_user_by_email,
    init_auth_db,
    list_users,
    record_login_failure,
    register_user,
    revoke_session,
    update_user_status,
)

log = get_logger("web_server")
STATIC_DIR = Path(__file__).resolve().parent / "static"
_ACTIVE_CUT_JOBS: dict[str, dict] = {}


def _regenerate_post_media(db: DBManager, post_id: int, include_images: bool = True) -> dict[str, Any]:
    """Regenera mídia de um post sem substituir conteúdo já publicado."""
    row = db.conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not row:
        raise ValueError("Post não encontrado")
    post = dict(row)
    verse_row = db.conn.execute("SELECT reference, source, text FROM verses WHERE id = ?", (post["verse_id"],)).fetchone()
    if not verse_row:
        raise ValueError("Tema associado ao post não encontrado")
    verse = dict(verse_row)
    reference = verse["reference"] or "Reflexão"
    source = verse["source"] or ""
    ref_lower = reference.lower()

    content_type = source or "verse"
    image_path = post.get("image_path", "")
    video_path = post.get("video_path", "")
    generated_slides: list[Path] = []

    is_saint = source == "saint" or any(k in ref_lower for k in ("santo", "santa", "são", "sao", "senhora"))
    is_gospel = source == "gospel" or "evangelho" in ref_lower
    is_novena = source == "novena" or "novena" in ref_lower

    if is_saint:
        content_type = "saint"
        from src.collector.saints import get_saint_images
        from src.media_gen.carousel_builder import generate_saint_carousel, build_saint_narration_text
        import re
        target_date = None
        date_match = re.search(r"\((\d{1,2})/(\d{1,2})\)", reference)
        if date_match:
            d_day, d_month = map(int, date_match.groups())
            target_date = date(date.today().year, d_month, d_day)
        saint_name = reference.split("(")[0].strip()
        saint_meta = get_saint_for_date(target_date) or {}
        raw_text = post.get("formatted_text") or verse["text"]
        title_hook = saint_meta.get("quote", "") or raw_text.split("\n\n—")[0]
        story_text = saint_meta.get("history", "") or raw_text
        prayer_text = saint_meta.get("prayer", "")
        if include_images:
            slides = generate_saint_carousel(
                post_id=post_id,
                saint_name=saint_name,
                title_hook=title_hook,
                story_text=story_text,
                prayer_text=prayer_text,
                bg_image_paths=get_saint_images(saint_name, count=5, target_date=target_date),
            )
            generated_slides = slides
            if slides:
                image_path = str(slides[0])
        narration = build_saint_narration_text(saint_name, title_hook, story_text, prayer_text)
    elif is_gospel:
        content_type = "gospel"
        from src.media_gen.tts import build_gospel_narration_text
        narration = build_gospel_narration_text(reference, verse["text"] or post["formatted_text"], concise=False)
    elif is_novena:
        content_type = "novena"
        from src.media_gen.tts import build_novena_narration_text
        narration = build_novena_narration_text(reference, verse["text"] or post["formatted_text"])
    else:
        from src.collector.backgrounds import get_thematic_background
        from src.media_gen.image_builder import generate_verse_scenes
        from src.media_gen.tts import build_verse_narration_text
        if include_images:
            generated_slides = generate_verse_scenes(post_id, reference, post["formatted_text"], post.get("visual_prompt", ""))
            if generated_slides:
                image_path = str(generated_slides[0])
            else:
                background = get_thematic_background(post.get("visual_prompt", ""), reference=reference)
                image_path = str(generate_post_image(post_id=post_id, text=post["formatted_text"], reference=reference, bg_image_path=background))
        narration = build_verse_narration_text(post["formatted_text"], reference=reference)

    video_target = Path(image_path) if image_path and Path(image_path).is_file() else None
    if include_images and generated_slides:
        video_slides = generated_slides
    elif not video_target and post.get("video_path"):
        raise ValueError("Imagem base não disponível para renderizar o vídeo")
    else:
        video_slides = None

    rendered = generate_video_from_image(
        video_target,
        slides=video_slides,
        narration_text=narration,
        theme=content_type,
        content_type=content_type,
    ) if video_target else None
    if rendered:
        video_path = str(rendered)
    elif video_target:
        raise RuntimeError("Falha ao gerar vídeo")

    db.update_post_media(post_id, image_path, video_path)
    return {"post_id": post_id, "image_path": image_path, "video_path": video_path, "content_type": content_type}


def _is_safe_subpath(base_dir: Path, target: Path) -> bool:
    """Garante que o caminho resolvido permanece estritamente dentro do diretório base."""
    try:
        return target.resolve().is_relative_to(base_dir.resolve())
    except Exception:
        return False


class BibleReelsHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # Silencia logs HTTP excessivos no console
        pass

    def _get_cookie_session(self) -> Optional[str]:
        raw_cookie = self.headers.get("Cookie", "")
        if not raw_cookie:
            return None
        for part in raw_cookie.split(";"):
            part = part.strip()
            if part.startswith(f"{SESSION_COOKIE_NAME}="):
                return part.split("=", 1)[1].strip()
        return None

    def _get_current_user(self) -> Optional[dict[str, Any]]:
        token = self._get_cookie_session()
        return get_session_user(token)

    def _require_auth(self) -> Optional[dict[str, Any]]:
        user = self._get_current_user()
        if not user:
            self._send_json({"error": "Autenticação necessária.", "need_auth": True}, status=401)
            return None
        if user.get("status") == "pending":
            self._send_json({
                "error": "Sua conta foi criada e está aguardando aprovação pelo administrador.",
                "status": "pending",
                "user": user
            }, status=403)
            return None
        if user.get("status") == "disabled":
            self._send_json({"error": "Sua conta foi desativada pelo administrador."}, status=403)
            return None
        return user

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        origin = self.headers.get("Origin", "")
        if origin and (origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1")):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            try:
                self._handle_api_get(path, parse_qs(parsed.query))
            except Exception as exc:
                log.exception(f"Erro inesperado em GET {path}: {exc}")
                self._send_json({"error": f"Erro interno: {exc}"}, status=500)
            return

        # Rota de mídias geradas
        if path.startswith("/media/"):
            self._serve_media(path[7:])
            return

        # Rota padrão para SPA
        if path in ("", "/"):
            self._serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return

        clean_path = path.lstrip("/")
        target_file = (STATIC_DIR / clean_path).resolve()
        if not _is_safe_subpath(STATIC_DIR, target_file):
            self.send_error(403, "Acesso proibido")
            return

        if target_file.is_file():
            mime_type, _ = mimetypes.guess_type(str(target_file))
            self._serve_file(target_file, mime_type or "application/octet-stream")
        else:
            self._serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(length) if length > 0 else b"{}"
            try:
                data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except Exception:
                data = {}
            try:
                self._handle_api_post(path, data)
            except Exception as exc:
                log.exception(f"Erro inesperado em {path}: {exc}")
                self._send_json({"success": False, "error": f"Erro interno no servidor: {exc}"}, status=500)
            return

        self._send_json({"error": "Endpoint não encontrado"}, status=404)

    def _serve_media(self, rel_path: str) -> None:
        clean = rel_path.lstrip("/\\")
        output_dir = (ROOT_DIR / "output").resolve()
        candidate = (ROOT_DIR / "output" / clean).resolve()

        if not candidate.is_file() or not _is_safe_subpath(output_dir, candidate):
            # Tenta buscar em images ou videos
            candidate_img = (OUTPUT_IMAGES / clean).resolve()
            candidate_vid = (OUTPUT_VIDEOS / clean).resolve()
            if candidate_img.is_file() and _is_safe_subpath(output_dir, candidate_img):
                candidate = candidate_img
            elif candidate_vid.is_file() and _is_safe_subpath(output_dir, candidate_vid):
                candidate = candidate_vid
            else:
                self.send_error(404, "Arquivo de mídia não encontrado")
                return

        if not _is_safe_subpath(output_dir, candidate):
            self.send_error(403, "Acesso proibido")
            return

        mime_type, _ = mimetypes.guess_type(str(candidate))
        self._serve_file(candidate, mime_type or "application/octet-stream")

    def _serve_file(self, file_path: Path, content_type: str) -> None:
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        except Exception as exc:
            try:
                self.send_error(500, f"Erro ao servir arquivo: {exc}")
            except Exception:
                pass

    def _send_json(self, data: Any, status: int = 200, set_cookie: Optional[str] = None) -> None:
        try:
            payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("X-Content-Type-Options", "nosniff")
            if set_cookie:
                self.send_header("Set-Cookie", set_cookie)

            origin = self.headers.get("Origin", "")
            if origin and (origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1") or "flowmedia.com.br" in origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
                self.send_header("Access-Control-Allow-Credentials", "true")

            self.end_headers()
            self.wfile.write(payload)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    # ── API Handlers ──────────────────────────────────────────────────────

    def _handle_api_get(self, path: str, params: dict[str, list[str]]) -> None:
        # Rotas públicas de autenticação
        if path == "/api/auth/me":
            user = self._get_current_user()
            if not user:
                self._send_json({"authenticated": False, "user": None})
            else:
                self._send_json({"authenticated": True, "user": user})
            return

        # Demais rotas exigem autenticação ativa
        current_user = self._require_auth()
        if not current_user:
            return

        # Rotas exclusivas de Admin
        if path == "/api/admin/users":
            if current_user.get("role") != "admin":
                self._send_json({"error": "Acesso restrito ao administrador."}, status=403)
                return
            self._send_json({"users": list_users()})
            return

        db = DBManager(DB_PATH)
        try:
            if path == "/api/stats":
                verses_count = db.conn.execute("SELECT COUNT(*) FROM verses").fetchone()[0]
                posts_count = db.conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
                pending_count = db.conn.execute("SELECT COUNT(*) FROM queue WHERE status = 'pending'").fetchone()[0]
                sent_count = db.conn.execute("SELECT COUNT(*) FROM queue WHERE status = 'sent'").fetchone()[0]
                failed_count = db.conn.execute("SELECT COUNT(*) FROM queue WHERE status = 'failed'").fetchone()[0]
                gospel_count = db.conn.execute("SELECT COUNT(*) FROM posts p JOIN verses v ON v.id = p.verse_id WHERE v.source = 'gospel'").fetchone()[0]
                saints_count = db.conn.execute("SELECT COUNT(*) FROM posts p JOIN verses v ON v.id = p.verse_id WHERE v.source = 'saint'").fetchone()[0]
                prayers_count = db.conn.execute("SELECT COUNT(*) FROM posts p JOIN verses v ON v.id = p.verse_id WHERE v.source = 'prayer'").fetchone()[0]
                psalms_count = db.conn.execute("SELECT COUNT(*) FROM posts p JOIN verses v ON v.id = p.verse_id WHERE v.source = 'psalm'").fetchone()[0]
                novenas_count = db.conn.execute("SELECT COUNT(*) FROM posts p JOIN verses v ON v.id = p.verse_id WHERE v.source = 'novena'").fetchone()[0]
                community_count = db.conn.execute("SELECT COUNT(*) FROM posts p JOIN verses v ON v.id = p.verse_id WHERE v.source = 'community'").fetchone()[0]

                from dotenv import load_dotenv
                load_dotenv(ROOT_DIR / ".env", override=True)
                active_pub = os.getenv("DEFAULT_PUBLISHER", DEFAULT_PUBLISHER)
                ig_user = os.getenv("INSTAGRAM_USERNAME", "")
                ig_pass = os.getenv("INSTAGRAM_PASSWORD", "")

                from src.collector.saints import check_active_novena
                active_nov = check_active_novena(date.today())

                self._send_json({
                    "verses_count": verses_count,
                    "posts_count": posts_count,
                    "queue_pending": pending_count,
                    "queue_sent": sent_count,
                    "queue_failed": failed_count,
                    "count_gospel": gospel_count,
                    "count_saints": saints_count,
                    "count_prayers": prayers_count,
                    "count_psalms": psalms_count,
                    "count_novenas": novenas_count,
                    "count_community": community_count,
                    "active_novena": active_nov,
                    "default_publisher": active_pub,
                    "webhook_configured": bool(os.getenv("WEBHOOK_URL")),
                    "instagram_configured": bool(ig_user and ig_pass),
                    "tiktok_configured": is_tiktok_authenticated(),
                    "postproxy_configured": bool(POSTPROXY_API_KEY),
                    "profile_ids": POSTPROXY_PROFILE_IDS
                })
                return

            if path == "/api/posts":
                limit = int(params.get("limit", ["100"])[0])
                status_filter = params.get("status", ["all"])[0].lower()
                type_filter = params.get("type", ["all"])[0].lower()
                post_id_param = params.get("id", [None])[0]

                query = """
                    SELECT p.*, v.reference, v.text as original_text, v.source as verse_source
                    FROM posts p
                    JOIN verses v ON v.id = p.verse_id
                """
                where_clauses = []
                sql_params = []

                if post_id_param and post_id_param.isdigit():
                    where_clauses.append("p.id = ?")
                    sql_params.append(int(post_id_param))
                else:
                    if status_filter in ("unpublished", "nao_publicados", "pending"):
                        where_clauses.append("p.status != 'published'")
                    elif status_filter in ("published", "publicados"):
                        where_clauses.append("p.status = 'published'")

                    if type_filter in ("scripture", "scriptures", "bible", "versiculo", "versiculos"):
                        where_clauses.append("v.source IN ('bible', 'bible_api', 'quotes', 'local_quotes')")
                    elif type_filter in ("saint", "saints", "santo", "santos"):
                        where_clauses.append("v.source = 'saint'")
                    elif type_filter in ("novena", "novenas"):
                        where_clauses.append("v.source = 'novena'")
                    elif type_filter in ("gospel", "evangelho", "liturgia"):
                        where_clauses.append("v.source = 'gospel'")
                    elif type_filter in ("prayer", "prayers", "oracao", "oracoes", "psalm", "salmo"):
                        where_clauses.append("v.source IN ('prayer', 'psalm')")
                    elif type_filter in ("community", "intercessao", "pedidos"):
                        where_clauses.append("v.source = 'community'")

                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)

                query += " ORDER BY p.id DESC LIMIT ? "
                sql_params.append(limit)

                rows = db.conn.execute(query, tuple(sql_params)).fetchall()

                posts = []
                for r in rows:
                    item = dict(r)
                    v_source = item.get("verse_source") or ""
                    ref_lower = (item.get("reference") or "").lower()
                    if v_source == "novena" or "novena" in ref_lower:
                        item["content_type"] = "novena"
                    elif v_source == "saint" or any(s in ref_lower for s in ("santo", "santa", "nossa senhora")):
                        item["content_type"] = "saint"
                    elif v_source == "gospel" or "evangelho" in ref_lower:
                        item["content_type"] = "gospel"
                    elif v_source in ("prayer", "psalm") or any(k in ref_lower for k in ("oração", "oracao", "salmo")):
                        item["content_type"] = "prayer"
                    elif v_source == "community":
                        item["content_type"] = "community"
                    else:
                        item["content_type"] = "scripture"

                    # Converte caminhos locais para URLs servidas
                    img_path = item.get("image_path") or ""
                    vid_path = item.get("video_path") or ""
                    item["image_url"] = None
                    item["video_url"] = None
                    item["is_carousel"] = False
                    item["carousel_slides"] = []
                    item["media_type"] = "image"

                    out_dir = (ROOT_DIR / "output").resolve()
                    if img_path and Path(img_path).is_file():
                        p_img = Path(img_path).resolve()
                        try:
                            rel = p_img.relative_to(out_dir).as_posix()
                            item["image_url"] = f"/media/{rel}"
                        except Exception:
                            item["image_url"] = f"/media/images/{p_img.name}"

                        is_slide_dir = any(k in p_img.parent.name.lower() for k in ("carousel_", "verse_", "scenes"))
                        if is_slide_dir:
                            item["is_carousel"] = True
                            item["media_type"] = "carousel"
                            slides = sorted([s for s in p_img.parent.iterdir() if s.is_file() and s.suffix.lower() in ('.png', '.jpg', '.jpeg')])
                            slide_urls = []
                            for s in slides:
                                try:
                                    slide_urls.append(f"/media/{s.resolve().relative_to(out_dir).as_posix()}")
                                except Exception:
                                    slide_urls.append(f"/media/{s.name}")
                            item["carousel_slides"] = slide_urls

                            # Detecta se existe trilha/áudio mixado para o carrossel
                            audio_file = p_img.parent / "carousel_audio.mp3"
                            if audio_file.is_file():
                                try:
                                    item["carousel_audio_url"] = f"/media/{audio_file.resolve().relative_to(out_dir).as_posix()}"
                                except Exception:
                                    item["carousel_audio_url"] = f"/media/carousels/{p_img.parent.name}/carousel_audio.mp3"
                            else:
                                item["carousel_audio_url"] = None
                        else:
                            item["carousel_audio_url"] = None

                    if vid_path and Path(vid_path).is_file():
                        p_vid = Path(vid_path).resolve()
                        try:
                            rel_v = p_vid.relative_to(out_dir).as_posix()
                            item["video_url"] = f"/media/{rel_v}"
                        except Exception:
                            item["video_url"] = f"/media/videos/{p_vid.name}"
                        item["media_type"] = "video"
                    
                    try:
                        item["hashtags"] = json.loads(item["hashtags"]) if item.get("hashtags") else []
                    except Exception:
                        item["hashtags"] = []
                    posts.append(item)

                self._send_json(posts)
                return

            if path == "/api/queue":
                limit = int(params.get("limit", ["50"])[0])
                rows = db.conn.execute("""
                    SELECT q.*, p.formatted_text, v.reference
                    FROM queue q
                    JOIN posts p ON p.id = q.post_id
                    JOIN verses v ON v.id = p.verse_id
                    ORDER BY q.id DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                self._send_json([dict(r) for r in rows])
                return

            if path == "/api/profiles":
                if not POSTPROXY_API_KEY:
                    self._send_json({"error": "POSTPROXY_API_KEY não configurada no .env"}, status=400)
                    return
                pub = PostproxyPublisher()
                try:
                    profiles = pub.listar_perfis()
                    self._send_json(profiles)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=500)
                return

            if path == "/api/logs":
                log_file = ROOT_DIR / "logs" / "bible_reels.log"
                lines = []
                if log_file.is_file():
                    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()[-60:]
                self._send_json({"lines": lines})
                return

            if path == "/api/actions/cut/status":
                job_id = params.get("job_id", [None])[0]
                if not job_id:
                    self._send_json({"jobs": list(_ACTIVE_CUT_JOBS.values())})
                    return
                info = _ACTIVE_CUT_JOBS.get(job_id)
                if not info:
                    from src.integrations.videoflow_client import VideoFlowClient
                    client = VideoFlowClient()
                    try:
                        remote = client.get_job_status(job_id)
                        self._send_json(remote)
                        return
                    except Exception as e:
                        self._send_json({"error": "Job não encontrado", "detail": str(e)}, status=404)
                        return
                self._send_json(info)
                return

            if path == "/api/analytics":
                summary = db.get_analytics_summary()
                self._send_json(summary)
                return

            self._send_json({"error": "Endpoint não encontrado"}, status=404)
        finally:
            db.close()

    def _handle_api_post(self, path: str, data: dict[str, Any]) -> None:
        client_ip = self.client_address[0] if self.client_address else "unknown"
        user_agent = self.headers.get("User-Agent", "")

        # 1. Login por Email e Senha
        if path == "/api/auth/login":
            email = str(data.get("email") or "").strip().lower()
            password = str(data.get("password") or "")
            remember_me = bool(data.get("remember_me", True))

            if not check_rate_limit(client_ip):
                self._send_json({"error": "Muitas tentativas sem sucesso. Aguarde alguns minutos."}, status=429)
                return

            user, err = authenticate_email_password(email, password)
            if not user or err:
                record_login_failure(client_ip)
                self._send_json({"error": err or "Credenciais inválidas."}, status=401)
                return

            clear_login_failures(client_ip)
            raw_token, max_age = create_session(user["id"], remember_me=remember_me, ip=client_ip, user_agent=user_agent)
            cookie_header = (
                f"{SESSION_COOKIE_NAME}={raw_token}; Max-Age={max_age}; Path=/; "
                f"SameSite=Lax; HttpOnly"
            )
            self._send_json({"success": True, "user": user}, set_cookie=cookie_header)
            return

        # 2. Cadastro de Nova Conta
        if path == "/api/auth/register":
            name = str(data.get("name") or "").strip()
            email = str(data.get("email") or "").strip().lower()
            password = str(data.get("password") or "")
            remember_me = bool(data.get("remember_me", True))

            user, err = register_user(name=name, email=email, password=password)
            if not user or err:
                self._send_json({"error": err or "Falha no cadastro."}, status=400)
                return

            raw_token, max_age = create_session(user["id"], remember_me=remember_me, ip=client_ip, user_agent=user_agent)
            cookie_header = (
                f"{SESSION_COOKIE_NAME}={raw_token}; Max-Age={max_age}; Path=/; "
                f"SameSite=Lax; HttpOnly"
            )
            self._send_json({"success": True, "user": user}, set_cookie=cookie_header)
            return

        # 3. Logout
        if path == "/api/auth/logout":
            token = self._get_cookie_session()
            if token:
                revoke_session(token)
            cookie_header = f"{SESSION_COOKIE_NAME}=; Max-Age=0; Path=/; SameSite=Lax; HttpOnly"
            self._send_json({"success": True}, set_cookie=cookie_header)
            return

        # As demais ações POST exigem usuário logado e ativo
        current_user = self._require_auth()
        if not current_user:
            return

        # Rotas exclusivas de Admin
        if path == "/api/admin/users/status":
            if current_user.get("role") != "admin":
                self._send_json({"error": "Acesso restrito ao administrador."}, status=403)
                return
            target_id = int(data.get("user_id", 0))
            new_status = str(data.get("status", "")).strip()
            new_role = data.get("role")
            ok, err = update_user_status(target_id, new_status, new_role)
            if ok:
                self._send_json({"success": True, "message": "Status do usuário atualizado!"})
            else:
                self._send_json({"error": err or "Erro ao atualizar usuário."}, status=400)
            return

        if path == "/api/admin/users/delete":
            if current_user.get("role") != "admin":
                self._send_json({"error": "Acesso restrito ao administrador."}, status=403)
                return
            target_id = int(data.get("user_id", 0))
            ok, err = delete_user(target_id)
            if ok:
                self._send_json({"success": True, "message": "Usuário excluído!"})
            else:
                self._send_json({"error": err or "Erro ao excluir usuário."}, status=400)
            return

        db = DBManager(DB_PATH)
        try:
            if path == "/api/actions/cut":
                url = (data.get("url") or "").strip()
                if not url:
                    self._send_json({"error": "URL do vídeo é obrigatória."}, status=400)
                    return
                preset = data.get("preset", "biblico")
                count = int(data.get("count", 3))

                from src.integrations.videoflow_client import VideoFlowClient
                client = VideoFlowClient()
                if not client.is_online():
                    self._send_json({"error": "VideoFlow está offline ou inacessível."}, status=503)
                    return

                try:
                    job = client.request_cuts(
                        source_url=url,
                        cut_mode="highlights",
                        niche_preset=preset,
                        max_clips=count,
                        publish_mode="draft"
                    )
                    job_id = job.get("job_id")
                    if not job_id:
                        self._send_json({"error": "VideoFlow não retornou job_id válido."}, status=500)
                        return

                    _ACTIVE_CUT_JOBS[job_id] = {
                        "job_id": job_id,
                        "status": "processing",
                        "url": url,
                        "preset": preset,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "post_ids": []
                    }

                    def _monitor():
                        try:
                            res = client.wait_for_job(job_id, timeout_seconds=900)
                            m_db = DBManager(DB_PATH)
                            try:
                                post_ids = client.import_to_bible_reels(res, m_db)
                                _ACTIVE_CUT_JOBS[job_id]["status"] = "completed"
                                _ACTIVE_CUT_JOBS[job_id]["post_ids"] = post_ids
                                _ACTIVE_CUT_JOBS[job_id]["message"] = f"{len(post_ids)} corte(s) importado(s) com sucesso!"
                            finally:
                                m_db.close()
                        except Exception as e:
                            log.error(f"Erro no monitoramento do corte {job_id}: {e}")
                            _ACTIVE_CUT_JOBS[job_id]["status"] = "failed"
                            _ACTIVE_CUT_JOBS[job_id]["error"] = str(e)

                    threading.Thread(target=_monitor, daemon=True).start()

                    self._send_json({
                        "success": True,
                        "job_id": job_id,
                        "message": f"Pedido enviado com sucesso ao VideoFlow (Job #{job_id[:8]})!"
                    })
                    return
                except Exception as exc:
                    log.error(f"Falha ao solicitar corte no VideoFlow: {exc}")
                    self._send_json({"error": str(exc)}, status=400)
                    return

            if path == "/api/actions/collect":
                source = data.get("source", "both")
                count = int(data.get("count", 1))
                theme = data.get("theme", "general")
                pub = data.get("publisher") or DEFAULT_PUBLISHER
                full_pipeline = bool(data.get("full_pipeline", False))

                if full_pipeline:
                    from main import step_collect, step_process, step_media
                    if source in ("saint", "santo"):
                        from main import run_saint_pipeline
                        t_date = None
                        t_raw = data.get("target_date") or data.get("date")
                        if t_raw:
                            try:
                                t_date = datetime.strptime(str(t_raw).strip(), "%Y-%m-%d").date()
                            except Exception:
                                pass
                        run_saint_pipeline(target_date=t_date, publisher=pub, make_video=True, dispatch=False)
                        self._send_json({"success": True, "message": "Pipeline do Santo do Dia executado até a renderização do vídeo final!"})
                        return

                    if source in ("novena", "novenas"):
                        from main import run_novena_pipeline
                        pid = run_novena_pipeline(publisher=pub, make_video=True, dispatch=False)
                        if pid:
                            self._send_json({"success": True, "message": f"Novena Litúrgica gerada e renderizada com sucesso (Post #{pid})!", "rendered_post_ids": [pid]})
                        else:
                            self._send_json({"success": False, "error": "Nenhuma novena litúrgica ativa no momento."}, status=400)
                        return

                    if source in ("prayer", "prayers", "oracao", "oracoes", "psalm", "salmo"):
                        from main import run_prayer_pipeline
                        pid = run_prayer_pipeline(source=source, publisher=pub, make_video=True, dispatch=False)
                        if pid:
                            self._send_json({"success": True, "message": f"Oração/Salmo gerado e renderizado com sucesso (Post #{pid})!", "rendered_post_ids": [pid]})
                        else:
                            self._send_json({"success": False, "error": "Falha ao gerar post de oração/salmo."}, status=500)
                        return

                    collected = step_collect(db, source=source, count=count, theme=theme)
                    post_ids = step_process(db, limit=count, publisher=pub, theme=theme, source=source if source != "both" else None)
                    rendered = []
                    if post_ids:
                        for pid in post_ids:
                            step_media(db, limit=1, make_video=True, post_id=pid)
                            rendered.append(pid)
                    else:
                        rendered = step_media(db, limit=count, make_video=True)
                    self._send_json({
                        "success": True,
                        "message": f"Pipeline concluído! {len(rendered)} vídeo(s) gerado(s) e adicionado(s) à fila.",
                        "rendered_post_ids": rendered
                    })
                    return

                if source in ("saint", "santo"):
                    collect_saint_of_day(db)
                elif source in ("novena", "novenas"):
                    from src.collector.saints import collect_novena_of_day
                    collect_novena_of_day(db)
                elif source in ("psalm", "salmo", "salmos"):
                    from src.collector.liturgy import collect_psalm_of_day
                    collect_psalm_of_day(db)
                elif source in ("gospel", "evangelho", "liturgia"):
                    collect_gospel_of_day(db)
                elif source in ("prayer", "prayers", "oracao", "oracoes"):
                    collect_classic_prayers(db, count=count)
                elif source in ("community", "intercessao", "pedidos"):
                    recent = db.get_recent_prayer_requests(limit=10)
                    c_hash = f"community_prayer_{date.today().isoformat()}"
                    if not db.verse_exists(c_hash):
                        authors = [c.get("author_name") for c in recent if c.get("author_name")]
                        names_preview = ", ".join(authors[:5]) if authors else "nossa comunidade"
                        db.insert_verse(
                            source="community",
                            reference="Oração pelos Inscritos",
                            text=f"Momento de intercessão e bênção pelas famílias de {names_preview} e de todos os inscritos.",
                            content_hash=c_hash,
                            translation="Comunidade de Fé"
                        )
                else:
                    if source in ("bible", "both"):
                        collect_verses(db, count=count, theme=theme)
                    if source in ("quotes", "both"):
                        collect_quotes(db, count=count, theme=theme)
                self._send_json({"success": True, "message": f"Coleta realizada com sucesso ({count} itens)."})
                return

            if path == "/api/actions/saint":
                pub = data.get("publisher") or DEFAULT_PUBLISHER
                media_format = data.get("format") or ("video" if data.get("make_video", True) else "image")
                target_date_raw = data.get("target_date") or data.get("date")
                schedule_time = data.get("schedule_time")
                auto_publish = bool(data.get("auto_publish", False)) or bool(schedule_time)

                target_date = date.today()
                if target_date_raw:
                    try:
                        target_date = datetime.strptime(str(target_date_raw).strip(), "%Y-%m-%d").date()
                    except Exception as exc:
                        log.warning(f"Formato inválido de target_date ({target_date_raw}): {exc}. Usando hoje.")

                saint = collect_saint_of_day(db, target_date=target_date, force=True)
                if not saint:
                    self._send_json({"error": "Falha ao coletar dados do Santo do Dia"}, status=500)
                    return

                verse_id = saint["verse_id"]
                ref_label = f"{saint['name']} ({saint.get('date_str', '')})"
                ai_data = format_saint_post(
                    reference=ref_label,
                    text=saint.get("quote", ""),
                    saint_metadata=saint
                )

                post_id = db.insert_post(
                    verse_id=verse_id,
                    formatted_text=ai_data["formatted_text"],
                    hashtags=ai_data["hashtags"],
                    visual_prompt=ai_data["visual_prompt"],
                    caption=ai_data.get("caption", "")
                )

                vid_path_str = ""
                carousel_slides_urls = []

                # Regra: Santo do Dia SEMPRE gera Carrossel (Instagram) + Vídeo vertical multi-cena (TikTok/YT)
                from src.media_gen.carousel_builder import generate_saint_carousel, build_saint_narration_text
                from src.collector.saints import get_saint_images
                saint_imgs = get_saint_images(saint["name"], count=5, target_date=target_date)
                slides = generate_saint_carousel(
                    post_id=post_id,
                    saint_name=saint["name"],
                    title_hook=saint.get("quote", ""),
                    story_text=saint.get("history", ""),
                    prayer_text=saint.get("prayer", ""),
                    bg_image_paths=saint_imgs
                )
                img_path = slides[0] if slides else (OUTPUT_IMAGES / f"post_{post_id:04d}.png")
                for s in slides:
                    try:
                        rel_s = s.relative_to(ROOT_DIR / "output").as_posix()
                        carousel_slides_urls.append(f"/media/{rel_s}")
                    except Exception:
                        carousel_slides_urls.append(f"/media/carousels/{s.parent.name}/{s.name}")

                # Gera o vídeo vertical MP4 sequencial a partir das lâminas para TikTok e YouTube Shorts
                # A narração contempla Capa/Citação + História + Oração
                saint_narration = build_saint_narration_text(
                    saint_name=saint["name"],
                    title_hook=saint.get("quote", ""),
                    story_text=saint.get("history", ""),
                    prayer_text=saint.get("prayer", "")
                )
                try:
                    scenes_dir = slides[0].parent / "scenes" if slides else None
                    v_scenes = [scenes_dir / f"scene_{i+1:02d}.png" for i in range(len(slides))] if (scenes_dir and scenes_dir.is_dir()) else slides
                    vid = generate_video_from_image(img_path, slides=v_scenes, narration_text=saint_narration, theme="saint", content_type="saint")
                    if vid:
                        vid_path_str = str(vid)
                except Exception as e_vid:
                    log.warning(f"Vídeo de apoio do Santo do Dia para TikTok/YouTube não renderizado: {e_vid}")

                db.update_post_media(post_id, str(img_path), vid_path_str)
                db.enqueue(post_id, pub)

                # Agendamento ou publicação automática caso solicitado
                scheduled_ok = False
                due_at_iso = None
                if schedule_time:
                    try:
                        dt_clean = str(schedule_time).strip()
                        if len(dt_clean) == 16:
                            dt_clean += ":00"
                        dt_parsed = datetime.fromisoformat(dt_clean)
                        if dt_parsed.tzinfo is None:
                            tz_br = timezone(timedelta(hours=-3))
                            dt_parsed = dt_parsed.replace(tzinfo=tz_br)
                        due_at_iso = dt_parsed.isoformat()
                    except Exception as exc:
                        log.warning(f"Erro ao converter schedule_time: {exc}")

                if auto_publish:
                    cur_p = db.conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
                    post_row = cur_p.fetchone()
                    if post_row:
                        p_dict = dict(post_row)
                        p_dict["reference"] = ref_label
                        scheduled_ok = publish_via_buffer(p_dict, due_at=due_at_iso)
                        if scheduled_ok:
                            db.mark_post_published(post_id)
                            db.conn.execute("UPDATE queue SET status = 'sent' WHERE post_id = ?", (post_id,))
                            db.conn.commit()

                format_label = "Carrossel de 5 Lâminas" if media_format == "carousel" else "Vídeo Vertical MP4" if media_format == "video" else "Imagem 9:16"
                msg = f"Post #{post_id} ({saint['name']}) gerado em formato {format_label} com sucesso!"
                if scheduled_ok:
                    msg += f" Agendado no Buffer para {schedule_time}!" if schedule_time else " Adicionado à fila do Buffer!"

                try:
                    rel_img = Path(img_path).relative_to(ROOT_DIR / "output").as_posix()
                    img_url = f"/media/{rel_img}"
                except Exception:
                    img_url = f"/media/images/{Path(img_path).name}"

                self._send_json({
                    "success": True,
                    "post_id": post_id,
                    "saint_name": saint["name"],
                    "title": saint.get("title", ""),
                    "format": media_format,
                    "scheduled": scheduled_ok,
                    "due_at": due_at_iso,
                    "image_url": img_url,
                    "carousel_slides": carousel_slides_urls,
                    "video_url": f"/media/videos/{Path(vid_path_str).name}" if vid_path_str else None,
                    "message": msg
                })
                return

            if path == "/api/actions/novena":
                pub = data.get("publisher") or DEFAULT_PUBLISHER
                make_video = bool(data.get("make_video", True))
                from main import run_novena_pipeline
                pid = run_novena_pipeline(publisher=pub, make_video=make_video, dispatch=False)
                if pid:
                    self._send_json({
                        "success": True,
                        "post_id": pid,
                        "message": f"Post #{pid} da Novena Litúrgica gerado com sucesso!",
                        "video_url": f"/media/videos/post_{pid:04d}.mp4" if make_video else None,
                        "image_url": f"/media/images/post_{pid:04d}.png"
                    })
                else:
                    self._send_json({"success": False, "error": "Nenhuma novena litúrgica ativa encontrada para hoje."}, status=400)
                return

            if path == "/api/actions/prayer":
                pub = data.get("publisher") or DEFAULT_PUBLISHER
                make_video = bool(data.get("make_video", True))
                source_kind = data.get("source") or "prayer"
                from main import run_prayer_pipeline
                pid = run_prayer_pipeline(source=source_kind, publisher=pub, make_video=make_video, dispatch=False)
                if pid:
                    self._send_json({
                        "success": True,
                        "post_id": pid,
                        "message": f"Post #{pid} ({source_kind}) gerado com sucesso!",
                        "video_url": f"/media/videos/post_{pid:04d}.mp4" if make_video else None,
                        "image_url": f"/media/images/post_{pid:04d}.png"
                    })
                else:
                    self._send_json({"success": False, "error": f"Falha ao gerar post para {source_kind}."}, status=500)
                return

            if path == "/api/actions/carousel":
                src = data.get("source") or "gospel"
                pub = data.get("publisher") or DEFAULT_PUBLISHER
                from main import run_carousel_pipeline
                ok = run_carousel_pipeline(source=src, publisher=pub)
                if ok:
                    self._send_json({"success": True, "message": f"Carrossel 4:5 ({src}) publicado com sucesso no feed do Instagram!"})
                else:
                    self._send_json({"success": False, "error": f"Falha ao publicar carrossel ({src}) no Instagram."}, status=500)
                return

            if path == "/api/actions/schedule-post":
                post_id = int(data.get("post_id", 0))
                schedule_time = data.get("schedule_time")
                if not post_id or not schedule_time:
                    self._send_json({"success": False, "error": "Parâmetros post_id e schedule_time obrigatórios"}, status=400)
                    return

                cur_p = db.conn.execute("SELECT p.*, v.reference FROM posts p JOIN verses v ON p.verse_id = v.id WHERE p.id = ?", (post_id,))
                row = cur_p.fetchone()
                if not row:
                    self._send_json({"success": False, "error": "Post não encontrado"}, status=404)
                    return

                p_dict = dict(row)
                due_at_iso = None
                try:
                    dt_clean = str(schedule_time).strip()
                    if len(dt_clean) == 16:
                        dt_clean += ":00"
                    dt_parsed = datetime.fromisoformat(dt_clean)
                    if dt_parsed.tzinfo is None:
                        tz_br = timezone(timedelta(hours=-3))
                        dt_parsed = dt_parsed.replace(tzinfo=tz_br)
                    due_at_iso = dt_parsed.isoformat()
                except Exception as exc:
                    log.warning(f"Erro ao converter schedule_time: {exc}")

                ok = publish_via_buffer(p_dict, due_at=due_at_iso)
                if ok:
                    db.mark_post_published(post_id)
                    db.conn.execute("UPDATE queue SET status = 'sent' WHERE post_id = ?", (post_id,))
                    db.conn.commit()
                    self._send_json({"success": True, "message": f"Post #{post_id} agendado no Buffer com sucesso para {schedule_time}!"})
                else:
                    self._send_json({"success": False, "error": f"Falha ao agendar post #{post_id} no Buffer. Verifique os logs."}, status=500)
                return

            if path == "/api/actions/process":
                limit = int(data.get("limit", 3))
                pub = data.get("publisher") or DEFAULT_PUBLISHER
                unused = db.get_unused_verses(limit=limit)
                processed = 0
                for item in unused:
                    if item.get("source") == "saint":
                        saint_meta = get_saint_for_date()
                        ai_data = format_saint_post(item["reference"], item["text"], saint_metadata=saint_meta)
                    elif item.get("source") == "gospel":
                        ai_data = format_gospel_post(item["reference"], item["text"], celebration=item.get("translation", ""))
                    elif item.get("source") == "community":
                        recent = db.get_recent_prayer_requests(limit=10)
                        ai_data = format_community_prayer_post(recent)
                    else:
                        try:
                            ai_data = format_verse(item["reference"], item["text"])
                        except Exception:
                            ai_data = None
                        if not ai_data:
                            ai_data = {
                                "formatted_text": f"{item['text']}\n\n— {item['reference']}",
                                "hashtags": ["fe", "gratidao", "motivacao", "palavradedeus", "reelsbrasil", "tiktokcristao"],
                                "visual_prompt": "Serene cinematic sunrise with mountains"
                            }
                    post_id = db.insert_post(
                        verse_id=item["id"],
                        formatted_text=ai_data["formatted_text"],
                        hashtags=ai_data["hashtags"],
                        visual_prompt=ai_data["visual_prompt"],
                        caption=ai_data.get("caption", "")
                    )
                    db.enqueue(post_id, pub)
                    processed += 1
                self._send_json({"success": True, "processed": processed, "publisher": pub})
                return

            if path in ("/api/actions/regenerate-video", "/api/actions/regenerate-full"):
                post_id_raw = data.get("post_id")
                if not post_id_raw:
                    self._send_json({"error": "post_id obrigatório"}, status=400)
                    return
                post_id = int(post_id_raw)
                row = db.conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
                if not row:
                    self._send_json({"error": "Post não encontrado"}, status=404)
                    return
                original = dict(row)
                working_id = post_id
                created_draft = False
                if original.get("status") == "published":
                    working_id = db.clone_post_draft(post_id)
                    created_draft = working_id is not None
                    if not created_draft:
                        self._send_json({"error": "Não foi possível criar a nova versão"}, status=500)
                        return

                if path == "/api/actions/regenerate-full":
                    verse = db.conn.execute("SELECT reference, source, text FROM verses WHERE id = ?", (original["verse_id"],)).fetchone()
                    if not verse:
                        self._send_json({"error": "Tema associado não encontrado"}, status=404)
                        return
                    verse = dict(verse)
                    source = verse.get("source", "")
                    reference = verse.get("reference", "")
                    raw_text = verse.get("text", original["formatted_text"])
                    formatted = None
                    try:
                        if source == "saint":
                            formatted = format_saint_post(reference, raw_text)
                        elif source == "gospel":
                            formatted = format_gospel_post(reference, raw_text)
                        elif source == "novena":
                            formatted = format_novena_post({
                                "saint_name": reference.split("(")[0].strip(),
                                "novena_day": 1,
                                "saint_data": {"history": raw_text, "prayer": raw_text},
                            })
                        elif source == "prayer":
                            formatted = format_prayer_post(reference, raw_text)
                        else:
                            formatted = format_verse(reference, raw_text)
                    except Exception as exc:
                        log.warning(f"Falha ao formatar conteúdo completo: {exc}")
                    if formatted:
                        db.update_post_content(
                            working_id,
                            formatted.get("formatted_text") or original["formatted_text"],
                            formatted.get("hashtags") or [],
                            formatted.get("visual_prompt") or original.get("visual_prompt", ""),
                            formatted.get("caption") or "",
                            formatted.get("hook_title") or original.get("hook_title", ""),
                        )

                try:
                    media = _regenerate_post_media(db, working_id, include_images=(path == "/api/actions/regenerate-full"))
                except Exception as exc:
                    log.error(f"Falha ao regenerar mídia do post #{working_id}: {exc}")
                    self._send_json({"error": str(exc)}, status=500)
                    return

                self._send_json({
                    "success": True,
                    "post_id": working_id,
                    "source_post_id": post_id,
                    "created_draft": created_draft,
                    "media_preserved_until_success": True,
                    "media": media,
                })
                return

            if path == "/api/actions/media":
                limit = int(data.get("limit", 3))
                make_video = bool(data.get("make_video", True))
                post_id = data.get("post_id")
                if post_id:
                    cur = db.conn.execute("SELECT * FROM posts WHERE id = ?", (int(post_id),))
                    row = cur.fetchone()
                    posts = [dict(row)] if row else []
                else:
                    posts = db.get_pending_posts(limit=limit, need_video=make_video, need_image=not make_video)

                rendered = 0
                for post in posts:
                    cur = db.conn.execute("SELECT reference, source FROM verses WHERE id = ?", (post["verse_id"],))
                    v_row = cur.fetchone()
                    ref = v_row["reference"] if v_row else "Reflexão"
                    source = v_row["source"] if v_row else ""

                    is_saint = source == "saint" or any(k in ref.lower() for k in ("santo", "santa", "são", "sao", "senhora"))
                    verse_scenes = []

                    if is_saint:
                        from src.collector.saints import get_saint_for_date, get_saint_images
                        from src.media_gen.carousel_builder import generate_saint_carousel, build_saint_narration_text
                        import re
                        target_date = None
                        date_match = re.search(r"\((\d{1,2})/(\d{1,2})\)", ref)
                        if date_match:
                            d_day, d_month = int(date_match.group(1)), int(date_match.group(2))
                            target_date = date(date.today().year, d_month, d_day)
                        clean_name = ref.split("(")[0].strip()
                        saint_meta = get_saint_for_date(target_date) or {}
                        raw_t = post.get("formatted_text") or ""
                        title_hook = saint_meta.get("quote", "") or raw_t.split("\n\n—")[0]
                        story_text = saint_meta.get("history", "") or raw_t
                        prayer_text = saint_meta.get("prayer", "")

                        saint_imgs = get_saint_images(clean_name, count=5, target_date=target_date)
                        slides = generate_saint_carousel(
                            post_id=post["id"],
                            saint_name=clean_name,
                            title_hook=title_hook,
                            story_text=story_text,
                            prayer_text=prayer_text,
                            bg_image_paths=saint_imgs
                        )
                        img_path = slides[0] if slides else (OUTPUT_IMAGES / f"post_{post['id']:04d}.png")
                        vid_target = img_path
                        verse_scenes = slides
                        n_text = build_saint_narration_text(clean_name, title_hook, story_text, prayer_text)
                    else:
                        from src.collector.backgrounds import get_thematic_background
                        from src.media_gen.image_builder import generate_verse_scenes
                        from src.media_gen.tts import build_verse_narration_text
                        verse_scenes = generate_verse_scenes(post["id"], ref, post["formatted_text"], post.get("visual_prompt", ""))
                        if verse_scenes:
                            img_path = verse_scenes[0]
                            vid_target = verse_scenes[0]
                        else:
                            bg_img = get_thematic_background(post.get("visual_prompt", ""), reference=ref)
                            img_path = generate_post_image(
                                post_id=post["id"],
                                text=post["formatted_text"],
                                reference=ref,
                                badge_text=None,
                                bg_image_path=bg_img
                            )
                            vid_target = img_path
                        n_text = build_verse_narration_text(post["formatted_text"], reference=ref)

                    vid_str = ""
                    if make_video:
                        vid = generate_video_from_image(vid_target, slides=verse_scenes if verse_scenes else None, narration_text=n_text)
                        if vid:
                            vid_str = str(vid)
                    db.update_post_media(post["id"], str(img_path), vid_str)
                    rendered += 1
                self._send_json({"success": True, "rendered": rendered, "post_ids": [p["id"] for p in posts]})
                return

            if path == "/api/actions/dispatch":
                items = db.get_pending_queue(limit=10)
                sent = 0
                for q in items:
                    cur = db.conn.execute("SELECT * FROM posts WHERE id = ?", (q["post_id"],))
                    row = cur.fetchone()
                    if not row:
                        continue
                    post = dict(row)
                    plat = (q.get("platform") or os.getenv("DEFAULT_PUBLISHER", DEFAULT_PUBLISHER)).lower()
                    if plat in ("all", "multi", "todos"):
                        s1 = publish_via_instagram_direct(post)
                        s2 = publish_via_webhook(post)
                        s3 = publish_via_tiktok_direct(post) if is_tiktok_authenticated() else False
                        success = s1 or s2 or s3
                    elif plat in ("instagram", "instagram_direct", "instagrapi"):
                        success = publish_via_instagram_direct(post)
                    elif plat in ("tiktok", "tiktok_official"):
                        from src.publisher.tiktok import publish_via_tiktok
                        success = publish_via_tiktok(post)
                    elif plat == "tiktok_direct":
                        success = publish_via_tiktok_direct(post)
                    elif plat in ("buffer", "buffer_api"):
                        from src.publisher.buffer_api import publish_via_buffer
                        success = publish_via_buffer(post)
                    elif plat == "postproxy":
                        success = publish_via_postproxy(post)
                    elif plat in ("social_publisher", "social", "hub"):
                        from src.publisher.social_publisher import publish_via_social_publisher
                        success = publish_via_social_publisher(post)
                    else:
                        success = publish_via_webhook(post)
                    if success:
                        db.mark_queue_sent(q["id"])
                        db.mark_post_published(post["id"])
                        sent += 1
                    else:
                        db.mark_queue_failed(q["id"])
                self._send_json({"success": True, "sent": sent, "total": len(items)})
                return

            if path == "/api/actions/publish-post":
                post_id = int(data.get("post_id", 0))
                from dotenv import load_dotenv
                load_dotenv(ROOT_DIR / ".env", override=True)
                pub = (data.get("publisher") or os.getenv("DEFAULT_PUBLISHER", DEFAULT_PUBLISHER)).lower()
                cur = db.conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
                row = cur.fetchone()
                if not row:
                    self._send_json({"success": False, "error": "Post não encontrado"}, status=404)
                    return
                post = dict(row)

                if pub in ("all", "multi", "todos"):
                    # 1. Instagram Direto
                    ok_ig = publish_via_instagram_direct(post)
                    # 2. YouTube Shorts (via n8n Webhook)
                    ok_yt = publish_via_webhook(post)
                    # 3. TikTok Direto via Playwright (se logado)
                    ok_tk = False
                    if is_tiktok_authenticated():
                        ok_tk = publish_via_tiktok_direct(post)

                    success = ok_ig or ok_yt or ok_tk
                    tt_status = f", TikTok: {'✅' if ok_tk else '❌'}" if is_tiktok_authenticated() else ""
                    target_name = f"Multi-Canal (Instagram: {'✅' if ok_ig else '❌'}, YouTube: {'✅' if ok_yt else '❌'}{tt_status})"
                elif pub in ("instagram", "instagram_direct", "instagrapi"):
                    success = publish_via_instagram_direct(post)
                    target_name = "Instagram Direto"
                elif pub in ("tiktok", "tiktok_official"):
                    from src.publisher.tiktok import publish_via_tiktok
                    success = publish_via_tiktok(post)
                    target_name = "TikTok Oficial (API v2)"
                elif pub == "tiktok_direct":
                    success = publish_via_tiktok_direct(post)
                    target_name = "TikTok Direto (Playwright)"
                elif pub in ("buffer", "buffer_api"):
                    from src.publisher.buffer_api import publish_via_buffer
                    success = publish_via_buffer(post)
                    target_name = "Buffer API (direto)"
                elif pub == "postproxy":
                    success = publish_via_postproxy(post)
                    target_name = "Postproxy"
                elif pub in ("social_publisher", "social", "hub"):
                    from src.publisher.social_publisher import publish_via_social_publisher
                    success = publish_via_social_publisher(post)
                    target_name = "Social Publisher Hub (:8000)"
                else:
                    success = publish_via_webhook(post)
                    target_name = "n8n Webhook / Buffer"

                if success:
                    db.mark_post_published(post_id)
                    db.conn.execute("UPDATE queue SET status = 'sent' WHERE post_id = ?", (post_id,))
                    db.conn.commit()
                    self._send_json({"success": True, "message": f"Post #{post_id} processado via {target_name}!"})
                else:
                    self._send_json({"success": False, "error": f"Falha ao enviar post #{post_id} via {target_name}. Verifique os logs."}, status=500)
                return

            if path == "/api/actions/delete-post":
                post_id = data.get("post_id")
                if not post_id:
                    self._send_json({"error": "post_id obrigatório"}, status=400)
                    return
                try:
                    deleted = db.delete_post_draft(int(post_id))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=409)
                    return
                if deleted:
                    self._send_json({"success": True, "message": f"Post #{int(post_id)} excluído permanentemente!", "post_id": int(post_id)})
                else:
                    self._send_json({"error": "Post não encontrado"}, status=404)
                return

            if path == "/api/actions/queue-remove":
                queue_id = data.get("queue_id")
                clear_all = bool(data.get("clear_all", False))
                if clear_all:
                    cur = db.conn.execute("DELETE FROM queue WHERE status IN ('pending', 'failed')")
                    deleted = cur.rowcount
                    db.conn.commit()
                    self._send_json({"success": True, "message": f"{deleted} post(s) não disparado(s) removido(s) da fila!", "deleted": deleted})
                    return
                elif queue_id:
                    cur = db.conn.execute("DELETE FROM queue WHERE id = ?", (int(queue_id),))
                    deleted = cur.rowcount
                    db.conn.commit()
                    if deleted > 0:
                        self._send_json({"success": True, "message": f"Item #{queue_id} removido da fila com sucesso!"})
                    else:
                        self._send_json({"success": False, "error": f"Item #{queue_id} não encontrado na fila."}, status=404)
                    return
                else:
                    self._send_json({"success": False, "error": "Parâmetro queue_id ou clear_all obrigatório."}, status=400)
                    return

            if path == "/api/actions/sync-metrics":
                from src.analytics.metrics_collector import collect_buffer_metrics
                summary = collect_buffer_metrics(db)
                self._send_json({"success": True, "message": "Métricas sincronizadas com sucesso!", "summary": summary})
                return

            self._send_json({"error": "Endpoint não encontrado"}, status=404)
        finally:
            db.close()


def run_web_server(port: int = 5000) -> None:
    init_auth_db()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, BibleReelsHandler)
    log.info(f"Interface Web iniciada com sucesso em: http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("Servidor Web finalizado.")
        httpd.server_close()


if __name__ == "__main__":
    port = 5000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_web_server(port)
