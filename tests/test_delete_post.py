from src.processor.db_manager import DBManager


def test_delete_draft_removes_queue(tmp_path):
    db = DBManager(tmp_path / "delete.db")
    verse_id = db.insert_verse("bible_api", "Jo 3:16", "texto", "hash-delete-test")
    post_id = db.insert_post(verse_id, "texto", [], "")
    db.enqueue(post_id, "instagram")

    assert db.delete_post_draft(post_id) is True
    assert db.conn.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone() is None
    assert db.conn.execute("SELECT 1 FROM queue WHERE post_id = ?", (post_id,)).fetchone() is None


def test_published_post_cannot_be_deleted(tmp_path):
    db = DBManager(tmp_path / "published.db")
    verse_id = db.insert_verse("bible_api", "Jo 3:16", "texto", "hash-published-test")
    post_id = db.insert_post(verse_id, "texto", [], "")
    db.mark_post_published(post_id)

    try:
        db.delete_post_draft(post_id)
    except ValueError:
        return
    raise AssertionError("post publicado deveria estar protegido")
