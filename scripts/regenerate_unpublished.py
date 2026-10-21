"""
scripts/regenerate_unpublished.py
---------------------------------
Regera imagens/cenas e vídeos MP4 dinâmicos (1080x1920) para todos os posts
com status != 'published', aplicando:
- Passagem bíblica integral completa no centro (as palavras da Escritura)
- 3 fundos de alta resolução alternando suavemente a cada 5s
- Narração neural Edge-TTS + trilha ambiente suave
- Efeito Ken Burns com movimento suave contínuo
- Atualização imediata dos caminhos no banco de dados
"""
import os
import sys
from pathlib import Path

# Ajusta path para importar módulos do projeto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3
from config.settings import DB_PATH, OUTPUT_VIDEOS, ROOT_DIR
from src.media_gen.image_builder import generate_verse_scenes
from src.media_gen.video_builder import generate_video_from_image
from src.utils.logger import get_logger

log = get_logger("regenerate_unpublished")

def regenerate_all_unpublished():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, p.formatted_text, p.visual_prompt, p.image_path, p.video_path,
               v.reference, v.text as original_text, v.source as verse_source
        FROM posts p
        JOIN verses v ON v.id = p.verse_id
        WHERE p.status != 'published'
        ORDER BY p.id ASC
    """)
    rows = cur.fetchall()

    log.info(f"Iniciando regeração de {len(rows)} posts não publicados...")

    success_count = 0
    fail_count = 0

    for idx, r in enumerate(rows, start=1):
        post_id = r["id"]
        reference = r["reference"] or "Versículo Bíblico"
        raw_text = r["original_text"] or r["formatted_text"] or ""
        verse_source = r["verse_source"] or ""
        visual_prompt = r["visual_prompt"] or ""
        is_saint = verse_source == "saint" or any(s in reference.lower() for s in ("santo", "santa", "nossa senhora"))

        log.info(f"[{idx}/{len(rows)}] Processando Post #{post_id:04d} ({reference})...")

        try:
            if not is_saint:
                # ── Post de Versículo da Bíblia ────────────────────────────────
                # 1. Gera as 3 cenas com o versículo integral no centro
                scenes = generate_verse_scenes(
                    post_id=post_id,
                    reference=reference,
                    text=raw_text,
                    visual_prompt=visual_prompt
                )

                if not scenes:
                    log.error(f"Post #{post_id}: falha ao gerar cenas.")
                    fail_count += 1
                    continue

                primary_img = scenes[0]
                from src.media_gen.tts import build_verse_narration_text
                text_to_narrate = build_verse_narration_text(raw_text, reference=reference)

                # 2. Renderiza vídeo multi-cena MP4 com Ken Burns e Edge-TTS
                vid_path = generate_video_from_image(
                    image_path=primary_img,
                    slides=scenes,
                    narration_text=text_to_narrate,
                    with_narration=True
                )

                if vid_path and Path(vid_path).is_file():
                    cur.execute("""
                        UPDATE posts
                        SET image_path = ?, video_path = ?
                        WHERE id = ?
                    """, (str(primary_img), str(vid_path), post_id))
                    conn.commit()
                    log.info(f"Post #{post_id} atualizado com sucesso: {vid_path.name}")
                    success_count += 1
                else:
                    log.error(f"Post #{post_id}: vídeo não foi gerado.")
                    fail_count += 1

            else:
                # ── Post de Santo do Dia ──────────────────────────────────────
                from datetime import date
                import re
                from src.collector.saints import get_saint_for_date
                from src.media_gen.carousel_builder import generate_saint_carousel, build_saint_narration_text

                target_date = None
                date_match = re.search(r"\((\d{1,2})/(\d{1,2})\)", reference)
                if date_match:
                    d_day, d_month = int(date_match.group(1)), int(date_match.group(2))
                    target_date = date(date.today().year, d_month, d_day)

                clean_name = reference.split("(")[0].strip()
                saint_meta = get_saint_for_date(target_date) or {}
                title_hook = saint_meta.get("quote", "") or raw_text.split("\n\n—")[0]
                story_text = saint_meta.get("history", "") or raw_text
                prayer_text = saint_meta.get("prayer", "")

                # Gera SEMPRE o carrossel narrativo de lâminas para o Instagram
                slides = generate_saint_carousel(
                    post_id=post_id,
                    saint_name=clean_name,
                    title_hook=title_hook,
                    story_text=story_text,
                    prayer_text=prayer_text
                )

                if slides:
                    primary_img = slides[0]
                    # Gera vídeo vertical a partir das lâminas para TikTok e YouTube Shorts com narração completa
                    saint_narration = build_saint_narration_text(clean_name, title_hook, story_text, prayer_text)
                    vid_path = generate_video_from_image(
                        image_path=primary_img,
                        slides=slides,
                        narration_text=saint_narration,
                        with_narration=True
                    )
                    vid_path_str = str(vid_path) if vid_path else ""
                    cur.execute("""
                        UPDATE posts
                        SET image_path = ?, video_path = ?
                        WHERE id = ?
                    """, (str(primary_img), vid_path_str, post_id))
                    conn.commit()
                    log.info(f"Post de Santo #{post_id} ({clean_name}) atualizado com Carrossel ({len(slides)} slides) e Vídeo!")
                    success_count += 1
                else:
                    log.warning(f"Post de Santo #{post_id}: falha ao gerar carrossel.")
                    fail_count += 1

        except Exception as exc:
            log.exception(f"Erro ao regerar Post #{post_id}: {exc}")
            fail_count += 1

    conn.close()
    log.info(f"Regeração concluída! Sucessos: {success_count} | Falhas: {fail_count}")

if __name__ == "__main__":
    regenerate_all_unpublished()
