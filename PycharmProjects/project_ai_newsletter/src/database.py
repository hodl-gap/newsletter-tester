"""
SQLite Database for Article Storage and Deduplication

Stores articles with embeddings for:
1. URL deduplication across runs
2. Semantic similarity comparison
3. Historical analysis
"""

import sqlite3
import hashlib
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional

from src.tracking import debug_log


# =============================================================================
# Configuration
# =============================================================================

DB_PATH = Path(__file__).parent.parent / "data" / "articles.db"

SCHEMA_SQL = """
-- Main articles table with full metadata for deduplication
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    url_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,
    source_type TEXT DEFAULT 'rss',
    pub_date TEXT NOT NULL,
    region TEXT,
    category TEXT,
    layer TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    embedding BLOB
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_url_hash ON articles(url_hash);
CREATE INDEX IF NOT EXISTS idx_pub_date ON articles(pub_date);
CREATE INDEX IF NOT EXISTS idx_source ON articles(source);
-- Note: idx_source_type created via migration for existing DBs

-- Deduplication audit log
CREATE TABLE IF NOT EXISTS dedup_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp TIMESTAMP NOT NULL,
    original_url TEXT NOT NULL,
    duplicate_of_url TEXT,
    dedup_type TEXT NOT NULL,
    similarity_score REAL,
    llm_confirmed INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dedup_run ON dedup_log(run_timestamp);
"""


# =============================================================================
# Database Helper Class
# =============================================================================

class ArticleDatabase:
    """
    SQLite database for article storage and deduplication.

    Provides methods for:
    - URL existence checks (for exact dedup)
    - Article insertion with embeddings
    - Recent article retrieval (for semantic dedup)
    - Deduplication logging (for audit trail)
    """

    def __init__(self, db_path: Path = DB_PATH):
        """
        Initialize the database connection.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._ensure_data_dir()
        self._init_db()

    def _ensure_data_dir(self):
        """Ensure the data directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._connection() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

            # Migration: Add source_type column if missing (for existing DBs)
            self._migrate_source_type(conn)

        debug_log(f"[DB] Database initialized at {self.db_path}")

    def _migrate_source_type(self, conn):
        """Add source_type column to existing databases."""
        try:
            # Check if column exists
            cursor = conn.execute("PRAGMA table_info(articles)")
            columns = [row[1] for row in cursor.fetchall()]

            if "source_type" not in columns:
                debug_log("[DB] Migrating: Adding source_type column")
                conn.execute("ALTER TABLE articles ADD COLUMN source_type TEXT DEFAULT 'rss'")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_source_type ON articles(source_type)")
                conn.commit()
                debug_log("[DB] Migration complete: source_type column added")
        except Exception as e:
            debug_log(f"[DB] Migration warning: {e}", "warning")

    # -------------------------------------------------------------------------
    # URL Deduplication
    # -------------------------------------------------------------------------

    def url_exists(self, url: str) -> bool:
        """
        Check if a URL already exists in the database.

        Args:
            url: The article URL to check.

        Returns:
            True if URL exists, False otherwise.
        """
        url_hash = self._hash_url(url)
        with self._connection() as conn:
            result = conn.execute(
                "SELECT 1 FROM articles WHERE url_hash = ?",
                (url_hash,)
            ).fetchone()
            return result is not None

    def get_existing_urls(self, urls: list[str]) -> set[str]:
        """
        Get the set of URLs that already exist in the database.

        Args:
            urls: List of URLs to check.

        Returns:
            Set of URLs that already exist.
        """
        if not urls:
            return set()

        url_hashes = {self._hash_url(url): url for url in urls}
        hash_list = list(url_hashes.keys())

        with self._connection() as conn:
            placeholders = ",".join("?" * len(hash_list))
            rows = conn.execute(
                f"SELECT url_hash FROM articles WHERE url_hash IN ({placeholders})",
                hash_list
            ).fetchall()

            existing_hashes = {row["url_hash"] for row in rows}
            return {url_hashes[h] for h in existing_hashes if h in url_hashes}

    @staticmethod
    def _hash_url(url: str) -> str:
        """Generate SHA256 hash of URL for fast lookup."""
        return hashlib.sha256(url.encode()).hexdigest()

    # -------------------------------------------------------------------------
    # Article Storage
    # -------------------------------------------------------------------------

    def insert_article(
        self,
        article: dict,
        embedding: Optional[np.ndarray] = None
    ) -> bool:
        """
        Insert a new article into the database.

        Args:
            article: Article dict with keys: url, title, contents/summary,
                     source, source_type, date, region, category, layer.
            embedding: Optional numpy array of embedding vector.

        Returns:
            True if inserted, False if URL already exists.
        """
        url = article.get("url", article.get("link", ""))
        url_hash = self._hash_url(url)

        embedding_blob = embedding.tobytes() if embedding is not None else None

        try:
            with self._connection() as conn:
                conn.execute(
                    """INSERT INTO articles
                       (url, url_hash, title, summary, source, source_type, pub_date,
                        region, category, layer, embedding)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        url,
                        url_hash,
                        article.get("title", ""),
                        article.get("contents", article.get("summary", "")),
                        article.get("source", ""),
                        article.get("source_type", "rss"),
                        article.get("date", article.get("pub_date", "")),
                        article.get("region"),
                        article.get("category"),
                        article.get("layer"),
                        embedding_blob
                    )
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            # URL already exists
            return False

    def insert_articles_batch(
        self,
        articles: list[dict],
        embeddings: Optional[list[np.ndarray]] = None
    ) -> int:
        """
        Insert multiple articles in a single transaction.

        Args:
            articles: List of article dicts.
            embeddings: Optional list of embedding arrays (same order as articles).

        Returns:
            Number of articles successfully inserted.
        """
        if embeddings is None:
            embeddings = [None] * len(articles)

        inserted = 0
        with self._connection() as conn:
            for article, embedding in zip(articles, embeddings):
                url = article.get("url", article.get("link", ""))
                url_hash = self._hash_url(url)
                embedding_blob = embedding.tobytes() if embedding is not None else None

                try:
                    conn.execute(
                        """INSERT INTO articles
                           (url, url_hash, title, summary, source, source_type, pub_date,
                            region, category, layer, embedding)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            url,
                            url_hash,
                            article.get("title", ""),
                            article.get("contents", article.get("summary", "")),
                            article.get("source", ""),
                            article.get("source_type", "rss"),
                            article.get("date", article.get("pub_date", "")),
                            article.get("region"),
                            article.get("category"),
                            article.get("layer"),
                            embedding_blob
                        )
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    # Skip duplicates
                    pass
            conn.commit()

        debug_log(f"[DB] Inserted {inserted}/{len(articles)} articles")
        return inserted

    # -------------------------------------------------------------------------
    # Historical Retrieval (for semantic dedup)
    # -------------------------------------------------------------------------

    def get_recent_articles(
        self,
        hours: int = 48,
        with_embeddings: bool = True
    ) -> list[dict]:
        """
        Get articles from the last N hours.

        Args:
            hours: Number of hours to look back (default: 48).
            with_embeddings: Whether to include embeddings (default: True).

        Returns:
            List of article dicts with embeddings if requested.
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d")

        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM articles WHERE pub_date >= ? ORDER BY pub_date DESC",
                (cutoff,)
            ).fetchall()

            articles = []
            for row in rows:
                article = self._row_to_dict(row, with_embeddings)
                articles.append(article)

            debug_log(f"[DB] Retrieved {len(articles)} articles from last {hours}h")
            return articles

    def get_article_count(self) -> int:
        """Get total number of articles in database."""
        with self._connection() as conn:
            result = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
            return result[0]

    def is_empty(self) -> bool:
        """Check if database has no articles."""
        return self.get_article_count() == 0

    def _row_to_dict(self, row: sqlite3.Row, with_embedding: bool = True) -> dict:
        """Convert database row to dict with optional numpy embedding."""
        d = dict(row)

        if with_embedding and d.get("embedding"):
            d["embedding"] = np.frombuffer(d["embedding"], dtype=np.float32)
        elif not with_embedding:
            d.pop("embedding", None)

        return d

    # -------------------------------------------------------------------------
    # Deduplication Logging
    # -------------------------------------------------------------------------

    def log_dedup(
        self,
        original_url: str,
        dedup_type: str,
        duplicate_of_url: Optional[str] = None,
        similarity_score: Optional[float] = None,
        llm_confirmed: Optional[bool] = None,
        run_timestamp: Optional[str] = None
    ):
        """
        Log a deduplication action for audit trail.

        Args:
            original_url: URL of the article being checked.
            dedup_type: Type of dedup ('url_exact', 'semantic_auto', 'semantic_llm').
            duplicate_of_url: URL of the matching article (if duplicate).
            similarity_score: Cosine similarity score (for semantic).
            llm_confirmed: Whether LLM confirmed the duplicate.
            run_timestamp: Timestamp of the run (default: now).
        """
        if run_timestamp is None:
            run_timestamp = datetime.now().isoformat()

        llm_value = None
        if llm_confirmed is not None:
            llm_value = 1 if llm_confirmed else 0

        with self._connection() as conn:
            conn.execute(
                """INSERT INTO dedup_log
                   (run_timestamp, original_url, duplicate_of_url,
                    dedup_type, similarity_score, llm_confirmed)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    run_timestamp,
                    original_url,
                    duplicate_of_url,
                    dedup_type,
                    similarity_score,
                    llm_value
                )
            )
            conn.commit()

    def log_dedup_batch(
        self,
        entries: list[dict],
        run_timestamp: Optional[str] = None
    ):
        """
        Log multiple deduplication actions in a single transaction.

        Args:
            entries: List of dicts with keys: original_url, dedup_type,
                     duplicate_of_url, similarity_score, llm_confirmed.
            run_timestamp: Shared timestamp for all entries.
        """
        if run_timestamp is None:
            run_timestamp = datetime.now().isoformat()

        with self._connection() as conn:
            for entry in entries:
                llm_value = None
                if entry.get("llm_confirmed") is not None:
                    llm_value = 1 if entry["llm_confirmed"] else 0

                conn.execute(
                    """INSERT INTO dedup_log
                       (run_timestamp, original_url, duplicate_of_url,
                        dedup_type, similarity_score, llm_confirmed)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        run_timestamp,
                        entry["original_url"],
                        entry.get("duplicate_of_url"),
                        entry["dedup_type"],
                        entry.get("similarity_score"),
                        llm_value
                    )
                )
            conn.commit()

        debug_log(f"[DB] Logged {len(entries)} dedup entries")

    def get_dedup_stats(self, hours: int = 24) -> dict:
        """
        Get deduplication statistics for the last N hours.

        Args:
            hours: Number of hours to look back.

        Returns:
            Dict with counts by dedup_type.
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        with self._connection() as conn:
            rows = conn.execute(
                """SELECT dedup_type, COUNT(*) as count
                   FROM dedup_log
                   WHERE run_timestamp >= ?
                   GROUP BY dedup_type""",
                (cutoff,)
            ).fetchall()

            return {row["dedup_type"]: row["count"] for row in rows}
