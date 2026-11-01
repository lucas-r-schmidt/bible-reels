"""Política central de formato de mídia por origem de conteúdo."""

CAROUSEL_CAPABLE_SOURCES = {"saint", "gospel", "prayer", "psalm", "novena"}
VIDEO_SOURCES = {"bible", "quote", "quotes", "community", "sunday_blessing"} | CAROUSEL_CAPABLE_SOURCES
CAROUSEL_SOURCES = CAROUSEL_CAPABLE_SOURCES


def normalize_content_source(source: str | None) -> str:
    value = (source or "").strip().lower()
    aliases = {
        "santo": "saint", "santos": "saint", "saints": "saint",
        "evangelho": "gospel", "liturgia": "gospel",
        "oracao": "prayer", "oracoes": "prayer", "prayers": "prayer",
        "salmo": "psalm", "salmos": "psalm",
        "novenas": "novena",
        "biblia": "bible", "versiculo": "bible",
        "frases": "quotes", "comunidade": "community",
    }
    return aliases.get(value, value)


def supports_carousel(source: str | None) -> bool:
    """Indica se a origem possui gerador de lâminas de carrossel complementar."""
    return normalize_content_source(source) in CAROUSEL_CAPABLE_SOURCES


def prefers_carousel(source: str | None, explicit_carousel: bool = False) -> bool:
    """Retorna True somente quando o disparo solicitar modo carrossel e a fonte suportar."""
    if not explicit_carousel:
        return False
    return supports_carousel(source)


def media_format(source: str | None, explicit_carousel: bool = False) -> str:
    if prefers_carousel(source, explicit_carousel=explicit_carousel):
        return "carousel"
    return "video"
