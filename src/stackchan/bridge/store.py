"""
Bridge SQLite：observations／event_log／outbox／sync_state。

不變式：
- event_log 與 outbox 必須同交易寫入
- (bridge_id, epoch, bridge_sequence) UNIQUE
- observation_id UNIQUE
- ACK 連續游標不得跳過缺口
- 斷電後 pending outbox 必須可重試
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from stackchan.contracts import ContractValidationError, validate_agent_event


class BridgeStoreError(ValueError):
    """Bridge 儲存規則違反。"""


@dataclass(frozen=True, slots=True)
class IngestResult:
    """事件寫入結果。"""

    event_id: str
    observation_id: str
    bridge_sequence: int
    epoch: str
    created: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class BridgeStore:
    """單一 Bridge 的本機 SQLite Outbox 儲存。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self.initialize_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> BridgeStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def initialize_schema(self) -> None:
        """建立 Bridge 表格與索引。"""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bridge_settings (
                bridge_id TEXT PRIMARY KEY,
                current_epoch TEXT NOT NULL,
                next_sequence INTEGER NOT NULL CHECK(next_sequence >= 1)
            );

            CREATE TABLE IF NOT EXISTS observations (
                observation_id TEXT PRIMARY KEY,
                adapter_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                source_event_id TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS event_log (
                event_id TEXT PRIMARY KEY,
                observation_id TEXT NOT NULL REFERENCES observations(observation_id),
                bridge_id TEXT NOT NULL,
                epoch TEXT NOT NULL,
                bridge_sequence INTEGER NOT NULL CHECK(bridge_sequence >= 1),
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(bridge_id, epoch, bridge_sequence)
            );

            CREATE TABLE IF NOT EXISTS outbox (
                event_id TEXT PRIMARY KEY REFERENCES event_log(event_id),
                status TEXT NOT NULL CHECK(status IN ('pending', 'acked', 'failed')),
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
                last_error TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                bridge_id TEXT NOT NULL,
                epoch TEXT NOT NULL,
                contiguous_acked_sequence INTEGER NOT NULL DEFAULT 0
                    CHECK(contiguous_acked_sequence >= 0),
                PRIMARY KEY (bridge_id, epoch)
            );

            CREATE INDEX IF NOT EXISTS idx_outbox_status
                ON outbox(status, attempt_count);
            CREATE INDEX IF NOT EXISTS idx_event_log_epoch_seq
                ON event_log(bridge_id, epoch, bridge_sequence);
            """
        )

    def ensure_bridge(self, bridge_id: str, *, epoch: str = "epoch-1") -> None:
        """初始化 bridge_settings 與 sync_state。"""
        if not bridge_id or not epoch:
            raise BridgeStoreError("bridge_id／epoch 不可為空")
        now_epoch = epoch
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT bridge_id FROM bridge_settings WHERE bridge_id = ?",
                (bridge_id,),
            ).fetchone()
            if row is None:
                self._conn.execute(
                    """
                    INSERT INTO bridge_settings(bridge_id, current_epoch, next_sequence)
                    VALUES (?, ?, 1)
                    """,
                    (bridge_id, now_epoch),
                )
                self._conn.execute(
                    """
                    INSERT INTO sync_state(bridge_id, epoch, contiguous_acked_sequence)
                    VALUES (?, ?, 0)
                    """,
                    (bridge_id, now_epoch),
                )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def rotate_epoch(self, bridge_id: str, new_epoch: str) -> None:
        """安裝重建或 sequence 歸零時啟用新 epoch。"""
        if not new_epoch:
            raise BridgeStoreError("new_epoch 不可為空")
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            settings = self._require_settings(bridge_id)
            if new_epoch == settings["current_epoch"]:
                raise BridgeStoreError("new_epoch 必須不同於 current_epoch")
            self._conn.execute(
                """
                UPDATE bridge_settings
                SET current_epoch = ?, next_sequence = 1
                WHERE bridge_id = ?
                """,
                (new_epoch, bridge_id),
            )
            self._conn.execute(
                """
                INSERT INTO sync_state(bridge_id, epoch, contiguous_acked_sequence)
                VALUES (?, ?, 0)
                ON CONFLICT(bridge_id, epoch) DO NOTHING
                """,
                (bridge_id, new_epoch),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def allocate_sequence(self, bridge_id: str) -> tuple[str, int]:
        """
        配置下一個 bridge_sequence（獨立交易）。

        Returns:
            (epoch, bridge_sequence)
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            settings = self._require_settings(bridge_id)
            epoch = settings["current_epoch"]
            sequence = int(settings["next_sequence"])
            self._conn.execute(
                """
                UPDATE bridge_settings
                SET next_sequence = next_sequence + 1
                WHERE bridge_id = ?
                """,
                (bridge_id,),
            )
            self._conn.execute("COMMIT")
            return epoch, sequence
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def ingest_event(self, event: dict[str, Any]) -> IngestResult:
        """
        原子寫入 observation + event_log + outbox(pending)。

        同一 event_id 重送視為冪等成功（created=False）。
        """
        try:
            validated = validate_agent_event(event)
        except ContractValidationError as exc:
            raise BridgeStoreError(str(exc)) from exc

        bridge_id = validated["bridge_id"]
        epoch = validated["epoch"]
        sequence = int(validated["bridge_sequence"])
        event_id = validated["event_id"]
        observation_id = validated["observation_id"]

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            settings = self._require_settings(bridge_id)
            if epoch != settings["current_epoch"]:
                raise BridgeStoreError(
                    f"事件 epoch={epoch!r} 與 current_epoch={settings['current_epoch']!r} 不符"
                )

            existing = self._conn.execute(
                "SELECT event_id, observation_id, bridge_sequence, epoch, payload_json "
                "FROM event_log WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if existing is not None:
                if json.loads(existing["payload_json"]) != validated:
                    raise BridgeStoreError(f"event_id={event_id} 已存在但 payload 不同")
                self._conn.execute("COMMIT")
                return IngestResult(
                    event_id=event_id,
                    observation_id=existing["observation_id"],
                    bridge_sequence=int(existing["bridge_sequence"]),
                    epoch=existing["epoch"],
                    created=False,
                )

            if sequence != int(settings["next_sequence"]):
                raise BridgeStoreError(
                    f"bridge_sequence 必須為 {settings['next_sequence']}，收到 {sequence}"
                )

            now = _utc_now()
            self._conn.execute(
                """
                INSERT INTO observations(
                    observation_id, adapter_id, observed_at, source_event_id, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    validated["adapter_id"],
                    validated["observed_at"],
                    validated.get("source_event_id"),
                    now,
                ),
            )
            self._conn.execute(
                """
                INSERT INTO event_log(
                    event_id, observation_id, bridge_id, epoch, bridge_sequence,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    observation_id,
                    bridge_id,
                    epoch,
                    sequence,
                    json.dumps(validated, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            self._conn.execute(
                """
                INSERT INTO outbox(event_id, status, attempt_count, last_error, updated_at)
                VALUES (?, 'pending', 0, NULL, ?)
                """,
                (event_id, now),
            )
            self._conn.execute(
                """
                UPDATE bridge_settings
                SET next_sequence = ?
                WHERE bridge_id = ?
                """,
                (sequence + 1, bridge_id),
            )
            self._conn.execute("COMMIT")
            return IngestResult(
                event_id=event_id,
                observation_id=observation_id,
                bridge_sequence=sequence,
                epoch=epoch,
                created=True,
            )
        except sqlite3.IntegrityError as exc:
            self._conn.execute("ROLLBACK")
            raise BridgeStoreError(f"唯一約束衝突: {exc}") from exc
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def list_pending(self, bridge_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """依 bridge_sequence 列出 pending outbox 事件。"""
        rows = self._conn.execute(
            """
            SELECT e.payload_json
            FROM outbox o
            JOIN event_log e ON e.event_id = o.event_id
            WHERE e.bridge_id = ? AND o.status = 'pending'
            ORDER BY e.bridge_sequence ASC
            LIMIT ?
            """,
            (bridge_id, limit),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def mark_upload_attempts(self, event_ids: list[str], *, error: str | None = None) -> None:
        """上傳嘗試：增加 attempt_count；可記錄暫時錯誤但仍保持 pending。"""
        if not event_ids:
            return
        now = _utc_now()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for event_id in event_ids:
                self._conn.execute(
                    """
                    UPDATE outbox
                    SET attempt_count = attempt_count + 1,
                        last_error = ?,
                        updated_at = ?
                    WHERE event_id = ? AND status = 'pending'
                    """,
                    (error, now, event_id),
                )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def apply_batch_ack(
        self,
        *,
        bridge_id: str,
        epoch: str,
        accepted_event_ids: list[str],
        missing_sequences: list[int] | None = None,
    ) -> int:
        """
        套用 Coordinator ACK：標記 accepted，並推進連續游標（不跳過缺口）。

        Returns:
            更新後的 contiguous_acked_sequence
        """
        missing = set(missing_sequences or [])
        now = _utc_now()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for event_id in accepted_event_ids:
                row = self._conn.execute(
                    """
                    SELECT e.bridge_id, e.epoch, e.bridge_sequence
                    FROM event_log e
                    WHERE e.event_id = ?
                    """,
                    (event_id,),
                ).fetchone()
                if row is None:
                    raise BridgeStoreError(f"ACK 未知 event_id={event_id}")
                if row["bridge_id"] != bridge_id or row["epoch"] != epoch:
                    raise BridgeStoreError("ACK bridge_id／epoch 與事件不符")
                if int(row["bridge_sequence"]) in missing:
                    raise BridgeStoreError(
                        f"sequence {row['bridge_sequence']} 不可同時 accepted 與 missing"
                    )
                self._conn.execute(
                    """
                    UPDATE outbox
                    SET status = 'acked', last_error = NULL, updated_at = ?
                    WHERE event_id = ?
                    """,
                    (now, event_id),
                )

            contiguous = self._compute_contiguous_acked(bridge_id, epoch)
            self._conn.execute(
                """
                INSERT INTO sync_state(bridge_id, epoch, contiguous_acked_sequence)
                VALUES (?, ?, ?)
                ON CONFLICT(bridge_id, epoch) DO UPDATE SET
                    contiguous_acked_sequence = excluded.contiguous_acked_sequence
                """,
                (bridge_id, epoch, contiguous),
            )
            self._conn.execute("COMMIT")
            return contiguous
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def get_contiguous_acked(self, bridge_id: str, epoch: str) -> int:
        """讀取連續 ACK 游標。"""
        row = self._conn.execute(
            """
            SELECT contiguous_acked_sequence FROM sync_state
            WHERE bridge_id = ? AND epoch = ?
            """,
            (bridge_id, epoch),
        ).fetchone()
        return int(row["contiguous_acked_sequence"]) if row else 0

    def get_settings(self, bridge_id: str) -> dict[str, Any]:
        """讀取 bridge_settings。"""
        settings = self._require_settings(bridge_id)
        return {
            "bridge_id": settings["bridge_id"],
            "current_epoch": settings["current_epoch"],
            "next_sequence": int(settings["next_sequence"]),
        }

    def _compute_contiguous_acked(self, bridge_id: str, epoch: str) -> int:
        rows = self._conn.execute(
            """
            SELECT e.bridge_sequence, o.status
            FROM event_log e
            JOIN outbox o ON o.event_id = e.event_id
            WHERE e.bridge_id = ? AND e.epoch = ?
            ORDER BY e.bridge_sequence ASC
            """,
            (bridge_id, epoch),
        ).fetchall()
        expected = 1
        for row in rows:
            sequence = int(row["bridge_sequence"])
            if sequence != expected:
                break
            if row["status"] != "acked":
                break
            expected += 1
        return expected - 1

    def _require_settings(self, bridge_id: str) -> sqlite3.Row:
        row = self._conn.execute(
            "SELECT bridge_id, current_epoch, next_sequence FROM bridge_settings WHERE bridge_id = ?",
            (bridge_id,),
        ).fetchone()
        if row is None:
            raise BridgeStoreError(f"未知 bridge_id={bridge_id}；請先 ensure_bridge")
        return row

    def iter_event_ids(self, bridge_id: str, epoch: str) -> Iterator[str]:
        """測試輔助：列出 epoch 內 event_id。"""
        rows = self._conn.execute(
            """
            SELECT event_id FROM event_log
            WHERE bridge_id = ? AND epoch = ?
            ORDER BY bridge_sequence ASC
            """,
            (bridge_id, epoch),
        ).fetchall()
        for row in rows:
            yield row["event_id"]
