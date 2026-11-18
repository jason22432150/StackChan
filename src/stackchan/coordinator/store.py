"""
Coordinator SQLite：追加式事件、任務投影、已讀、Receipt、migration。

不變式：
- events.event_id UNIQUE；同 event_id 重送冪等
- (bridge_id, epoch, bridge_sequence) UNIQUE
- response.completed 不得把 task_projections 標成 succeeded
- ReadState 顯式操作，version 樂觀鎖
- presentation_receipts.receipt_id UNIQUE
- schema_migrations 追蹤版本；僅向前 migration
- 已清理事件寫入 purged_events tombstone，禁止重導入
- 清理水位保留 sync cursor 連續性（不因刪除舊序號而假缺口）
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

SCHEMA_VERSION = 3


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

    def __init__(self, path: str | Path, *, check_same_thread: bool = True) -> None:
        self.path = Path(path)
        # Pi HTTP（ThreadingHTTPServer）會在工作執行緒存取；呼叫端須自行序列化寫入。
        self._conn = sqlite3.connect(
            self.path,
            isolation_level=None,
            check_same_thread=check_same_thread,
        )
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
        if self.schema_version() < 2:
            self._apply_migration_2()
        if self.schema_version() < 3:
            self._apply_migration_3()

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

    def _apply_migration_2(self) -> None:
        """版本化設定、清理水位與 purged tombstone。"""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1),
                value_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (key, version)
            );

            CREATE TABLE IF NOT EXISTS app_settings_current (
                key TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                FOREIGN KEY (key, version) REFERENCES app_settings(key, version)
            );

            CREATE TABLE IF NOT EXISTS purged_events (
                event_id TEXT PRIMARY KEY,
                bridge_id TEXT NOT NULL,
                epoch TEXT NOT NULL,
                bridge_sequence INTEGER NOT NULL,
                ingested_at TEXT NOT NULL,
                purged_at TEXT NOT NULL,
                reason TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cleanup_watermarks (
                bridge_id TEXT NOT NULL,
                epoch TEXT NOT NULL,
                purged_through_sequence INTEGER NOT NULL DEFAULT 0
                    CHECK(purged_through_sequence >= 0),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (bridge_id, epoch)
            );

            CREATE INDEX IF NOT EXISTS idx_purged_events_bridge_epoch
                ON purged_events(bridge_id, epoch, bridge_sequence);
            CREATE INDEX IF NOT EXISTS idx_app_settings_key
                ON app_settings(key, version);
            """
        )
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (2, ?)",
                (_utc_now(),),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def _apply_migration_3(self) -> None:
        """個人版待派送通知佇列（FIFO／優先／TTL）。"""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pending_notifications (
                delivery_id TEXT PRIMARY KEY,
                notification_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                event_ids_json TEXT NOT NULL,
                priority INTEGER NOT NULL CHECK(priority >= 0 AND priority <= 100),
                policy_version TEXT NOT NULL,
                generation INTEGER NOT NULL CHECK(generation >= 0),
                expires_at TEXT NOT NULL,
                presentation_policy_json TEXT NOT NULL,
                presentation_profile TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'expired', 'cancelled')),
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_pending_notifications_status_pri
                ON pending_notifications(status, priority DESC, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_pending_notifications_expires
                ON pending_notifications(status, expires_at);
            """
        )
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (3, ?)",
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

                if self._is_purged_unlocked(event["event_id"]):
                    rejected.append(
                        {
                            "event_id": event["event_id"],
                            "error": "event_purged_no_reimport",
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
        watermark = self.get_cleanup_watermark(bridge_id, epoch)
        # 已清理的連續序號視為仍存在，避免清理後出現假缺口
        if watermark > 0:
            present.update(range(1, watermark + 1))
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

    def list_missing_sequences(self, bridge_id: str, epoch: str) -> list[int]:
        """回傳目前已知的序號缺口（不含已清理水位內的假缺口）。"""
        _, missing = self._recompute_sync_cursor(bridge_id, epoch)
        return missing

    def list_events_for_source_task(self, source_task_id: str) -> list[dict[str, Any]]:
        """列出同一 source_task_id 的全部原始事件（跨 Bridge）。"""
        rows = self._conn.execute(
            """
            SELECT payload_json FROM events
            WHERE json_extract(payload_json, '$.source_task_id') = ?
            ORDER BY ingested_at ASC, bridge_id ASC, bridge_sequence ASC
            """,
            (source_task_id,),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_recent_event_summaries(
        self, *, limit: int = 50, bridge_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        管理頁用近期事件摘要（不含 payload_json／Prompt）。
        limit 範圍 1..100；可選 bridge_id 過濾（個人版 Bridge Token 應對齊自身）。
        """
        if not 1 <= limit <= 100:
            raise CoordinatorStoreError("limit 必須在 1..100")
        if bridge_id is None:
            rows = self._conn.execute(
                """
                SELECT event_id, bridge_id, epoch, bridge_sequence, event_type,
                       evidence_level, privacy_class, observed_at, ingested_at
                FROM events
                ORDER BY ingested_at DESC, bridge_sequence DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            if not bridge_id or len(bridge_id) > 128:
                raise CoordinatorStoreError("bridge_id 無效")
            rows = self._conn.execute(
                """
                SELECT event_id, bridge_id, epoch, bridge_sequence, event_type,
                       evidence_level, privacy_class, observed_at, ingested_at
                FROM events
                WHERE bridge_id = ?
                ORDER BY ingested_at DESC, bridge_sequence DESC
                LIMIT ?
                """,
                (bridge_id, limit),
            ).fetchall()
        return [
            {
                "event_id": str(row["event_id"]),
                "bridge_id": str(row["bridge_id"]),
                "epoch": str(row["epoch"]),
                "bridge_sequence": int(row["bridge_sequence"]),
                "event_type": str(row["event_type"]),
                "evidence_level": str(row["evidence_level"]),
                "privacy_class": str(row["privacy_class"]),
                "observed_at": str(row["observed_at"]),
                "ingested_at": str(row["ingested_at"]),
            }
            for row in rows
        ]

    def expire_pending_notifications(self, *, now_iso: str | None = None) -> int:
        """將過期 pending 標為 expired；回傳更新筆數。"""
        now = now_iso or _utc_now()
        cur = self._conn.execute(
            """
            UPDATE pending_notifications
            SET status = 'expired'
            WHERE status = 'pending' AND expires_at <= ?
            """,
            (now,),
        )
        return int(cur.rowcount)

    def enqueue_pending_notification(self, intent: dict[str, Any]) -> bool:
        """
        寫入待派送通知。delivery_id 已存在則視為去重（回傳 False）。
        呼叫端應先 validate_notification_intent。
        """
        delivery_id = str(intent["delivery_id"])
        self.expire_pending_notifications()
        existing = self._conn.execute(
            "SELECT delivery_id, status FROM pending_notifications WHERE delivery_id = ?",
            (delivery_id,),
        ).fetchone()
        if existing is not None:
            return False

        pending_count = self._conn.execute(
            "SELECT COUNT(*) AS c FROM pending_notifications WHERE status = 'pending'"
        ).fetchone()["c"]
        if int(pending_count) >= 64:
            raise CoordinatorStoreError("pending notification 佇列已滿")

        self.ensure_device(str(intent["device_id"]))
        self.ensure_delivery(delivery_id, str(intent["device_id"]), int(intent["generation"]))
        self._conn.execute(
            """
            INSERT INTO pending_notifications(
                delivery_id, notification_id, device_id, event_ids_json, priority,
                policy_version, generation, expires_at, presentation_policy_json,
                presentation_profile, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                delivery_id,
                str(intent["notification_id"]),
                str(intent["device_id"]),
                json.dumps(list(intent["event_ids"]), ensure_ascii=True, separators=(",", ":")),
                int(intent["priority"]),
                str(intent["policy_version"]),
                int(intent["generation"]),
                str(intent["expires_at"]),
                json.dumps(intent["presentation_policy"], ensure_ascii=True, separators=(",", ":")),
                intent.get("presentation_profile"),
                _utc_now(),
            ),
        )
        return True

    def list_pending_notifications(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """
        列出未過期 pending（優先級高者在前，同優先級 FIFO）。
        回傳可再組成 NotificationIntent 的摘要列。
        """
        if not 1 <= limit <= 100:
            raise CoordinatorStoreError("limit 必須在 1..100")
        self.expire_pending_notifications()
        rows = self._conn.execute(
            """
            SELECT delivery_id, notification_id, device_id, event_ids_json, priority,
                   policy_version, generation, expires_at, presentation_policy_json,
                   presentation_profile, created_at
            FROM pending_notifications
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "schema_version": "0.1",
                    "notification_id": str(row["notification_id"]),
                    "delivery_id": str(row["delivery_id"]),
                    "device_id": str(row["device_id"]),
                    "event_ids": json.loads(row["event_ids_json"]),
                    "priority": int(row["priority"]),
                    "policy_version": str(row["policy_version"]),
                    "generation": int(row["generation"]),
                    "expires_at": str(row["expires_at"]),
                    "presentation_policy": json.loads(row["presentation_policy_json"]),
                    "presentation_profile": row["presentation_profile"],
                    "created_at": str(row["created_at"]),
                }
            )
        return items

    def record_task_conflict(
        self,
        *,
        task_key: str,
        note: str,
        event_ids: list[str],
        mark_projection_conflict: bool,
    ) -> None:
        """
        記錄跨 Bridge 矛盾證據。

        不依 observed_at 覆寫真相；可選將投影標為 conflict 並清除 succeeded。
        """
        now = _utc_now()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for event_id in event_ids:
                exists = self._conn.execute(
                    "SELECT event_id FROM events WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
                if exists is None:
                    continue
                self._conn.execute(
                    """
                    INSERT INTO event_evidence(event_id, evidence_level, note, recorded_at)
                    VALUES (?, 'unknown', ?, ?)
                    """,
                    (event_id, note, now),
                )
            if mark_projection_conflict:
                self._conn.execute(
                    """
                    UPDATE task_projections
                    SET status = 'conflict', succeeded = 0, updated_at = ?
                    WHERE task_key = ?
                    """,
                    (now, task_key),
                )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

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

    def set_setting(self, key: str, value: Any) -> int:
        """寫入版本化設定，回傳新 version。"""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS v FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
            version = int(row["v"]) + 1
            now = _utc_now()
            self._conn.execute(
                """
                INSERT INTO app_settings(key, version, value_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, version, json.dumps(value, ensure_ascii=False), now),
            )
            self._conn.execute(
                """
                INSERT INTO app_settings_current(key, version)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET version = excluded.version
                """,
                (key, version),
            )
            self._conn.execute("COMMIT")
            return version
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            """
            SELECT s.value_json
            FROM app_settings_current c
            JOIN app_settings s ON s.key = c.key AND s.version = c.version
            WHERE c.key = ?
            """,
            (key,),
        ).fetchone()
        if row is None:
            return default
        return json.loads(row["value_json"])

    def get_setting_version(self, key: str) -> int:
        row = self._conn.execute(
            "SELECT version FROM app_settings_current WHERE key = ?",
            (key,),
        ).fetchone()
        return int(row["version"]) if row else 0

    def is_purged(self, event_id: str) -> bool:
        return self._is_purged_unlocked(event_id)

    def _is_purged_unlocked(self, event_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM purged_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        return row is not None

    def get_cleanup_watermark(self, bridge_id: str, epoch: str) -> int:
        row = self._conn.execute(
            """
            SELECT purged_through_sequence FROM cleanup_watermarks
            WHERE bridge_id = ? AND epoch = ?
            """,
            (bridge_id, epoch),
        ).fetchone()
        return int(row["purged_through_sequence"]) if row else 0

    def purge_eligible_events(
        self,
        *,
        bridge_id: str,
        epoch: str,
        cutoff_iso: str,
        reason: str = "retention_policy",
    ) -> list[str]:
        """
        清理已納入連續 ACK 且早於 cutoff 的事件。

        不得清理 contiguous 之後／缺口中的事件；清理後寫 tombstone。
        """
        contiguous = self.get_sync_cursor(bridge_id, epoch)
        if contiguous <= 0:
            return []

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            rows = self._conn.execute(
                """
                SELECT event_id, bridge_sequence, ingested_at
                FROM events
                WHERE bridge_id = ? AND epoch = ?
                  AND bridge_sequence <= ?
                  AND ingested_at < ?
                ORDER BY bridge_sequence ASC
                """,
                (bridge_id, epoch, contiguous, cutoff_iso),
            ).fetchall()
            purged_ids: list[str] = []
            now = _utc_now()
            max_purged_seq = self.get_cleanup_watermark(bridge_id, epoch)
            for row in rows:
                event_id = row["event_id"]
                sequence = int(row["bridge_sequence"])
                self._conn.execute(
                    """
                    INSERT INTO purged_events(
                        event_id, bridge_id, epoch, bridge_sequence,
                        ingested_at, purged_at, reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        bridge_id,
                        epoch,
                        sequence,
                        row["ingested_at"],
                        now,
                        reason,
                    ),
                )
                self._conn.execute(
                    "DELETE FROM event_evidence WHERE event_id = ?",
                    (event_id,),
                )
                self._conn.execute(
                    "DELETE FROM read_states WHERE event_id = ?",
                    (event_id,),
                )
                # task_projections 可能仍指向此 event；改為保留列但清除 FK 風險：
                # 先把 latest_event_id 指到自己佔位不可能；改刪除僅當 latest 為此 id
                self._conn.execute(
                    "DELETE FROM task_projections WHERE latest_event_id = ?",
                    (event_id,),
                )
                self._conn.execute("DELETE FROM events WHERE event_id = ?", (event_id,))
                purged_ids.append(event_id)
                max_purged_seq = max(max_purged_seq, sequence)

            if purged_ids:
                # 水位只能推進到「從 1 起連續已 purge／仍存在」的最大序號
                watermark = self._compute_purge_watermark(bridge_id, epoch, max_purged_seq)
                self._conn.execute(
                    """
                    INSERT INTO cleanup_watermarks(
                        bridge_id, epoch, purged_through_sequence, updated_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(bridge_id, epoch) DO UPDATE SET
                        purged_through_sequence = excluded.purged_through_sequence,
                        updated_at = excluded.updated_at
                    """,
                    (bridge_id, epoch, watermark, now),
                )
            self._conn.execute("COMMIT")
            return purged_ids
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def _compute_purge_watermark(
        self, bridge_id: str, epoch: str, candidate_max: int
    ) -> int:
        """水位 = 從 1 起連續皆已 purge 或不需再保留的最大序號。"""
        purged = {
            int(row["bridge_sequence"])
            for row in self._conn.execute(
                """
                SELECT bridge_sequence FROM purged_events
                WHERE bridge_id = ? AND epoch = ?
                """,
                (bridge_id, epoch),
            ).fetchall()
        }
        watermark = 0
        for sequence in range(1, candidate_max + 1):
            if sequence in purged:
                watermark = sequence
            else:
                break
        return watermark
