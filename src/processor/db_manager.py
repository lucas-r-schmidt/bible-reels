"""
src/processor/db_manager.py
---------------------------
Gerencia persistencia no SQLite.
Tabelas: verses (coletados), posts (gerados), queue (fila de publicacao).
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DBManager:
    """CRUD sobre bible_reels.db."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        log.info(f"SQLite conectado: {self.db_path}")

    # ── Schema ────────────────────────────────────────────────────────────

    def _create_tables(self) -> None:
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS verses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source      TEXT NOT NULL,          -- 'bible_api' | 'local_quotes'
                reference   TEXT NOT NULL,           -- 'Joao 3:16' ou autor
                text        TEXT NOT NULL,
                translation TEXT DEFAULT '',
                hash        TEXT UNIQUE NOT NULL,    -- sha256 para deduplicacao
                collected_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS posts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                verse_id      INTEGER NOT NULL REFERENCES verses(id),
                formatted_text TEXT NOT NULL,
                hashtags       TEXT DEFAULT '',       -- JSON array
                visual_prompt  TEXT DEFAULT '',
                image_path     TEXT DEFAULT '',
                video_path     TEXT DEFAULT '',
                status         TEXT DEFAULT 'created', -- created | published | failed
                created_at     TEXT NOT NULL,
                published_at   TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS queue (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id   INTEGER NOT NULL REFERENCES posts(id),
                platform  TEXT NOT NULL,             -- instagram | tiktok | kwai | webhook
                status    TEXT DEFAULT 'pending',    -- pending | sent | failed
                attempts  INTEGER DEFAULT 0,
                queued_at TEXT NOT NULL,
                sent_at   TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS comment_interactions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                platform     TEXT NOT NULL,          -- 'youtube' | 'instagram' | 'tiktok'
                channel_id   TEXT DEFAULT '',
                video_id     TEXT DEFAULT '',
                comment_id   TEXT UNIQUE NOT NULL,
                author_name  TEXT DEFAULT '',
                comment_text TEXT NOT NULL,
                sentiment    TEXT DEFAULT 'general',
                reply_text   TEXT DEFAULT '',
                reply_id     TEXT DEFAULT '',
                status       TEXT DEFAULT 'replied', -- replied | ignored | failed
                created_at   TEXT NOT NULL,
                replied_at   TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_verses_hash ON verses(hash);
            CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
            CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
            CREATE INDEX IF NOT EXISTS idx_comment_interactions_id ON comment_interactions(comment_id);
        """)
        self.conn.commit()

        # Migração retrocompatível: adiciona colunas se não existirem
        for col in ("caption", "hook_title"):
            try:
                self.conn.execute(f"ALTER TABLE posts ADD COLUMN {col} TEXT DEFAULT ''")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass

    # ── Verses ────────────────────────────────────────────────────────────

    def verse_exists(self, content_hash: str) -> bool:
        """Verifica se versiculo/frase ja foi coletado (deduplicacao)."""
        row = self.conn.execute(
            "SELECT 1 FROM verses WHERE hash = ?", (content_hash,)
        ).fetchone()
        return row is not None

    def verse_reference_exists(self, reference: str) -> bool:
        """Verifica se uma referencia biblica ja foi coletada."""
        row = self.conn.execute(
            "SELECT 1 FROM verses WHERE LOWER(reference) = LOWER(?)", (reference.strip(),)
        ).fetchone()
        return row is not None

    def insert_verse(
        self,
        source: str,
        reference: str,
        text: str,
        content_hash: str,
        translation: str = "",
    ) -> int:
        """Insere versiculo e retorna ID."""
        cur = self.conn.execute(
            """INSERT INTO verses (source, reference, text, hash, translation, collected_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (source, reference, text, content_hash, translation, _now_iso()),
        )
        self.conn.commit()
        log.debug(f"Verso inserido: {reference}")
        return cur.lastrowid  # type: ignore[return-value]

    def get_unused_verses(self, limit: int = 5, allow_recycling: bool = True, source: str | None = None) -> list[dict[str, Any]]:
        """Retorna versiculos que ainda nao viraram posts. Se todos ja viraram, recicla os mais antigos."""
        if source:
            source_map = {
                "bible": ("bible", "bible_api"),
                "quotes": ("quotes", "local_quotes"),
                "saint": ("saint",),
            }
            target_sources = source_map.get(source, (source,))
            placeholders = ",".join("?" for _ in target_sources)
            rows = self.conn.execute(
                f"""SELECT v.* FROM verses v
                   LEFT JOIN posts p ON p.verse_id = v.id
                   WHERE p.id IS NULL AND v.source IN ({placeholders})
                   ORDER BY v.collected_at ASC
                   LIMIT ?""",
                (*target_sources, limit),
            ).fetchall()
            if not rows and allow_recycling:
                rows = self.conn.execute(
                    f"""SELECT v.* FROM verses v
                       JOIN posts p ON p.verse_id = v.id
                       WHERE v.source IN ({placeholders})
                       GROUP BY v.id
                       ORDER BY MAX(p.created_at) ASC
                       LIMIT ?""",
                    (*target_sources, limit),
                ).fetchall()
            return [dict(r) for r in rows]

        rows = self.conn.execute(
            """SELECT v.* FROM verses v
               LEFT JOIN posts p ON p.verse_id = v.id
               WHERE p.id IS NULL
               ORDER BY v.collected_at ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        if not rows and allow_recycling:
            rows = self.conn.execute(
                """SELECT v.* FROM verses v
                   JOIN posts p ON p.verse_id = v.id
                   GROUP BY v.id
                   ORDER BY MAX(p.created_at) ASC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Posts ──────────────────────────────────────────────────────────────

    def insert_post(
        self,
        verse_id: int,
        formatted_text: str,
        hashtags: list[str],
        visual_prompt: str,
        image_path: str = "",
        video_path: str = "",
        caption: str = "",
        hook_title: str = "",
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO posts
               (verse_id, formatted_text, hashtags, visual_prompt,
                image_path, video_path, status, created_at, caption, hook_title)
               VALUES (?, ?, ?, ?, ?, ?, 'created', ?, ?, ?)""",
            (
                verse_id,
                formatted_text,
                json.dumps(hashtags, ensure_ascii=False),
                visual_prompt,
                image_path,
                video_path,
                _now_iso(),
                caption,
                hook_title,
            ),
        )
        self.conn.commit()
        log.debug(f"Post criado: id={cur.lastrowid}")
        return cur.lastrowid  # type: ignore[return-value]

    def update_post_media(self, post_id: int, image_path: str, video_path: str) -> None:
        self.conn.execute(
            "UPDATE posts SET image_path = ?, video_path = ? WHERE id = ?",
            (image_path, video_path, post_id),
        )
        self.conn.commit()

    def mark_post_published(self, post_id: int) -> None:
        self.conn.execute(
            "UPDATE posts SET status = 'published', published_at = ? WHERE id = ?",
            (_now_iso(), post_id),
        )
        self.conn.commit()

    def has_post_published_between(self, start_dt: datetime, end_dt: datetime, source: str | None = None) -> tuple[bool, dict[str, Any] | None]:
        """
        Verifica se algum post foi publicado dentro da janela de datas fornecida.
        Opcionalmente filtra por fonte ('saint' ou 'bible').
        Compara convertendo published_at (ISO UTC) para o mesmo fuso de start_dt/end_dt.
        """
        if source:
            rows = self.conn.execute(
                """SELECT p.* FROM posts p
                   JOIN verses v ON v.id = p.verse_id
                   WHERE p.status = 'published' AND p.published_at IS NOT NULL AND p.published_at != ''
                   AND v.source = ?
                   ORDER BY p.id DESC LIMIT 50""",
                (source,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM posts
                   WHERE status = 'published' AND published_at IS NOT NULL AND published_at != ''
                   ORDER BY id DESC LIMIT 50"""
            ).fetchall()

        for row in rows:
            pub_str = row["published_at"]
            try:
                pub_dt = datetime.fromisoformat(pub_str)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)

                if start_dt.tzinfo:
                    pub_dt_cmp = pub_dt.astimezone(start_dt.tzinfo)
                else:
                    pub_dt_cmp = pub_dt.astimezone().replace(tzinfo=None)

                if start_dt <= pub_dt_cmp <= end_dt:
                    return True, dict(row)
            except Exception as exc:
                log.debug(f"Erro ao parsear published_at do post {row['id']}: {exc}")
                continue

        return False, None

    def has_saint_post_for_date(self, target_date: date) -> tuple[bool, dict[str, Any] | None]:
        """
        Verifica se já existe post gerado ou publicado para o Santo da data indicada.
        Evita duplicação caso o post já tenha sido agendado ou enviado previamente.
        """
        d_str = f"{target_date.day:02d}/{target_date.month:02d}"
        row = self.conn.execute(
            """SELECT p.* FROM posts p
               JOIN verses v ON v.id = p.verse_id
               WHERE v.source = 'saint' AND v.reference LIKE ?
               ORDER BY p.id DESC LIMIT 1""",
            (f"%({d_str})%",)
        ).fetchone()
        if row:
            return True, dict(row)
        return False, None

    def get_pending_posts(self, limit: int = 10, need_video: bool = False, need_image: bool = False) -> list[dict[str, Any]]:
        # Expira posts antigos pendentes (> 24h) para evitar resgate indevido de conteúdo defasado
        self.conn.execute(
            "UPDATE posts SET status = 'expired' WHERE status = 'created' AND created_at < datetime('now', '-1 day')"
        )
        self.conn.commit()

        query = "SELECT * FROM posts WHERE status = 'created' AND created_at >= datetime('now', '-1 day')"
        if need_video:
            query += " AND (video_path IS NULL OR video_path = '')"
        elif need_image:
            query += " AND (image_path IS NULL OR image_path = '')"
        query += " ORDER BY id DESC LIMIT ?"
        rows = self.conn.execute(query, (limit,)).fetchall()
        # Se todos já tiverem a mídia filtrada, traz os criados recentes
        if not rows and (need_video or need_image):
            rows = self.conn.execute(
                "SELECT * FROM posts WHERE status = 'created' AND created_at >= datetime('now', '-1 day') ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Queue ─────────────────────────────────────────────────────────────

    def enqueue(self, post_id: int, platform: str) -> int:
        cur = self.conn.execute(
            """INSERT INTO queue (post_id, platform, status, queued_at)
               VALUES (?, ?, 'pending', ?)""",
            (post_id, platform, _now_iso()),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_pending_queue(self, platform: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        # Expira itens pendentes antigos (> 24h) para evitar envio de posts defasados
        self.conn.execute(
            "UPDATE queue SET status = 'expired' WHERE status = 'pending' AND queued_at < datetime('now', '-1 day')"
        )
        self.conn.commit()

        if platform:
            rows = self.conn.execute(
                "SELECT * FROM queue WHERE status = 'pending' AND platform = ? ORDER BY id DESC LIMIT ?",
                (platform, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM queue WHERE status = 'pending' ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_queue_sent(self, queue_id: int) -> None:
        self.conn.execute(
            "UPDATE queue SET status = 'sent', sent_at = ? WHERE id = ?",
            (_now_iso(), queue_id),
        )
        self.conn.commit()

    def mark_queue_failed(self, queue_id: int) -> None:
        self.conn.execute(
            "UPDATE queue SET status = 'failed', attempts = attempts + 1 WHERE id = ?",
            (queue_id,),
        )
        self.conn.commit()

    # ── Community Interactions ───────────────────────────────────────────

    def is_comment_processed(self, comment_id: str) -> bool:
        """Verifica se um comentario ja foi processado/respondido anteriormente."""
        row = self.conn.execute(
            "SELECT 1 FROM comment_interactions WHERE comment_id = ?",
            (comment_id,)
        ).fetchone()
        return row is not None

    def log_comment_interaction(
        self,
        platform: str,
        comment_id: str,
        comment_text: str,
        author_name: str = "",
        channel_id: str = "",
        video_id: str = "",
        sentiment: str = "general",
        reply_text: str = "",
        reply_id: str = "",
        status: str = "replied"
    ) -> int:
        """Registra a resposta enviada a um comentario."""
        cur = self.conn.execute(
            """INSERT INTO comment_interactions
               (platform, channel_id, video_id, comment_id, author_name,
                comment_text, sentiment, reply_text, reply_id, status, created_at, replied_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                platform, channel_id, video_id, comment_id, author_name,
                comment_text, sentiment, reply_text, reply_id, status,
                _now_iso(), _now_iso() if status == "replied" else ""
            )
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_recent_interactions(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT * FROM comment_interactions
               ORDER BY id DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def close(self) -> None:
        self.conn.close()
        log.info("SQLite desconectado.")