from src.media_gen.tts import split_sentence_into_subtitles


def test_subtitle_chunks_keep_complete_story_phrases():
    text = "Francisco nasceu em uma família humilde e dedicou toda a vida ao evangelho dos pobres."
    chunks = split_sentence_into_subtitles(text)
    rendered = " ".join(" ".join(chunk) for chunk in chunks)

    assert rendered == text
    assert all(len(chunk) <= 8 for chunk in chunks)


def test_subtitle_chunk_is_not_limited_to_a_short_phrase():
    chunks = split_sentence_into_subtitles("Este santo deixou um legado de fé esperança humildade e serviço aos necessitados")
    assert max(len(chunk) for chunk in chunks) >= 5
