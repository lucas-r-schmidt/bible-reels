"""
src/publisher/kwai.py
---------------------
Stub e conector Kwai Open API.
"""
from config.settings import KWAI_ACCESS_TOKEN
from src.utils.logger import get_logger

log = get_logger(__name__)

def publish_to_kwai(video_path: str, caption: str) -> bool:
    if not KWAI_ACCESS_TOKEN:
        log.warning("KWAI_ACCESS_TOKEN não configurado no .env.")
        return False
    log.info("Kwai publisher configurado.")
    return True