"""
src/collector/bible_api.py
--------------------------
Coleta versiculos da Bible API gratuita (bible-api.com).
Nao requer chave de API. Suporta busca por referencia e aleatorio.
"""
import hashlib
import random

import requests

from config.settings import BIBLE_API_URL, BIBLE_TRANSLATION, CONTENT_LANGUAGE
from src.processor.db_manager import DBManager
from src.utils.logger import get_logger

log = get_logger(__name__)

# Versiculos para injeção de ânimo e direcionamento matinal (06:00)
MORNING_VERSES: list[str] = [
    "Salmos 143:8", "Salmos 30:5", "Lamentações 3:22-23", "Josué 1:9",
    "Isaías 40:31", "Filipenses 4:13", "Provérbios 16:3", "Salmos 118:24",
    "Romanos 8:31", "Salmos 90:14", "2 Timóteo 1:7", "Salmos 37:5",
    "Isaías 41:10", "Salmos 121:1-2", "Deuteronômio 31:6", "Colossenses 3:23",
    "Salmos 5:3", "Salmos 59:16", "Salmos 92:1-2", "Salmos 119:147",
    "Salmos 46:5", "Provérbios 3:5-6", "Provérbios 4:18", "Provérbios 8:17",
    "Isaías 26:9", "Isaías 33:2", "Isaías 43:18-19", "Jeremias 29:11",
    "Sofonias 3:17", "Habacuque 3:19", "Mateus 6:33-34", "Marcos 1:35",
    "Lucas 1:78-79", "Romanos 12:11-12", "1 Coríntios 15:58", "2 Coríntios 4:16",
    "2 Coríntios 5:17", "2 Coríntios 9:8", "Efésios 5:14", "Efésios 6:10",
    "Filipenses 3:13-14", "Filipenses 4:19", "Colossenses 1:11", "1 Tessalonicenses 5:5-6",
    "1 Timóteo 6:12", "2 Timóteo 4:7", "Hebreus 10:35-36", "Hebreus 12:1-2",
    "Tiago 1:5", "1 Pedro 5:10", "2 Pedro 1:3", "Salmos 19:14",
    "Salmos 27:1", "Salmos 28:7", "Salmos 63:1", "Salmos 73:26",
    "Salmos 84:11", "Salmos 108:1-2", "Salmos 138:8", "Provérbios 18:10",
    "Salmos 1:1-3", "Salmos 16:11", "Salmos 34:8", "Salmos 100:1-5",
    "Salmos 103:1-2", "Salmos 119:105", "Isaías 12:2", "Isaías 40:29"
]

# Versiculos para gratidão, fé, alívio e paz noturna (18:00)
EVENING_VERSES: list[str] = [
    "Salmos 4:8", "Mateus 11:28", "Salmos 91:1-2", "Filipenses 4:6-7",
    "1 Pedro 5:7", "Salmos 121:3-4", "Salmos 103:1-5", "1 Tessalonicenses 5:18",
    "João 14:27", "Salmos 62:1-2", "Salmos 46:1", "Salmos 23:1-6",
    "Salmos 119:105", "Salmos 34:18", "Romanos 15:13", "Sofonias 3:17",
    "Salmos 3:5", "Salmos 16:7-8", "Salmos 42:8", "Salmos 63:6-7",
    "Salmos 91:4-6", "Salmos 91:11-12", "Salmos 116:7", "Salmos 127:2",
    "Salmos 130:5-6", "Salmos 134:1-2", "Salmos 139:11-12", "Provérbios 3:24",
    "Isaías 26:3", "Isaías 30:15", "Isaías 32:17-18", "Jeremias 31:25",
    "Mateus 6:26-27", "Mateus 11:29-30", "Lucas 12:22-26", "João 16:33",
    "Romanos 8:38-39", "2 Coríntios 12:9", "Efésios 2:14", "Efésios 4:26",
    "Filipenses 4:8", "Colossenses 3:15", "2 Tessalonicenses 3:16", "Hebreus 4:9-10",
    "Hebreus 13:5-6", "1 Pedro 1:8", "1 João 4:18", "Apocalipse 21:4",
    "Salmos 27:14", "Salmos 29:11", "Salmos 37:7", "Salmos 55:22",
    "Salmos 62:5", "Salmos 94:19", "Salmos 119:165", "Salmos 131:2",
    "Provérbios 14:30", "Salmos 34:1-4", "Salmos 40:1-3", "Salmos 66:16-20",
    "Salmos 86:15", "Salmos 107:1", "Salmos 136:1", "Lamentações 3:25-26"
]

POPULAR_VERSES: list[str] = MORNING_VERSES + EVENING_VERSES


# Mapeamento de traducao para parametro da API
TRANSLATION_MAP: dict[str, str] = {
    "almeida": "almeida",
    "kjv": "kjv",
    "web": "web",
    "bbl": "bbl",
}


def _hash_text(text: str) -> str:
    """SHA-256 do texto normalizado para deduplicacao."""
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def fetch_verse(reference: str | None = None) -> dict | None:
    """
    Busca um versiculo da Bible API.

    Args:
        reference: Referencia biblica (ex: 'João 3:16'). Se None, escolhe aleatoriamente.

    Returns:
        dict com keys: reference, text, translation  |  None se falhar.
    """
    ref = reference or random.choice(POPULAR_VERSES)
    translation = TRANSLATION_MAP.get(BIBLE_TRANSLATION, "almeida")

    url = f"{BIBLE_API_URL}/{ref}"
    params = {"translation": translation}

    try:
        log.info(f"Buscando: {ref} (traducao: {translation})")
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        text = data.get("text", "").strip()
        if not text:
            log.warning(f"Resposta vazia para: {ref}")
            return None

        # Limpa espaços duplos e non-breaking spaces mantendo texto 100% fiel
        text = text.replace("\xa0", " ")
        text = " ".join(text.split())

        return {
            "reference": data.get("reference", ref),
            "text": text,
            "translation": translation,
        }

    except requests.RequestException as exc:
        log.error(f"Erro ao buscar {ref}: {exc}")
        return None


def collect_verses(db: DBManager, count: int = 5, theme: str = "general") -> list[dict]:
    """
    Coleta N versiculos unicos (deduplica pelo hash).
    theme: 'morning', 'evening' ou 'general'.
    Garante que nunca esgote o acervo através de filtragem inteligente e fallback dinâmico.
    """
    collected: list[dict] = []
    attempts = 0

    if theme == "morning":
        pool = list(MORNING_VERSES)
    elif theme == "evening":
        pool = list(EVENING_VERSES)
    else:
        pool = list(POPULAR_VERSES)

    random.shuffle(pool)

    # 1. Prioriza referências que ainda não constam na tabela verses
    candidates = [r for r in pool if not db.verse_reference_exists(r)]

    # 2. Se todos os versículos do pool já foram coletados, gera candidatos dinâmicos
    if len(candidates) < count * 2:
        dynamic_refs: list[str] = []
        for _ in range(15):
            psalm_num = random.randint(1, 150)
            verse_num = random.randint(1, 6)
            dynamic_refs.append(f"Salmos {psalm_num}:{verse_num}")
        for _ in range(10):
            prov_num = random.randint(1, 31)
            verse_num = random.randint(1, 7)
            dynamic_refs.append(f"Provérbios {prov_num}:{verse_num}")
        dynamic_candidates = [r for r in dynamic_refs if not db.verse_reference_exists(r)]
        candidates.extend(dynamic_candidates)

    # Fallback final se tudo acima já existir: usa todo o pool embaralhado
    if not candidates:
        candidates = list(pool)
        random.shuffle(candidates)

    for ref in candidates:
        if len(collected) >= count:
            break
        attempts += 1

        verse = fetch_verse(ref)
        if not verse:
            continue

        content_hash = _hash_text(verse["text"])
        if db.verse_exists(content_hash):
            log.debug(f"Duplicata ignorada: {verse['reference']}")
            continue

        verse_id = db.insert_verse(
            source="bible_api",
            reference=verse["reference"],
            text=verse["text"],
            content_hash=content_hash,
            translation=verse["translation"],
        )
        verse["id"] = verse_id
        collected.append(verse)
        log.info(f"[green]Coletado:[/green] {verse['reference']}")

    log.info(f"Coleta finalizada: {len(collected)}/{count} versiculos novos ({attempts} tentativas)")
    return collected