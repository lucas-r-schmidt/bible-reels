from pathlib import Path


def test_dashboard_prefers_complete_caption():
    app = Path("src/web/static/app.js").read_text(encoding="utf-8")
    assert 'modalTxt.textContent = post.caption || post.formatted_text' in app


def test_saint_caption_contains_history_and_cta():
    from src.processor.ai_formatter import format_saint_post
    result = format_saint_post(
        "Santo Teste (31/10)",
        "Uma frase de fé.",
        {"name": "Santo Teste", "history": "Nascido em família humilde, dedicou sua vida ao Evangelho.", "prayer": "Senhor, escuta nossa oração."},
    )
    caption = result.get("caption", "")
    assert result.get("formatted_text") == "Uma frase de fé.\n\n— Santo Teste"
    assert "história" in caption.lower() or "História" in caption
    assert "Amém" in caption
