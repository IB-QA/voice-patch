"""Durable record of every voice exchange, keyed by session.

Two jobs:

* ``history``: every spoken line (what the user said, what the agent said) is
  stored per session, so a dashboard, an editor extension, or another agent can
  list sessions and read a conversation back.
* ``undelivered`` (see ``conversation_jobs``): a transcript that finished while
  no agent was polling is kept until something collects it, so the user's words
  are never lost when an agent ends its turn early.

One MCP server process serves one coding-tool session, so the session key is
made once per process. Set ``VOICEMODE_SESSION_KEY`` to pin it (a client hook
can do this with its own session id).
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("voicemode.inbox")

ROLE_FOR_TYPE = {"stt": "user", "tts": "agent"}


def new_session_key() -> str:
    explicit = os.environ.get("VOICEMODE_SESSION_KEY", "").strip()
    if explicit:
        return explicit
    return f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"


SESSION_KEY = new_session_key()


class Inbox:
    """SQLite store. A new connection per call keeps it safe across threads."""

    def __init__(self, path: Path, session_key: Optional[str] = None) -> None:
        self.path = Path(path)
        self.session_key = session_key or SESSION_KEY
        self._lock = threading.Lock()
        self._ready = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        if not self._ready:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_key TEXT PRIMARY KEY,
                    project_path TEXT,
                    started_at REAL NOT NULL,
                    last_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_key TEXT NOT NULL,
                    ts REAL NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    conversation_id TEXT
                );
                CREATE INDEX IF NOT EXISTS messages_session
                    ON messages(session_key, id);
                """
            )
            self._ready = True
        return conn

    def record(
        self,
        utterance_type: str,
        text: str,
        project_path: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> None:
        """Store one line. Never raises: voice must not break over bookkeeping."""
        role = ROLE_FOR_TYPE.get(utterance_type)
        if role is None or not text:
            return
        now = time.time()
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO sessions(session_key, project_path, started_at, last_at)"
                    " VALUES(?,?,?,?)"
                    " ON CONFLICT(session_key) DO UPDATE SET last_at=excluded.last_at",
                    (self.session_key, project_path, now, now),
                )
                conn.execute(
                    "INSERT INTO messages(session_key, ts, role, text, conversation_id)"
                    " VALUES(?,?,?,?,?)",
                    (self.session_key, now, role, text, conversation_id),
                )
        except (sqlite3.Error, OSError) as exc:
            logger.debug("Could not record to the inbox: %s", exc)

    def sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT s.session_key, s.project_path, s.started_at, s.last_at,"
                    " (SELECT COUNT(*) FROM messages m WHERE m.session_key=s.session_key)"
                    " AS messages FROM sessions s ORDER BY s.last_at DESC LIMIT ?",
                    (max(1, min(int(limit), 500)),),
                ).fetchall()
        except (sqlite3.Error, OSError):
            return []
        return [dict(row) for row in rows]

    def history(
        self, session_key: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        key = session_key or self.session_key
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT id, ts, role, text FROM messages WHERE session_key=?"
                    " ORDER BY id DESC LIMIT ?",
                    (key, max(1, min(int(limit), 500))),
                ).fetchall()
        except (sqlite3.Error, OSError):
            return []
        return [dict(row) for row in reversed(rows)]
