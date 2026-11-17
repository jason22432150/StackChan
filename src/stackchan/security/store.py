"""Security SQLite：配對工作階段、授權 grant、政策版本。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stackchan.contracts.authz import Principal
from stackchan.security.identity import TokenHasher


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SecurityStore:
    """獨立安全資料庫（憑證僅存雜湊）。"""

    def __init__(self, path: str | Path, *, hasher: TokenHasher, read_only: bool = False) -> None:
        self.path = Path(path)
        self._hasher = hasher
        location = f"{self.path.resolve().as_uri()}?mode=ro" if read_only else self.path
        self._conn = sqlite3.connect(location, uri=read_only, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA foreign_keys = ON")
            if read_only:
                self._conn.execute(
                    "SELECT 1 FROM subjects, authorization_grants, privacy_policies, device_policy_bindings LIMIT 0"
                )
            else:
                self.initialize_schema()
        except sqlite3.Error:
            self._conn.close()
            raise

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SecurityStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def initialize_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS subjects (
                subject_id TEXT PRIMARY KEY,
                subject_type TEXT NOT NULL CHECK(
                    subject_type IN ('bridge', 'device', 'dashboard', 'admin')
                ),
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pairing_sessions (
                pairing_id TEXT PRIMARY KEY,
                subject_type TEXT NOT NULL,
                display_name TEXT NOT NULL,
                user_code_hash TEXT NOT NULL,
                status TEXT NOT NULL CHECK(
                    status IN ('pending', 'approved', 'rejected', 'completed', 'expired')
                ),
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                confirmed_at TEXT,
                completed_at TEXT,
                subject_id TEXT
            );

            CREATE TABLE IF NOT EXISTS authorization_grants (
                grant_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
                subject_type TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                scopes_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT
            );

            CREATE TABLE IF NOT EXISTS privacy_policies (
                policy_id TEXT NOT NULL,
                version TEXT NOT NULL,
                privacy_mode TEXT NOT NULL CHECK(
                    privacy_mode IN ('private', 'public', 'strict')
                ),
                valid_until TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0, 1)),
                created_at TEXT NOT NULL,
                PRIMARY KEY (policy_id, version)
            );

            CREATE TABLE IF NOT EXISTS device_policy_bindings (
                device_id TEXT PRIMARY KEY,
                policy_id TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                bound_at TEXT NOT NULL,
                FOREIGN KEY (policy_id, policy_version)
                    REFERENCES privacy_policies(policy_id, version)
            );

            CREATE INDEX IF NOT EXISTS idx_grants_subject
                ON authorization_grants(subject_id, revoked_at);
            CREATE INDEX IF NOT EXISTS idx_policies_revoked
                ON privacy_policies(revoked, valid_until);
            """
        )

    def create_pairing_session(
        self,
        *,
        pairing_id: str,
        subject_type: str,
        display_name: str,
        user_code: str,
        expires_at: str,
    ) -> None:
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO pairing_sessions(
                pairing_id, subject_type, display_name, user_code_hash, status,
                created_at, expires_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                pairing_id,
                subject_type,
                display_name,
                self._hasher.hash_token(user_code),
                now,
                expires_at,
            ),
        )

    def get_pairing(self, pairing_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM pairing_sessions WHERE pairing_id = ?",
            (pairing_id,),
        ).fetchone()
        return dict(row) if row else None

    def verify_pairing_code(self, pairing_id: str, user_code: str) -> bool:
        row = self.get_pairing(pairing_id)
        if row is None:
            return False
        return self._hasher.verify(user_code, row["user_code_hash"])

    def set_pairing_status(
        self,
        pairing_id: str,
        status: str,
        *,
        subject_id: str | None = None,
    ) -> None:
        now = _utc_now()
        if status == "approved":
            self._conn.execute(
                """
                UPDATE pairing_sessions
                SET status = ?, confirmed_at = ?
                WHERE pairing_id = ?
                """,
                (status, now, pairing_id),
            )
        elif status == "completed":
            self._conn.execute(
                """
                UPDATE pairing_sessions
                SET status = ?, completed_at = ?, subject_id = ?
                WHERE pairing_id = ?
                """,
                (status, now, subject_id, pairing_id),
            )
        else:
            self._conn.execute(
                "UPDATE pairing_sessions SET status = ? WHERE pairing_id = ?",
                (status, pairing_id),
            )

    def upsert_subject(self, subject_id: str, subject_type: str, display_name: str) -> None:
        self._conn.execute(
            """
            INSERT INTO subjects(subject_id, subject_type, display_name, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(subject_id) DO UPDATE SET
                display_name = excluded.display_name
            """,
            (subject_id, subject_type, display_name, _utc_now()),
        )

    def issue_grant(
        self,
        *,
        grant_id: str,
        subject_id: str,
        subject_type: str,
        token_plaintext: str,
        scopes: list[str],
        expires_at: str,
    ) -> None:
        token_hash = self._hasher.hash_token(token_plaintext)
        self._conn.execute(
            """
            INSERT INTO authorization_grants(
                grant_id, subject_id, subject_type, token_hash, scopes_json,
                created_at, expires_at, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                grant_id,
                subject_id,
                subject_type,
                token_hash,
                json.dumps(sorted(scopes)),
                _utc_now(),
                expires_at,
            ),
        )

    def resolve_principal(self, token_plaintext: str, *, now: str | None = None) -> Principal | None:
        token_hash = self._hasher.hash_token(token_plaintext)
        row = self._conn.execute(
            """
            SELECT subject_id, subject_type, scopes_json, expires_at, revoked_at
            FROM authorization_grants WHERE token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        current = now or _utc_now()
        if row["revoked_at"] is not None:
            return Principal(
                subject_id=row["subject_id"],
                subject_type=row["subject_type"],
                scopes=frozenset(json.loads(row["scopes_json"])),
                revoked=True,
            )
        if row["expires_at"] <= current:
            return None
        return Principal(
            subject_id=row["subject_id"],
            subject_type=row["subject_type"],
            scopes=frozenset(json.loads(row["scopes_json"])),
            revoked=False,
        )

    def revoke_grant_by_token(self, token_plaintext: str) -> bool:
        token_hash = self._hasher.hash_token(token_plaintext)
        cur = self._conn.execute(
            """
            UPDATE authorization_grants
            SET revoked_at = ?
            WHERE token_hash = ? AND revoked_at IS NULL
            """,
            (_utc_now(), token_hash),
        )
        return cur.rowcount > 0

    def count_plaintext_token_columns(self) -> int:
        """審查輔助：確認 grants 表沒有明文 token 欄位。"""
        rows = self._conn.execute("PRAGMA table_info(authorization_grants)").fetchall()
        forbidden = {"token", "access_token", "token_plaintext", "secret"}
        return sum(1 for row in rows if row["name"].lower() in forbidden)

    def publish_policy(
        self,
        *,
        policy_id: str,
        version: str,
        privacy_mode: str,
        valid_until: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO privacy_policies(
                policy_id, version, privacy_mode, valid_until, revoked, created_at
            ) VALUES (?, ?, ?, ?, 0, ?)
            """,
            (policy_id, version, privacy_mode, valid_until, _utc_now()),
        )

    def revoke_policy(self, policy_id: str, version: str) -> None:
        self._conn.execute(
            """
            UPDATE privacy_policies SET revoked = 1
            WHERE policy_id = ? AND version = ?
            """,
            (policy_id, version),
        )

    def get_policy(self, policy_id: str, version: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT policy_id, version, privacy_mode, valid_until, revoked, created_at
            FROM privacy_policies WHERE policy_id = ? AND version = ?
            """,
            (policy_id, version),
        ).fetchone()
        return dict(row) if row else None

    def bind_device_policy(self, device_id: str, policy_id: str, policy_version: str) -> None:
        self._conn.execute(
            """
            INSERT INTO device_policy_bindings(device_id, policy_id, policy_version, bound_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                policy_id = excluded.policy_id,
                policy_version = excluded.policy_version,
                bound_at = excluded.bound_at
            """,
            (device_id, policy_id, policy_version, _utc_now()),
        )

    def get_device_binding(self, device_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT device_id, policy_id, policy_version, bound_at
            FROM device_policy_bindings WHERE device_id = ?
            """,
            (device_id,),
        ).fetchone()
        return dict(row) if row else None
