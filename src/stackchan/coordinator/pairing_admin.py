"""Explicit manual approval through the loopback-only pairing endpoint."""

from __future__ import annotations

import http.client
import json
import re
import ssl
from pathlib import Path


def confirm_pairing(
    *, port: int, ca: Path, pairing_id: str, user_code: str, approved: bool, admin_token: str,
) -> None:
    """Confirm once; never follow redirects, retry, or receive a device grant."""
    if (
        not 1 <= port <= 65535 or not re.fullmatch(r"pair_[0-9a-f]{16}", pairing_id)
        or not re.fullmatch(r"[A-Z0-9]{6}", user_code)
        or not re.fullmatch(r"[A-Za-z0-9\-._~+/]+=*", admin_token)
    ):
        raise ValueError("invalid pairing confirmation input")
    context = ssl.create_default_context(cafile=ca)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    connection = http.client.HTTPSConnection("127.0.0.1", port, context=context, timeout=5)
    try:
        connection.request("POST", f"/v1/pairing/sessions/{pairing_id}/confirm", body=json.dumps({
            "schema_version": "0.1", "pairing_id": pairing_id, "user_code": user_code, "approved": approved,
        }).encode(), headers={
            "Authorization": f"Bearer {admin_token}", "Content-Type": "application/json",
            "Connection": "close",
        })
        response = connection.getresponse()
        lengths = response.headers.get_all("Content-Length", [])
        if (
            response.status != 200 or response.headers.get("Content-Type") != "application/json"
            or response.headers.get_all("Transfer-Encoding") or response.headers.get_all("Location")
            or len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,4}", lengths[0])
            or not 0 < int(lengths[0]) <= 4096
        ):
            raise ValueError("pairing confirmation refused")
        body = response.read(4097)
        if len(body) != int(lengths[0]):
            raise ValueError("invalid confirmation response")
        result = json.loads(body)
        # The frozen API returns Error-shaped acknowledgement even on HTTP 200.
        if (
            not isinstance(result, dict) or set(result) != {"schema_version", "error", "message", "retryable"}
            or result["schema_version"] != "0.1" or result["retryable"] is not False
            or not isinstance(result["message"], str)
            or result["error"] != ("unauthorized" if approved else "forbidden")
        ):
            raise ValueError("invalid confirmation response")
    finally:
        connection.close()
