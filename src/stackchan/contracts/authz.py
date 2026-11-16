"""API 授權閘道：未授權／缺 scope 必須拒絕讀寫。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

import yaml

from stackchan.contracts.paths import contracts_dir


class AuthorizationError(PermissionError):
    """未授權或權限不足。"""

    def __init__(self, code: str, message: str, *, http_status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True, slots=True)
class Principal:
    """已驗證主體（憑證內容為記憶體中的 opaque token，不寫入日誌）。"""

    subject_id: str
    subject_type: str
    scopes: frozenset[str]
    revoked: bool = False


@dataclass(frozen=True, slots=True)
class RouteRequirement:
    """OpenAPI 路徑的必要 scope。"""

    method: str
    path_template: str
    required_scopes: frozenset[str]
    allow_anonymous: bool


def _template_to_regex_parts(path_template: str) -> list[str]:
    parts: list[str] = []
    for segment in path_template.strip("/").split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            parts.append("*")
        else:
            parts.append(segment)
    return parts


def match_path_template(path_template: str, request_path: str) -> bool:
    """比對 OpenAPI path template 與實際 request path。"""
    template_parts = _template_to_regex_parts(path_template)
    request_parts = request_path.strip("/").split("/") if request_path.strip("/") else []
    if len(template_parts) != len(request_parts):
        return False
    for expected, actual in zip(template_parts, request_parts, strict=True):
        if expected == "*":
            continue
        if expected != actual:
            return False
    return True


@lru_cache(maxsize=1)
def load_route_requirements() -> tuple[RouteRequirement, ...]:
    """自 openapi.yaml 的 x-required-scopes 載入路由授權表。"""
    openapi_path = contracts_dir() / "openapi.yaml"
    with openapi_path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)

    routes: list[RouteRequirement] = []
    paths: Mapping[str, Any] = document.get("paths") or {}
    for path_template, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            if method.startswith("x-") or not isinstance(operation, dict):
                continue
            scopes = operation.get("x-required-scopes")
            if scopes is None:
                raise ValueError(f"{method.upper()} {path_template} 缺少 x-required-scopes")
            security = operation.get("security", document.get("security"))
            allow_anonymous = security == []
            routes.append(
                RouteRequirement(
                    method=method.upper(),
                    path_template=path_template,
                    required_scopes=frozenset(scopes),
                    allow_anonymous=allow_anonymous,
                )
            )
    return tuple(routes)


def find_route(method: str, path: str) -> RouteRequirement | None:
    """尋找符合的路由需求。"""
    method_u = method.upper()
    for route in load_route_requirements():
        if route.method != method_u:
            continue
        if match_path_template(route.path_template, path):
            return route
    return None


class TokenDirectory:
    """測試／雛形用的 opaque token 目錄（非生產密鑰庫）。"""

    def __init__(self) -> None:
        self._tokens: dict[str, Principal] = {}

    def issue(self, token: str, principal: Principal) -> None:
        self._tokens[token] = principal

    def revoke(self, token: str) -> None:
        principal = self._tokens.get(token)
        if principal is not None:
            self._tokens[token] = Principal(
                subject_id=principal.subject_id,
                subject_type=principal.subject_type,
                scopes=principal.scopes,
                revoked=True,
            )

    def resolve(self, token: str) -> Principal | None:
        return self._tokens.get(token)


def parse_bearer_authorization(authorization_header: str | None) -> str | None:
    """解析 Authorization: Bearer <token>；格式錯誤回傳 None。"""
    if not authorization_header:
        return None
    parts = authorization_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        return None
    return parts[1].strip()


class ApiGate:
    """
    契約層授權閘道。

    尚未部署真實 HTTP server；測試以此驗證未授權不可讀寫。
    """

    def __init__(self, tokens: TokenDirectory) -> None:
        self._tokens = tokens

    def authorize(
        self,
        method: str,
        path: str,
        authorization_header: str | None,
    ) -> Principal | None:
        """
        授權成功回傳 Principal；匿名允許的路由回傳 None。

        Raises:
            AuthorizationError: 401／403
        """
        route = find_route(method, path)
        if route is None:
            raise AuthorizationError(
                "not_found",
                f"未知路由 {method.upper()} {path}",
                http_status=404,
            )

        token = parse_bearer_authorization(authorization_header)
        if token is None:
            if route.allow_anonymous and not route.required_scopes:
                return None
            raise AuthorizationError(
                "unauthorized",
                "缺少或無效的 Bearer token",
                http_status=401,
            )

        principal = self._tokens.resolve(token)
        if principal is None:
            raise AuthorizationError(
                "unauthorized",
                "未知或無效的憑證",
                http_status=401,
            )
        if principal.revoked:
            raise AuthorizationError(
                "revoked",
                "憑證已撤銷",
                http_status=403,
            )

        missing = route.required_scopes - principal.scopes
        if missing:
            raise AuthorizationError(
                "forbidden",
                f"缺少必要 scope: {', '.join(sorted(missing))}",
                http_status=403,
            )
        return principal
