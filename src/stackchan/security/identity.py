"""主體身分與 opaque token 雜湊（明文僅回傳一次，不落地）。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from stackchan.contracts.authz import Principal, TokenDirectory


def issue_opaque_token(*, nbytes: int = 32) -> str:
    """產生高熵 opaque token（僅記憶體回傳）。"""
    return secrets.token_urlsafe(nbytes)


@dataclass(frozen=True, slots=True)
class TokenHasher:
    """HMAC-SHA256 token 雜湊；pepper 來自程序設定，不寫入 DB 明文 token。"""

    pepper: bytes

    def hash_token(self, token: str) -> str:
        digest = hmac.new(self.pepper, token.encode("utf-8"), hashlib.sha256).hexdigest()
        return digest

    def verify(self, token: str, token_hash: str) -> bool:
        return hmac.compare_digest(self.hash_token(token), token_hash)


class HashedTokenDirectory(TokenDirectory):
    """
    以雜湊比對的 TokenDirectory。

    注意：為相容 ApiGate，issue() 仍接受 plaintext token 作為查找鍵，
    但生產路徑應透過 SecurityStore.issue_grant 只持久化 hash。
    本類別供測試／記憶體閘道使用；持久化請用 SecurityStore。
    """

    def __init__(self, hasher: TokenHasher) -> None:
        super().__init__()
        self._hasher = hasher
        self._hash_to_principal: dict[str, Principal] = {}

    def issue(self, token: str, principal: Principal) -> None:
        token_hash = self._hasher.hash_token(token)
        self._hash_to_principal[token_hash] = principal
        # 保留父類 plaintext map 僅供同進程 ApiGate；不應序列化
        super().issue(token, principal)

    def revoke(self, token: str) -> None:
        token_hash = self._hasher.hash_token(token)
        principal = self._hash_to_principal.get(token_hash)
        if principal is not None:
            self._hash_to_principal[token_hash] = Principal(
                subject_id=principal.subject_id,
                subject_type=principal.subject_type,
                scopes=principal.scopes,
                revoked=True,
            )
        super().revoke(token)

    def resolve(self, token: str) -> Principal | None:
        token_hash = self._hasher.hash_token(token)
        principal = self._hash_to_principal.get(token_hash)
        if principal is not None:
            return principal
        return super().resolve(token)
