"""Stato persistente in SQLite: coda dei video, canali, eventi, costi LLM.

Una sola tabella ``videos`` fa da coda e da registro (D-007). Le migrazioni usano ``PRAGMA user_version``.
Ogni thread usa la propria connessione.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ytkb.models import VideoStatus
from ytkb.utils.timeutil import from_iso, plus_minutes, to_iso, utcnow

MIGRATIONS: list[str] = [
    # v1
    """
    CREATE TABLE channels (
        channel_id      TEXT PRIMARY KEY,
        title           TEXT NOT NULL DEFAULT '',
        handle          TEXT NOT NULL DEFAULT '',
        enabled         INTEGER NOT NULL DEFAULT 1,
        added_at        TEXT NOT NULL,
        last_polled_at  TEXT,
        last_poll_ok    INTEGER,
        last_poll_error TEXT
    );
    CREATE TABLE videos (
        video_id        TEXT PRIMARY KEY,
        channel_id      TEXT NOT NULL DEFAULT '',
        channel_title   TEXT NOT NULL DEFAULT '',
        title           TEXT NOT NULL DEFAULT '',
        published_at    TEXT,
        source          TEXT NOT NULL,
        status          TEXT NOT NULL,
        stage           TEXT,
        attempts        INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TEXT,
        last_error      TEXT,
        skip_reason     TEXT,
        archive_dir     TEXT,
        priority        INTEGER NOT NULL DEFAULT 0,
        requested_by    TEXT,
        cost_usd        REAL NOT NULL DEFAULT 0,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL,
        started_at      TEXT,
        finished_at     TEXT
    );
    CREATE INDEX idx_videos_due ON videos(status, next_attempt_at);
    CREATE INDEX idx_videos_channel ON videos(channel_id, published_at);
    CREATE TABLE events (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT,
        ts       TEXT NOT NULL,
        level    TEXT NOT NULL,
        stage    TEXT,
        message  TEXT NOT NULL
    );
    CREATE INDEX idx_events_video ON events(video_id, id);
    CREATE TABLE llm_calls (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id       TEXT,
        ts             TEXT NOT NULL,
        purpose        TEXT NOT NULL,
        model          TEXT NOT NULL,
        service_tier   TEXT,
        input_tokens   INTEGER NOT NULL DEFAULT 0,
        output_tokens  INTEGER NOT NULL DEFAULT 0,
        thought_tokens INTEGER NOT NULL DEFAULT 0,
        video_tokens   INTEGER NOT NULL DEFAULT 0,
        cost_usd       REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX idx_llm_calls_ts ON llm_calls(ts);
    CREATE TABLE kv (
        key   TEXT PRIMARY KEY,
        value TEXT
    );
    """,
]

ACTIVE_STATUSES = (VideoStatus.QUEUED, VideoStatus.WAITING, VideoStatus.PROCESSING)


@dataclass(frozen=True)
class VideoRow:
    video_id: str
    channel_id: str
    channel_title: str
    title: str
    published_at: str | None
    source: str
    status: str
    stage: str | None
    attempts: int
    next_attempt_at: str | None
    last_error: str | None
    skip_reason: str | None
    archive_dir: str | None
    priority: int
    requested_by: str | None
    cost_usd: float
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> VideoRow:
        return cls(**{k: row[k] for k in row.keys()})  # noqa: SIM118 (sqlite3.Row)


@dataclass(frozen=True)
class ChannelRow:
    channel_id: str
    title: str
    handle: str
    enabled: bool
    added_at: str
    last_polled_at: str | None
    last_poll_ok: bool | None
    last_poll_error: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ChannelRow:
        d = {k: row[k] for k in row.keys()}  # noqa: SIM118 (sqlite3.Row)
        d["enabled"] = bool(d["enabled"])
        d["last_poll_ok"] = None if d["last_poll_ok"] is None else bool(d["last_poll_ok"])
        return cls(**d)


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._local = threading.local()

    # --- connessione -----------------------------------------------------------------
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            c = sqlite3.connect(self.path, isolation_level=None, timeout=30)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA busy_timeout=30000")
            self._local.conn = c
        return c

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        c = self.conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
        except BaseException:
            c.execute("ROLLBACK")
            raise
        else:
            c.execute("COMMIT")

    def migrate(self) -> int:
        c = self.conn()
        version = c.execute("PRAGMA user_version").fetchone()[0]
        for i, script in enumerate(MIGRATIONS[version:], start=version + 1):
            c.executescript(f"BEGIN;\n{script}\nPRAGMA user_version={i};\nCOMMIT;")
        return c.execute("PRAGMA user_version").fetchone()[0]

    # --- video -----------------------------------------------------------------------
    def add_video(
        self,
        video_id: str,
        *,
        source: str,
        channel_id: str = "",
        channel_title: str = "",
        title: str = "",
        published_at: datetime | None = None,
        priority: int = 0,
        requested_by: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Inserisce un video in coda. Restituisce False se esisteva già (non lo tocca)."""
        ts = to_iso(now or utcnow())
        cur = self.conn().execute(
            """INSERT OR IGNORE INTO videos (video_id, channel_id, channel_title, title, published_at, source,
                   status, priority, requested_by, created_at, updated_at, next_attempt_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (video_id, channel_id, channel_title, title, to_iso(published_at), source,
             VideoStatus.QUEUED.value, priority, requested_by, ts, ts, ts),
        )
        return cur.rowcount == 1

    def get_video(self, video_id: str) -> VideoRow | None:
        row = self.conn().execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        return VideoRow.from_row(row) if row else None

    def update_video(self, video_id: str, now: datetime | None = None, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = to_iso(now or utcnow())
        cols = ", ".join(f"{k} = ?" for k in fields)
        values = [v.value if isinstance(v, VideoStatus) else v for v in fields.values()]
        self.conn().execute(f"UPDATE videos SET {cols} WHERE video_id = ?", (*values, video_id))

    def requeue(self, video_id: str, *, priority: int | None = None, requested_by: str | None = None,
                reset_attempts: bool = True, now: datetime | None = None) -> None:
        fields: dict[str, Any] = {
            "status": VideoStatus.QUEUED, "next_attempt_at": to_iso(now or utcnow()),
            "last_error": None, "skip_reason": None,
        }
        if reset_attempts:
            fields["attempts"] = 0
        if priority is not None:
            fields["priority"] = priority
        if requested_by is not None:
            fields["requested_by"] = requested_by
        self.update_video(video_id, now=now, **fields)

    def claim_next_due(self, now: datetime | None = None) -> VideoRow | None:
        """Prende (in modo atomico) il prossimo video da lavorare e lo marca ``processing``."""
        ts = to_iso(now or utcnow())
        with self.transaction() as c:
            row = c.execute(
                """SELECT * FROM videos
                   WHERE status IN (?, ?) AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                   ORDER BY priority DESC, next_attempt_at ASC, created_at ASC LIMIT 1""",
                (VideoStatus.QUEUED.value, VideoStatus.WAITING.value, ts),
            ).fetchone()
            if row is None:
                return None
            c.execute(
                "UPDATE videos SET status = ?, started_at = ?, updated_at = ? WHERE video_id = ?",
                (VideoStatus.PROCESSING.value, ts, ts, row["video_id"]),
            )
        return self.get_video(row["video_id"])

    def release_stale(self, older_than_minutes: float, now: datetime | None = None) -> int:
        """Rimette in coda i video rimasti ``processing`` troppo a lungo (es. dopo un crash)."""
        now = now or utcnow()
        limit = to_iso(plus_minutes(now, -older_than_minutes))
        cur = self.conn().execute(
            "UPDATE videos SET status = ?, updated_at = ? WHERE status = ? AND (started_at IS NULL OR started_at < ?)",
            (VideoStatus.QUEUED.value, to_iso(now), VideoStatus.PROCESSING.value, limit),
        )
        return cur.rowcount

    def list_videos(self, limit: int = 20, status: str | None = None) -> list[VideoRow]:
        if status:
            rows = self.conn().execute(
                "SELECT * FROM videos WHERE status = ? ORDER BY updated_at DESC LIMIT ?", (status, limit)
            ).fetchall()
        else:
            rows = self.conn().execute("SELECT * FROM videos ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [VideoRow.from_row(r) for r in rows]

    def videos_of_channel(self, channel_id: str, status: str | None = None) -> list[VideoRow]:
        sql = "SELECT * FROM videos WHERE channel_id = ?"
        args: list[Any] = [channel_id]
        if status:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY published_at DESC, created_at DESC"
        return [VideoRow.from_row(r) for r in self.conn().execute(sql, args).fetchall()]

    def count_by_status(self) -> dict[str, int]:
        rows = self.conn().execute("SELECT status, COUNT(*) AS n FROM videos GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    def known_video_ids(self, video_ids: list[str]) -> set[str]:
        if not video_ids:
            return set()
        marks = ",".join("?" * len(video_ids))
        rows = self.conn().execute(f"SELECT video_id FROM videos WHERE video_id IN ({marks})", video_ids).fetchall()
        return {r["video_id"] for r in rows}

    # --- eventi ----------------------------------------------------------------------
    def add_event(self, video_id: str | None, level: str, message: str, stage: str | None = None,
                  now: datetime | None = None) -> None:
        self.conn().execute(
            "INSERT INTO events (video_id, ts, level, stage, message) VALUES (?, ?, ?, ?, ?)",
            (video_id, to_iso(now or utcnow()), level, stage, message[:4000]),
        )

    def events_of(self, video_id: str, limit: int = 50) -> list[sqlite3.Row]:
        return self.conn().execute(
            "SELECT * FROM events WHERE video_id = ? ORDER BY id DESC LIMIT ?", (video_id, limit)
        ).fetchall()

    # --- costi LLM -------------------------------------------------------------------
    def record_llm_call(self, *, video_id: str | None, purpose: str, model: str, service_tier: str | None,
                        input_tokens: int, output_tokens: int, thought_tokens: int, video_tokens: int,
                        cost_usd: float, now: datetime | None = None) -> None:
        self.conn().execute(
            """INSERT INTO llm_calls (video_id, ts, purpose, model, service_tier, input_tokens, output_tokens,
                   thought_tokens, video_tokens, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (video_id, to_iso(now or utcnow()), purpose, model, service_tier, input_tokens, output_tokens,
             thought_tokens, video_tokens, cost_usd),
        )
        if video_id:
            self.conn().execute("UPDATE videos SET cost_usd = cost_usd + ? WHERE video_id = ?", (cost_usd, video_id))

    def llm_cost_since(self, since: datetime) -> float:
        row = self.conn().execute("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE ts >= ?",
                                  (to_iso(since),)).fetchone()
        return float(row[0])

    def llm_cost_summary(self, since: datetime) -> list[sqlite3.Row]:
        return self.conn().execute(
            """SELECT substr(ts, 1, 10) AS day, purpose, model, COUNT(*) AS calls,
                      SUM(input_tokens) AS input_tokens, SUM(output_tokens + thought_tokens) AS output_tokens,
                      SUM(cost_usd) AS cost_usd
               FROM llm_calls WHERE ts >= ? GROUP BY day, purpose, model ORDER BY day DESC, purpose""",
            (to_iso(since),),
        ).fetchall()

    # --- canali ----------------------------------------------------------------------
    def upsert_channel(self, channel_id: str, title: str = "", handle: str = "", enabled: bool = True,
                       now: datetime | None = None) -> None:
        self.conn().execute(
            """INSERT INTO channels (channel_id, title, handle, enabled, added_at) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(channel_id) DO UPDATE SET
                   title = CASE WHEN excluded.title != '' THEN excluded.title ELSE channels.title END,
                   handle = CASE WHEN excluded.handle != '' THEN excluded.handle ELSE channels.handle END,
                   enabled = excluded.enabled""",
            (channel_id, title, handle, int(enabled), to_iso(now or utcnow())),
        )

    def get_channel(self, channel_id: str) -> ChannelRow | None:
        row = self.conn().execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,)).fetchone()
        return ChannelRow.from_row(row) if row else None

    def list_channels(self, only_enabled: bool = False) -> list[ChannelRow]:
        sql = "SELECT * FROM channels"
        if only_enabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY title COLLATE NOCASE"
        return [ChannelRow.from_row(r) for r in self.conn().execute(sql).fetchall()]

    def mark_channel_polled(self, channel_id: str, ok: bool, error: str | None = None,
                            now: datetime | None = None) -> None:
        self.conn().execute(
            "UPDATE channels SET last_polled_at = ?, last_poll_ok = ?, last_poll_error = ? WHERE channel_id = ?",
            (to_iso(now or utcnow()), int(ok), error, channel_id),
        )

    # --- chiave/valore ---------------------------------------------------------------
    def kv_get(self, key: str, default: str | None = None) -> str | None:
        row = self.conn().execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def kv_set(self, key: str, value: str | None) -> None:
        self.conn().execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET "
                            "value = excluded.value", (key, value))


def open_db(path: Path) -> Database:
    db = Database(path)
    db.migrate()
    return db


def is_due(row: VideoRow, now: datetime | None = None) -> bool:
    nxt = from_iso(row.next_attempt_at)
    return nxt is None or nxt <= (now or utcnow())
