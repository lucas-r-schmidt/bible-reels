"""config/settings.py — Loader de configuracao centralizado."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR: Path = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
BIBLE_API_URL: str = os.getenv("BIBLE_API_URL", "https://bible-api.com")
BIBLE_API_KEY: str = os.getenv("BIBLE_API_KEY", "")
BIBLE_TRANSLATION: str = os.getenv("BIBLE_TRANSLATION", "almeida")
CONTENT_LANGUAGE: str = os.getenv("CONTENT_LANGUAGE", "pt-BR")
POSTS_PER_RUN: int = int(os.getenv("POSTS_PER_RUN", "5"))
DB_PATH: Path = ROOT_DIR / os.getenv("DB_PATH", "data/db/bible_reels.db")
OUTPUT_IMAGES: Path = ROOT_DIR / os.getenv("OUTPUT_IMAGES_PATH", "output/images")
OUTPUT_VIDEOS: Path = ROOT_DIR / os.getenv("OUTPUT_VIDEOS_PATH", "output/videos")
OUTPUT_QUEUE: Path = ROOT_DIR / os.getenv("OUTPUT_QUEUE_PATH", "output/queue")
FONTS_PATH: Path = ROOT_DIR / os.getenv("FONTS_PATH", "data/fonts")
AUDIO_PATH: Path = ROOT_DIR / os.getenv("AUDIO_PATH", "data/audio")
CANVAS_WIDTH: int = int(os.getenv("CANVAS_WIDTH", "1080"))
CANVAS_HEIGHT: int = int(os.getenv("CANVAS_HEIGHT", "1920"))
VIDEO_DURATION: int = int(os.getenv("VIDEO_DURATION", "15"))
VIDEO_DURATION_VERSE: int = int(os.getenv("VIDEO_DURATION_VERSE", "14"))
VIDEO_DURATION_SAINT: int = int(os.getenv("VIDEO_DURATION_SAINT", "68"))
ENABLE_AUDIO_CTA: bool = os.getenv("ENABLE_AUDIO_CTA", "true").lower() in ("true", "1", "yes")
CTA_VERSE_TEXT: str = os.getenv(
    "CTA_VERSE_TEXT",
    "Escreva Amém e coloque o seu pedido de oração nos comentários. Compartilhe com quem você ama e siga para a bênção diária."
)
CTA_SAINT_TEXT: str = os.getenv(
    "CTA_SAINT_TEXT",
    "Escreva nos comentários quem você coloca em oração hoje. Deixe seu Amém, compartilhe esta bênção e siga nossa página."
)
INSTAGRAM_ACCESS_TOKEN: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_ACCOUNT_ID: str = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
INSTAGRAM_USERNAME: str = os.getenv("INSTAGRAM_USERNAME", "")
INSTAGRAM_PASSWORD: str = os.getenv("INSTAGRAM_PASSWORD", "")
INSTAGRAM_SESSIONID: str = os.getenv("INSTAGRAM_SESSIONID", "")
TIKTOK_SESSION_ID: str = os.getenv("TIKTOK_SESSION_ID", "").strip()
TIKTOK_ACCESS_TOKEN: str = os.getenv("TIKTOK_ACCESS_TOKEN", "")
TIKTOK_CLIENT_KEY: str = os.getenv("TIKTOK_CLIENT_KEY", "")
KWAI_ACCESS_TOKEN: str = os.getenv("KWAI_ACCESS_TOKEN", "")
WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")
PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "")
CLOUDINARY_URL: str = os.getenv("CLOUDINARY_URL", "")
POSTPROXY_API_KEY: str = os.getenv("POSTPROXY_API_KEY", "")
POSTPROXY_BASE_URL: str = os.getenv("POSTPROXY_BASE_URL", "https://api.postproxy.dev/api")
POSTPROXY_PROFILE_IDS: list[str] = [p.strip() for p in os.getenv("POSTPROXY_PROFILE_IDS", "").split(",") if p.strip()]
DEFAULT_PUBLISHER: str = os.getenv("DEFAULT_PUBLISHER", "webhook")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: Path = ROOT_DIR / os.getenv("LOG_FILE", "logs/bible_reels.log")

BUFFER_GATEWAY_URL: str = os.getenv('BUFFER_GATEWAY_URL', 'http://localhost:8090').rstrip('/')
BUFFER_GATEWAY_API_KEY: str = os.getenv('BUFFER_GATEWAY_API_KEY', 'gateway_secret_token_123')
BUFFER_GATEWAY_PROFILE: str = os.getenv('BUFFER_GATEWAY_PROFILE', 'bible-reels')

# Provedores de Imagem FLUX (Cascata: Cloudflare -> HuggingFace -> Pollinations -> Wikimedia/Pexels -> Unsplash)
CLOUDFLARE_ACCOUNT_ID: str = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_API_TOKEN: str = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
HUGGINGFACE_API_TOKEN: str = os.getenv("HUGGINGFACE_API_TOKEN", os.getenv("HF_TOKEN", "")).strip()
PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "").strip()
PIXABAY_API_KEY: str = os.getenv("PIXABAY_API_KEY", "").strip()

ENABLE_CAROUSEL: bool = os.getenv("ENABLE_CAROUSEL", "false").lower() in ("true", "1", "yes")

# Integracao com VideoFlow
VIDEOFLOW_URL: str = os.getenv('VIDEOFLOW_URL', 'http://localhost:8000').rstrip('/')
VIDEOFLOW_API_TOKEN: str = os.getenv('VIDEOFLOW_API_TOKEN', '').strip()
