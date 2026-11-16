"""
Coordinator SQLite：追加式事件、任務投影、已讀、Receipt、migration。

不變式：
- events.event_id UNIQUE；同 event_id 重送冪等
- (bridge_id, epoch, bridge_sequence) UNIQUE
- response.completed 不得把 task_projections 標成 succeeded
- ReadState 顯式操作，version 樂觀鎖
- presentation_receipts.receipt_id UNIQUE
- schema_migrations 追蹤版本；僅向前 migration
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stackchan.contracts import (
    ContractValidationError,
    implies_task_succeeded,
    validate_agent_event,
    validate_presentation_receipt,
)

SCHEMA_VERSION = 1


class CoordinatorStoreError(ValueError):
    """Coordinator 儲存規則違反。"""


@dataclass(frozen=True, slots=True)
class BatchIngestResult:
    """批次匯入結果（可作為 ACK 素材）。"""

    bridge_id: str
    epoch: str
    accepted_event_ids: list[str] = field(default_factory=list)
    duplicate_event_ids: list[str] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)
    contiguous_acked_sequence: int = 0
    missing_sequences: list[int] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReadResult:
    """已讀標記結果。"""

    event_id: str
    read: bool
    version: int


@dataclass(frozen=True, slots=True)
class ReceiptResult:
    """Receipt 寫入結果。"""

    receipt_id: str
    accepted: bool
    created: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _task_key(event: dict[str, Any]) -> str:
    source_task_id = event.get("source_task_id")
    if isinstance(source_task_id, str) and source_task_id:
        return source_task_id
    session_id = event.get("session_id")
    if isinstance(session_id, str) and session_id:
        return f"session:{session_id}"
    return f"event:{event['event_id']}"


def _projection_status(event_type: str) -> str | None:
    mapping = {
        "task.started": "started",
        "task.running": "running",
        "task.awaiting_user": "awaiting_user",
        "task.succeeded": "succeeded",
        "task.failed": "failed",
        "task.cancelled": "cancelled",
        "response.completed": "response_completed",
        "observation.uncertain": "uncertain",
    }
    return mapping.get(event_type)


class CoordinatorStore:
    """Coordinator SQLite 儲存。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> CoordinatorStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def schema_version(self) -> int:
        row = self._conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return int(row["version"]) if row else 0

    def migrate(self) -> None:
        """套用向前 migration（可重複呼叫）。"""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        current = self.schema_version()
        if current < 1:
            self._apply_migration_1()

    def _apply_migration_1(self) -> None:
        # executescript 會自行 commit，不可包在外層 BEGIN/COMMIT
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'paired',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                observation_id TEXT NOT NULL,
                bridge_id TEXT NOT NULL,
                epoch TEXT NOT NULL,
                bridge_sequence INTEGER NOT NULL CHECK(bridge_sequence >= 1),
                event_type TEXT NOT NULL,
                evidence_level TEXT NOT NULL,
                privacy_class TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                UNIQUE(bridge_id, epoch, bridge_sequence)
            );

            CREATE TABLE IF NOT EXISTS event_evidence (
                evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL REFERENCES events(event_id),
                evidence_level TEXT NOT NULL,
                note TEXT,
                recorded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_projections (
                task_key TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                latest_event_id TEXT NOT NULL REFERENCES events(event_id),
                succeeded INTEGER NOT NULL DEFAULT 0 CHECK(succeeded IN (0, 1)),
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sync_cursors (
                bridge_id TEXT NOT NULL,
                epoch TEXT NOT NULL,
                contiguous_acked_sequence INTEGER NOT NULL DEFAULT 0
                    CHECK(contiguous_acked_sequence >= 0),
                PRIMARY KEY (bridge_id, epoch)
            );

            CREATE TABLE IF NOT EXISTS read_states (
                event_id TEXT PRIMARY KEY REFERENCES events(event_id),
                read INTEGER NOT NULL CHECK(read IN (0, 1)),
                version INTEGER NOT NULL CHECK(version >= 0),
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deliveries (
                delivery_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL REFERENCES devices(device_id),
                generation INTEGER NOT NULL CHECK(generation >= 0),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS presentation_receipts (
                receipt_id TEXT PRIMARY KEY,
                delivery_id TEXT NOT NULL REFERENCES deliveries(delivery_id),
                attempt_id TEXT NOT NULL,
                device_id TEXT NOT NULL REFERENCES devices(device_id),
                generation INTEGER NOT NULL CHECK(generation >= 0),
                status TEXT NOT NULL,
                reason TEXT,
                reported_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_bridge_epoch_seq
                ON events(bridge_id, epoch, bridge_sequence);
            CREATE INDEX IF NOT EXISTS idx_events_type
                ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_event_evidence_event
                ON event_evidence(event_id, recorded_at);
            CREATE INDEX IF NOT EXISTS idx_task_projections_status
                ON task_projections(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_read_states_read
                ON read_states(read, version);
            CREATE INDEX IF NOT EXISTS idx_receipts_delivery
                ON presentation_receipts(delivery_id, reported_at);
            """
        )
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (1, ?)",
                (_utc_now(),),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def ensure_device(self, device_id: str) -> None:
        """確保裝置列存在（Receipt FK 用）。"""
        self._conn.execute(
            """
            INSERT INTO devices(device_id, status, created_at)
            VALUES (?, 'paired', ?)
            ON CONFLICT(device_id) DO NOTHING
            """,
            (device_id, _utc_now()),
        )

    def ensure_delivery(self, delivery_id: str, device_id: str, generation: int = 0) -> None:
        """確保 delivery 列存在。"""
        self.ensure_device(device_id)
        self._conn.execute(
            """
            INSERT INTO deliveries(delivery_id, device_id, generation, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(delivery_id) DO NOTHING
            """,
            (delivery_id, device_id, generation, _utc_now()),
        )

    def ingest_event_batch(
        self,
        *,
        bridge_id: str,
        epoch: str,
        events: list[dict[str, Any]],
    ) -> BatchIngestResult:
        """
        冪等匯入事件批次；交易提交後才回傳可持久 ACK 的游標。
        """
        if not events:
            raise CoordinatorStoreError("events 不可為空")

        accepted: list[str] = []
        duplicates: list[str] = []
        rejected: list[dict[str, str]] = []

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for raw in events:
                try:
                    event = validate_agent_event(raw)
                except ContractValidationError as exc:
                    rejected.append(
                        {
                            "event_id": str(raw.get("event_id", "")),
                            "error": str(exc),
                        }
                    )
                    continue

                if event["bridge_id"] != bridge_id or event["epoch"] != epoch:
                    rejected.append(
                        {
                            "event_id": event["event_id"],
                            "error": "bridge_id／epoch 與批次標頭不符",
                        }
                    )
                    continue

                existing = self._conn.execute(
                    "SELECT payload_json FROM events WHERE event_id = ?",
                    (event["event_id"],),
                ).fetchone()
                if existing is not None:
                    if json.loads(existing["payload_json"]) != event:
                        rejected.append(
                            {
                                "event_id": event["event_id"],
                                "error": "event_id 已存在但 payload 不同",
                            }
                        )
                    else:
                        duplicates.append(event["event_id"])
                    continue

                now = _utc_now()
                try:
                    self._conn.execute(
                        """
                        INSERT INTO events(
                            event_id, observation_id, bridge_id, epoch, bridge_sequence,
                            event_type, evidence_level, privacy_class, observed_at,
                            payload_json, ingested_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event["event_id"],
                            event["observation_id"],
                            event["bridge_id"],
                            event["epoch"],
                            int(event["bridge_sequence"]),
                            event["event_type"],
                            event["evidence_level"],
                            event["privacy_class"],
                            event["observed_at"],
                            json.dumps(event, ensure_ascii=False, separators=(",", ":")),
                            now,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    rejected.append(
                        {
                            "event_id": event["event_id"],
                            "error": f"唯一約束衝突: {exc}",
                        }
                    )
                    continue

                self._conn.execute(
                    """
                    INSERT INTO event_evidence(event_id, evidence_level, note, recorded_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        event["event_id"],
                        event["evidence_level"],
                        f"ingest:{event['event_type']}",
                        now,
                    ),
                )
                self._upsert_task_projection(event, now)
                accepted.append(event["event_id"])

            contiguous, missing = self._recompute_sync_cursor(bridge_id, epoch)
            self._conn.execute("COMMIT")
            return BatchIngestResult(
                bridge_id=bridge_id,
                epoch=epoch,
                accepted_event_ids=accepted,
                duplicate_event_ids=duplicates,
                rejected=rejected,
                contiguous_acked_sequence=contiguous,
                missing_sequences=missing,
            )
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def _upsert_task_projection(self, event: dict[str, Any], now: str) -> None:
        status = _projection_status(event["event_type"])
        if status is None:
            return
        task_key = _task_key(event)
        succeeded = 1 if implies_task_succeeded(event) else 0
        existing = self._conn.execute(
            "SELECT succeeded FROM task_projections WHERE task_key = ?",
            (task_key,),
        ).fetchone()
        if existing is not None and int(existing["succeeded"]) == 1 and succeeded == 0:
            # 已確認成功後，不以 response.completed 等覆寫成功旗標或降級 status
            self._conn.execute(
                """
                UPDATE task_projections
                SET latest_event_id = ?, updated_at = ?
                WHERE task_key = ?
                """,
                (event["event_id"], now, task_key),
            )
            return
        self._conn.execute(
            """
            INSERT INTO task_projections(
                task_key, agent_id, status, latest_event_id, succeeded, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_key) DO UPDATE SET
                status = excluded.status,
                latest_event_id = excluded.latest_event_id,
                succeeded = excluded.succeeded,
                updated_at = excluded.updated_at
            """,
            (
                task_key,
                event["agent_id"],
                status,
                event["event_id"],
                succeeded,
                now,
            ),
        )

    def _recompute_sync_cursor(self, bridge_id: str, epoch: str) -> tuple[int, list[int]]:
        rows = self._conn.execute(
            """
            SELECT bridge_sequence FROM events
            WHERE bridge_id = ? AND epoch = ?
            ORDER BY bridge_sequence ASC
            """,
            (bridge_id, epoch),
        ).fetchall()
        present = {int(row["bridge_sequence"]) for row in rows}
        if not present:
            contiguous = 0
            missing: list[int] = []
        else:
            max_seq = max(present)
            contiguous = 0
            missing = []
            for sequence in range(1, max_seq + 1):
                if sequence in present:
                    if not missing:
                        contiguous = sequence
                else:
                    missing.append(sequence)
        self._conn.execute(
            """
            INSERT INTO sync_cursors(bridge_id, epoch, contiguous_acked_sequence)
            VALUES (?, ?, ?)
            ON CONFLICT(bridge_id, epoch) DO UPDATE SET
                contiguous_acked_sequence = excluded.contiguous_acked_sequence
            """,
            (bridge_id, epoch, contiguous),
        )
        return contiguous, missing

    def get_sync_cursor(self, bridge_id: str, epoch: str) -> int:
        row = self._conn.execute(
            """
            SELECT contiguous_acked_sequence FROM sync_cursors
            WHERE bridge_id = ? AND epoch = ?
            """,
            (bridge_id, epoch),
        ).fetchone()
        return int(row["contiguous_acked_sequence"]) if row else 0

    def get_task_projection(self, task_key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT task_key, agent_id, status, latest_event_id, succeeded, updated_at
            FROM task_projections WHERE task_key = ?
            """,
            (task_key,),
        ).fetchone()
        if row is None:
            return None
        return {
            "task_key": row["task_key"],
            "agent_id": row["agent_id"],
            "status": row["status"],
            "latest_event_id": row["latest_event_id"],
            "succeeded": bool(row["succeeded"]),
            "updated_at": row["updated_at"],
        }

    def mark_read(
        self,
        event_id: str,
        *,
        operation_id: str,
        expected_version: int,
        read: bool = True,
    ) -> ReadResult:
        """顯式已讀；expected_version 樂觀鎖（0 表示尚無 read_states）。"""
        _ = operation_id  # 預留給冪等操作日誌（P1-05+）
        exists = self._conn.execute(
            "SELECT event_id FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if exists is None:
            raise CoordinatorStoreError(f"未知 event_id={event_id}")

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT version, read FROM read_states WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            current_version = int(row["version"]) if row else 0
            if current_version != expected_version:
                raise CoordinatorStoreError(
                    f"read version conflict: expected {expected_version}, actual {current_version}"
                )
            new_version = current_version + 1
            now = _utc_now()
            self._conn.execute(
                """
                INSERT INTO read_states(event_id, read, version, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    read = excluded.read,
                    version = excluded.version,
                    updated_at = excluded.updated_at
                """,
                (event_id, 1 if read else 0, new_version, now),
            )
            self._conn.execute("COMMIT")
            return ReadResult(event_id=event_id, read=read, version=new_version)
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def submit_receipt(self, receipt: dict[str, Any]) -> ReceiptResult:
        """冪等寫入 PresentationReceipt。"""
        try:
            validated = validate_presentation_receipt(receipt)
        except ContractValidationError as exc:
            raise CoordinatorStoreError(str(exc)) from exc

        self.ensure_delivery(
            validated["delivery_id"],
            validated["device_id"],
            int(validated["generation"]),
        )

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            existing = self._conn.execute(
                "SELECT payload_json FROM presentation_receipts WHERE receipt_id = ?",
                (validated["receipt_id"],),
            ).fetchone()
            if existing is not None:
                if json.loads(existing["payload_json"]) != validated:
                    raise CoordinatorStoreError("receipt_id 已存在但 payload 不同")
                self._conn.execute("COMMIT")
                return ReceiptResult(
                    receipt_id=validated["receipt_id"],
                    accepted=True,
                    created=False,
                )

            now = _utc_now()
            self._conn.execute(
                """
                INSERT INTO presentation_receipts(
                    receipt_id, delivery_id, attempt_id, device_id, generation,
                    status, reason, reported_at, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    validated["receipt_id"],
                    validated["delivery_id"],
                    validated["attempt_id"],
                    validated["device_id"],
                    int(validated["generation"]),
                    validated["status"],
                    validated.get("reason"),
                    validated["reported_at"],
                    json.dumps(validated, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            self._conn.execute("COMMIT")
            return ReceiptResult(
                receipt_id=validated["receipt_id"],
                accepted=True,
                created=True,
            )
        except sqlite3.IntegrityError as exc:
            self._conn.execute("ROLLBACK")
            raise CoordinatorStoreError(f"receipt 約束衝突: {exc}") from exc
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def list_indexes(self) -> set[str]:
        """測試輔助：列出使用者索引名稱。"""
        rows = self._conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        return {row["name"] for row in rows}
