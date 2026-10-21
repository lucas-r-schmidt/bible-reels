"""
src/media_gen/carousel_builder.py
---------------------------------
Renderiza carrosséis narrativos de alta conversão e retenção (Instagram 4:5 e TikTok):
- Lâminas sequenciais (1080x1350 formato padrão do feed ou 1080x1920 vertical)
- Distribuição de múltiplas imagens autênticas do santo através dos slides
- Slide 1: Gancho / Capa de impacto com arte principal e badge
- Slide 2-3: História / Contexto / Mensagem com pinturas históricas
- Slide 4: Oração do dia com detalhe sacro
- Slide 5: Card de bênção e CTA ("Salve e Compartilhe")
"""
from pathlib import Path
import re
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageOps

import random
import subprocess
from config.settings import ROOT_DIR, FONTS_PATH, AUDIO_PATH
from src.collector.saints import get_saint_images
from src.media_gen.image_builder import _get_font, _create_gradient_background
from src.media_gen.tts import generate_narration
from src.media_gen.video_builder import get_available_audio_tracks, _get_audio_duration
from src.utils.logger import get_logger

log = get_logger(__name__)

CAROUSEL_OUTPUT_DIR = ROOT_DIR / "output" / "carousels"


def generate_carousel_audio(
    post_dir: Path,
    narration_text: str | None = None,
    preferred_bg_music: Path | None = None
) -> Path | None:
    """
    Gera arquivo de áudio de alta qualidade (narração + música sacra de fundo)
    para acompanhar a visualização do Carrossel e para as lâminas.
    Salva 'carousel_audio.mp3' na pasta do carrossel.
    """
    out_audio = post_dir / "carousel_audio.mp3"
    
    # Se já existir e for recente, reaproveita
    if out_audio.is_file() and out_audio.stat().st_size > 2000:
        return out_audio

    tts_audio: Path | None = None
    if narration_text and narration_text.strip():
        tts_audio = post_dir / "tts_temp.mp3"
        ok_tts = generate_narration(narration_text.strip(), tts_audio)
        if not ok_tts or not tts_audio.is_file():
            tts_audio = None

    bg_music = preferred_bg_music
    if not bg_music or not Path(bg_music).is_file():
        tracks = get_available_audio_tracks()
        if tracks:
            bg_music = random.choice(tracks)
    if bg_music and Path(bg_music).is_file():
        log.info(f"Trilha de fundo do carrossel selecionada: {Path(bg_music).name}")

    # 1. Se tem narração e trilha de fundo, mixa suavemente
    if tts_audio and tts_audio.is_file() and bg_music and Path(bg_music).is_file():
        dur_vocal = _get_audio_duration(tts_audio)
        total_dur = max(8.0, dur_vocal + 1.0)
        fade_start = max(1.0, total_dur - 1.5)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(tts_audio),
            "-i", str(bg_music),
            "-filter_complex",
            f"[0:a]volume=1.0[vocal];"
            f"[1:a]volume=0.15,afade=t=out:st={fade_start:.1f}:d=1.5[bg];"
            f"[vocal][bg]amix=inputs=2:duration=longest:dropout_transition=2[aout]",
            "-map", "[aout]",
            "-c:a", "libmp3lame", "-b:a", "192k",
            "-t", f"{total_dur:.1f}",
            str(out_audio)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and out_audio.is_file():
            log.info(f"Áudio do carrossel gerado com sucesso (narração + trilha): {out_audio.name}")
            return out_audio

    # 2. Se tem apenas narração
    if tts_audio and tts_audio.is_file():
        try:
            tts_audio.replace(out_audio)
            return out_audio
        except Exception:
            return tts_audio

    # 3. Se tem apenas trilha de fundo sacra
    if bg_music and Path(bg_music).is_file():
        cmd = [
            "ffmpeg", "-y",
            "-i", str(bg_music),
            "-af", "volume=0.85,afade=t=out:st=38:d=2",
            "-c:a", "libmp3lame", "-b:a", "192k",
            "-t", "40",
            str(out_audio)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and out_audio.is_file():
            log.info(f"Trilha sacra do carrossel gerada com sucesso: {out_audio.name}")
            return out_audio

    return None


def build_saint_narration_text(
    saint_name: str,
    title_hook: str,
    story_text: str,
    prayer_text: str,
    with_cta: bool | None = None
) -> str:
    """
    Constrói a narração completa do Santo do Dia em sincronia com as lâminas do vídeo:
    1. Capa / Gancho (Nome do santo + frase/citação de impacto)
    2. História resumida (principais sentenças do testemunho)
    3. Oração devocional final com Amém
    4. Chamada de encerramento (CTA de oração, bênção, salvar e seguir)
    """
    from config.settings import ENABLE_AUDIO_CTA, CTA_SAINT_TEXT

    use_cta = ENABLE_AUDIO_CTA if with_cta is None else with_cta
    clean_name = saint_name.split("(")[0].strip()
    capa = f"Santo do Dia: {clean_name}. {title_hook.strip()}." if title_hook else f"Santo do Dia: {clean_name}."

    # Pega até 2 sentenças da história para manter o vídeo dinâmico e conciso
    story_clean = story_text.replace("\n", " ").strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", story_clean) if s.strip()]
    historia = " ".join(sentences[:2]) if sentences else story_clean

    oracao = prayer_text.strip()
    if oracao and not (oracao.endswith("Amém.") or oracao.endswith("Amém")):
        oracao = f"{oracao} Amém."

    parts = [capa, historia, oracao]
    if use_cta and CTA_SAINT_TEXT:
        parts.append("[PAUSE:1.5]")
        parts.append(CTA_SAINT_TEXT)

    full_text = " ".join([p for p in parts if p]).strip()
    full_text = re.sub(r"(?<=\b)(\d{3,4})\s*[-–—]\s*(\d{3,4})(?=\b)", r"\1 a \2", full_text)
    full_text = re.sub(r"[—–-]\s*", " ", full_text)
    full_text = re.sub(r"\s+", " ", full_text)
    return full_text


def generate_carousel_video_slides(
    slides_4_5: list[Path],
    audio_path: Path,
    out_dir: Path
) -> list[Path]:
    """
    Renderiza cada lâmina 4:5 como um micro-vídeo MP4 com áudio de fundo (1080x1350).
    Permite publicação no carrossel do Instagram e TikTok com som em cada slide.
    """
    if not audio_path or not audio_path.is_file():
        return []

    video_slides_dir = out_dir / "video_slides"
    video_slides_dir.mkdir(parents=True, exist_ok=True)

    n = len(slides_4_5)
    if n == 0:
        return []

    audio_dur = _get_audio_duration(audio_path)
    dur_per_slide = max(6.0, audio_dur / n) if audio_dur > 0 else 7.0

    rendered_video_slides = []
    for idx, slide_path in enumerate(slides_4_5):
        out_vslide = video_slides_dir / f"slide_{idx+1:02d}.mp4"
        start_time = idx * dur_per_slide
        # Corta a parte correspondente do áudio para o slide ou usa fade
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", f"{dur_per_slide:.2f}",
            "-i", str(slide_path),
            "-ss", f"{start_time:.2f}",
            "-t", f"{dur_per_slide:.2f}",
            "-i", str(audio_path),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(out_vslide)
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            if res.returncode == 0 and out_vslide.is_file():
                rendered_video_slides.append(out_vslide)
        except Exception as e:
            log.warning(f"Erro ao renderizar slide em vídeo {out_vslide.name}: {e}")

    if rendered_video_slides:
        log.info(f"{len(rendered_video_slides)} lâminas em vídeo 4:5 geradas com áudio em {video_slides_dir.name}")
    return rendered_video_slides


def generate_saint_carousel(
    post_id: int,
    saint_name: str,
    title_hook: str,
    story_text: str,
    prayer_text: str,
    bg_image_paths: list[Path] | Path | None = None,
    width: int = 1080,
    height: int = 1350,  # 4:5 clássico do feed do Instagram
    generate_video_scenes: bool = True,
    with_audio: bool = True,
) -> list[Path]:
    """
    Gera conjunto de lâminas para publicação em carrossel.
    Distribui diferentes imagens do santo (pinturas, milagres, santuário) entre os slides.
    Retorna lista de Paths ordenados dos slides gerados.
    """
    CAROUSEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    post_dir = CAROUSEL_OUTPUT_DIR / f"carousel_{post_id:04d}_{re.sub(r'[^a-zA-Z0-9]', '_', saint_name)[:30]}"

    post_dir.mkdir(parents=True, exist_ok=True)


    # 1. Prepara conteúdo dos slides
    slides_data = []

    # Slide 1: Capa / Gancho
    slides_data.append({
        "badge": "SANTO DO DIA",
        "title": saint_name.upper(),
        "body": title_hook or "Conheça a história e receba a poderosa bênção deste dia.",
        "footer": "Deslize para o lado ➔",
        "is_cover": True,
    })

    # Divide história em 1 ou 2 slides se for longa
    story_paragraphs = [p.strip() for p in story_text.split("\n\n") if p.strip()]
    if len(story_paragraphs) >= 2:
        part1 = story_paragraphs[0]
        part2 = " ".join(story_paragraphs[1:])
        slides_data.append({
            "badge": "HISTÓRIA & MILAGRES",
            "title": "A Jornada de Fé",
            "body": part1,
            "footer": "Continua no próximo slide ➔",
            "is_cover": False,
        })
        slides_data.append({
            "badge": "O EXEMPLO DE VIDA",
            "title": "O Testemunho",
            "body": part2,
            "footer": "Veja a oração a seguir ➔",
            "is_cover": False,
        })
    else:
        slides_data.append({
            "badge": "HISTÓRIA & LIÇÃO",
            "title": "A Jornada de Fé",
            "body": story_text,
            "footer": "Veja a oração a seguir ➔",
            "is_cover": False,
        })

    # Slide de Oração
    if prayer_text:
        slides_data.append({
            "badge": "ORAÇÃO PODEROSA",
            "title": f"Oração a {saint_name}",
            "body": prayer_text,
            "footer": "Digite AMÉM nos comentários",
            "is_cover": False,
        })

    # Slide Final: CTA / Bênção
    slides_data.append({
        "badge": "BÊNÇÃO DO DIA",
        "title": "Que a graça divina esteja com você",
        "body": "Que a intercessão deste Santo traga paz, saúde e proteção ao seu lar e à sua família neste dia.",
        "footer": "Salve este post e compartilhe com quem precisa",
        "is_cover": False,
    })

    total_slides = len(slides_data)

    # 2. Resolução do acervo de imagens para o santo
    images_pool: list[Path] = []
    if isinstance(bg_image_paths, (list, tuple)):
        images_pool = [Path(p) for p in bg_image_paths if Path(p).is_file()]
    elif isinstance(bg_image_paths, (Path, str)) and Path(bg_image_paths).is_file():
        images_pool = [Path(bg_image_paths)]

    # Se não foram fornecidas imagens explicitamente, busca imagens correspondentes ao santo
    if not images_pool:
        images_pool = get_saint_images(saint_name=saint_name, count=total_slides)

    log.info(f"Carrossel '{saint_name}': {len(images_pool)} imagens específicas disponíveis para {total_slides} slides.")

    generated_files = []
    generated_video_scenes = []

    # 3. Renderiza cada lâmina
    scenes_dir = post_dir / "scenes"
    if generate_video_scenes:
        scenes_dir.mkdir(parents=True, exist_ok=True)

    for idx, slide in enumerate(slides_data, start=1):
        current_img: Path | None = None
        if images_pool:
            current_img = images_pool[(idx - 1) % len(images_pool)]

        # --- A. Lâmina 4:5 Feed Instagram (1080x1350) ---
        if slide["is_cover"] and current_img and current_img.is_file():
            bg = Image.open(current_img).convert("RGBA")
            bg = ImageOps.fit(bg, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 150))
            img = Image.alpha_composite(bg, overlay)
        elif current_img and current_img.is_file():
            bg = Image.open(current_img).convert("RGBA")
            bg = ImageOps.fit(bg, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
            overlay = Image.new("RGBA", (width, height), (8, 12, 22, 205))
            img = Image.alpha_composite(bg, overlay)
        else:
            img = _create_gradient_background(width, height)

        draw = ImageDraw.Draw(img)

        # Indicador numérico no topo direito (ex: 1/5)
        font_counter = _get_font(size=26, bold=True)
        draw.text((width - 90, 70), f"{idx}/{total_slides}", font=font_counter, fill=(212, 175, 55, 230), anchor="mm")

        # Badge decorativo no topo
        font_badge = _get_font(size=28, bold=True)
        draw.text((width // 2, 130), slide["badge"], font=font_badge, fill=(212, 175, 55, 240), anchor="mm")
        draw.line([(width // 2 - 80, 160), (width // 2 + 80, 160)], fill=(212, 175, 55, 180), width=2)

        # Título do Slide
        title_font_size = 50 if slide["is_cover"] else 42
        font_title = _get_font(size=title_font_size, bold=True)
        title_wrapped = textwrap.wrap(slide["title"], width=26)
        title_y = 230
        for t_line in title_wrapped:
            draw.text((width // 2, title_y), t_line, font=font_title, fill=(255, 255, 255, 255), anchor="mm")
            title_y += 55

        # Corpo do Texto
        body_font_size = 42 if len(slide["body"]) < 200 else 34
        font_body = _get_font(size=body_font_size, bold=False)
        line_height = 56 if body_font_size == 42 else 48
        body_wrapped = textwrap.wrap(slide["body"], width=30 if body_font_size == 42 else 36)

        start_body_y = max(title_y + 60, (height - (len(body_wrapped) * line_height)) // 2)

        for b_line in body_wrapped:
            draw.text((width // 2 + 2, start_body_y + 2), b_line, font=font_body, fill=(0, 0, 0, 180), anchor="mm")
            draw.text((width // 2, start_body_y), b_line, font=font_body, fill=(240, 240, 245, 255), anchor="mm")
            start_body_y += line_height

        # Rodapé / Chamada (Safe Zone 4:5 e miniatura 1:1 da grade do perfil: Y <= 1200)
        font_footer = _get_font(size=26, bold=True)
        f_lines = textwrap.wrap(slide["footer"], width=30)
        y_f45 = 1175 if len(f_lines) > 1 else 1190
        for fl in f_lines:
            draw.text((width // 2, y_f45), fl, font=font_footer, fill=(212, 175, 55, 220), anchor="mm")
            y_f45 += 32

        out_path = post_dir / f"slide_{idx:02d}.png"
        img.convert("RGB").save(out_path, format="PNG", quality=95)
        generated_files.append(out_path)

        # --- B. Cena 9:16 Vertical para Vídeo (TikTok & YouTube Shorts - 1080x1920) ---
        if generate_video_scenes:
            v_w, v_h = 1080, 1920
            if slide["is_cover"] and current_img and current_img.is_file():
                v_bg = Image.open(current_img).convert("RGBA")
                v_bg = ImageOps.fit(v_bg, (v_w, v_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
                v_overlay = Image.new("RGBA", (v_w, v_h), (0, 0, 0, 160))
                v_img = Image.alpha_composite(v_bg, v_overlay)
            elif current_img and current_img.is_file():
                v_bg = Image.open(current_img).convert("RGBA")
                v_bg = ImageOps.fit(v_bg, (v_w, v_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
                v_overlay = Image.new("RGBA", (v_w, v_h), (8, 12, 22, 210))
                v_img = Image.alpha_composite(v_bg, v_overlay)
            else:
                v_img = _create_gradient_background(v_w, v_h)

            v_draw = ImageDraw.Draw(v_img)

            # Badge decorativo vertical (safe zone superior TikTok/Shorts: Y >= 280)
            font_v_badge = _get_font(size=28, bold=True)
            v_draw.text((v_w // 2, 300), slide["badge"], font=font_v_badge, fill=(212, 175, 55, 240), anchor="mm")
            v_draw.line([(v_w // 2 - 80, 330), (v_w // 2 + 80, 330)], fill=(212, 175, 55, 180), width=2)

            # Título do Slide vertical (safe zone: max width 780px, Y ~ 400)
            font_v_title = _get_font(size=46 if slide["is_cover"] else 38, bold=True)
            v_title_wrapped = textwrap.wrap(slide["title"], width=22)
            v_title_y = 390
            for t_line in v_title_wrapped:
                v_draw.text((v_w // 2, v_title_y), t_line, font=font_v_title, fill=(255, 255, 255, 255), anchor="mm")
                v_title_y += 54

            # Corpo do Texto vertical (safe zone: margins >= 140px, Y bounded between title and Y=1360)
            v_body_font_size = 38 if len(slide["body"]) < 160 else 32
            font_v_body = _get_font(size=v_body_font_size, bold=False)
            v_line_height = 54 if v_body_font_size == 38 else 46
            v_body_wrapped = textwrap.wrap(slide["body"], width=24 if v_body_font_size == 38 else 28)

            content_height = len(v_body_wrapped) * v_line_height
            v_start_body_y = max(v_title_y + 50, (1360 + v_title_y - content_height) // 2)
            for b_line in v_body_wrapped:
                v_draw.text((v_w // 2 + 2, v_start_body_y + 2), b_line, font=font_v_body, fill=(0, 0, 0, 190), anchor="mm")
                v_draw.text((v_w // 2, v_start_body_y), b_line, font=font_v_body, fill=(240, 240, 245, 255), anchor="mm")
                v_start_body_y += v_line_height

            # Rodapé decorativo vertical (Safe Zone inferior e lateral: margem >= 160px)
            if slide["is_cover"] or idx == total_slides:
                v_footer = "Siga para mais bênçãos 🙏" if slide["is_cover"] else "Amém! Deixe sua intenção\nnos comentários ✝️"
                font_v_footer = _get_font(size=25, bold=True)
                vf_lines = v_footer.split("\n")
                y_vf = 1365 if len(vf_lines) > 1 else 1380
                for vfl in vf_lines:
                    v_draw.text((v_w // 2, y_vf), vfl, font=font_v_footer, fill=(212, 175, 55, 225), anchor="mm")
                    y_vf += 34

            v_out_path = scenes_dir / f"scene_{idx:02d}.png"
            v_img.convert("RGB").save(v_out_path, format="PNG", quality=95)
            generated_video_scenes.append(v_out_path)
            if idx == 1:
                from config.settings import OUTPUT_IMAGES
                OUTPUT_IMAGES.mkdir(parents=True, exist_ok=True)
                v_img.convert("RGB").save(OUTPUT_IMAGES / f"post_{post_id:04d}.png", format="PNG", quality=95)

    # 4. Geração do áudio exclusivo do carrossel (narração completa + música sacra de fundo)
    if with_audio:
        narration_full = build_saint_narration_text(saint_name, title_hook, story_text, prayer_text)
        carousel_audio = generate_carousel_audio(post_dir, narration_text=narration_full)
        if carousel_audio and carousel_audio.is_file():
            # Gera também as versões em micro-vídeo MP4 para publicação com áudio ativo
            generate_carousel_video_slides(generated_files, carousel_audio, post_dir)

    log.info(f"Carrossel e Cenas de Vídeo de {saint_name} concluídos com sucesso: {len(generated_files)} slides 4:5 e {len(generated_video_scenes)} cenas 9:16 em {post_dir.name}")
    from config.settings import ENABLE_CAROUSEL
    if not ENABLE_CAROUSEL and generated_video_scenes:
        return generated_video_scenes
    return generated_files or generated_video_scenes

