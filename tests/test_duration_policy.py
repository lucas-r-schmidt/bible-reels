from src.media_gen.duration_policy import (
    LONG_CONTENT_MIN_SECONDS,
    SHORTS_MAX_SECONDS,
    minimum_duration,
    resolve_video_duration,
)


def test_long_types_have_65_second_minimum():
    for content_type in ("saint", "gospel", "novena", "Santo", "Evangelho"):
        assert minimum_duration(content_type) == LONG_CONTENT_MIN_SECONDS


def test_short_content_uses_natural_duration():
    assert resolve_video_duration("verse", 30.0, None) == 31
    assert resolve_video_duration("psalm", 42.0, None) == 43


def test_long_content_is_never_below_65():
    assert resolve_video_duration("gospel", 20.0, None) == 65


def test_duration_over_shorts_limit_is_rejected():
    try:
        resolve_video_duration("novena", 181.0, None)
    except ValueError:
        return
    raise AssertionError("duração acima de 180 segundos deveria ser rejeitada")


def test_explicit_duration_over_shorts_limit_is_rejected():
    try:
        resolve_video_duration("verse", 30.0, SHORTS_MAX_SECONDS + 1)
    except ValueError:
        return
    raise AssertionError("duração explícita acima de 180 segundos deveria ser rejeitada")
