"""
scripts/rebuild_all_saint_carousels.py
--------------------------------------
Gera obrigatoriamente Carrossel completo (4 a 5 slides) e Vídeo multi-cena
para todos os posts de Santo do Dia cadastrados no banco de dados.
"""
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlite3
from config.settings import DB_PATH
from src.collector.saints import get_saint_for_date
from src.media_gen.carousel_builder import generate_saint_carousel, build_saint_narration_text
from src.media_gen.video_builder import generate_video_from_image
from src.utils.logger import get_logger

log = get_logger("rebuild_saint_carousels")

def rebuild_saints():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, p.formatted_text, v.reference, v.text as original_text
        FROM posts p
        JOIN verses v ON v.id = p.verse_id
        WHERE v.source = 'saint'
           OR v.reference LIKE '%Santo%'
           OR v.reference LIKE '%Santa%'
           OR v.reference LIKE '%Senhora%'
           OR v.reference LIKE '%Teresa%'
           OR v.reference LIKE '%Calisto%'
        ORDER BY p.id ASC
    """)
    rows = cur.fetchall()
    log.info(f"Reconstruindo Carrosséis para {len(rows)} posts de Santos...")

    for r in rows:
        post_id = r["id"]
        reference = r["reference"]
        raw_text = r["original_text"] or r["formatted_text"] or ""

        target_date = None
        date_match = re.search(r"\((\d{1,2})/(\d{1,2})\)", reference)
        if date_match:
            d_day, d_month = int(date_match.group(1)), int(date_match.group(2))
            target_date = date(date.today().year, d_month, d_day)

        clean_name = reference.split("(")[0].strip()
        saint_meta = get_saint_for_date(target_date) or {}

        log.info(f"Gerando carrossel de lâminas para Post #{post_id} ({clean_name})...")
        slides = generate_saint_carousel(
            post_id=post_id,
            saint_name=clean_name,
            title_hook=saint_meta.get("quote", "") or raw_text.split("\n\n—")[0],
            story_text=saint_meta.get("history", "") or raw_text,
            prayer_text=saint_meta.get("prayer", "")
        )

        if not slides:
            log.error(f"Post #{post_id}: falha ao gerar carrossel.")
            continue

        primary_img = slides[0]
        # Gera também o vídeo a partir das lâminas do carrossel com a narração completa
        saint_narration = build_saint_narration_text(
            saint_name=clean_name,
            title_hook=saint_meta.get("quote", "") or raw_text.split("\n\n—")[0],
            story_text=saint_meta.get("history", "") or raw_text,
            prayer_text=saint_meta.get("prayer", "")
        )
        vid_path_str = ""
        try:
            vid = generate_video_from_image(primary_img, slides=slides, narration_text=saint_narration, with_narration=True)
            if vid:
                vid_path_str = str(vid)
        except Exception as e_vid:
            log.warning(f"Vídeo de apoio para Post #{post_id} não renderizado: {e_vid}")

        cur.execute("""
            UPDATE posts
            SET image_path = ?, video_path = ?
            WHERE id = ?
        """, (str(primary_img), vid_path_str, post_id))
        conn.commit()
        log.info(f"Post #{post_id} atualizado com sucesso! Carrossel ({len(slides)} slides em {primary_img.parent.name}) + Vídeo ({Path(vid_path_str).name if vid_path_str else 'Nenhum'})")

    conn.close()
    log.info("Reconstrução de carrosséis de Santos concluída com sucesso!")

if __name__ == "__main__":
    rebuild_saints()
