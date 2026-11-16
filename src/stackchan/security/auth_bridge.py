"""將 SecurityStore 接到 ApiGate 的 TokenDirectory。"""

from __future__ import annotations

from stackchan.contracts.authz import Principal, TokenDirectory
from stackchan.security.store import SecurityStore


class StoreBackedTokenDirectory(TokenDirectory):
    """只從雜湊 grant 解析主體；不在目錄中保留明文 token 清單可序列化狀態。"""

    def __init__(self, store: SecurityStore) -> None:
        super().__init__()
        self._store = store

    def issue(self, token: str, principal: Principal) -> None:
        raise RuntimeError("請透過 PairingService.complete／SecurityStore.issue_grant 發放憑證")

    def revoke(self, token: str) -> None:
        self._store.revoke_grant_by_token(token)

    def resolve(self, token: str) -> Principal | None:
        return self._store.resolve_principal(token)
