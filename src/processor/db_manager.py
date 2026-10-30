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

            CREATE TABLE IF NOT EXISTS post_metrics (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                buffer_post_id  TEXT NOT NULL,
                platform        TEXT NOT NULL,          -- 'youtube' | 'tiktok' | 'instagram'
                external_link   TEXT DEFAULT '',
                sent_at         TEXT DEFAULT '',
                text_snippet    TEXT DEFAULT '',
                theme           TEXT DEFAULT 'faith',   -- 'gospel' | 'saint' | 'psalm' | 'prayer' | 'faith' | 'novena'
                post_hour       INTEGER DEFAULT 0,       -- hora local do envio (0-23)
                views           INTEGER DEFAULT 0,
                likes           INTEGER DEFAULT 0,
                comments        INTEGER DEFAULT 0,
                shares          INTEGER DEFAULT 0,
                reach           INTEGER DEFAULT 0,
                engagement_rate REAL DEFAULT 0.0,
                watch_time_sec  REAL DEFAULT 0.0,
                raw_metrics     TEXT DEFAULT '{}',
                updated_at      TEXT NOT NULL,
                UNIQUE(buffer_post_id, platform)
            );

            CREATE INDEX IF NOT EXISTS idx_verses_hash ON verses(hash);
            CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
            CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
            CREATE INDEX IF NOT EXISTS idx_comment_interactions_id ON comment_interactions(comment_id);
            CREATE INDEX IF NOT EXISTS idx_post_metrics_theme ON post_metrics(theme);
            CREATE INDEX IF NOT EXISTS idx_post_metrics_platform ON post_metrics(platform);
            CREATE INDEX IF NOT EXISTS idx_post_metrics_hour ON post_metrics(post_hour);
        """)
        self.conn.commit()

        # Migração retrocompatível: adiciona colunas se não existirem
        for col in ("caption", "hook_title", "series_id", "series_day"):
            try:
                col_type = "INTEGER DEFAULT 0" if col == "series_day" else "TEXT DEFAULT ''"
                self.conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {col_type}")
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

    def delete_post_draft(self, post_id: int) -> bool:
        row = self.conn.execute("SELECT status FROM posts WHERE id = ?", (post_id,)).fetchone()
        if not row:
            return False
        if row["status"] == "published":
            raise ValueError("Posts publicados não podem ser excluídos pelo painel")
        with self.conn:
            self.conn.execute("DELETE FROM queue WHERE post_id = ?", (post_id,))
            self.conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        return True

    def update_post_content(
        self,
        post_id: int,
        formatted_text: str,
        hashtags: list[str],
        visual_prompt: str,
        caption: str = "",
        hook_title: str = "",
    ) -> None:
        self.conn.execute(
            """UPDATE posts
               SET formatted_text = ?, hashtags = ?, visual_prompt = ?,
                   caption = ?, hook_title = ?
               WHERE id = ?""",
            (
                formatted_text,
                json.dumps(hashtags, ensure_ascii=False),
                visual_prompt,
                caption,
                hook_title,
                post_id,
            ),
        )
        self.conn.commit()

    def clone_post_draft(self, post_id: int) -> int | None:
        row = self.conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if not row:
            return None
        post = dict(row)
        return self.insert_post(
            verse_id=post["verse_id"],
            formatted_text=post["formatted_text"],
            hashtags=json.loads(post["hashtags"] or "[]"),
            visual_prompt=post.get("visual_prompt", ""),
            caption=post.get("caption", ""),
            hook_title=post.get("hook_title", ""),
        )

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

    def has_saint_post_for_date(
        self,
        target_date: date,
        saint_name: str | None = None
    ) -> tuple[bool, dict[str, Any] | None]:
        """
        Verifica se já existe o Santo CORRETO gerado ou enviado para a data indicada.
        Verifica:
        1. Vínculo direto com versículo do tipo 'saint' contendo a data (DD/MM).
        2. Vínculo com versículo ou legenda contendo o nome canônico do Santo correto.
        3. Menção à data litúrgica (DD/MM) ou ao Santo no título/legenda.
        4. Status na fila ('sent' / 'pending') e status na tabela posts ('published' / 'created').
        """
        d_str = f"{target_date.day:02d}/{target_date.month:02d}"
        clauses = [
            "(v.reference LIKE ? OR v.text LIKE ?)",
            "(p.caption LIKE ? AND (p.caption LIKE '%#santododia%' OR p.caption LIKE '%santododia%' OR p.hook_title LIKE '%SANTO DO DIA%'))",
            "(p.hook_title LIKE ?)"
        ]
        params: list[Any] = [f"%({d_str})%", f"%({d_str})%", f"%({d_str})%", f"%{d_str}%"]

        if saint_name and saint_name.strip():
            clean_name = saint_name.strip()
            clauses.append("(v.reference LIKE ? OR p.caption LIKE ? OR p.hook_title LIKE ?)")
            params.extend([f"%{clean_name}%", f"%{clean_name}%", f"%{clean_name.upper()}%"])

        where_inner = " OR ".join(clauses)
        where_sql = f"v.source = 'saint' AND ({where_inner})"
        query = f"""
            SELECT p.*, q.status AS queue_status
            FROM posts p
            JOIN verses v ON v.id = p.verse_id
            LEFT JOIN queue q ON q.post_id = p.id
            WHERE {where_sql}
            ORDER BY p.id DESC LIMIT 1
        """
        row = self.conn.execute(query, params).fetchone()
        if row:
            post_dict = dict(row)
            if post_dict.get("queue_status") == "sent" or post_dict.get("status") == "published":
                post_dict["is_sent"] = True
            return True, post_dict

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

    def get_recent_prayer_requests(self, limit: int = 10, days: int = 14) -> list[dict[str, Any]]:
        """Busca comentários recentes de seguidores com pedidos de oração ou fé."""
        rows = self.conn.execute(
            """SELECT * FROM comment_interactions
               WHERE (sentiment IN ('prayer_request', 'faith', 'gratitude')
                  OR comment_text LIKE '%orai%'
                  OR comment_text LIKE '%oração%'
                  OR comment_text LIKE '%oracao%'
                  OR comment_text LIKE '%amém%'
                  OR comment_text LIKE '%amem%'
                  OR comment_text LIKE '%peço%'
                  OR comment_text LIKE '%reze%')
                 AND created_at >= datetime('now', ?)
               ORDER BY id DESC LIMIT ?""",
            (f"-{days} days", limit)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Post Metrics (Analytics) ──────────────────────────────────────────

    def upsert_post_metric(
        self,
        buffer_post_id: str,
        platform: str,
        external_link: str = "",
        sent_at: str = "",
        text_snippet: str = "",
        theme: str = "faith",
        post_hour: int = 0,
        views: int = 0,
        likes: int = 0,
        comments: int = 0,
        shares: int = 0,
        reach: int = 0,
        engagement_rate: float = 0.0,
        watch_time_sec: float = 0.0,
        raw_metrics: str = "{}",
    ) -> None:
        """Insere ou atualiza métricas de engajamento de um post."""
        self.conn.execute(
            """INSERT INTO post_metrics (
                   buffer_post_id, platform, external_link, sent_at, text_snippet,
                   theme, post_hour, views, likes, comments, shares, reach,
                   engagement_rate, watch_time_sec, raw_metrics, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(buffer_post_id, platform) DO UPDATE SET
                   external_link = excluded.external_link,
                   sent_at = CASE WHEN excluded.sent_at != '' THEN excluded.sent_at ELSE post_metrics.sent_at END,
                   text_snippet = CASE WHEN excluded.text_snippet != '' THEN excluded.text_snippet ELSE post_metrics.text_snippet END,
                   theme = excluded.theme,
                   post_hour = excluded.post_hour,
                   views = excluded.views,
                   likes = excluded.likes,
                   comments = excluded.comments,
                   shares = excluded.shares,
                   reach = excluded.reach,
                   engagement_rate = excluded.engagement_rate,
                   watch_time_sec = excluded.watch_time_sec,
                   raw_metrics = excluded.raw_metrics,
                   updated_at = excluded.updated_at
            """,
            (
                buffer_post_id, platform, external_link, sent_at, text_snippet,
                theme, post_hour, views, likes, comments, shares, reach,
                engagement_rate, watch_time_sec, raw_metrics, _now_iso()
            )
        )
        self.conn.commit()

    def get_analytics_summary(self) -> dict[str, Any]:
        """Gera resumo consolidado das métricas de todas as redes."""
        row_totals = self.conn.execute(
            """SELECT
                   COUNT(*) as total_posts,
                   COALESCE(SUM(views), 0) as total_views,
                   COALESCE(SUM(likes), 0) as total_likes,
                   COALESCE(SUM(comments), 0) as total_comments,
                   COALESCE(SUM(shares), 0) as total_shares,
                   COALESCE(SUM(reach), 0) as total_reach,
                   ROUND(AVG(engagement_rate), 2) as avg_engagement_rate
               FROM post_metrics"""
        ).fetchone()

        by_platform = self.conn.execute(
            """SELECT
                   platform,
                   COUNT(*) as posts_count,
                   COALESCE(SUM(views), 0) as views,
                   COALESCE(SUM(likes), 0) as likes,
                   COALESCE(SUM(comments), 0) as comments,
                   COALESCE(SUM(shares), 0) as shares,
                   ROUND(AVG(engagement_rate), 2) as avg_engagement_rate
               FROM post_metrics
               GROUP BY platform"""
        ).fetchall()

        return {
            "totals": dict(row_totals) if row_totals else {},
            "by_platform": [dict(r) for r in by_platform],
            "themes": self.get_theme_performance(),
            "hourly": self.get_hourly_performance(),
            "top_posts": self.get_top_posts(limit=5)
        }

    def get_top_posts(self, limit: int = 10, order_by: str = "views") -> list[dict[str, Any]]:
        """Retorna os posts mais engajados."""
        valid_orders = {"views", "likes", "comments", "shares", "engagement_rate"}
        sort_col = order_by if order_by in valid_orders else "views"
        rows = self.conn.execute(
            f"""SELECT id, buffer_post_id, platform, external_link, sent_at, text_snippet,
                       theme, post_hour, views, likes, comments, shares, engagement_rate, updated_at
                FROM post_metrics
                ORDER BY {sort_col} DESC, id DESC
                LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_theme_performance(self) -> list[dict[str, Any]]:
        """Retorna o desempenho médio por tema litúrgico."""
        rows = self.conn.execute(
            """SELECT
                   theme,
                   COUNT(*) as posts_count,
                   COALESCE(SUM(views), 0) as total_views,
                   ROUND(AVG(views), 1) as avg_views,
                   COALESCE(SUM(likes), 0) as total_likes,
                   COALESCE(SUM(comments), 0) as total_comments,
                   ROUND(AVG(engagement_rate), 2) as avg_engagement_rate
               FROM post_metrics
               GROUP BY theme
               ORDER BY avg_views DESC, total_views DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_hourly_performance(self) -> list[dict[str, Any]]:
        """Retorna o desempenho por horário de publicação."""
        rows = self.conn.execute(
            """SELECT
                   post_hour,
                   COUNT(*) as posts_count,
                   COALESCE(SUM(views), 0) as total_views,
                   ROUND(AVG(views), 1) as avg_views,
                   COALESCE(SUM(likes), 0) as total_likes,
                   COALESCE(SUM(comments), 0) as total_comments,
                   ROUND(AVG(engagement_rate), 2) as avg_engagement_rate
               FROM post_metrics
               GROUP BY post_hour
               ORDER BY avg_views DESC, total_views DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def close(self) -> None:
        self.conn.close()
        log.info("SQLite desconectado.")
