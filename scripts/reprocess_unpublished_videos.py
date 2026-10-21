import os
import sys
import sqlite3
import re
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import DB_PATH, OUTPUT_VIDEOS, OUTPUT_IMAGES
from src.media_gen.video_builder import generate_video_from_image
from src.processor.db_manager import DBManager
from src.utils.logger import get_logger

log = get_logger("reprocess")

def reprocess_all_unpublished():
    db = DBManager(DB_PATH)
    try:
        # Find all posts that are NOT published
        c = db.conn.cursor()
        c.execute("""
            SELECT p.id, p.status, p.created_at, p.published_at, v.reference, v.source, p.formatted_text, p.visual_prompt, p.video_path, p.image_path
            FROM posts p
            LEFT JOIN verses v ON v.id = p.verse_id
            WHERE p.status != 'published' OR p.published_at IS NULL OR p.published_at = ''
            ORDER BY p.id ASC
        """)
        cols = ['id', 'status', 'created_at', 'published_at', 'reference', 'source', 'formatted_text', 'visual_prompt', 'video_path', 'image_path']
        posts = [dict(zip(cols, r)) for r in c.fetchall()]
        
        log.info(f"Total de posts não publicados encontrados: {len(posts)}")
        if not posts:
            log.info("Nenhum post não publicado para reprocessar.")
            return

        for p in posts:
            p_id = p["id"]
            ref = p.get("reference") or f"Post #{p_id}"
            log.info(f"\n--- Reprocessando Post #{p_id} ({ref}) ---")
            
            # Find slides or images
            slides_for_video = []
            vid_target = None
            
            # Check if scenes exist
            img_path_str = p.get("image_path")
            if img_path_str:
                p_img = Path(img_path_str)
                if p_img.is_file():
                    vid_target = p_img
                # Check parent scenes/
                cand_dirs = [p_img.parent, p_img.parent / "scenes"]
                for c_dir in cand_dirs:
                    if c_dir.is_dir():
                        scenes = sorted([s for s in c_dir.glob("scene_*.png") if s.is_file()])
                        if len(scenes) > 1:
                            slides_for_video = scenes
                            vid_target = scenes[0]
                            break
                        slides = sorted([s for s in c_dir.glob("slide_*.png") if s.is_file()])
                        if len(slides) > 1:
                            slides_for_video = slides
                            vid_target = slides[0]
                            break

            # Fallback image search
            if not vid_target or not vid_target.is_file():
                for pat in [f"post_{p_id:04d}.png", f"post_{p_id}.png"]:
                    cand = OUTPUT_IMAGES / pat
                    if cand.is_file():
                        vid_target = cand
                        break

            if not vid_target or not vid_target.is_file():
                log.warning(f"Post #{p_id}: nenhuma imagem encontrada ({img_path_str}). Pulando.")
                continue

            # Build narration text
            is_saint = (p.get("source") == "saint") or any(k in (ref or "").lower() for k in ("santo", "santa", "são", "sao", "senhora"))
            formatted_text = p.get("formatted_text") or ""
            if is_saint:
                from src.media_gen.carousel_builder import build_saint_narration_text
                clean_name = ref.split("(")[0].strip()
                title_hook = formatted_text.split("\n\n—")[0]
                narration_text = build_saint_narration_text(clean_name, title_hook, formatted_text, "")
            else:
                from src.media_gen.tts import build_verse_narration_text
                narration_text = build_verse_narration_text(formatted_text, reference=ref)

            out_file = OUTPUT_VIDEOS / f"post_{p_id:04d}.mp4"
            log.info(f"Renderizando vídeo seguro com trilha clássica/royalty-free para: {out_file.name}")
            
            try:
                new_vid = generate_video_from_image(
                    vid_target,
                    slides=slides_for_video if slides_for_video else None,
                    output_path=out_file,
                    narration_text=narration_text
                )
                if new_vid and new_vid.is_file():
                    db.update_post_media(p_id, str(vid_target), str(new_vid))
                    log.info(f"✅ Post #{p_id} vídeo reprocessado com sucesso: {new_vid.name} ({new_vid.stat().st_size // 1024} KB)")
                else:
                    log.error(f"❌ Falha ao gerar vídeo para Post #{p_id}")
            except Exception as e:
                log.error(f"❌ Erro ao reprocessar Post #{p_id}: {e}")

    finally:
        db.close()

if __name__ == "__main__":
    reprocess_all_unpublished()
