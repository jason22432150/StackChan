"""Security 測試 fixtures。"""

from __future__ import annotations

from pathlib import Path

import pytest

from stackchan.security import PairingService, PolicyService, SecurityStore, TokenHasher


@pytest.fixture
def hasher() -> TokenHasher:
    return TokenHasher(pepper=b"test-pepper-not-for-production")


@pytest.fixture
def security_db(tmp_path: Path, hasher: TokenHasher) -> SecurityStore:
    store = SecurityStore(tmp_path / "security.sqlite3", hasher=hasher)
    yield store
    store.close()


@pytest.fixture
def pairing(security_db: SecurityStore) -> PairingService:
    return PairingService(security_db)


@pytest.fixture
def policies(security_db: SecurityStore) -> PolicyService:
    return PolicyService(security_db)
