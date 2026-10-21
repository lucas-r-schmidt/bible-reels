"""
scripts/generate_saint_tomorrow.py
----------------------------------
Gera o post do Santo de amanhã e adiciona diretamente à fila do Buffer (addToQueue).
"""
from datetime import date, timedelta
from pathlib import Path
import sys

# Garante que raiz está no sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import DB_PATH
from src.collector.saints import collect_saint_of_day, get_saint_image
from src.media_gen.image_builder import generate_post_image
from src.media_gen.video_builder import generate_video_from_image
from src.processor.ai_formatter import format_saint_post
from src.processor.db_manager import DBManager
from src.publisher.buffer_api import publish_via_buffer
from src.utils.logger import get_logger

log = get_logger("tomorrow_saint")


def main() -> None:
    db = DBManager(DB_PATH)
    tomorrow = date.today() + timedelta(days=1)
    log.info(f"=== Gerando Santo de Amanhã ({tomorrow.strftime('%d/%m/%Y')}) ===")

    # 1. Coleta santo de amanhã
    saint = collect_saint_of_day(db, target_date=tomorrow, force=True)
    ref_label = f"{saint['name']} ({saint.get('date_str', '')})"
    log.info(f"Santo identificado: {ref_label} - {saint.get('title', '')}")

    # 2. Formata com IA
    log.info("Formatando texto com biografia e oração via Gemini...")
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
    log.info(f"Post registrado no banco: #{post_id}")

    # 4. Gera Carrossel narrativo com múltiplas imagens para o Instagram
    log.info("Gerando carrossel narrativo para o Instagram...")
    from src.media_gen.carousel_builder import generate_saint_carousel
    slides = generate_saint_carousel(
        post_id=post_id,
        saint_name=saint["name"],
        title_hook=saint.get("quote", ""),
        story_text=saint.get("history", ""),
        prayer_text=saint.get("prayer", "")
    )
    bg_img = get_saint_image(saint["name"], target_date=tomorrow)
    img_path = slides[0] if slides else generate_post_image(
        post_id=post_id,
        text=ai_data["formatted_text"],
        reference=saint["name"],
        badge_text="MENSAGEM DO SANTO DO DIA",
        bg_image_path=bg_img
    )
    log.info(f"Carrossel pronto: {len(slides) if slides else 1} lâminas geradas para o Instagram.")

    # 5. Renderiza vídeo MP4 dinâmico (Ken Burns + Voz Neural) para TikTok e YouTube
    log.info("Renderizando vídeo MP4 vertical dinâmico para TikTok e YouTube...")
    vid_path = generate_video_from_image(img_path, narration_text=ai_data["formatted_text"])
    vid_str = str(vid_path) if vid_path else ""

    if not vid_path or not vid_path.is_file():
        log.error("Geração de vídeo dinâmico falhou. Abortando envio para proteger o canal contra posts sem engajamento.")
        return

    db.update_post_media(post_id, str(img_path), vid_str)
    db.enqueue(post_id, "buffer")

    # 6. Envia para o Buffer com agendamento pontual sincronizado (Instagram, TikTok e YouTube)
    schedule_hour = 6
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        schedule_hour = int(sys.argv[1])
    due_at = f"{tomorrow.isoformat()}T{schedule_hour:02d}:00:00-03:00"

    log.info(f"Agendando publicação no Buffer sincronizada para {tomorrow.strftime('%d/%m/%Y')} às {schedule_hour:02d}:00...")
    post_row = db.conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    post_dict = dict(post_row)
    post_dict["reference"] = ref_label

    success = publish_via_buffer(post_dict, due_at=due_at)
    if success:
        db.mark_post_published(post_id)
        q_row = db.conn.execute("SELECT id FROM queue WHERE post_id = ?", (post_id,)).fetchone()
        if q_row:
            db.mark_queue_sent(q_row["id"])
        log.info(f"Post de {saint['name']} agendado com sucesso no Buffer para {schedule_hour:02d}:00 (Instagram: Carrossel, TikTok/YT: Vídeo)!")
    else:
        log.error("Falha ao agendar no Buffer.")


if __name__ == "__main__":
    main()
