"""
main.py
-------
Pipeline CLI principal para automação de vídeos/posts bíblicos e motivacionais.

Modos de uso:
    python main.py --all                   # Executa fluxo completo (coleta -> IA -> imagem -> fila)
    python main.py --collect --source bible # Apenas coleta versículos bíblicos
    python main.py --collect --source quotes# Apenas coleta frases do JSON local
    python main.py --process               # Processa versículos pendentes com Gemini Flash
    python main.py --media                 # Gera imagens verticais (9:16)
    python main.py --dispatch              # Dispara posts para webhooks/fila
    python main.py --daemon                # Executa em loop agendado
"""
import argparse
import os
import random
import re
import sys
import time
from datetime import date, datetime, timedelta, time as dtime
from pathlib import Path

from config.settings import DB_PATH, POSTS_PER_RUN, DEFAULT_PUBLISHER, OUTPUT_IMAGES, OUTPUT_VIDEOS
from src.collector.bible_api import collect_verses
from src.collector.local_quotes import collect_quotes, collect_classic_prayers
from src.collector.liturgy import collect_gospel_of_day, collect_psalm_of_day
from src.collector.saints import collect_saint_of_day, get_saint_for_date, get_saint_image, check_active_novena, collect_novena_of_day
from src.media_gen.image_builder import generate_post_image
from src.media_gen.video_builder import generate_video_from_image
from src.processor.ai_formatter import (
    format_verse,
    format_saint_post,
    format_gospel_post,
    format_community_prayer_post,
    format_novena_post,
    format_prayer_post
)
from src.processor.db_manager import DBManager
from src.publisher.postproxy import PostproxyPublisher, publish_via_postproxy
from src.publisher.webhook import publish_via_webhook
from src.publisher.instagram_direct import publish_via_instagram_direct
from src.publisher.tiktok_direct import publish_via_tiktok_direct, is_tiktok_authenticated
from src.utils.logger import get_logger

log = get_logger("main")

def step_collect(db: DBManager, source: str = "both", count: int = 5, theme: str = "general") -> list[dict]:
    log.info(f"=== [1/4] Coleta de Conteúdo (Fonte: {source}, Meta: {count}, Tema: {theme}) ===")
    collected_items: list[dict] = []
    if source == "both":
        if count == 1:
            # Alterna dinamicamente entre versículo e mensagem motivacional/reflexão
            chosen = random.choice(["bible", "quotes"])
            log.info(f"Fonte selecionada para este post: {chosen.upper()}")
            if chosen == "bible":
                collected_items = collect_verses(db, count=1, theme=theme)
            else:
                collected_items = collect_quotes(db, count=1, theme=theme)
        else:
            c_bible = count // 2
            c_quotes = count - c_bible
            collected_items = collect_verses(db, count=c_bible, theme=theme) + collect_quotes(db, count=c_quotes, theme=theme)
    elif source == "bible":
        collected_items = collect_verses(db, count=count, theme=theme)
    elif source == "quotes":
        collected_items = collect_quotes(db, count=count, theme=theme)
    elif source in ("saint", "saints", "santo"):
        from datetime import date, timedelta
        # Publicação às 20:30 da véspera: busca o santo do dia seguinte!
        tomorrow = date.today() + timedelta(days=1)
        res = collect_saint_of_day(db, target_date=tomorrow)
        if res and res.get("verse_id"):
            collected_items = [{"id": res["verse_id"], "reference": res.get("name"), "source": "saint"}]
    elif source in ("gospel", "evangelho", "liturgia"):
        from datetime import date
        res = collect_gospel_of_day(db, target_date=date.today())
        if res and res.get("verse_id"):
            collected_items = [{"id": res["verse_id"], "reference": res.get("reference"), "source": "gospel"}]
    elif source in ("prayer", "prayers", "oracao", "oracoes"):
        collected_items = collect_classic_prayers(db, count=count)
    elif source in ("psalm", "salmo", "salmos"):
        res = collect_psalm_of_day(db, target_date=date.today())
        if res and res.get("verse_id"):
            collected_items = [{"id": res["verse_id"], "reference": res.get("reference"), "source": "psalm"}]
    elif source in ("novena", "novenas"):
        res = collect_novena_of_day(db, target_date=date.today())
        if res and res.get("verse_id"):
            collected_items = [{"id": res["verse_id"], "reference": res.get("saint_name"), "source": "novena"}]
    elif source in ("community", "intercessao", "pedidos"):
        # Coleta pedidos de oração de seguidores
        recent = db.get_recent_prayer_requests(limit=10)
        c_hash = f"community_prayer_{date.today().isoformat()}"
        if not db.verse_exists(c_hash):
            authors = [c.get("author_name") for c in recent if c.get("author_name")]
            names_preview = ", ".join(authors[:5]) if authors else "nossa comunidade"
            v_id = db.insert_verse(
                source="community",
                reference="Oração pelos Inscritos",
                text=f"Momento de intercessão e bênção pelas famílias de {names_preview} e de todos os inscritos.",
                content_hash=c_hash,
                translation="Comunidade de Fé"
            )
            collected_items = [{"id": v_id, "reference": "Oração pelos Inscritos", "source": "community"}]
        else:
            row = db.conn.execute("SELECT id, reference, source FROM verses WHERE hash = ?", (c_hash,)).fetchone()
            if row:
                collected_items = [dict(row)]
    return collected_items

def step_process(db: DBManager, limit: int = 5, publisher: str = DEFAULT_PUBLISHER, theme: str = "general", source: str | None = None) -> list[int]:
    log.info(f"=== [2/4] Processamento com Gemini Flash (Limite: {limit}, Tema: {theme}) ===")
    unused = db.get_unused_verses(limit=limit, source=source)
    if not unused:
        log.info("Nenhum versículo pendente de formatação.")
        return []

    created_post_ids: list[int] = []
    for item in unused:
        log.info(f"Processando verso ID={item['id']}: {item['reference']} (Origem: {item.get('source')}, Tema: {theme})")
        if item.get("source") == "saint":
            target_d = None
            date_match = re.search(r"\((\d{1,2})/(\d{1,2})\)", item["reference"])
            if date_match:
                target_d = date(date.today().year, int(date_match.group(2)), int(date_match.group(1)))
            saint_meta = get_saint_for_date(target_d)
            ai_data = format_saint_post(item["reference"], item["text"], saint_metadata=saint_meta, is_eve=True)
        elif item.get("source") == "gospel":
            ai_data = format_gospel_post(item["reference"], item["text"], celebration=item.get("translation", ""))
        elif item.get("source") == "novena":
            nov_info = check_active_novena(date.today()) or {
                "saint_name": item["reference"].split("(")[0].replace("Novena de", "").strip(),
                "novena_day": 1,
                "total_days": 9,
                "feast_date": "",
                "saint_data": {"prayer": item["text"]}
            }
            ai_data = format_novena_post(nov_info)
        elif item.get("source") in ("prayer", "psalm"):
            ai_data = format_prayer_post(item["reference"], item["text"])
        elif item.get("source") == "community":
            recent = db.get_recent_prayer_requests(limit=10)
            ai_data = format_community_prayer_post(recent)
        else:
            try:
                ai_data = format_verse(item["reference"], item["text"], theme=theme)
            except Exception as exc:
                log.warning(f"Falha na chamada Gemini ({exc}). Usando fallback local.")
                ai_data = None

            if not ai_data:
                if theme == "morning":
                    ai_data = {
                        "formatted_text": f"{item['text']}\n\n— {item['reference']}",
                        "hashtags": ["bomdia", "forca", "animo", "devocionalmatinal", "fe", "palavradodia", "reelsbrasil"],
                        "visual_prompt": "Cinematic sunrise over golden mountains, hopeful morning dawn, warm sunlight"
                    }
                elif theme == "midday":
                    ai_data = {
                        "formatted_text": f"{item['text']}\n\n— {item['reference']}",
                        "hashtags": ["meiodia", "fe", "sabedoria", "perseveranca", "palavradedeus", "reelsbrasil", "motivacaocrista"],
                        "visual_prompt": "Radiant midday sunbeams over lush green hills and clear blue skies, cinematic and bright"
                    }
                elif theme == "evening":
                    ai_data = {
                        "formatted_text": f"{item['text']}\n\n— {item['reference']}",
                        "hashtags": ["boanoite", "gratidao", "paz", "descanso", "fe", "alivio", "oracaodanoite"],
                        "visual_prompt": "Serene twilight lake with calm water at sunset, tranquil stars and gentle evening peace"
                    }
                else:
                    ai_data = {
                        "formatted_text": f"{item['text']}\n\n— {item['reference']}",
                        "hashtags": ["fe", "gratidao", "motivacao", "palavradedeus", "reelsbrasil", "tiktokcristao"],
                        "visual_prompt": "Serene cinematic landscape at sunrise, golden sunlight filtering through mountains"
                    }

        post_id = db.insert_post(
            verse_id=item["id"],
            formatted_text=ai_data["formatted_text"],
            hashtags=ai_data["hashtags"],
            visual_prompt=ai_data["visual_prompt"],
            caption=ai_data.get("caption", ""),
            hook_title=ai_data.get("hook_title", "")
        )
        created_post_ids.append(post_id)
        # Enfileira para publicador configurado
        target_platform = publisher or DEFAULT_PUBLISHER
        db.enqueue(post_id, target_platform)

    return created_post_ids

def step_media(db: DBManager, limit: int = 5, make_video: bool = True, post_id: int | None = None) -> list[int]:
    log.info(f"=== [3/4] Geração de Mídia Dinâmica (Vídeo Multi-Cena & Carrossel, Limite: {limit}, Post ID: {post_id or 'pendentes'}) ===")
    if post_id:
        cur_single = db.conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        row_s = cur_single.fetchone()
        pending_posts = [dict(row_s)] if row_s else []
    else:
        pending_posts = db.get_pending_posts(limit=limit)

    if not pending_posts:
        log.info("Nenhum post pendente de mídia.")
        return []

    rendered_post_ids: list[int] = []
    for post in pending_posts:
        if post["image_path"] and not make_video and not post_id:
            continue

        # Busca dados do verso original para referência
        cur = db.conn.execute("SELECT reference, source FROM verses WHERE id = ?", (post["verse_id"],))
        v_row = cur.fetchone()
        ref = v_row["reference"] if v_row else "Reflexão"
        source = v_row["source"] if v_row else ""

        if source == "saint" or (source not in ("novena", "prayer", "psalm") and any(k in ref.lower() for k in ("santo", "santa", "são", "sao", "senhora"))):
            from src.media_gen.carousel_builder import generate_saint_carousel, build_saint_narration_text
            target_date = None
            date_match = re.search(r"\((\d{1,2})/(\d{1,2})\)", ref)
            if date_match:
                d_day, d_month = int(date_match.group(1)), int(date_match.group(2))
                target_date = date(date.today().year, d_month, d_day)

            clean_saint_name = ref.split("(")[0].strip()
            saint_meta = get_saint_for_date(target_date) or {}
            title_hook = saint_meta.get("quote", "") or post["formatted_text"].split("\n\n—")[0]
            story_text = saint_meta.get("history", "") or post["formatted_text"]
            prayer_text = saint_meta.get("prayer", "")

            slides = generate_saint_carousel(
                post_id=post["id"],
                saint_name=clean_saint_name,
                title_hook=title_hook,
                story_text=story_text,
                prayer_text=prayer_text
            )
            scenes_dir = slides[0].parent / "scenes" if slides else None
            v_scenes = [scenes_dir / f"scene_{i+1:02d}.png" for i in range(len(slides))] if (scenes_dir and scenes_dir.is_dir()) else slides
            img_path = (scenes_dir / "scene_01.png") if (scenes_dir and (scenes_dir / "scene_01.png").is_file()) else (
                slides[0] if slides else generate_post_image(
                    post_id=post["id"],
                    text=post["formatted_text"],
                    reference=clean_saint_name,
                    badge_text="MENSAGEM DO SANTO DO DIA",
                    bg_image_path=get_saint_image(clean_saint_name, target_date=target_date)
                )
            )
            from src.collector.saints import get_saint_images
            from src.media_gen.image_builder import generate_saint_video_scenes
            saint_imgs = get_saint_images(clean_saint_name)
            saint_vscenes = generate_saint_video_scenes(
                post_id=post["id"],
                saint_name=clean_saint_name,
                title_hook=title_hook,
                saint_images=saint_imgs,
                reference=clean_saint_name
            )
            vid_target = saint_vscenes[0]
            slides_for_video = saint_vscenes
            narration_text = build_saint_narration_text(clean_saint_name, title_hook, story_text, prayer_text)
        elif source == "gospel" or "evangelho" in ref.lower():
            from src.media_gen.carousel_builder import generate_gospel_carousel
            from src.media_gen.tts import build_gospel_narration_text

            hook_title = post.get("hook_title") or ""
            caption = post.get("caption") or ""

            # Extrai reflexão pastoral da legenda se disponível
            homily = ""
            if "Reflexão:" in caption:
                m_reflec = re.search(r"Reflexão:\s*([^\n\r]+)", caption)
                if m_reflec:
                    homily = m_reflec.group(1).strip()
            if not homily and hook_title:
                homily = hook_title

            slides = generate_gospel_carousel(
                post_id=post["id"],
                reference=ref,
                full_text=post["formatted_text"],
                homily_reflection=homily,
                hook_title=hook_title,
                visual_prompt=post.get("visual_prompt", "")
            )
            scenes_dir = slides[0].parent / "scenes" if slides else None
            v_scenes = [scenes_dir / f"scene_{i+1:02d}.png" for i in range(len(slides))] if (scenes_dir and scenes_dir.is_dir()) else slides
            img_path = (scenes_dir / "scene_01.png") if (scenes_dir and (scenes_dir / "scene_01.png").is_file()) else (slides[0] if slides else OUTPUT_IMAGES / f"post_{post['id']:04d}.png")
            from src.media_gen.image_builder import generate_video_frame
            video_frame = generate_video_frame(
                post_id=post["id"],
                reference=ref,
                badge_text="EVANGELHO DO DIA",
                hook_title=hook_title or homily,
                bg_image_path=scenes_dir / "scene_01.png" if (scenes_dir and (scenes_dir / "scene_01.png").is_file()) else None
            )
            vid_target = video_frame
            slides_for_video = [video_frame]
            narration_text = build_gospel_narration_text(
                reference=ref,
                text=post["formatted_text"],
                homily_reflection=homily,
                concise=True
            )
        elif source == "novena" or "novena" in ref.lower():
            from src.media_gen.carousel_builder import generate_prayer_carousel
            from src.media_gen.tts import build_novena_narration_text

            hook_title = post.get("hook_title") or ""
            slides = generate_prayer_carousel(
                post_id=post["id"],
                reference=ref,
                full_text=post["formatted_text"],
                hook_title=hook_title,
                visual_prompt=post.get("visual_prompt", ""),
                source="novena"
            )
            scenes_dir = slides[0].parent / "scenes" if slides else None
            v_scenes = [scenes_dir / f"scene_{i+1:02d}.png" for i in range(len(slides))] if (scenes_dir and scenes_dir.is_dir()) else slides
            img_path = (scenes_dir / "scene_01.png") if (scenes_dir and (scenes_dir / "scene_01.png").is_file()) else (slides[0] if slides else OUTPUT_IMAGES / f"post_{post['id']:04d}.png")
            from src.media_gen.image_builder import generate_video_frame
            video_frame = generate_video_frame(
                post_id=post["id"],
                reference=ref,
                badge_text="NOVENA",
                hook_title=hook_title,
                bg_image_path=scenes_dir / "scene_01.png" if (scenes_dir and (scenes_dir / "scene_01.png").is_file()) else None
            )
            vid_target = video_frame
            slides_for_video = [video_frame]
            narration_text = build_novena_narration_text(
                reference=ref,
                text=post["formatted_text"],
                hook_title=hook_title,
                concise=True
            )
        elif source in ("prayer", "psalm") or any(k in ref.lower() for k in ("salmo", "oração", "oracao")):
            from src.media_gen.carousel_builder import generate_prayer_carousel
            from src.media_gen.tts import build_prayer_narration_text

            hook_title = post.get("hook_title") or ""
            slides = generate_prayer_carousel(
                post_id=post["id"],
                reference=ref,
                full_text=post["formatted_text"],
                hook_title=hook_title,
                visual_prompt=post.get("visual_prompt", ""),
                source=source or "prayer"
            )
            scenes_dir = slides[0].parent / "scenes" if slides else None
            v_scenes = [scenes_dir / f"scene_{i+1:02d}.png" for i in range(len(slides))] if (scenes_dir and scenes_dir.is_dir()) else slides
            img_path = (scenes_dir / "scene_01.png") if (scenes_dir and (scenes_dir / "scene_01.png").is_file()) else (slides[0] if slides else OUTPUT_IMAGES / f"post_{post['id']:04d}.png")
            from src.media_gen.image_builder import generate_video_frame
            video_frame = generate_video_frame(
                post_id=post["id"],
                reference=ref,
                badge_text="ORAÇÃO & SALMO",
                hook_title=hook_title,
                bg_image_path=scenes_dir / "scene_01.png" if (scenes_dir and (scenes_dir / "scene_01.png").is_file()) else None
            )
            vid_target = video_frame
            slides_for_video = [video_frame]
            narration_text = build_prayer_narration_text(
                reference=ref,
                text=post["formatted_text"],
                hook_title=hook_title,
                concise=True
            )
        else:
            from src.collector.backgrounds import get_thematic_background
            bg_img = get_thematic_background(post.get("visual_prompt", ""), reference=ref)
            img_path = generate_post_image(
                post_id=post["id"],
                text=post["formatted_text"],
                reference=ref,
                badge_text="ORAÇÃO DA COMUNIDADE" if source == "community" else None,
                bg_image_path=bg_img
            )
            hook_title = post.get("hook_title") or ""
            from src.media_gen.image_builder import generate_verse_scenes
            verse_scenes = generate_verse_scenes(
                post["id"],
                ref,
                post["formatted_text"],
                post.get("visual_prompt", ""),
                hook_title=hook_title
            )
            from src.media_gen.image_builder import generate_video_frame
            video_frame = generate_video_frame(
                post_id=post["id"],
                reference=ref,
                badge_text="ORAÇÃO DA COMUNIDADE" if source == "community" else "VERSÍCULO DO DIA",
                hook_title=hook_title,
                bg_image_path=bg_img
            )
            vid_target = video_frame
            slides_for_video = [video_frame]
            from src.media_gen.tts import build_verse_narration_text
            narration_text = build_verse_narration_text(
                post["formatted_text"],
                reference=ref,
                hook_title=hook_title
            )

        vid_path_str = ""
        if make_video:
            vid_path = generate_video_from_image(vid_target, slides=slides_for_video, narration_text=narration_text)
            if vid_path:
                vid_path_str = str(vid_path)

        db.update_post_media(post["id"], str(img_path), vid_path_str)
        rendered_post_ids.append(post["id"])

    return rendered_post_ids

def step_dispatch(db: DBManager, platform: str | None = None, limit: int = 10, make_video: bool = True, post_id: int | None = None) -> int:
    log.info(f"=== [4/4] Distribuição e Fila (Limite de envio: {limit}, Post ID: {post_id or 'todos'}) ===")
    filter_plat = None if platform == "all" else platform
    if post_id:
        items = db.conn.execute(
            "SELECT * FROM queue WHERE post_id = ? AND status = 'pending' ORDER BY id ASC LIMIT 1",
            (post_id,)
        ).fetchall()
        items = [dict(r) for r in items]
        if not items:
            p_row = db.conn.execute("SELECT id FROM posts WHERE id = ? AND status = 'created'", (post_id,)).fetchone()
            if p_row:
                db.enqueue(post_id, platform or DEFAULT_PUBLISHER)
                items = [dict(r) for r in db.conn.execute(
                    "SELECT * FROM queue WHERE post_id = ? AND status = 'pending' LIMIT 1", (post_id,)
                ).fetchall()]
    else:
        items = db.get_pending_queue(platform=filter_plat, limit=limit)
        if not items:
            # Fallback de segurança: se a fila estiver vazia, verifica se há posts recentes com status 'created'
            pending_posts = db.conn.execute(
                "SELECT id FROM posts WHERE status = 'created' AND created_at >= datetime('now', '-1 day') ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            for p_row in pending_posts:
                db.enqueue(p_row[0], platform or DEFAULT_PUBLISHER)
            if pending_posts:
                items = db.get_pending_queue(platform=filter_plat, limit=limit)

    if not items:
        log.info("Fila vazia ou nenhum item pendente.")
        return 0

    dispatched = 0
    for q in items:
        cur = db.conn.execute("SELECT * FROM posts WHERE id = ?", (q["post_id"],))
        row = cur.fetchone()
        if not row:
            continue
        post = dict(row)

        # Ignora se já tiver sido postado anteriormente
        if post.get("status") == "published":
            log.info(f"Post #{post['id']} já publicado anteriormente. Ignorando reenvio.")
            db.mark_queue_sent(q["id"])
            continue

        # Verifica se o arquivo de mídia existe fisicamente no disco
        def _has_file(p: str | None, folder: Path) -> bool:
            if not p:
                return False
            if os.path.isfile(p):
                return True
            return (folder / Path(p).name).is_file()

        has_media = _has_file(post.get("video_path"), OUTPUT_VIDEOS) or _has_file(post.get("image_path"), OUTPUT_IMAGES)

        # Se não tiver mídia gerada ainda, renderiza agora antes de disparar
        if not has_media:
            log.info(f"Post #{post['id']} sem mídia em disco. Gerando agora...")
            cur_v = db.conn.execute("SELECT reference, source FROM verses WHERE id = ?", (post["verse_id"],))
            v_row = cur_v.fetchone()
            ref = v_row["reference"] if v_row else "Reflexão"
            source = v_row["source"] if v_row else ""

            if source == "saint" or (source not in ("novena", "prayer", "psalm") and any(k in ref.lower() for k in ("santo", "santa", "são", "sao", "senhora"))):
                from src.media_gen.carousel_builder import generate_saint_carousel, build_saint_narration_text
                saint_meta = get_saint_for_date()
                title_hook = saint_meta.get("quote", "") or post["formatted_text"].split("\n\n—")[0]
                story_text = saint_meta.get("history", "") or post["formatted_text"]
                prayer_text = saint_meta.get("prayer", "")
                slides = generate_saint_carousel(
                    post_id=post["id"],
                    saint_name=ref,
                    title_hook=title_hook,
                    story_text=story_text,
                    prayer_text=prayer_text
                )
                img_path = slides[0] if slides else generate_post_image(
                    post_id=post["id"],
                    text=post["formatted_text"],
                    reference=ref,
                    badge_text="MENSAGEM DO SANTO DO DIA",
                    bg_image_path=get_saint_image(ref)
                )
                vid_target = img_path
                slides_for_vid = slides
                narration_text = build_saint_narration_text(ref, title_hook, story_text, prayer_text)
            else:
                from src.media_gen.image_builder import generate_verse_scenes
                verse_scenes = generate_verse_scenes(post["id"], ref, post["formatted_text"], post.get("visual_prompt", ""))
                img_path = verse_scenes[0] if verse_scenes else generate_post_image(post_id=post["id"], text=post["formatted_text"], reference=ref)
                vid_target = verse_scenes[0] if verse_scenes else img_path
                slides_for_vid = verse_scenes
                from src.media_gen.tts import build_verse_narration_text
                narration_text = build_verse_narration_text(post["formatted_text"], reference=ref)

            vid_path_str = ""
            if make_video:
                vid_path = generate_video_from_image(vid_target, slides=slides_for_vid, narration_text=narration_text)
                if vid_path:
                    vid_path_str = str(vid_path)
            db.update_post_media(post["id"], str(img_path), vid_path_str)
            post["image_path"] = str(img_path)
            post["video_path"] = vid_path_str

        q_plat = (q.get("platform") or DEFAULT_PUBLISHER).lower()

        if q_plat in ("all", "multi", "todos"):
            log.info(f"Disparando Post #{post['id']} em modo Multi-Canal (Instagram + YouTube/Webhook + TikTok)...")
            ok_ig = publish_via_instagram_direct(post)
            ok_yt = publish_via_webhook(post)
            ok_tk = publish_via_tiktok_direct(post) if is_tiktok_authenticated() else False
            success = ok_ig or ok_yt or ok_tk
        elif q_plat in ("instagram", "instagram_direct", "instagrapi"):
            success = publish_via_instagram_direct(post)
        elif q_plat in ("tiktok", "tiktok_official"):
            from src.publisher.tiktok import publish_via_tiktok
            success = publish_via_tiktok(post)
        elif q_plat == "tiktok_direct":
            success = publish_via_tiktok_direct(post)
        elif q_plat == "webhook":
            success = publish_via_webhook(post)
        elif q_plat == "postproxy":
            success = publish_via_postproxy(post)
        elif q_plat in ("buffer", "buffer_api"):
            from src.publisher.buffer_api import publish_via_buffer
            success = publish_via_buffer(post)
        else:
            log.warning(f"Plataforma '{q_plat}' não reconhecida. Usando Webhook.")
            success = publish_via_webhook(post)

        if success:
            db.mark_queue_sent(q["id"])
            db.mark_post_published(post["id"])
            dispatched += 1
            log.info(f"Post #{post['id']} publicado e marcado como enviado.")
        else:
            db.mark_queue_failed(q["id"])

    return dispatched

def list_postproxy_profiles() -> None:
    publisher = PostproxyPublisher()
    try:
        profiles = publisher.listar_perfis()
        log.info(f"=== Perfis Conectados no Postproxy ({len(profiles)}) ===")
        for p in profiles:
            pid = p.get("id") or p.get("accountId")
            name = p.get("name") or p.get("username") or "Sem nome"
            plat = p.get("platform") or p.get("type") or "desconhecida"
            print(f"- [{str(plat).upper()}] ID: {pid} | Nome: {name}")
    except Exception as exc:
        log.error(f"Erro ao listar perfis do Postproxy: {exc}")

def run_saint_pipeline(
    target_date: date | None = None,
    publisher: str = DEFAULT_PUBLISHER,
    make_video: bool = True,
    dispatch: bool = False
) -> None:
    """Executa o pipeline completo para geração do Santo do Dia em 1 comando."""
    log.info("=== [PIPELINE ESPECIAL] Santo do Dia ===")
    db = DBManager(DB_PATH)
    try:
        t_date = target_date or (date.today() + timedelta(days=1) if datetime.now().hour >= 18 else date.today())

        # 1. Identifica o Santo canônico correto para a data
        from src.collector.saints import get_saint_for_date
        saint_info = get_saint_for_date(t_date)
        saint_name = saint_info.get("name") if saint_info else None

        # 2. Idempotência estrita: verifica se o santo correto já foi gerado ou enviado
        has_saint, s_post = db.has_saint_post_for_date(t_date, saint_name=saint_name)
        if has_saint and s_post:
            is_already_sent = (
                s_post.get("status") == "published"
                or s_post.get("is_sent")
                or s_post.get("queue_status") == "sent"
            )
            if is_already_sent:
                log.info(
                    f"Post do Santo correto ({saint_name or t_date.strftime('%d/%m')}) já foi publicado/enviado "
                    f"(Post #{s_post['id']}). Ignorando execução para evitar post duplicado."
                )
                return
            elif s_post.get("status") == "created":
                # Verifica se a fila já enviou
                q_sent = db.conn.execute(
                    "SELECT id FROM queue WHERE post_id = ? AND status = 'sent'",
                    (s_post['id'],)
                ).fetchone()
                if q_sent:
                    db.mark_post_published(s_post['id'])
                    log.info(
                        f"Post do Santo correto ({saint_name or t_date.strftime('%d/%m')}) já consta como enviado na fila "
                        f"(Post #{s_post['id']}). Ignorando execução."
                    )
                    return

                log.info(
                    f"Post do Santo correto ({saint_name or t_date.strftime('%d/%m')}) já estava gerado "
                    f"(Post #{s_post['id']}). Despachando agora para publicação..."
                )
                q_item = db.conn.execute("SELECT id FROM queue WHERE post_id = ? AND status = 'pending'", (s_post['id'],)).fetchone()
                if not q_item:
                    db.enqueue(s_post['id'], publisher)
                if dispatch:
                    step_dispatch(db, platform=publisher, limit=1, make_video=make_video, post_id=s_post['id'])
                return

        saint = collect_saint_of_day(db, target_date=t_date, force=True)
        if not saint or not saint.get("verse_id"):
            log.error(f"Falha ao identificar Santo do Dia para {t_date.strftime('%d/%m')}. Pipeline abortado sem gerar conteúdo substituto.")
            return

        verse_id = saint.get("verse_id")
        ref_label = f"{saint['name']} ({saint.get('date_str', '')})"
        log.info(f"Formatando post do Santo do Dia com IA: {ref_label}...")

        is_eve = (t_date > date.today())
        ai_data = format_saint_post(
            reference=ref_label,
            text=saint.get("quote", ""),
            saint_metadata=saint,
            is_eve=is_eve
        )

        post_id = db.insert_post(
            verse_id=verse_id,
            formatted_text=ai_data["formatted_text"],
            hashtags=ai_data["hashtags"],
            visual_prompt=ai_data["visual_prompt"],
            caption=ai_data.get("caption", "")
        )

        log.info(f"Gerando carrossel narrativo de 5 lâminas e cenas dinâmicas para {saint['name']}...")
        from src.media_gen.carousel_builder import generate_saint_carousel, build_saint_narration_text
        slides = generate_saint_carousel(
            post_id=post_id,
            saint_name=saint["name"],
            title_hook=saint.get("quote", ""),
            story_text=saint.get("history", ""),
            prayer_text=saint.get("prayer", "")
        )
        scenes_dir = slides[0].parent / "scenes" if slides else None
        v_scenes = [scenes_dir / f"scene_{i+1:02d}.png" for i in range(len(slides))] if (scenes_dir and scenes_dir.is_dir()) else slides
        img_path = (scenes_dir / "scene_01.png") if (scenes_dir and (scenes_dir / "scene_01.png").is_file()) else (
            slides[0] if slides else generate_post_image(
                post_id=post_id,
                text=ai_data["formatted_text"],
                reference=saint["name"],
                badge_text="MENSAGEM DO SANTO DO DIA",
                bg_image_path=get_saint_image(saint["name"], target_date=t_date)
            )
        )

        vid_path_str = ""
        # Santo do Dia gera vídeo sequencial com múltiplas pinturas sacras alternadas
        from src.collector.saints import get_saint_images
        from src.media_gen.image_builder import generate_saint_video_scenes
        saint_imgs = get_saint_images(saint["name"])
        saint_vscenes = generate_saint_video_scenes(
            post_id=post_id,
            saint_name=saint["name"],
            title_hook=saint.get("quote", ""),
            saint_images=saint_imgs,
            reference=ref_label
        )
        saint_narration = build_saint_narration_text(
            saint_name=saint["name"],
            title_hook=saint.get("quote", ""),
            story_text=saint.get("history", ""),
            prayer_text=saint.get("prayer", "")
        )
        if make_video:
            try:
                vid_path = generate_video_from_image(saint_vscenes[0], slides=saint_vscenes, narration_text=saint_narration, theme="saint")
                if vid_path:
                    vid_path_str = str(vid_path)
            except Exception as e_vid:
                log.warning(f"Vídeo de apoio do Santo do Dia não pôde ser gerado: {e_vid}")

        db.update_post_media(post_id, str(img_path), vid_path_str)
        target_platform = publisher or DEFAULT_PUBLISHER
        db.enqueue(post_id, target_platform)
        log.info(f"Post do Santo do Dia pronto na fila! (Post #{post_id} | Instagram: Carrossel | TikTok e YouTube: Vídeo MP4)")

        if dispatch:
            step_dispatch(db, platform=target_platform, limit=1, make_video=make_video, post_id=post_id)
    finally:
        db.close()


def run_novena_pipeline(
    target_date: date | None = None,
    publisher: str = DEFAULT_PUBLISHER,
    make_video: bool = True,
    dispatch: bool = False
) -> int | None:
    """Executa o pipeline completo para a Novena Litúrgica ativa."""
    log.info("=== [PIPELINE ESPECIAL] Novena Litúrgica ===")
    db = DBManager(DB_PATH)
    try:
        t_date = target_date or date.today()
        nov = collect_novena_of_day(db, target_date=t_date)
        if not nov:
            log.info(f"Nenhuma novena litúrgica ativa para {t_date.strftime('%d/%m')}.")
            return None

        post_ids = step_process(db, limit=1, publisher=publisher, source="novena")
        if not post_ids:
            return None
        pid = post_ids[0]
        step_media(db, limit=1, make_video=make_video, post_id=pid)
        if dispatch:
            step_dispatch(db, platform=publisher, limit=1, make_video=make_video, post_id=pid)
        log.info(f"Novena ({nov['saint_name']} - Dia {nov['novena_day']}) processada com sucesso! Post #{pid}")
        return pid
    finally:
        db.close()


def run_prayer_pipeline(
    source: str = "prayer",
    publisher: str = DEFAULT_PUBLISHER,
    make_video: bool = True,
    dispatch: bool = False
) -> int | None:
    """Executa o pipeline completo para Orações Clássicas ou Salmos."""
    log.info(f"=== [PIPELINE ESPECIAL] Oração Clássica / Salmo ({source}) ===")
    db = DBManager(DB_PATH)
    try:
        if source in ("psalm", "salmo", "salmos"):
            item = collect_psalm_of_day(db)
        else:
            item = collect_classic_prayers(db, count=1)
        if not item:
            log.warning("Nenhuma oração ou salmo disponível para coleta.")
            return None

        post_ids = step_process(db, limit=1, publisher=publisher, source="psalm" if source in ("psalm", "salmo", "salmos") else "prayer")
        if not post_ids:
            return None
        pid = post_ids[0]
        step_media(db, limit=1, make_video=make_video, post_id=pid)
        if dispatch:
            step_dispatch(db, platform=publisher, limit=1, make_video=make_video, post_id=pid)
        log.info(f"Oração/Salmo ({source}) processado com sucesso! Post #{pid}")
        return pid
    finally:
        db.close()

def run_carousel_pipeline(
    source: str = "gospel",
    target_date: date | None = None,
    publisher: str = DEFAULT_PUBLISHER
) -> bool:
    """Publica especificamente o Carrossel 4:5 das lâminas para o feed do Instagram."""
    log.info(f"=== [PIPELINE CARROSSEL 4:5] Origem: {source} ===")
    db = DBManager(DB_PATH)
    t_date = target_date or date.today()

    try:
        target_post = None
        if source == "gospel":
            cur = db.conn.execute(
                """SELECT p.*, v.reference, v.source as verse_source
                   FROM posts p
                   JOIN verses v ON p.verse_id = v.id
                   WHERE v.source = 'gospel' AND date(p.created_at) >= date('now', '-1 day')
                   ORDER BY p.id DESC LIMIT 1"""
            )
            r = cur.fetchone()
            if r:
                target_post = dict(r)
            else:
                run_pipeline(source="gospel", count=1, make_video=True, publisher=publisher, dispatch_limit=0)
                cur2 = db.conn.execute(
                    """SELECT p.*, v.reference, v.source as verse_source
                       FROM posts p
                       JOIN verses v ON p.verse_id = v.id
                       WHERE v.source = 'gospel'
                       ORDER BY p.id DESC LIMIT 1"""
                )
                r2 = cur2.fetchone()
                if r2:
                    target_post = dict(r2)

        elif source in ("saint", "santo"):
            # Busca o post do Santo do Dia (gerado na véspera ou hoje)
            cur = db.conn.execute(
                """SELECT p.*, v.reference, v.source as verse_source
                   FROM posts p
                   JOIN verses v ON p.verse_id = v.id
                   WHERE v.source = 'saint' AND date(p.created_at) >= date('now', '-2 days')
                   ORDER BY p.id DESC LIMIT 1"""
            )
            r = cur.fetchone()
            if r:
                target_post = dict(r)
            else:
                run_saint_pipeline(target_date=t_date, publisher=publisher, make_video=False, dispatch=False)
                cur2 = db.conn.execute(
                    """SELECT p.*, v.reference, v.source as verse_source
                       FROM posts p
                       JOIN verses v ON p.verse_id = v.id
                       WHERE v.source = 'saint'
                       ORDER BY p.id DESC LIMIT 1"""
                )
                r2 = cur2.fetchone()
                if r2:
                    target_post = dict(r2)

        elif source in ("prayer", "oracao", "oracoes"):
            cur = db.conn.execute(
                """SELECT p.*, v.reference, v.source as verse_source
                   FROM posts p JOIN verses v ON p.verse_id = v.id
                   WHERE v.source = 'prayer' AND date(p.created_at) >= date('now', '-1 day')
                   ORDER BY p.id DESC LIMIT 1"""
            )
            r = cur.fetchone()
            if r:
                target_post = dict(r)
            else:
                run_prayer_pipeline(source="prayer", publisher=publisher, make_video=False, dispatch=False)
                cur2 = db.conn.execute(
                    """SELECT p.*, v.reference, v.source as verse_source
                       FROM posts p JOIN verses v ON p.verse_id = v.id
                       WHERE v.source = 'prayer'
                       ORDER BY p.id DESC LIMIT 1"""
                )
                r2 = cur2.fetchone()
                if r2:
                    target_post = dict(r2)

        elif source in ("psalm", "salmo", "salmos"):
            cur = db.conn.execute(
                """SELECT p.*, v.reference, v.source as verse_source
                   FROM posts p JOIN verses v ON p.verse_id = v.id
                   WHERE v.source = 'psalm' AND date(p.created_at) >= date('now', '-1 day')
                   ORDER BY p.id DESC LIMIT 1"""
            )
            r = cur.fetchone()
            if r:
                target_post = dict(r)
            else:
                run_prayer_pipeline(source="psalm", publisher=publisher, make_video=False, dispatch=False)
                cur2 = db.conn.execute(
                    """SELECT p.*, v.reference, v.source as verse_source
                       FROM posts p JOIN verses v ON p.verse_id = v.id
                       WHERE v.source = 'psalm'
                       ORDER BY p.id DESC LIMIT 1"""
                )
                r2 = cur2.fetchone()
                if r2:
                    target_post = dict(r2)

        elif source in ("novena", "novenas"):
            cur = db.conn.execute(
                """SELECT p.*, v.reference, v.source as verse_source
                   FROM posts p JOIN verses v ON p.verse_id = v.id
                   WHERE v.source = 'novena' AND date(p.created_at) >= date('now', '-1 day')
                   ORDER BY p.id DESC LIMIT 1"""
            )
            r = cur.fetchone()
            if r:
                target_post = dict(r)
            else:
                run_novena_pipeline(publisher=publisher, make_video=False, dispatch=False)
                cur2 = db.conn.execute(
                    """SELECT p.*, v.reference, v.source as verse_source
                       FROM posts p JOIN verses v ON p.verse_id = v.id
                       WHERE v.source = 'novena'
                       ORDER BY p.id DESC LIMIT 1"""
                )
                r2 = cur2.fetchone()
                if r2:
                    target_post = dict(r2)

        if not target_post:
            log.warning(f"Nenhum post disponível para gerar carrossel da origem '{source}'.")
            return False

        # Verifica se as lâminas 4:5 do carrossel existem no disco
        img_p = target_post.get("image_path") or ""
        has_slides = False
        if img_p:
            p_img = Path(img_p)
            c_dir = p_img.parent if "carousel_" in p_img.parent.name.lower() else (p_img.parent.parent if "carousel_" in p_img.parent.parent.name.lower() else None)
            if c_dir:
                slides = [s for s in c_dir.iterdir() if s.is_file() and s.name.startswith("slide_")]
                if slides:
                    has_slides = True

        if not has_slides:
            log.info(f"Lâminas do carrossel não encontradas para o Post #{target_post['id']}. Gerando agora...")
            step_media(db, limit=1, make_video=False, post_id=target_post["id"])
            target_post = dict(db.conn.execute("SELECT * FROM posts WHERE id = ?", (target_post["id"],)).fetchone())

        from src.publisher.buffer_api import publish_via_buffer
        ok = publish_via_buffer(target_post, target_service="instagram,tiktok", prefer_carousel=True)
        if ok:
            log.info(f"✅ Carrossel do Post #{target_post['id']} publicado com sucesso (Instagram Feed + TikTok Photo Mode)!")
            return True
        else:
            log.error(f"❌ Falha ao publicar Carrossel do Post #{target_post['id']}.")
            return False
    except Exception as exc:
        log.error(f"Erro no run_carousel_pipeline: {exc}")
        return False
    finally:
        db.close()



def run_pipeline(
    source: str = "both",
    count: int = POSTS_PER_RUN,
    make_video: bool = True,
    publisher: str = DEFAULT_PUBLISHER,
    dispatch_limit: int | None = None,
    theme: str = "general"
) -> None:
    # Delegação para pipelines especializados
    if source in ("saint", "saints", "santo"):
        from datetime import timedelta
        target_saint_date = date.today() + timedelta(days=1)
        run_saint_pipeline(
            target_date=target_saint_date,
            publisher=publisher,
            make_video=make_video,
            dispatch=True
        )
        return
    elif source in ("novena", "novenas"):
        run_novena_pipeline(publisher=publisher, make_video=make_video, dispatch=True)
        return
    elif source in ("prayer", "prayers", "oracao", "oracoes", "psalm", "salmo"):
        run_prayer_pipeline(source=source, publisher=publisher, make_video=make_video, dispatch=True)
        return

    db = DBManager(DB_PATH)
    try:

        step_collect(db, source=source, count=count, theme=theme)
        step_process(db, limit=count, publisher=publisher, theme=theme, source=source if source != "both" else None)
        step_media(db, limit=count, make_video=make_video)
        limit_to_send = dispatch_limit if dispatch_limit is not None else count
        step_dispatch(db, platform=publisher, limit=limit_to_send, make_video=make_video)
        log.info(f"Pipeline concluído com sucesso! (Tema: {theme})")
    finally:
        db.close()

def check_and_catchup_missed_post(
    db: DBManager,
    source: str = "both",
    make_video: bool = True,
    publisher: str = "buffer",
    daily_count: int = 1,
) -> None:
    """
    Auto-recuperação pós-reinicialização / queda do daemon:
    Verifica se o post agendado para o período atual (manhã ou noite) já foi enviado hoje.
    Se não foi enviado e o horário já passou, executa o pipeline imediatamente.
    """
    now = datetime.now().astimezone()
    today = now.date()

    morning_start = datetime.combine(today, dtime(6, 30, 0)).astimezone()
    morning_end = datetime.combine(today, dtime(11, 59, 59)).astimezone()

    afternoon_start = datetime.combine(today, dtime(12, 0, 0)).astimezone()
    afternoon_end = datetime.combine(today, dtime(14, 59, 59)).astimezone()

    novena_start = datetime.combine(today, dtime(15, 0, 0)).astimezone()
    novena_end = datetime.combine(today, dtime(17, 59, 59)).astimezone()

    evening_start = datetime.combine(today, dtime(18, 0, 0)).astimezone()
    evening_end = datetime.combine(today, dtime(20, 29, 59)).astimezone()

    saint_eve_start = datetime.combine(today, dtime(20, 30, 0)).astimezone()
    saint_eve_end = datetime.combine(today, dtime(23, 59, 59)).astimezone()

    log.info(f"[SELF-HEALING] Verificando se posts do dia foram entregues ({now.strftime('%d/%m/%Y %H:%M:%S')})...")

    if now < morning_start:
        log.info("⏳ Madrugada / início da manhã. Aguardando primeiro agendamento matinal (06:30).")
        return

    if morning_start <= now <= morning_end:
        has_morning, post_info = db.has_post_published_between(morning_start, morning_end)
        if has_morning and post_info:
            pub_time = post_info.get("published_at", "")
            log.info(f"✅ [OK] Post matinal das 06:30 de hoje já foi publicado (Post #{post_info.get('id')} às {pub_time[:19]}).")
        else:
            log.warning("⚠️ [CATCH-UP] Horário matinal (06:30) já passou e NENHUM post foi enviado nesta janela!")
            log.info("🚀 Executando post de recuperação matinal (Bênção & Devocional) agora...")
            try:
                run_pipeline(
                    source="bible",
                    count=daily_count,
                    make_video=make_video,
                    publisher=publisher,
                    dispatch_limit=daily_count,
                    theme="morning",
                )
                log.info("✅ Post de recuperação matinal concluído com sucesso!")
            except Exception as exc:
                log.error(f"❌ Falha ao executar post de recuperação matinal: {exc}")
        return

    if afternoon_start <= now <= afternoon_end:
        has_midday, post_info = db.has_post_published_between(afternoon_start, afternoon_end)
        if has_midday and post_info:
            pub_time = post_info.get("published_at", "")
            log.info(f"✅ [OK] Post do meio-dia de hoje já foi publicado (Post #{post_info.get('id')} às {pub_time[:19]}).")
        else:
            log.warning("⚠️ [CATCH-UP] Horário do meio-dia (12:00) já passou e NENHUM post foi enviado nesta janela!")
            log.info("🚀 Executando post de recuperação do meio-dia (Palavra de Fé & Sabedoria) agora...")
            try:
                run_pipeline(
                    source="bible",
                    count=daily_count,
                    make_video=make_video,
                    publisher=publisher,
                    dispatch_limit=daily_count,
                    theme="midday",
                )
                log.info("✅ Post de recuperação do meio-dia concluído com sucesso!")
            except Exception as exc:
                log.error(f"❌ Falha ao executar post de recuperação do meio-dia: {exc}")
        return

    if novena_start <= now <= novena_end:
        from src.collector.saints import check_active_novena
        nov = check_active_novena(today)
        if nov:
            has_novena, post_info = db.has_post_published_between(novena_start, novena_end, source="novena")
            if has_novena and post_info:
                pub_time = post_info.get("published_at", "")
                log.info(f"✅ [OK] Post da Novena das 15:00 ({nov['saint_name']}) de hoje já foi publicado (Post #{post_info.get('id')} às {pub_time[:19]}).")
            else:
                log.warning(f"⚠️ [CATCH-UP] Horário da Novena (15:00 - {nov['saint_name']}) já passou e não foi enviado!")
                log.info("🚀 Executando post de recuperação da Novena agora...")
                try:
                    run_novena_pipeline(publisher=publisher, make_video=make_video, dispatch=True)
                    log.info("✅ Post de recuperação da Novena concluído com sucesso!")
                except Exception as exc:
                    log.error(f"❌ Falha ao executar post de recuperação da Novena: {exc}")
        else:
            log.info("ℹ️ Janela das 15:00: Nenhuma novena litúrgica ativa hoje.")
        return

    if evening_start <= now <= evening_end:
        has_evening, post_info = db.has_post_published_between(evening_start, evening_end)
        if has_evening and post_info:
            pub_time = post_info.get("published_at", "")
            log.info(f"✅ [OK] Post noturno das 18:00 de hoje já foi publicado (Post #{post_info.get('id')} às {pub_time[:19]}).")
        else:
            log.warning("⚠️ [CATCH-UP] Horário noturno (18:00) já passou e NENHUM post foi enviado nesta janela!")
            log.info("🚀 Executando post de recuperação noturno (Oração & Gratidão) agora...")
            try:
                run_pipeline(
                    source=source,
                    count=daily_count,
                    make_video=make_video,
                    publisher=publisher,
                    dispatch_limit=daily_count,
                    theme="evening",
                )
                log.info("✅ Post de recuperação noturno concluído com sucesso!")
            except Exception as exc:
                log.error(f"❌ Falha ao executar post de recuperação noturno: {exc}")
        return

    if now >= saint_eve_start:
        tomorrow = today + timedelta(days=1)
        from src.collector.saints import get_saint_for_date
        saint_info = get_saint_for_date(tomorrow)
        saint_name = saint_info.get("name") if saint_info else None

        has_saint, post_info = db.has_saint_post_for_date(tomorrow, saint_name=saint_name)
        if not (has_saint and post_info):
            has_saint, post_info = db.has_post_published_between(saint_eve_start, saint_eve_end, source="saint")

        is_already_sent = (
            has_saint and post_info and (
                post_info.get("status") == "published"
                or post_info.get("is_sent")
                or post_info.get("queue_status") == "sent"
            )
        )

        if is_already_sent:
            pub_time = post_info.get("published_at", "") or "enviado"
            log.info(f"✅ [OK] Post do Santo da véspera ({saint_name or tomorrow.strftime('%d/%m')}) já foi publicado/enviado (Post #{post_info.get('id')} às {pub_time[:19]}).")
        else:
            log.warning(f"⚠️ [CATCH-UP] Horário de véspera do Santo ({tomorrow.strftime('%d/%m')}) já passou e post não foi enviado!")
            log.info("🚀 Executando post de Santo do Dia (Carrossel & Vídeo) agora...")
            try:
                run_saint_pipeline(
                    target_date=tomorrow,
                    publisher=publisher,
                    make_video=make_video,
                    dispatch=True
                )
                log.info("✅ Post do Santo do Dia concluído com sucesso!")
            except Exception as exc:
                log.error(f"❌ Falha ao executar post do Santo do Dia: {exc}")
        return



def run_videoflow_cut(
    url: str,
    preset: str = "biblico",
    wait: bool = False,
    count: int = 3,
    publisher: str = DEFAULT_PUBLISHER,
    db: DBManager = None
) -> None:
    """Solicita corte inteligente de vídeo ao VideoFlow e opcionalmente importa para o banco."""
    from src.integrations.videoflow_client import VideoFlowClient
    client = VideoFlowClient()
    if not client.is_online():
        log.warning("⚠️ Serviço VideoFlow não respondeu em http://localhost:8000. Verifique se o backend do VideoFlow está ativo.")

    log.info(f"🎬 Solicitando cortes inteligentes para: {url} | Preset: {preset}")
    try:
        job = client.request_cuts(
            source_url=url,
            cut_mode="highlights",
            niche_preset=preset,
            max_clips=count,
            publish_mode="draft",
        )
        job_id = job.get("job_id")
        log.info(f"✅ Job registrado no VideoFlow! ID: {job_id}")

        if wait and db:
            log.info("⏳ Aguardando renderização do VideoFlow para importar clipes...")
            job_data = client.wait_for_job(job_id)
            post_ids = client.import_to_bible_reels(job_data, db)
            log.info(f"✨ Importação concluída! {len(post_ids)} vídeo(s) importados para o Bible-Reels: {post_ids}")
    except Exception as exc:
        log.error(f"❌ Falha ao solicitar cortes no VideoFlow: {exc}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Bible Reels Content Automation Engine")
    parser.add_argument("--all", action="store_true", help="Executa todo o pipeline")
    parser.add_argument("--collect", action="store_true", help="Executa apenas etapa de coleta")
    parser.add_argument("--process", action="store_true", help="Executa apenas etapa de processamento IA")
    parser.add_argument("--media", action="store_true", help="Executa apenas renderização de mídia")
    parser.add_argument("--dispatch", action="store_true", help="Dispara itens da fila de publicação")
    parser.add_argument("--source", choices=["bible", "quotes", "both", "saint", "gospel", "prayer", "psalm", "novena", "community"], default="both", help="Origem dos dados")
    parser.add_argument("--saint", action="store_true", help="Gera post completo do Santo do Dia (coleta, IA, arte e fila)")
    parser.add_argument("--novena", action="store_true", help="Gera post da Novena Litúrgica ativa (Dia 1 a 9)")
    parser.add_argument("--gospel", action="store_true", help="Gera post do Evangelho do Dia (liturgia diária oficial)")
    parser.add_argument("--prayer", action="store_true", help="Gera post de Grandes Orações e Salmos clássicos")
    parser.add_argument("--psalm", action="store_true", help="Gera post do Salmo Responsorial do Dia")
    parser.add_argument("--community", action="store_true", help="Gera post de Oração Comunitária com nomes de inscritos")
    parser.add_argument("--carousel", action="store_true", help="Dispara a versão Carrossel 4:5 para o feed do Instagram")
    parser.add_argument("--count", type=int, default=POSTS_PER_RUN, help="Quantidade de itens")
    parser.add_argument("--no-video", action="store_true", help="Desativa renderização de vídeo MP4 (gera apenas imagem estática)")
    parser.add_argument("--video", action="store_true", default=True, help="Gera vídeo MP4 dinâmico com narração (ativo por padrão)")
    parser.add_argument("--publisher", choices=["all", "tiktok", "instagram_direct", "tiktok_direct", "webhook", "postproxy", "buffer"], default=DEFAULT_PUBLISHER, help="Canal de publicação")
    parser.add_argument("--theme", choices=["morning", "midday", "evening", "general", "ansiedade", "cansaco", "medo", "familia", "esperanca", "cura", "sunday_blessing"], default="general", help="Tema ou dor emocional do post")
    parser.add_argument("--list-profiles", action="store_true", help="Lista perfis conectados no Postproxy")
    parser.add_argument("--analytics", action="store_true", help="Sincroniza métricas do Buffer e exibe painel de inteligência")
    parser.add_argument("--daemon", action="store_true", help="Executa em segundo plano com agendamento diário")
    parser.add_argument("--cut-url", type=str, default="", help="URL do YouTube ou vídeo para corte inteligente no VideoFlow")
    parser.add_argument("--cut-preset", type=str, default="biblico", help="Preset do VideoFlow (padrão: biblico)")
    parser.add_argument("--cut-wait", action="store_true", help="Aguarda conclusão do job no VideoFlow e importa vídeos gerados")

    args = parser.parse_args()
    make_video_eff = not args.no_video

    if args.list_profiles:
        list_postproxy_profiles()
        return

    db = DBManager(DB_PATH)

    if args.analytics:
        from src.analytics.metrics_collector import collect_buffer_metrics, print_analytics_report
        summary = collect_buffer_metrics(db)
        print_analytics_report(summary)
        db.close()
        return

    if args.daemon:
        import schedule
        daily_count = 1 if args.count == POSTS_PER_RUN else args.count
        log.info("Iniciando modo Daemon com agendamento completo de 8 horários diários (4 Vídeos + 3 Carrosséis Instagram/TikTok Photo Mode + 1 Novena):")
        log.info(f"  🌅 06:30 -> Vídeo 9:16: Devocional Matinal & Evangelho do Dia (Reels, TikTok, YouTube)")
        log.info(f"  🕊️ 08:30 -> Carrossel: Santo do Dia (Instagram Feed 4:5 + TikTok Photo Mode 9:16)")
        log.info(f"  📖 10:00 -> Carrossel: Evangelho do Dia (Instagram Feed 4:5 + TikTok Photo Mode 9:16)")
        log.info(f"  ☀️ 12:00 -> Vídeo 9:16: Palavra de Fé & Sabedoria (Reels, TikTok, YouTube)")
        log.info(f"  🔥 15:00 -> Vídeo / Post: Novena Litúrgica ativa (somente se houver novena)")
        log.info(f"  🌙 18:00 -> Vídeo 9:16: Salmo ou Oração de Proteção (Reels, TikTok, YouTube)")
        log.info(f"  🙏 19:15 -> Carrossel: Oração / Salmo das 18h (Instagram Feed 4:5 + TikTok Photo Mode 9:16)")
        log.info(f"  ✨ 20:30 -> Vídeo 9:16: Santo do Dia da Véspera (Reels, TikTok, YouTube)")

        # Agendamento das 06:30 (Matinal: Domingo = Bênção da Semana, Segunda a Sábado = Evangelho do Dia)
        def _morning_job():
            is_sunday = (datetime.now().weekday() == 6)
            if is_sunday:
                log.info("🌅 Especial de Domingo: Bênção da Semana e Consagração da Família")
                run_pipeline(source="bible", count=daily_count, make_video=make_video_eff, publisher=args.publisher, dispatch_limit=daily_count, theme="sunday_blessing")
            else:
                log.info("🌅 Matinal Oficial: Evangelho do Dia (Liturgia Diária CNBB)")
                run_pipeline(source="gospel", count=daily_count, make_video=make_video_eff, publisher=args.publisher, dispatch_limit=daily_count, theme="morning")

        schedule.every().day.at("06:30").do(_morning_job)

        # Agendamento das 08:30 (Carrossel 4:5 no Feed do Instagram: Santo do Dia)
        def _morning_saint_carousel_job():
            log.info("🕊️ [08:30] Publicando Carrossel 4:5 do Santo do Dia no feed do Instagram...")
            run_carousel_pipeline(source="saint", publisher=args.publisher)

        schedule.every().day.at("08:30").do(_morning_saint_carousel_job)

        # Agendamento das 10:00 (Carrossel 4:5 no Feed do Instagram: Aprofundamento do Evangelho)
        def _morning_gospel_carousel_job():
            log.info("📖 [10:00] Publicando Carrossel 4:5 do Evangelho do Dia no feed do Instagram...")
            run_carousel_pipeline(source="gospel", publisher=args.publisher)

        schedule.every().day.at("10:00").do(_morning_gospel_carousel_job)

        # Agendamento das 12:00 (Meio-dia: Palavra de Fé & Sabedoria Bíblica)
        schedule.every().day.at("12:00").do(
            run_pipeline,
            source="bible",
            count=daily_count,
            make_video=make_video_eff,
            publisher=args.publisher,
            dispatch_limit=daily_count,
            theme="midday"
        )

        # Agendamento das 15:00 (Novena Litúrgica Ativa: Vídeo / Post)
        def _novena_job():
            nov = check_active_novena(date.today())
            if nov:
                log.info(f"🔥 [15:00] Novena ativa detectada: {nov['saint_name']} - {nov['novena_day']}º Dia")
                run_novena_pipeline(publisher=args.publisher, make_video=make_video_eff, dispatch=True)
            else:
                log.info("🕊️ [15:00] Nenhuma novena litúrgica ativa para hoje.")

        schedule.every().day.at("15:00").do(_novena_job)

        # Agendamento das 18:00 (Noturno: Oração Clássica / Salmo de Proteção e Paz)
        def _evening_prayer_job():
            is_even = (datetime.now().day % 2 == 0)
            if is_even:
                log.info("🌙 Noturno Oficial: Salmo Responsorial do Dia (Liturgia CNBB)")
                run_prayer_pipeline(source="psalm", publisher=args.publisher, make_video=make_video_eff, dispatch=True)
            else:
                log.info("🌙 Noturno Oficial: Oração Clássica de Proteção (Salmo 91, São Bento, São Miguel)")
                run_prayer_pipeline(source="prayer", publisher=args.publisher, make_video=make_video_eff, dispatch=True)

        schedule.every().day.at("18:00").do(_evening_prayer_job)

        # Agendamento das 19:15 (Carrossel no Feed: Oração / Salmo independente das 18h)
        def _evening_carousel_job():
            is_even = (datetime.now().day % 2 == 0)
            # Alterna fonte para nunca repetir o tema das 18h (se 18h foi Oração, 19:15 é Salmo; se 18h foi Salmo, 19:15 é Oração)
            alt_source = "prayer" if is_even else "psalm"
            log.info(f"🙏 [19:15] Publicando Carrossel independente ({alt_source}) no feed...")
            run_carousel_pipeline(source=alt_source, publisher=args.publisher)

        schedule.every().day.at("19:15").do(_evening_carousel_job)

        # Agendamento das 20:30 (Véspera: Santo do Dia seguinte)
        def _saint_eve_job():
            tomorrow = date.today() + timedelta(days=1)
            log.info(f"✨ [20:30] Gerando e publicando Santo do Dia da véspera ({tomorrow.strftime('%d/%m')})...")
            run_saint_pipeline(
                target_date=tomorrow,
                publisher=args.publisher,
                make_video=make_video_eff,
                dispatch=True
            )

        schedule.every().day.at("20:30").do(_saint_eve_job)

        # Agendamento das 23:15 (Loop de Métricas & Analytics Noturno)
        def _analytics_job():
            try:
                log.info("📊 Sincronizando métricas de engajamento do Buffer...")
                from src.analytics.metrics_collector import collect_buffer_metrics, print_analytics_report
                summary = collect_buffer_metrics(db)
                print_analytics_report(summary)
            except Exception as e_an:
                log.warning(f"Falha na sincronização periódica de analytics: {e_an}")

        schedule.every().day.at("23:15").do(_analytics_job)

        # Executa verificação inicial de auto-recuperação (Catch-up)
        check_and_catchup_missed_post(
            db=db,
            source=args.source,
            make_video=make_video_eff,
            publisher=args.publisher,
            daily_count=daily_count,
        )

        while True:
            schedule.run_pending()
            time.sleep(30)

    if args.carousel:
        src = args.source if args.source in ("gospel", "prayer", "psalm", "saint", "novena") else "gospel"
        run_carousel_pipeline(source=src, publisher=args.publisher)
        return

    if args.saint:
        run_saint_pipeline(publisher=args.publisher, make_video=make_video_eff, dispatch=args.dispatch)
        return

    if args.novena:
        run_novena_pipeline(publisher=args.publisher, make_video=make_video_eff, dispatch=args.dispatch)
        return

    if args.psalm:
        run_prayer_pipeline(source="psalm", publisher=args.publisher, make_video=make_video_eff, dispatch=args.dispatch)
        return

    if args.prayer:
        run_prayer_pipeline(source="prayer", publisher=args.publisher, make_video=make_video_eff, dispatch=args.dispatch)
        return

    if args.community:
        run_pipeline(source="community", count=1, make_video=make_video_eff, publisher=args.publisher, theme="evening")
        return
    if args.cut_url:
        run_videoflow_cut(url=args.cut_url, preset=args.cut_preset, wait=args.cut_wait, count=args.count, publisher=args.publisher, db=db)
        db.close()
        return


    if args.all or len(sys.argv) == 1:
        run_pipeline(source=args.source, count=args.count, make_video=make_video_eff, publisher=args.publisher, theme=args.theme)
        return

    try:
        if args.collect:
            step_collect(db, source=args.source, count=args.count, theme=args.theme)
        if args.process:
            step_process(db, limit=args.count, publisher=args.publisher, theme=args.theme)
        if args.media:
            step_media(db, limit=args.count, make_video=make_video_eff)
        if args.dispatch:
            step_dispatch(db, platform=args.publisher, make_video=make_video_eff)
    finally:
        db.close()

if __name__ == "__main__":
    main()
