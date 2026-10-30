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

    # Captura a narrativa completa da história (alvo de ~110 a 140 palavras) para garantir
    # profundidade e duração no formato de vídeo longo (>60s a 80s) para monetização e devoção
    story_clean = story_text.replace("\n", " ").strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", story_clean) if s.strip()]
    chosen_sentences = []
    w_count = 0
    for s in sentences:
        chosen_sentences.append(s)
        w_count += len(s.split())
        if w_count >= 120 and len(chosen_sentences) >= 4:
            break
    historia = " ".join(chosen_sentences) if chosen_sentences else story_clean

    oracao = prayer_text.strip()
    if oracao and not (oracao.endswith("Amém.") or oracao.endswith("Amém")):
        oracao = f"{oracao} Amém."

    parts = [capa, historia, oracao]
    if use_cta and CTA_SAINT_TEXT:
        parts.append("[PAUSE:1.5]")
        parts.append(CTA_SAINT_TEXT)

    full_text = " ".join([p for p in parts if p]).strip()
    full_text = full_text.replace("\u2011", " ")
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
        "footer": "Deslize para o lado >>",
        "is_cover": True,
    })

    # Divide a história em blocos de até ~170 caracteres para nunca sobrecarregar uma lâmina
    clean_story = story_text.replace("\u2011", "-").strip()
    paragraphs = [p.strip() for p in clean_story.split("\n\n") if p.strip()]
    story_chunks: list[str] = []
    for p in paragraphs:
        if len(p) <= 170:
            story_chunks.append(p)
        else:
            sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", p) if s.strip()]
            curr_chunk = ""
            for s in sentences:
                if not curr_chunk:
                    curr_chunk = s
                elif len(curr_chunk) + len(s) + 1 <= 170:
                    curr_chunk += " " + s
                else:
                    story_chunks.append(curr_chunk)
                    curr_chunk = s
            if curr_chunk:
                story_chunks.append(curr_chunk)

    # Limita lâminas de história entre 2 e 3 para ritmo dinâmico no carrossel
    if len(story_chunks) > 3:
        story_chunks = [story_chunks[0], story_chunks[1], " ".join(story_chunks[2:])]
    elif not story_chunks and clean_story:
        story_chunks = [clean_story]

    story_badges = ["HISTÓRIA & VOCAÇÃO", "O TESTEMUNHO", "DEFESA DA FÉ"]
    story_titles = ["A Jornada de Fé", "O Chamado de Deus", "O Legado Sagrado"]

    for s_idx, chunk in enumerate(story_chunks):
        is_last_story = (s_idx == len(story_chunks) - 1)
        s_badge = story_badges[s_idx % len(story_badges)]
        s_title = story_titles[s_idx % len(story_titles)]
        s_footer = "Veja a oração a seguir >>" if is_last_story else "Continua no próximo slide >>"
        slides_data.append({
            "badge": s_badge,
            "title": s_title,
            "body": chunk,
            "footer": s_footer,
            "is_cover": False,
        })

    # Slide de Oração
    if prayer_text:
        slides_data.append({
            "badge": "ORAÇÃO PODEROSA",
            "title": f"Oração a {saint_name}",
            "body": prayer_text.replace("\u2011", "-").strip(),
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
        title_font_size = 50 if slide["is_cover"] else 40
        font_title = _get_font(size=title_font_size, bold=True)
        title_wrapped = textwrap.wrap(slide["title"], width=26)
        title_y = 230
        for t_line in title_wrapped:
            draw.text((width // 2, title_y), t_line, font=font_title, fill=(255, 255, 255, 255), anchor="mm")
            title_y += 50

        # Corpo do Texto - Auto-fit inteligente de tipografia
        body_clean = slide["body"].replace("\u2011", "-").strip()
        body_len = len(body_clean)
        if body_len <= 110:
            body_font_size = 40
            wrap_chars = 34
            line_height = 58
        elif body_len <= 180:
            body_font_size = 36
            wrap_chars = 38
            line_height = 52
        elif body_len <= 260:
            body_font_size = 32
            wrap_chars = 42
            line_height = 46
        else:
            body_font_size = 28
            wrap_chars = 46
            line_height = 42

        font_body = _get_font(size=body_font_size, bold=False)
        body_wrapped = textwrap.wrap(body_clean, width=wrap_chars)

        total_text_height = len(body_wrapped) * line_height
        available_top = title_y + 40
        available_bottom = 1140
        start_body_y = available_top + max(20, (available_bottom - available_top - total_text_height) // 2)

        for b_line in body_wrapped:
            draw.text((width // 2 + 2, start_body_y + 2), b_line, font=font_body, fill=(0, 0, 0, 190), anchor="mm")
            draw.text((width // 2, start_body_y), b_line, font=font_body, fill=(240, 240, 245, 255), anchor="mm")
            start_body_y += line_height

        # Rodapé / Chamada (Safe Zone 4:5 e miniatura 1:1 da grade do perfil: Y <= 1200)
        font_footer = _get_font(size=25, bold=True)
        f_lines = textwrap.wrap(slide["footer"], width=32)
        y_f45 = 1180 if len(f_lines) > 1 else 1195
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

            # Título do Slide vertical
            font_v_title = _get_font(size=44 if slide["is_cover"] else 38, bold=True)
            v_title_wrapped = textwrap.wrap(slide["title"], width=24)
            v_title_y = 390
            for t_line in v_title_wrapped:
                v_draw.text((v_w // 2, v_title_y), t_line, font=font_v_title, fill=(255, 255, 255, 255), anchor="mm")
                v_title_y += 50

            # Corpo do Texto vertical - Auto-fit inteligente de tipografia
            v_body_clean = slide["body"].replace("\u2011", "-").strip()
            v_body_len = len(v_body_clean)
            if v_body_len <= 110:
                v_body_font_size = 38
                v_wrap_chars = 28
                v_line_height = 56
            elif v_body_len <= 180:
                v_body_font_size = 34
                v_wrap_chars = 32
                v_line_height = 50
            elif v_body_len <= 260:
                v_body_font_size = 30
                v_wrap_chars = 36
                v_line_height = 46
            else:
                v_body_font_size = 27
                v_wrap_chars = 40
                v_line_height = 42

            font_v_body = _get_font(size=v_body_font_size, bold=False)
            v_body_wrapped = textwrap.wrap(v_body_clean, width=v_wrap_chars)

            v_content_height = len(v_body_wrapped) * v_line_height
            v_avail_top = v_title_y + 40
            v_avail_bottom = 1350
            v_start_body_y = v_avail_top + max(20, (v_avail_bottom - v_avail_top - v_content_height) // 2)

            for b_line in v_body_wrapped:
                v_draw.text((v_w // 2 + 2, v_start_body_y + 2), b_line, font=font_v_body, fill=(0, 0, 0, 200), anchor="mm")
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


def generate_gospel_carousel(
    post_id: int,
    reference: str,
    full_text: str,
    key_passage: str = "",
    homily_reflection: str = "",
    hook_title: str = "",
    visual_prompt: str = "",
    width: int = 1080,
    height: int = 1350,
    generate_video_scenes: bool = True,
    with_audio: bool = True,
) -> list[Path]:
    """
    Renderiza Carrossel e Cenas de Vídeo 9:16 dedicados para o Evangelho do Dia:
    - 5 Lâminas estruturadas:
      1. Capa / Proclamação (Badge solene + Gancho magnético + Referência bíblica limpa)
      2. Palavra do Senhor - Parte 1 (Versículo-chave central legível, fonte grande)
      3. Palavra do Senhor - Parte 2 (Conclusão do ensinamento bíblico)
      4. Reflexão Pastoral / Homilia (Aplicação prática para a vida)
      5. Bênção & CTA ("Deixe seu Amém e compartilhe")
    - Cada cena recebe fundo temático sacro diferente (altar, bíblia, raios de luz, paisagem bíblica)
    - Gera cenas 9:16 em 'scenes/scene_*.png' para montagem de vídeo dinâmico para Reels/Shorts/TikTok.
    """
    from src.collector.backgrounds import get_thematic_background
    from src.media_gen.tts import build_gospel_narration_text

    CAROUSEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    post_dir = CAROUSEL_OUTPUT_DIR / f"carousel_{post_id:04d}_evangelho"
    post_dir.mkdir(parents=True, exist_ok=True)

    # Limpa referência e detecta evangelista
    m_inner = re.search(r"\(([^)]+)\)", reference)
    clean_ref = m_inner.group(1).strip() if m_inner else reference.strip()
    clean_ref = re.sub(r"\s*-\s*\d{1,2}/\d{1,2}", "", clean_ref).strip()

    ref_low = clean_ref.lower()
    evangelist = "São Lucas"
    if "lc" in ref_low or "lucas" in ref_low:
        evangelist = "São Lucas"
    elif "mc" in ref_low or "marcos" in ref_low:
        evangelist = "São Marcos"
    elif "jo" in ref_low or "joão" in ref_low or "joao" in ref_low:
        evangelist = "São João"
    elif "mt" in ref_low or "mateus" in ref_low:
        evangelist = "São Mateus"

    # Segmenta texto para os slides da Palavra
    raw_passage = (key_passage or full_text).strip()
    raw_passage = re.sub(r"(?<=\s)\d+\s*(?=[\"“«A-ZÀ-Ú])", "", raw_passage)
    raw_passage = re.sub(r"^[\s\"“«]*\d+\s*[\"“«]?", "", raw_passage).strip()
    if raw_passage.endswith(f"— {clean_ref}"):
        raw_passage = raw_passage[: -len(f"— {clean_ref}")].strip()

    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", raw_passage) if s.strip()]
    if len(sentences) >= 2:
        mid = max(1, len(sentences) // 2)
        part1 = " ".join(sentences[:mid])
        part2 = " ".join(sentences[mid:])
    elif len(raw_passage) > 180 and "," in raw_passage:
        commas = [m.start() for m in re.finditer(r",", raw_passage)]
        mid_target = len(raw_passage) // 2
        best_comma = min(commas, key=lambda c: abs(c - mid_target))
        part1 = raw_passage[: best_comma + 1].strip()
        part2 = raw_passage[best_comma + 1 :].strip()
    else:
        part1 = raw_passage
        part2 = ""

    title_h = (hook_title or f"O EVANGELHO DE HOJE").upper()

    slides_data = [
        {
            "badge": "EVANGELHO DO DIA",
            "title": title_h,
            "body": f"Proclamação do Evangelho de Jesus Cristo segundo {evangelist}.\n\n📖 {clean_ref}",
            "footer": "Deslize para ler a Palavra ➔",
            "prompt": f"Sacred golden altar with Holy Bible open, celestial sunbeams, ancient reverent church atmosphere, {visual_prompt}",
            "is_cover": True,
        },
        {
            "badge": "A PALAVRA DO SENHOR",
            "title": "O Ensinamento de Jesus",
            "body": f'"{part1}"' if not part1.startswith('"') else part1,
            "footer": "Continua no próximo slide ➔" if part2 else f"— {clean_ref}",
            "prompt": "Jesus Christ teaching disciples with divine grace and love, biblical sacred atmosphere, warm golden light",
            "is_cover": False,
        },
    ]

    if part2:
        slides_data.append({
            "badge": "MENSAGEM SAGRADA",
            "title": "A Voz do Evangelho",
            "body": f'"{part2}"' if not part2.startswith('"') else part2,
            "footer": f"— {clean_ref}",
            "prompt": "Radiant celestial sunbeams shining over biblical landscape at dawn, holy atmosphere",
            "is_cover": False,
        })

    # Homilia / Reflexão pastoral
    reflec_text = homily_reflection.strip() if homily_reflection else "Que a mensagem de Cristo ilumine as suas escolhas e fortaleça sua fé ao longo deste dia."
    slides_data.append({
        "badge": "REFLEXÃO DO DIA",
        "title": "Para sua Vida Hoje",
        "body": reflec_text,
        "footer": "Veja a bênção a seguir ➔",
        "prompt": "Peaceful morning dawn over tranquil lake and majestic mountains, warm sunbeams of hope",
        "is_cover": False,
    })

    # Bênção e Chamada à Ação
    slides_data.append({
        "badge": "BÊNÇÃO & PAZ",
        "title": "Receba Esta Palavra",
        "body": "Que a Palavra de Cristo habite ricamente em seu coração, guardando sua casa e abençoando toda a sua família.",
        "footer": "Escreva 'Amém' 🙏 Compartilhe a Boa Nova",
        "prompt": "Holy dove of peace with gentle divine golden light, blessings falling softly, sacred tranquility",
        "is_cover": False,
    })

    total_slides = len(slides_data)
    generated_files: list[Path] = []
    generated_video_scenes: list[Path] = []

    scenes_dir = post_dir / "scenes"
    if generate_video_scenes:
        scenes_dir.mkdir(parents=True, exist_ok=True)

    for idx, slide in enumerate(slides_data, start=1):
        bg_p = get_thematic_background(slide["prompt"], reference=f"gospel_{post_id}_{idx}")
        current_img = bg_p if (bg_p and bg_p.is_file()) else None

        # --- A. Lâmina 4:5 clássica (1080x1350) para Carrossel do Feed ---
        if current_img:
            bg = Image.open(current_img).convert("RGBA")
            bg = ImageOps.fit(bg, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 165))
            img = Image.alpha_composite(bg, overlay)
        else:
            img = _create_gradient_background(width, height)

        draw = ImageDraw.Draw(img)

        # Badge decorativo
        font_badge = _get_font(size=26, bold=True)
        draw.text((width // 2, 175), slide["badge"], font=font_badge, fill=(212, 175, 55, 230), anchor="mm")
        draw.line([(width // 2 - 80, 205), (width // 2 + 80, 205)], fill=(212, 175, 55, 180), width=2)

        # Título
        font_title = _get_font(size=40 if slide["is_cover"] else 36, bold=True)
        t_lines = textwrap.wrap(slide["title"], width=24)
        title_y = 250
        for tl in t_lines:
            draw.text((width // 2, title_y), tl, font=font_title, fill=(255, 255, 255, 255), anchor="mm")
            title_y += 50

        # Corpo
        b_font_sz = 38 if len(slide["body"]) < 140 else 32
        font_b = _get_font(size=b_font_sz, bold=False)
        lh = 52 if b_font_sz == 38 else 44
        b_wrapped = textwrap.wrap(slide["body"], width=28 if b_font_sz == 38 else 32)
        start_by = max(title_y + 40, (height - (len(b_wrapped) * lh)) // 2)

        for bl in b_wrapped:
            draw.text((width // 2 + 2, start_by + 2), bl, font=font_b, fill=(0, 0, 0, 190), anchor="mm")
            draw.text((width // 2, start_by), bl, font=font_b, fill=(240, 240, 245, 255), anchor="mm")
            start_by += lh

        # Rodapé
        font_foot = _get_font(size=25, bold=True)
        f_lines = textwrap.wrap(slide["footer"], width=30)
        yf45 = 1175 if len(f_lines) > 1 else 1190
        for fl in f_lines:
            draw.text((width // 2, yf45), fl, font=font_foot, fill=(212, 175, 55, 220), anchor="mm")
            yf45 += 32

        out_slide_path = post_dir / f"slide_{idx:02d}.png"
        img.convert("RGB").save(out_slide_path, format="PNG", quality=95)
        generated_files.append(out_slide_path)

        # --- B. Cena 9:16 Vertical para Vídeo (TikTok, Reels, Shorts - 1080x1920) ---
        if generate_video_scenes:
            v_w, v_h = 1080, 1920
            if current_img:
                v_bg = Image.open(current_img).convert("RGBA")
                v_bg = ImageOps.fit(v_bg, (v_w, v_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
                v_overlay = Image.new("RGBA", (v_w, v_h), (8, 12, 22, 195))
                v_img = Image.alpha_composite(v_bg, v_overlay)
            else:
                v_img = _create_gradient_background(v_w, v_h)

            v_draw = ImageDraw.Draw(v_img)

            # Badge superior (Safe Zone Y=300)
            font_v_badge = _get_font(size=28, bold=True)
            v_draw.text((v_w // 2, 300), slide["badge"], font=font_v_badge, fill=(212, 175, 55, 240), anchor="mm")
            v_draw.line([(v_w // 2 - 80, 330), (v_w // 2 + 80, 330)], fill=(212, 175, 55, 180), width=2)

            # Título (Safe Zone Y=390)
            font_v_title = _get_font(size=44 if slide["is_cover"] else 38, bold=True)
            vt_lines = textwrap.wrap(slide["title"], width=22)
            v_ty = 390
            for tl in vt_lines:
                v_draw.text((v_w // 2, v_ty), tl, font=font_v_title, fill=(255, 255, 255, 255), anchor="mm")
                v_ty += 52

            # Corpo
            v_font_sz = 38 if len(slide["body"]) < 150 else 32
            font_vb = _get_font(size=v_font_sz, bold=False)
            v_lh = 54 if v_font_sz == 38 else 46
            vb_wrapped = textwrap.wrap(slide["body"], width=24 if v_font_sz == 38 else 28)

            content_h = len(vb_wrapped) * v_lh
            v_start_by = max(v_ty + 50, (1360 + v_ty - content_h) // 2)
            for bl in vb_wrapped:
                v_draw.text((v_w // 2 + 2, v_start_by + 2), bl, font=font_vb, fill=(0, 0, 0, 190), anchor="mm")
                v_draw.text((v_w // 2, v_start_by), bl, font=font_vb, fill=(240, 240, 245, 255), anchor="mm")
                v_start_by += v_lh

            # Rodapé (Safe Zone Y=1365-1380)
            v_foot = "Siga para a Palavra Diária ✝️" if slide["is_cover"] else slide["footer"]
            font_vf = _get_font(size=25, bold=True)
            vf_lines = textwrap.wrap(v_foot, width=26)
            y_vf = 1365 if len(vf_lines) > 1 else 1380
            for vfl in vf_lines:
                v_draw.text((v_w // 2, y_vf), vfl, font=font_vf, fill=(212, 175, 55, 225), anchor="mm")
                y_vf += 34

            v_out_path = scenes_dir / f"scene_{idx:02d}.png"
            v_img.convert("RGB").save(v_out_path, format="PNG", quality=95)
            generated_video_scenes.append(v_out_path)

            if idx == 1:
                from config.settings import OUTPUT_IMAGES
                OUTPUT_IMAGES.mkdir(parents=True, exist_ok=True)
                v_img.convert("RGB").save(OUTPUT_IMAGES / f"post_{post_id:04d}.png", format="PNG", quality=95)

    # 3. Áudio do Carrossel (Narração concisa de 50-65s + Trilha Sacra de fundo)
    if with_audio:
        narration_full = build_gospel_narration_text(
            reference=reference,
            text=full_text,
            homily_reflection=homily_reflection,
            key_passage=key_passage,
            concise=True
        )
        carousel_audio = generate_carousel_audio(post_dir, narration_text=narration_full)
        if carousel_audio and carousel_audio.is_file():
            generate_carousel_video_slides(generated_files, carousel_audio, post_dir)

    log.info(f"Carrossel e Cenas do Evangelho ({clean_ref}) concluídos com sucesso: {len(generated_files)} slides 4:5 e {len(generated_video_scenes)} cenas 9:16 em {post_dir.name}")
    from config.settings import ENABLE_CAROUSEL
    if not ENABLE_CAROUSEL and generated_video_scenes:
        return generated_video_scenes
    return generated_files or generated_video_scenes

def generate_prayer_carousel(
    post_id: int,
    reference: str,
    full_text: str,
    hook_title: str = "",
    visual_prompt: str = "",
    source: str = "prayer",
    width: int = 1080,
    height: int = 1350,
    generate_video_scenes: bool = True,
    with_audio: bool = True,
) -> list[Path]:
    """
    Renderiza Carrossel 4:5 e Cenas de Vídeo 9:16 para Grandes Orações, Salmos e Novenas:
    - 5 Lâminas estruturadas:
      1. Capa (Badge solene + Hook magnético de alta retenção + Referência)
      2. Oração/Salmo - Parte 1 (Leitura legível, destaque tipográfico sagrado)
      3. Oração/Salmo - Parte 2 (Conclusão da prece ou palavra de confiança)
      4. Bênção sobre o Lar (Proteção da família e alívio da aflição)
      5. Partilha de Fé & CTA ("Salve para rezar antes de dormir e envie no grupo da família")
    - Cada cena recebe fundo gerado por IA ou gradiente sacro.
    """
    from src.collector.backgrounds import get_thematic_background
    from src.media_gen.tts import build_prayer_narration_text

    CAROUSEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    post_dir = CAROUSEL_OUTPUT_DIR / f"carousel_{post_id:04d}_{source}"
    post_dir.mkdir(parents=True, exist_ok=True)

    clean_ref = reference.split("(")[0].strip()
    is_psalm = ("salmo" in reference.lower()) or (source == "psalm")
    is_novena = ("novena" in reference.lower()) or (source == "novena")

    if is_psalm:
        badge_main = "SALMO DO DIA"
        default_hook = "30 SEGUNDOS PARA BLINDAR A SUA CASA HOJE"
        footer_s1 = "Deslize para ler o Salmo ➔"
    elif is_novena:
        m_day = re.search(r"\((\d{1,2})[ºoªa]?\s*dia\)", reference, re.IGNORECASE)
        day_label = f" • {m_day.group(1)}º DIA" if m_day else ""
        badge_main = f"NOVENA LITÚRGICA{day_label}"
        default_hook = "REZEMOS JUNTOS PELA SUA CAUSA MAIS URGENTE"
        footer_s1 = "Deslize para rezar a novena ➔"
    else:
        badge_main = "ORAÇÃO PODEROSA"
        default_hook = "COLOQUE A MÃO NO CORAÇÃO E RECEBA ESTA ORAÇÃO"
        footer_s1 = "Deslize para fazer esta oração ➔"

    title_h = (hook_title or default_hook).upper()

    # Limpa texto para body
    clean_body = full_text.strip()
    clean_body = re.sub(r"—\s*[^—]+$", "", clean_body).strip()
    clean_body = re.sub(r"^[\s\"“«]+", "", clean_body).strip()
    clean_body = re.sub(r"[\s\"”»]+$", "", clean_body).strip()

    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", clean_body) if s.strip()]
    if len(sentences) >= 2:
        mid = max(1, len(sentences) // 2)
        part1 = " ".join(sentences[:mid])
        part2 = " ".join(sentences[mid:])
    elif len(clean_body) > 180 and "," in clean_body:
        commas = [m.start() for m in re.finditer(r",", clean_body)]
        mid_target = len(clean_body) // 2
        best_comma = min(commas, key=lambda c: abs(c - mid_target))
        part1 = clean_body[: best_comma + 1].strip()
        part2 = clean_body[best_comma + 1 :].strip()
    else:
        part1 = clean_body
        part2 = ""

    slides_data = [
        {
            "badge": badge_main,
            "title": title_h,
            "body": f"Um momento sagrado de paz, refúgio e bênção para você e seu lar.\n\n🕊️ {clean_ref}",
            "footer": footer_s1,
            "prompt": visual_prompt or "Cinematic holy sanctuary, soft warm candles glowing, gentle divine rays through stained glass, 8k",
            "is_cover": True,
        },
        {
            "badge": "O SALMO SAGRADO" if is_psalm else "A ORAÇÃO SAGRADA",
            "title": "Momento de Clamor e Fé",
            "body": f'"{part1}"' if not part1.startswith('"') else part1,
            "footer": "Continua no próximo slide ➔" if part2 else f"— {clean_ref}",
            "prompt": "Hands united in peaceful reverent prayer, soft golden aura, sacred ambiance, divine grace",
            "is_cover": False,
        },
    ]

    if part2:
        slides_data.append({
            "badge": "ENTREGA & CONFIANÇA",
            "title": "A Força da Prece",
            "body": f'"{part2}"' if not part2.startswith('"') else part2,
            "footer": f"— {clean_ref}",
            "prompt": "Peaceful morning sunlight illuminating tranquil holy chapel altar, celestial rays",
            "is_cover": False,
        })

    slides_data.append({
        "badge": "BÊNÇÃO SOBRE O LAR",
        "title": "Paz para sua Família",
        "body": "Que a paz do Altíssimo guarde o seu coração, blindando a sua casa contra todo o mal e derramando saúde e vitória sobre os seus familiares.",
        "footer": "Escreva 'Amém' nos comentários 🙏",
        "prompt": "Warm glowing candle flame in peaceful darkness, holy spiritual light of protection and warmth",
        "is_cover": False,
    })

    slides_data.append({
        "badge": "PARTILHA DE FÉ",
        "title": "Propague Esta Luz",
        "body": "Salve este post para rezar sempre que seu coração precisar de forças e compartilhe no WhatsApp de quem você ama e quer proteger.",
        "footer": "Siga para receber a oração diária ✝️",
        "prompt": "Dove of the Holy Spirit soaring in radiant celestial golden clouds, divine peace and hope",
        "is_cover": False,
    })

    total_slides = len(slides_data)
    generated_files: list[Path] = []
    generated_video_scenes: list[Path] = []

    scenes_dir = post_dir / "scenes"
    if generate_video_scenes:
        scenes_dir.mkdir(parents=True, exist_ok=True)

    for idx, slide in enumerate(slides_data, start=1):
        bg_p = get_thematic_background(slide["prompt"], reference=f"{source}_{post_id}_{idx}")
        current_img = bg_p if (bg_p and bg_p.is_file()) else None

        # --- A. Lâmina 4:5 clássica (1080x1350) para Feed Instagram ---
        if current_img:
            bg = Image.open(current_img).convert("RGBA")
            bg = ImageOps.fit(bg, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 165))
            img = Image.alpha_composite(bg, overlay)
        else:
            img = _create_gradient_background(width, height)

        draw = ImageDraw.Draw(img)

        # Badge decorativo
        font_badge = _get_font(size=26, bold=True)
        draw.text((width // 2, 175), slide["badge"], font=font_badge, fill=(212, 175, 55, 230), anchor="mm")
        draw.line([(width // 2 - 80, 205), (width // 2 + 80, 205)], fill=(212, 175, 55, 180), width=2)

        # Título
        font_title = _get_font(size=40 if slide["is_cover"] else 36, bold=True)
        t_lines = textwrap.wrap(slide["title"], width=24)
        title_y = 250
        for tl in t_lines:
            draw.text((width // 2, title_y), tl, font=font_title, fill=(255, 255, 255, 255), anchor="mm")
            title_y += 50

        # Corpo
        b_font_sz = 38 if len(slide["body"]) < 140 else 32
        font_b = _get_font(size=b_font_sz, bold=False)
        lh = 52 if b_font_sz == 38 else 44
        b_wrapped = textwrap.wrap(slide["body"], width=28 if b_font_sz == 38 else 32)
        start_by = max(title_y + 40, (height - (len(b_wrapped) * lh)) // 2)

        for bl in b_wrapped:
            draw.text((width // 2 + 2, start_by + 2), bl, font=font_b, fill=(0, 0, 0, 190), anchor="mm")
            draw.text((width // 2, start_by), bl, font=font_b, fill=(240, 240, 245, 255), anchor="mm")
            start_by += lh

        # Rodapé
        font_foot = _get_font(size=25, bold=True)
        f_lines = textwrap.wrap(slide["footer"], width=30)
        yf45 = 1175 if len(f_lines) > 1 else 1190
        for fl in f_lines:
            draw.text((width // 2, yf45), fl, font=font_foot, fill=(212, 175, 55, 220), anchor="mm")
            yf45 += 32

        out_slide_path = post_dir / f"slide_{idx:02d}.png"
        img.convert("RGB").save(out_slide_path, format="PNG", quality=95)
        generated_files.append(out_slide_path)

        # --- B. Cena 9:16 Vertical para Vídeo (TikTok, Reels, Shorts - 1080x1920) ---
        if generate_video_scenes:
            v_w, v_h = 1080, 1920
            if current_img:
                v_bg = Image.open(current_img).convert("RGBA")
                v_bg = ImageOps.fit(v_bg, (v_w, v_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
                v_overlay = Image.new("RGBA", (v_w, v_h), (8, 12, 22, 195))
                v_img = Image.alpha_composite(v_bg, v_overlay)
            else:
                v_img = _create_gradient_background(v_w, v_h)

            v_draw = ImageDraw.Draw(v_img)

            # Badge superior
            font_v_badge = _get_font(size=28, bold=True)
            v_draw.text((v_w // 2, 300), slide["badge"], font=font_v_badge, fill=(212, 175, 55, 240), anchor="mm")
            v_draw.line([(v_w // 2 - 80, 330), (v_w // 2 + 80, 330)], fill=(212, 175, 55, 180), width=2)

            # Título
            font_v_title = _get_font(size=44 if slide["is_cover"] else 38, bold=True)
            vt_lines = textwrap.wrap(slide["title"], width=22)
            v_ty = 390
            for tl in vt_lines:
                v_draw.text((v_w // 2, v_ty), tl, font=font_v_title, fill=(255, 255, 255, 255), anchor="mm")
                v_ty += 52

            # Corpo
            v_font_sz = 38 if len(slide["body"]) < 150 else 32
            font_vb = _get_font(size=v_font_sz, bold=False)
            v_lh = 54 if v_font_sz == 38 else 46
            vb_wrapped = textwrap.wrap(slide["body"], width=24 if v_font_sz == 38 else 28)

            content_h = len(vb_wrapped) * v_lh
            v_start_by = max(v_ty + 50, (1360 + v_ty - content_h) // 2)
            for bl in vb_wrapped:
                v_draw.text((v_w // 2 + 2, v_start_by + 2), bl, font=font_vb, fill=(0, 0, 0, 190), anchor="mm")
                v_draw.text((v_w // 2, v_start_by), bl, font=font_vb, fill=(240, 240, 245, 255), anchor="mm")
                v_start_by += v_lh

            # Rodapé
            v_foot = "Siga para a Oração Diária ✝️" if slide["is_cover"] else slide["footer"]
            font_vf = _get_font(size=25, bold=True)
            vf_lines = textwrap.wrap(v_foot, width=26)
            y_vf = 1365 if len(vf_lines) > 1 else 1380
            for vfl in vf_lines:
                v_draw.text((v_w // 2, y_vf), vfl, font=font_vf, fill=(212, 175, 55, 225), anchor="mm")
                y_vf += 34

            v_out_path = scenes_dir / f"scene_{idx:02d}.png"
            v_img.convert("RGB").save(v_out_path, format="PNG", quality=95)
            generated_video_scenes.append(v_out_path)

            if idx == 1:
                from config.settings import OUTPUT_IMAGES
                OUTPUT_IMAGES.mkdir(parents=True, exist_ok=True)
                v_img.convert("RGB").save(OUTPUT_IMAGES / f"post_{post_id:04d}.png", format="PNG", quality=95)

    if with_audio:
        narration_full = build_prayer_narration_text(
            reference=reference,
            text=full_text,
            hook_title=hook_title,
            concise=True
        )
        carousel_audio = generate_carousel_audio(post_dir, narration_text=narration_full)
        if carousel_audio and carousel_audio.is_file():
            generate_carousel_video_slides(generated_files, carousel_audio, post_dir)

    log.info(f"Carrossel e Cenas de {source.upper()} ({clean_ref}) concluídos com sucesso: {len(generated_files)} slides 4:5 e {len(generated_video_scenes)} cenas 9:16 em {post_dir.name}")
    from config.settings import ENABLE_CAROUSEL
    if not ENABLE_CAROUSEL and generated_video_scenes:
        return generated_video_scenes
    return generated_files or generated_video_scenes

