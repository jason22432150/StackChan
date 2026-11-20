"""SQLite schema 草案與最小初始化（Phase 0）。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

INTEREST_IDS = ("reading", "coding", "food", "exploration", "creative")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pet_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  mood INTEGER NOT NULL DEFAULT 50 CHECK (mood BETWEEN 0 AND 100),
  energy INTEGER NOT NULL DEFAULT 70 CHECK (energy BETWEEN 0 AND 100),
  affinity INTEGER NOT NULL DEFAULT 50 CHECK (affinity BETWEEN 0 AND 100),
  activity INTEGER NOT NULL DEFAULT 50 CHECK (activity BETWEEN 0 AND 100),
  current_action TEXT NOT NULL DEFAULT 'idle',
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pet_interests (
  interest_id TEXT PRIMARY KEY,
  score INTEGER NOT NULL DEFAULT 50 CHECK (score BETWEEN 0 AND 100),
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pet_activity_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,
  interest_id TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  interrupted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS user_preferences (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  summary TEXT NOT NULL,
  importance INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proactive_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  decision TEXT NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_events (
  event_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  title TEXT,
  summary TEXT,
  confidence TEXT NOT NULL DEFAULT 'unverified',
  created_at TEXT NOT NULL,
  read_at TEXT
);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Storage:
    """最小 SQLite 存取層；Phase 0 只做 schema 初始化與讀取。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self.initialize()

    def close(self) -> None:
        self._conn.close()

    def initialize(self) -> None:
        self._conn.executescript(SCHEMA_SQL)
        row = self._conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            self._conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
        now = utc_now_iso()
        existing = self._conn.execute("SELECT id FROM pet_state WHERE id = 1").fetchone()
        if existing is None:
            self._conn.execute(
                """
                INSERT INTO pet_state(id, mood, energy, affinity, activity, current_action, updated_at)
                VALUES (1, 50, 70, 50, 50, 'idle', ?)
                """,
                (now,),
            )
        for interest_id in INTEREST_IDS:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO pet_interests(interest_id, score, updated_at)
                VALUES (?, 50, ?)
                """,
                (interest_id, now),
            )
        self._conn.commit()

    def get_schema_version(self) -> int:
        row = self._conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        return int(row["version"]) if row else 0

    def list_interests(self) -> dict[str, int]:
        rows = self._conn.execute("SELECT interest_id, score FROM pet_interests").fetchall()
        return {str(r["interest_id"]): int(r["score"]) for r in rows}
