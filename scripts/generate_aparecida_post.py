"""
scripts/generate_aparecida_post.py
-----------------------------------
Gera o post completo de Nossa Senhora Aparecida (12/10) com a imagem oficial canônica.
"""
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import DB_PATH
from src.collector.saints import collect_saint_of_day, get_saint_image
from src.media_gen.image_builder import generate_post_image
from src.media_gen.video_builder import generate_video_from_image
from src.processor.ai_formatter import format_saint_post
from src.processor.db_manager import DBManager
from src.utils.logger import get_logger

log = get_logger("gen_aparecida")


def main():
    db = DBManager(DB_PATH)
    target_date = date(2026, 10, 12)

    # 1. Coleta dados de Aparecida
    saint = collect_saint_of_day(db, target_date=target_date, force=True)
    ref_label = f"{saint['name']} ({saint.get('date_str', '')})"
    log.info(f"Santo: {ref_label} - {saint.get('title', '')}")

    # 2. Formata legenda e textos
    ai_data = format_saint_post(
        reference=ref_label,
        text=saint.get("quote", ""),
        saint_metadata=saint
    )

    # 3. Insere no banco
    post_id = db.insert_post(
        verse_id=saint["verse_id"],
        formatted_text=ai_data["formatted_text"],
        hashtags=ai_data["hashtags"],
        visual_prompt=ai_data["visual_prompt"],
        caption=ai_data.get("caption", "")
    )
    log.info(f"Post registrado no SQLite: #{post_id}")

    # 4. Busca imagem canônica oficial
    bg_img = get_saint_image(saint["name"], target_date=target_date)
    log.info(f"Imagem oficial utilizada: {bg_img}")

    # 5. Gera imagem 9:16
    img_path = generate_post_image(
        post_id=post_id,
        text=ai_data["formatted_text"],
        reference=saint["name"],
        badge_text="MENSAGEM DO SANTO DO DIA",
        bg_image_path=bg_img
    )
    log.info(f"Imagem gerada: {img_path} ({img_path.stat().st_size} bytes)")

    # 6. Renderiza vídeo vertical MP4 com áudio
    log.info("Renderizando vídeo MP4 vertical...")
    vid_path = generate_video_from_image(img_path, narration_text=ai_data["formatted_text"])
    vid_str = str(vid_path) if vid_path else ""
    log.info(f"Vídeo gerado: {vid_str}")

    db.update_post_media(post_id, str(img_path), vid_str)
    log.info(f"Post #{post_id} finalizado com sucesso!")


if __name__ == "__main__":
    main()
