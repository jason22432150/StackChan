"""
個人版 CoreS3 啟動接線用設定（host）。

對應 firmware `PersonalPendingBootConfig`／`PersonalPendingWorkerRequest`。
不燒錄；供 accept-boot 驗收與 NVS／Kconfig 對齊。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse


class BootConfigError(ValueError):
    """啟動設定不合法。"""


_HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


@dataclass(frozen=True, slots=True)
class PersonalPendingBootConfig:
    """可排程 personal pending worker 的啟動參數。"""

    coordinator_host: str
    port: int
    device_id: str
    device_token: str
    policy_version: str = "pol_personal_v1"
    generation: int = 1
    policy_ttl_seconds: int = 86_400
    fetch_interval_ms: int = 5_000
    coordinator_ca_pem: str = ""
    session: int = 1
    limit: int = 50

    def __post_init__(self) -> None:
        object.__setattr__(self, "coordinator_host", self.coordinator_host.strip())
        object.__setattr__(self, "device_id", self.device_id.strip())
        object.__setattr__(self, "device_token", self.device_token.strip())
        object.__setattr__(self, "policy_version", self.policy_version.strip())
        object.__setattr__(self, "coordinator_ca_pem", self.coordinator_ca_pem.strip())
        self.validate()

    def validate(self) -> None:
        if not _HOST_RE.match(self.coordinator_host):
            raise BootConfigError("coordinator_host 不合法")
        if not 1 <= self.port <= 65535:
            raise BootConfigError("port 必須在 1..65535")
        if not self.device_id or len(self.device_id) > 128 or "\0" in self.device_id:
            raise BootConfigError("device_id 不合法")
        if len(self.device_token) < 16 or len(self.device_token) > 512:
            raise BootConfigError("device_token 長度必須在 16..512")
        if not self.policy_version or len(self.policy_version) > 128:
            raise BootConfigError("policy_version 不合法")
        if self.generation < 0:
            raise BootConfigError("generation 不可為負")
        if self.session <= 0:
            raise BootConfigError("session 必須 > 0")
        if not 30 <= self.policy_ttl_seconds <= 86400 * 30:
            raise BootConfigError("policy_ttl_seconds 超出範圍")
        if self.fetch_interval_ms < 1000:
            raise BootConfigError("fetch_interval_ms 必須 >= 1000")
        if not 1 <= self.limit <= 100:
            raise BootConfigError("limit 必須在 1..100")
        if self.coordinator_ca_pem and not self.coordinator_ca_pem.startswith(
            "-----BEGIN CERTIFICATE-----"
        ):
            raise BootConfigError("coordinator_ca_pem 必須為 PEM 或空（cleartext）")

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> PersonalPendingBootConfig:
        src = env if env is not None else dict(os.environ)
        host = (src.get("STACKCHAN_PERSONAL_PENDING_HOST") or "").strip()
        port_raw = (src.get("STACKCHAN_PERSONAL_PENDING_PORT") or "").strip()
        url = (src.get("STACKCHAN_COORDINATOR_URL") or "").strip()
        if url and (not host or not port_raw):
            parsed = urlparse(url)
            if parsed.hostname:
                host = host or parsed.hostname
            if parsed.port:
                port_raw = port_raw or str(parsed.port)
            elif parsed.scheme == "http":
                port_raw = port_raw or "80"
            elif parsed.scheme == "https":
                port_raw = port_raw or "443"
        if not host:
            raise BootConfigError("缺少 STACKCHAN_COORDINATOR_URL 或 STACKCHAN_PERSONAL_PENDING_HOST")
        try:
            port = int(port_raw or "8443")
        except ValueError as exc:
            raise BootConfigError("port 必須為整數") from exc
        return cls(
            coordinator_host=host,
            port=port,
            device_id=(src.get("STACKCHAN_DEVICE_ID") or "cores3_primary").strip(),
            device_token=(src.get("STACKCHAN_DEVICE_TOKEN") or "").strip(),
            policy_version=(src.get("STACKCHAN_PERSONAL_POLICY_VERSION") or "pol_personal_v1").strip(),
            generation=int(src.get("STACKCHAN_PERSONAL_GENERATION") or "1"),
            policy_ttl_seconds=int(src.get("STACKCHAN_PERSONAL_POLICY_TTL_SECONDS") or "86400"),
            fetch_interval_ms=int(src.get("STACKCHAN_PERSONAL_FETCH_INTERVAL_MS") or "5000"),
            coordinator_ca_pem=(src.get("STACKCHAN_PERSONAL_CA_PEM") or "").strip(),
            session=int(src.get("STACKCHAN_PERSONAL_SESSION") or "1"),
            limit=int(src.get("STACKCHAN_DEVICE_PULL_LIMIT") or "50"),
        )

    def policy_expires_at_utc(self, *, now: datetime | None = None) -> datetime:
        clock = now or datetime.now(timezone.utc)
        if clock.tzinfo is None:
            clock = clock.replace(tzinfo=timezone.utc)
        return clock.astimezone(timezone.utc) + timedelta(seconds=self.policy_ttl_seconds)

    def to_public_dict(self, *, now: datetime | None = None) -> dict[str, Any]:
        expires = self.policy_expires_at_utc(now=now)
        return {
            "coordinator_host": self.coordinator_host,
            "port": self.port,
            "transport": "https" if self.coordinator_ca_pem else "http_cleartext",
            "device_id": self.device_id,
            "device_token_len": len(self.device_token),
            "device_token_set": True,
            "policy_version": self.policy_version,
            "generation": self.generation,
            "session": self.session,
            "policy_expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fetch_interval_ms": self.fetch_interval_ms,
            "limit": self.limit,
            "nvs_namespace": "personal_pend",
            "maps_to": "PersonalPendingWorkerRequest",
        }

    def coordinator_base_url(self) -> str:
        scheme = "https" if self.coordinator_ca_pem else "http"
        return f"{scheme}://{self.coordinator_host}:{self.port}"
