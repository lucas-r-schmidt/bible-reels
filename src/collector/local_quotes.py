"""
src/collector/local_quotes.py
-----------------------------
Carrega citacoes motivacionais de um arquivo JSON local.
Formato esperado do JSON:

[
  {"text": "A frase motivacional...", "author": "Autor Tal"},
  ...
]
"""
import hashlib
import json
import random
from pathlib import Path

from src.processor.db_manager import DBManager
from src.utils.logger import get_logger

log = get_logger(__name__)

DEFAULT_QUOTES_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "quotes" / "motivacional.json"
CLASSIC_PRAYERS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "quotes" / "oracoes_classicas.json"


def load_classic_prayers() -> list[dict]:
    """Carrega as grandes orações e salmos clássicos da tradição cristã."""
    if not CLASSIC_PRAYERS_FILE.is_file():
        log.warning(f"Arquivo de orações clássicas não encontrado: {CLASSIC_PRAYERS_FILE}")
        return []
    try:
        with open(CLASSIC_PRAYERS_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as exc:
        log.error(f"Erro ao carregar orações clássicas: {exc}")
        return []


def collect_classic_prayers(db: DBManager, count: int = 1) -> list[dict]:
    """Coleta e registra oração clássica no banco com source='prayer'."""
    prayers = load_classic_prayers()
    if not prayers:
        return []
    random.shuffle(prayers)

    candidates = [p for p in prayers if not db.verse_reference_exists(p.get("title", p.get("reference", "")))]
    if not candidates:
        candidates = prayers

    collected = []
    for item in candidates:
        if len(collected) >= count:
            break
        ref = item.get("title", item.get("reference", "Oração Clássica"))
        text = item.get("text", "").strip()
        c_hash = _hash_text(f"prayer_{ref}_{text[:50]}")
        if db.verse_exists(c_hash):
            continue
        v_id = db.insert_verse(
            source="prayer",
            reference=ref,
            text=text,
            content_hash=c_hash,
            translation=item.get("author", "Tradição Cristã")
        )
        collected.append({
            "id": v_id,
            "reference": ref,
            "text": text,
            "author": item.get("author", "Tradição Cristã"),
            "source": "prayer"
        })
        log.info(f"Oração clássica coletada: {ref} (ID {v_id})")
    return collected


def _hash_text(text: str) -> str:
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_quotes_file(filepath: Path | None = None) -> list[dict]:
    """Carrega e retorna lista de citacoes do JSON."""
    path = filepath or DEFAULT_QUOTES_FILE
    if not path.exists():
        log.warning(f"Arquivo de citacoes nao encontrado: {path}")
        return []

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        log.error("Formato invalido: esperado lista de objetos.")
        return []

    log.info(f"Carregadas {len(data)} citacoes de {path.name}")
    return data


def generate_ai_reflection(theme: str = "general") -> dict | None:
    """Gera reflexão/frase motivacional original e inspiradora via Gemini."""
    try:
        import google.generativeai as genai
        from config.settings import GEMINI_API_KEY, GEMINI_MODEL
        if not GEMINI_API_KEY:
            return None
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)

        if theme == "morning":
            focus = "injeção de ânimo, força, coragem, determinação e direcionamento matinal para vencer o dia"
            default_author = "Mensagem do Dia"
        elif theme == "evening":
            focus = "gratidão pelas vitórias, paz interior, serenidade, alívio e descanso para a noite"
            default_author = "Reflexão da Noite"
        else:
            focus = "sabedoria de vida, perseverança, fé e motivação diária"
            default_author = "Sabedoria Diária"

        prompt = f"""Crie uma frase/reflexão motivacional e profunda em português (máximo 180 caracteres).
Tema central: {focus}.
Retorne EXCLUSIVAMENTE um objeto JSON estrito com exatamente as chaves:
{{
  "text": "sua frase inspiradora aqui",
  "author": "{default_author}"
}}"""

        res = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(res.text.strip())
        if data.get("text"):
            return {
                "text": data["text"].strip(),
                "author": data.get("author", default_author).strip()
            }
    except Exception as exc:
        log.warning(f"Falha ao gerar reflexão motivacional via IA ({exc}).")
    return None


def _is_quote_matching_theme(q: dict, theme: str) -> bool:
    """Verifica se citação é estritamente compatível com o tema (morning, evening, general)."""
    q_theme = q.get("theme", "general").strip().lower()
    full_text = f"{q.get('author', '')} {q.get('text', '')}".lower()

    morning_keywords = ("bom dia", "amanhecer", "manhã", "matinal", "novo dia")
    evening_keywords = ("boa noite", "anoitecer", "noite", "noturna", "dormir", "descanso")

    if theme == "morning":
        if q_theme == "evening":
            return False
        if any(k in full_text for k in evening_keywords):
            return False
        return True

    if theme == "evening":
        if q_theme == "morning":
            return False
        if any(k in full_text for k in morning_keywords):
            return False
        return True

    # general: neutras que não sejam exclusivamente matinais nem noturnas
    if q_theme in ("morning", "evening"):
        return False
    if any(k in full_text for k in morning_keywords) or any(k in full_text for k in evening_keywords):
        return False
    return True


def collect_quotes(db: DBManager, count: int = 5, filepath: Path | None = None, theme: str = "general") -> list[dict]:
    """
    Coleta N citacoes/mensagens motivacionais unicas (deduplica pelo hash).
    theme: 'morning', 'evening' ou 'general'.
    """
    quotes = load_quotes_file(filepath)
    if quotes:
        quotes = [q for q in quotes if _is_quote_matching_theme(q, theme)]
        exact_matches = [q for q in quotes if q.get("theme") == theme]
        other_matches = [q for q in quotes if q.get("theme") != theme]
        random.shuffle(exact_matches)
        random.shuffle(other_matches)
        quotes = exact_matches + other_matches
    collected: list[dict] = []

    for q in quotes:
        if len(collected) >= count:
            break

        text = q.get("text", "").strip()
        author = q.get("author", "Reflexão").strip()
        if not text:
            continue

        content_hash = _hash_text(text)
        if db.verse_exists(content_hash):
            continue

        verse_id = db.insert_verse(
            source="local_quotes",
            reference=author,
            text=text,
            content_hash=content_hash,
        )
        entry = {"id": verse_id, "reference": author, "text": text}
        collected.append(entry)
        log.info(f"[green]Citacao coletada:[/green] {author}")

    # Fallback gerativo com IA caso o arquivo local não tenha mais itens inéditos
    while len(collected) < count:
        ai_ref = generate_ai_reflection(theme=theme)
        if not ai_ref:
            break
        c_hash = _hash_text(ai_ref["text"])
        if db.verse_exists(c_hash):
            break
        verse_id = db.insert_verse(
            source="ai_quotes",
            reference=ai_ref["author"],
            text=ai_ref["text"],
            content_hash=c_hash,
        )
        entry = {"id": verse_id, "reference": ai_ref["author"], "text": ai_ref["text"]}
        collected.append(entry)
        log.info(f"[green]Reflexão motivacional IA gerada:[/green] {ai_ref['author']}")
        break

    log.info(f"Citacoes coletadas: {len(collected)}/{count}")
    return collected