"""Política central de formato de mídia por origem de conteúdo."""

CAROUSEL_SOURCES = {"saint", "gospel", "prayer", "psalm", "novena"}
VIDEO_SOURCES = {"bible", "quote", "quotes", "community", "sunday_blessing"}


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


def prefers_carousel(source: str | None) -> bool:
    return normalize_content_source(source) in CAROUSEL_SOURCES


def media_format(source: str | None) -> str:
    normalized = normalize_content_source(source)
    if prefers_carousel(normalized):
        return "carousel"
    return "video" if normalized in VIDEO_SOURCES else "video"
