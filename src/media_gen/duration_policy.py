"""Políticas de duração de vídeo por tipo de conteúdo."""

SHORTS_MAX_SECONDS = 180
LONG_CONTENT_MIN_SECONDS = 65


def normalize_content_type(content_type: str | None) -> str:
    value = (content_type or "").strip().lower()
    aliases = {
        "santo": "saint", "santos": "saint", "santa": "saint",
        "evangelho": "gospel", "liturgia": "gospel",
        "novena": "novena", "novenas": "novena",
    }
    return aliases.get(value, value)


def minimum_duration(content_type: str | None) -> int:
    normalized = normalize_content_type(content_type)
    if normalized in {"saint", "gospel", "novena"}:
        return LONG_CONTENT_MIN_SECONDS
    return 0


def maximum_duration(_content_type: str | None) -> int:
    return SHORTS_MAX_SECONDS


def resolve_video_duration(content_type: str | None, narration_seconds: float, explicit_duration: int | None = None) -> int:
    minimum = minimum_duration(content_type)
    maximum = maximum_duration(content_type)
    natural_duration = max(1, int(round(narration_seconds + 1.0))) if narration_seconds > 0 else explicit_duration

    if natural_duration is None:
        natural_duration = max(6, minimum)
    if natural_duration > maximum:
        raise ValueError(
            f"Vídeo excede o limite de {maximum}s para Shorts "
            f"({natural_duration}s calculados)."
        )

    requested_duration = int(explicit_duration or natural_duration)
    if requested_duration > maximum:
        raise ValueError(
            f"Vídeo excede o limite de {maximum}s para Shorts "
            f"({requested_duration}s solicitados)."
        )
    return max(minimum, natural_duration, requested_duration)
