"""
src/collector/backgrounds.py
----------------------------
Localizador e gerador de imagens de fundo temáticas para versículos, evangelho, salmos e orações.
- Cascata Resiliente de Geração / Obtenção 9:16 (1080x1920):
  1º Cloudflare Workers AI (@cf/black-forest-labs/flux-1-schnell nativo 9:16)
  2º Hugging Face Serverless API (black-forest-labs/FLUX.1-schnell)
  3º Pollinations.ai (FLUX 1080x1920 gratuito)
  4º Wikimedia Commons Sacred Art (Domínio Público clássico: Caravaggio, Doré, Rembrandt, Rafael)
  5º Pexels / Pixabay API (Fotos verticais 9:16 de santuários, velas, vitrais e natureza)
  6º Unsplash Fallback (Acervo fotográfico sacro curado em alta resolução)
- Mantém cache local em data/backgrounds/cache para velocidade instantânea
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from urllib.parse import quote
import requests

from config.settings import (
    ROOT_DIR,
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_API_TOKEN,
    HUGGINGFACE_API_TOKEN,
    PEXELS_API_KEY,
    PIXABAY_API_KEY,
)
from src.utils.logger import get_logger

log = get_logger(__name__)

BACKGROUNDS_DIR = ROOT_DIR / "data" / "backgrounds"
CACHE_DIR = BACKGROUNDS_DIR / "cache"


def _prompt_hash(prompt: str) -> str:
    return hashlib.md5(prompt.strip().lower().encode("utf-8")).hexdigest()[:16]


def _try_generate_cloudflare_flux(prompt: str, cached_file: Path) -> Path | None:
    """1ª Opção: Cloudflare Workers AI (@cf/black-forest-labs/flux-1-schnell). Gratuito (10k neurônios/dia)."""
    if not (CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN):
        return None

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}"
        f"/ai/run/@cf/black-forest-labs/flux-1-schnell"
    )
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt[:2048],
        "steps": 4,
        "width": 768,
        "height": 1344,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") and data.get("result", {}).get("image"):
                img_bytes = base64.b64decode(data["result"]["image"])
                if len(img_bytes) > 10000:
                    cached_file.write_bytes(img_bytes)
                    log.info(f"Fundo temático gerado com sucesso via Cloudflare Workers AI (FLUX.1 9:16): {cached_file.name}")
                    return cached_file
            else:
                log.warning(f"Cloudflare Workers AI erro: {data.get('errors')}")
        else:
            log.warning(f"Cloudflare Workers AI HTTP {resp.status_code}: {resp.text[:180]}")
    except Exception as exc:
        log.warning(f"Falha ao conectar no Cloudflare Workers AI ({exc}).")

    return None


def _try_generate_huggingface_flux(prompt: str, cached_file: Path) -> Path | None:
    """2ª Opção: Hugging Face Serverless Inference API (black-forest-labs/FLUX.1-schnell)."""
    if not HUGGINGFACE_API_TOKEN:
        return None

    url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    headers = {
        "Authorization": f"Bearer {HUGGINGFACE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"inputs": prompt[:2048]}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=12)
        if resp.status_code == 200 and len(resp.content) > 10000:
            cached_file.write_bytes(resp.content)
            log.info(f"Fundo temático gerado com sucesso via Hugging Face (FLUX.1): {cached_file.name}")
            return cached_file
        elif resp.status_code == 503:
            log.warning("Hugging Face FLUX.1 iniciando (cold start). Tentando próximo provedor...")
        else:
            log.warning(f"Hugging Face HTTP {resp.status_code}: {resp.text[:120]}. Tentando próximo provedor...")
    except Exception as exc:
        log.warning(f"Falha ao conectar no Hugging Face FLUX ({exc}).")

    return None


def _try_generate_pollinations_flux(prompt: str, cached_file: Path) -> Path | None:
    """3ª Opção: Pollinations.ai (Flux gratuito sem autenticação)."""
    try:
        url = (
            f"https://image.pollinations.ai/prompt/{quote(prompt)}"
            f"?width=1080&height=1920&nologo=true&enhance=true&model=flux"
        )
        resp = requests.get(url, timeout=25)
        if resp.status_code == 200 and len(resp.content) > 15000:
            cached_file.write_bytes(resp.content)
            log.info(f"Fundo temático gerado com sucesso via Pollinations (FLUX): {cached_file.name}")
            return cached_file
        else:
            log.warning(f"Pollinations retornou status {resp.status_code} ({len(resp.content)} bytes).")
    except Exception as exc:
        log.warning(f"Falha ao gerar fundo via Pollinations ({exc}).")

    return None


def _try_fetch_wikimedia_sacred_art(clean_prompt: str, reference: str, cached_file: Path) -> Path | None:
    """4ª Opção: Wikimedia Commons Sacred Art (Domínio público: pinturas bíblicas clássicas)."""
    try:
        terms = []
        low = f"{clean_prompt} {reference}".lower()
        if "maria" in low or "senhora" in low or "madonna" in low:
            terms.append("Madonna painting")
        elif "jesus" in low or "cristo" in low or "evangelho" in low:
            terms.append("Jesus Christ painting")
        elif "anjo" in low or "arcanjo" in low or "miguel" in low:
            terms.append("Archangel Michael painting")
        elif "salmo" in low or "oracao" in low or "oração" in low:
            terms.append("Biblical prayer painting")
        else:
            terms.append("Caravaggio sacred painting")

        search_query = terms[0]
        url = (
            "https://commons.wikimedia.org/w/api.php?action=query&generator=search"
            f"&gsrnamespace=6&gsrsearch={quote('filetype:bitmap ' + search_query)}"
            "&gsrlimit=5&prop=imageinfo&iiprop=url|size&format=json"
        )
        resp = requests.get(url, headers={"User-Agent": "BibleReelsBot/1.0"}, timeout=12)
        if resp.status_code == 200:
            pages = resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                info = page.get("imageinfo", [{}])[0]
                img_url = info.get("url")
                width = info.get("width", 0)
                height = info.get("height", 0)
                if img_url and (height >= 800 or width >= 800) and not img_url.lower().endswith(".svg"):
                    img_resp = requests.get(img_url, headers={"User-Agent": "BibleReelsBot/1.0"}, timeout=15)
                    if img_resp.status_code == 200 and len(img_resp.content) > 20000:
                        cached_file.write_bytes(img_resp.content)
                        log.info(f"Arte Sacra obtida via Wikimedia Commons: {cached_file.name}")
                        return cached_file
    except Exception as exc:
        log.warning(f"Wikimedia Commons fallback falhou: {exc}")

    return None


def _try_fetch_stock_vertical(clean_prompt: str, reference: str, cached_file: Path) -> Path | None:
    """5ª Opção: Pexels / Pixabay API para imagens verticais de alta resolução."""
    # A. Pexels API
    if PEXELS_API_KEY:
        try:
            query = "church candle stained glass sanctuary cross"
            url = f"https://api.pexels.com/v1/search?query={quote(query)}&orientation=portrait&per_page=10"
            resp = requests.get(url, headers={"Authorization": PEXELS_API_KEY}, timeout=12)
            if resp.status_code == 200:
                photos = resp.json().get("photos", [])
                if photos:
                    pick = photos[int(hashlib.md5(reference.encode()).hexdigest(), 16) % len(photos)]
                    img_url = pick.get("src", {}).get("large2x") or pick.get("src", {}).get("portrait")
                    if img_url:
                        dl = requests.get(img_url, timeout=15)
                        if dl.status_code == 200 and len(dl.content) > 20000:
                            cached_file.write_bytes(dl.content)
                            log.info(f"Fundo temático vertical obtido via Pexels API: {cached_file.name}")
                            return cached_file
        except Exception as exc:
            log.warning(f"Pexels API falhou: {exc}")

    # B. Pixabay API
    if PIXABAY_API_KEY:
        try:
            query = "church sanctuary stained glass prayer"
            url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={quote(query)}&image_type=photo&orientation=vertical&per_page=10"
            resp = requests.get(url, timeout=12)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                if hits:
                    pick = hits[int(hashlib.md5(reference.encode()).hexdigest(), 16) % len(hits)]
                    img_url = pick.get("largeImageURL")
                    if img_url:
                        dl = requests.get(img_url, timeout=15)
                        if dl.status_code == 200 and len(dl.content) > 20000:
                            cached_file.write_bytes(dl.content)
                            log.info(f"Fundo temático vertical obtido via Pixabay API: {cached_file.name}")
                            return cached_file
        except Exception as exc:
            log.warning(f"Pixabay API falhou: {exc}")

    return None


def _try_fetch_unsplash_fallback(clean_prompt: str, reference: str, cached_file: Path) -> Path | None:
    """6ª Opção: Acervo curado Unsplash de alta resolução para redundância total."""
    try:
        fallbacks = [
            # Arte Sacra & Atmosfera Litúrgica (Velas, Vitrais, Catedral)
            "https://images.unsplash.com/photo-1548625361-16a70a8d8745?w=1080&h=1920&fit=crop",  # Luz divina e velas no altar
            "https://images.unsplash.com/photo-1519817650390-64a93db51149?w=1080&h=1920&fit=crop",  # Vitral sacro e raios de sol
            "https://images.unsplash.com/photo-1438232992991-995b7058bbb3?w=1080&h=1920&fit=crop",  # Bíblia sagrada sob luz de velas
            "https://images.unsplash.com/photo-1507692049790-de58290a4334?w=1080&h=1920&fit=crop",  # Catedral e teto gótico celestial
            # Natureza Celestial Bíblica (Montanhas, Alvorada, Luz Divina)
            "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=1080&h=1920&fit=crop",  # Montanhas e amanhecer
            "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=1080&h=1920&fit=crop",  # Mar sereno ao entardecer
            "https://images.unsplash.com/photo-1437719417032-8595fd9e9dc6?w=1080&h=1920&fit=crop",  # Floresta com raios divinos
            "https://images.unsplash.com/photo-1470252649378-9c29740c9fa8?w=1080&h=1920&fit=crop",  # Campos dourados de trigo
            "https://images.unsplash.com/photo-1518495973542-4542c06a5843?w=1080&h=1920&fit=crop",  # Sol entre as folhas
            "https://images.unsplash.com/photo-1499346030926-9a72daac6c63?w=1080&h=1920&fit=crop",  # Céu dourado de esperança
            "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=1080&h=1920&fit=crop",  # Vale verdejante e paz
            "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?w=1080&h=1920&fit=crop",  # Céu aberto e caminho sereno
        ]
        pick_idx = int(hashlib.md5((reference or clean_prompt).encode("utf-8")).hexdigest(), 16) % len(fallbacks)
        unsplash_url = fallbacks[pick_idx]

        resp_u = requests.get(unsplash_url, timeout=15)
        if resp_u.status_code == 200 and len(resp_u.content) > 15000:
            cached_file.write_bytes(resp_u.content)
            log.info(f"Fundo temático obtido via Unsplash ({pick_idx}): {cached_file.name}")
            return cached_file
    except Exception as exc:
        log.warning(f"Fallback Unsplash falhou: {exc}")

    return None


def get_thematic_background(
    visual_prompt: str,
    reference: str = "",
    theme: str = "general"
) -> Path | None:
    """
    Obtém uma imagem de fundo 9:16 (1080x1920) em cascata resiliente de 6 etapas:
    1º: Cloudflare Workers AI (FLUX.1 Schnell nativo 9:16)
    2º: Hugging Face Serverless (FLUX.1 Schnell)
    3º: Pollinations.ai (FLUX)
    4º: Wikimedia Commons Sacred Art (Domínio público)
    5º: Pexels / Pixabay API (Stock vertical gratuito)
    6º: Unsplash (Fallback fotográfico curado)
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    clean_prompt = (visual_prompt or "").strip()
    if not clean_prompt:
        clean_prompt = f"Serene cinematic sacred landscape, peaceful celestial sunlight, holy divine atmosphere, inspiring {reference}"

    p_hash = _prompt_hash(clean_prompt)
    cached_file = CACHE_DIR / f"bg_{p_hash}.jpg"
    if cached_file.is_file() and cached_file.stat().st_size > 15000:
        return cached_file

    full_prompt = (
        f"{clean_prompt}, vertical 9:16 aspect ratio, cinematic sacred lighting, 8k photo, "
        f"serene peaceful atmosphere, masterpiece, no text, no words, no watermark"
    )

    log.info(f"Buscando/gerando fundo temático para '{reference or clean_prompt[:35]}...'")

    # 1. Cloudflare Workers AI (FLUX.1 Schnell)
    bg = _try_generate_cloudflare_flux(full_prompt, cached_file)
    if bg:
        return bg

    # 2. Hugging Face Inference API (FLUX.1 Schnell)
    bg = _try_generate_huggingface_flux(full_prompt, cached_file)
    if bg:
        return bg

    # 3. Pollinations.ai (FLUX)
    bg = _try_generate_pollinations_flux(full_prompt, cached_file)
    if bg:
        return bg

    # 4. Wikimedia Commons Sacred Art
    bg = _try_fetch_wikimedia_sacred_art(clean_prompt, reference, cached_file)
    if bg:
        return bg

    # 5. Pexels / Pixabay API
    bg = _try_fetch_stock_vertical(clean_prompt, reference, cached_file)
    if bg:
        return bg

    # 6. Fallback Unsplash
    return _try_fetch_unsplash_fallback(clean_prompt, reference, cached_file)
