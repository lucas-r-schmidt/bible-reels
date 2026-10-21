"""
src/media_gen/image_builder.py
------------------------------
Gera imagens verticais (9:16 - 1080x1920) prontas para Reels/TikTok/Kwai.
Cria fundo com gradiente sutil + overlay escuro + texto centralizado e quebrado.
"""
from pathlib import Path
import re
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageOps

from config.settings import CANVAS_WIDTH, CANVAS_HEIGHT, OUTPUT_IMAGES, FONTS_PATH
from src.utils.logger import get_logger

log = get_logger(__name__)

def _get_font(size: int = 56, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Tenta carregar fonte do sistema (Linux e Windows) ou fallback para default."""
    candidates = [
        FONTS_PATH / ("Roboto-Bold.ttf" if bold else "Roboto-Regular.ttf"),
        # Fontes padrão Linux Ubuntu/Debian (Oracle Cloud)
        Path("/usr/share/fonts/truetype/dejavu/" + ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")),
        Path("/usr/share/fonts/truetype/liberation/" + ("LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf")),
        Path("/usr/share/fonts/truetype/freefont/" + ("FreeSansBold.ttf" if bold else "FreeSans.ttf")),
        # Fontes Windows
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()

def _create_gradient_background(width: int, height: int) -> Image.Image:
    """Cria imagem vertical com degradê elegante escuro."""
    base = Image.new("RGBA", (width, height), (15, 18, 28, 255))
    draw = ImageDraw.Draw(base)

    top_color = (18, 24, 38)
    bottom_color = (6, 8, 14)

    for y in range(height):
        ratio = y / float(height)
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    return base

def generate_post_image(
    post_id: int,
    text: str,
    reference: str,
    output_path: Path | None = None,
    bg_image_path: Path | None = None,
    badge_text: str | None = None,
) -> Path:
    """
    Renderiza imagem 1080x1920 com texto e autor/versiculo.
    Retorna Path da imagem salva.
    """
    width = CANVAS_WIDTH
    height = CANVAS_HEIGHT

    if bg_image_path and bg_image_path.exists():
        bg = Image.open(bg_image_path).convert("RGBA")
        bg = ImageOps.fit(bg, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 145))
        img = Image.alpha_composite(bg, overlay)
    else:
        img = _create_gradient_background(width, height)

    draw = ImageDraw.Draw(img)

    # Remove qualquer referência ou travessão no final do texto para evitar duplicação na imagem
    clean_text = text.strip()
    if reference:
        clean_text = re.sub(rf"(?:[\n\r\s—–-]*){re.escape(reference.strip())}[\s.]*$", "", clean_text, flags=re.IGNORECASE).strip()
        clean_text = re.sub(r"[\n\r\s—–-]+$", "", clean_text).strip()

    # Ajuste dinâmico de tamanho para tipografia nítida e impactante
    text_len = len(clean_text)
    if text_len <= 130:
        font_size = 62
        line_height = 86
        wrap_width = 24
    elif text_len <= 260:
        font_size = 54
        line_height = 76
        wrap_width = 27
    else:
        font_size = 46
        line_height = 66
        wrap_width = 30

    font_text = _get_font(size=font_size, bold=False)
    font_ref = _get_font(size=42, bold=True)
    font_badge = _get_font(size=30, bold=True)

    # Header badge
    if badge_text:
        header_badge = badge_text.strip().upper()
    elif any(k in reference.lower() for k in ("santo", "santa", "são", "sao", "senhora", "nossa senhora")):
        header_badge = "MENSAGEM DO SANTO DO DIA"
    else:
        header_badge = "MENSAGEM DO DIA"

    draw.text((width // 2, 300), header_badge, font=font_badge, fill=(212, 175, 55, 220), anchor="mm")

    # Linha divisoria sutil
    line_y = 330
    draw.line([(width // 2 - 80, line_y), (width // 2 + 80, line_y)], fill=(212, 175, 55, 180), width=2)

    # Quebra de texto automatica
    wrapped_lines = textwrap.wrap(clean_text, width=wrap_width)
    total_text_height = len(wrapped_lines) * line_height

    start_y = max(400, (1320 - total_text_height) // 2)

    # Render texto principal
    for i, line in enumerate(wrapped_lines):
        y = start_y + (i * line_height)
        # Sombra sutil
        draw.text((width // 2 + 2, y + 2), line, font=font_text, fill=(0, 0, 0, 200), anchor="mm")
        draw.text((width // 2, y), line, font=font_text, fill=(255, 255, 255, 255), anchor="mm")

    # Render referencia / autor
    ref_y = min(1320, start_y + total_text_height + 60)
    draw.text((width // 2 + 2, ref_y + 2), reference, font=font_ref, fill=(0, 0, 0, 180), anchor="mm")
    draw.text((width // 2, ref_y), reference, font=font_ref, fill=(225, 200, 120, 255), anchor="mm")

    # Rodapé sutil (Safe Zone inferior: quebrado para não colidir com botões laterais)
    footer_lines = textwrap.wrap("Escreva 'Amém' 🙏 Siga para receber a Palavra diária", width=26)
    font_foot = _get_font(size=25, bold=True)
    y_foot = 1365 if len(footer_lines) > 1 else 1380
    for fl in footer_lines:
        draw.text((width // 2, y_foot), fl, font=font_foot, fill=(212, 175, 55, 220), anchor="mm")
        y_foot += 34

    OUTPUT_IMAGES.mkdir(parents=True, exist_ok=True)
    out_file = output_path or (OUTPUT_IMAGES / f"post_{post_id:04d}.png")
    img.convert("RGB").save(out_file, format="PNG", quality=95)

    log.info(f"Imagem gerada: {out_file.name}")
    return out_file


def generate_verse_scenes(
    post_id: int,
    reference: str,
    text: str,
    visual_prompt: str = "",
    hook_title: str | None = None
) -> list[Path]:
    """
    Gera conjunto dinâmico de cenas 9:16 (1080x1920) para o versículo bíblico:
    - Cena 1: Gancho magnético + Texto Sagrado da Escritura (Safe Zone)
    - Cena 2: Bênção inspiradora + Chamada para 'Amém' e Compartilhamento
    - Cada cena recebe fundo cinematográfico temático diferente
    """
    from config.settings import ROOT_DIR
    from src.collector.backgrounds import get_thematic_background

    post_dir = ROOT_DIR / "output" / "carousels" / f"verse_{post_id:04d}"
    scenes_dir = post_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    clean_verse = text.split("\n\n—")[0].strip()
    if reference:
        clean_verse = re.sub(rf"(?:[\n\r\s—–-]*){re.escape(reference.strip())}[\s.]*$", "", clean_verse, flags=re.IGNORECASE).strip()
        clean_verse = re.sub(r"[\n\r\s—–-]+$", "", clean_verse).strip()

    clean_prompt = visual_prompt or f"peaceful biblical landscape for {reference}"

    full_scripture = f'"{clean_verse}"' if not clean_verse.startswith('"') else clean_verse
    scene_1_title = (hook_title or reference).upper()

    scenes_data = [
        {
            "badge": "VERSÍCULO DO DIA",
            "title": scene_1_title,
            "body": full_scripture,
            "footer": f"— {reference}",
            "prompt": f"majestic golden sunrise over calm mountains, spiritual light, {clean_prompt}"
        },
        {
            "badge": "BÊNÇÃO & ORAÇÃO",
            "title": "RECEBA ESTA BÊNÇÃO",
            "body": "Que esta palavra ilumine seus caminhos, renove suas forças e traga a paz de Deus para você e toda a sua família.",
            "footer": "Escreva 'Amém' para receber 🙏 Compartilhe com quem você ama",
            "prompt": f"serene twilight sky with gentle golden glow, holy peace and tranquility, {clean_prompt}"
        }
    ]

    v_w, v_h = 1080, 1920
    generated_scenes: list[Path] = []

    for idx, sc in enumerate(scenes_data, start=1):
        bg_p = get_thematic_background(sc["prompt"], reference=f"{reference}_{idx}")
        if bg_p and bg_p.is_file():
            bg = Image.open(bg_p).convert("RGBA")
            bg = ImageOps.fit(bg, (v_w, v_h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
            overlay = Image.new("RGBA", (v_w, v_h), (8, 12, 22, 195))
            img = Image.alpha_composite(bg, overlay)
        else:
            img = _create_gradient_background(v_w, v_h)

        draw = ImageDraw.Draw(img)

        # Badge decorativo vertical (Safe Zone superior: Y=300)
        font_badge = _get_font(size=28, bold=True)
        draw.text((v_w // 2, 300), sc["badge"], font=font_badge, fill=(212, 175, 55, 240), anchor="mm")
        draw.line([(v_w // 2 - 80, 330), (v_w // 2 + 80, 330)], fill=(212, 175, 55, 180), width=2)

        # Título do Slide (Safe Zone: Y=390, max width 22 chars)
        font_title = _get_font(size=42, bold=True)
        t_lines = textwrap.wrap(sc["title"], width=22)
        y_t = 390
        for l in t_lines:
            draw.text((v_w // 2, y_t), l, font=font_title, fill=(255, 255, 255, 255), anchor="mm")
            y_t += 50

        # Texto do Versículo / Bênção (Safe Zone: limites laterais >= 140px, inferior Y <= 1360)
        b_font_size = 40 if len(sc["body"]) < 140 else 34 if len(sc["body"]) < 220 else 30
        font_body = _get_font(size=b_font_size, bold=False)
        lh = 58 if b_font_size == 40 else 50 if b_font_size == 34 else 44
        wrap_chars = 24 if b_font_size >= 34 else 28
        b_lines = textwrap.wrap(sc["body"], width=wrap_chars)

        content_height = len(b_lines) * lh
        y_b = max(y_t + 40, (1350 + y_t - content_height) // 2)

        for l in b_lines:
            draw.text((v_w // 2 + 2, y_b + 2), l, font=font_body, fill=(0, 0, 0, 200), anchor="mm")
            draw.text((v_w // 2, y_b), l, font=font_body, fill=(245, 245, 250, 255), anchor="mm")
            y_b += lh

        # Rodapé elegante (Safe Zone: quebrado em linhas curtas para margem >= 160px)
        font_foot = _get_font(size=25, bold=True)
        footer_lines = textwrap.wrap(sc["footer"], width=26)
        y_foot = 1365 if len(footer_lines) > 1 else 1380
        for fl in footer_lines:
            draw.text((v_w // 2, y_foot), fl, font=font_foot, fill=(212, 175, 55, 225), anchor="mm")
            y_foot += 34

        sc_path = scenes_dir / f"scene_{idx:02d}.png"
        img.convert("RGB").save(sc_path, format="PNG", quality=95)
        # Salva também como slide para permitir navegação no painel web
        img.convert("RGB").save(post_dir / f"slide_{idx:02d}.png", format="PNG", quality=95)
        generated_scenes.append(sc_path)

    log.info(f"Cenas do versículo {reference} geradas com sucesso: {len(generated_scenes)} cenas em {post_dir.name}")
    return generated_scenes