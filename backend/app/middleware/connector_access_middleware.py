"""
Law connector access middleware — admission, size limit, rate limits and quotas.

Pure ASGI, like the BYOK middleware, so the MCP endpoint's streamed responses
pass through untouched. It guards only the connector's own paths; the app's
other middleware leave those paths alone (see their allowlists), because the
connector has its own callers — outside AI agents — and its own access modes.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config.settings import settings
from app.services.connector_access_service import (
    DAY,
    MINUTE,
    ConnectorAccessDenied,
    get_connector_access_service,
)
from app.services.connector_rate_limiter import check_memory_rate_limit
from app.utils.logger import get_logger

logger = get_logger(__name__)

CONNECTOR_PREFIXES = ("/mcp", "/api/v1/connector", "/coverage")
# Discovery documents a client must read before it can sign in.
CONNECTOR_OPEN_PATHS = {"/api/v1/connector/openapi.json"}

BODY_METHODS = {"POST", "PUT", "PATCH"}


async def rate_limiter(key: str, limit: int, window: float) -> tuple[bool, int]:
    """Count one request in this process's memory (one worker serves the connector)."""
    return await check_memory_rate_limit(key, limit, window)


def is_connector_path(path: str) -> bool:
    return path.startswith(CONNECTOR_PREFIXES)


def _header(scope: Scope, name: bytes) -> str:
    for raw_name, raw_value in scope.get("headers") or []:
        if raw_name.lower() == name:
            return raw_value.decode("latin-1").strip()
    return ""


async def _reply(send: Send, status: int, body: dict, headers: list[tuple[bytes, bytes]]) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(payload)).encode()),
            *headers,
        ],
    })
    await send({"type": "http.response.body", "body": payload})


WWW_AUTHENTICATE = [(b"www-authenticate", b"Bearer")]


def _body_refusal(scope: Scope) -> tuple[int, str, str] | None:
    """Why this request's body is not accepted (status, code, message), or None.

    The declared length is what is checked, so a body must declare one: the
    server itself stops a sender that goes past the length it declared.
    """
    declared = _header(scope, b"content-length")
    if not declared:
        if scope.get("method") in BODY_METHODS:
            return 411, "length_required", "Send a Content-Length header with the request body."
        return None
    if not declared.isdigit() or int(declared) > settings.connector_max_body_bytes:
        return (
            413, "request_too_large",
            f"The request body may be at most {settings.connector_max_body_bytes} bytes.",
        )
    return None


class ConnectorAccessMiddleware:
    """Admit, rate-limit and meter calls to the law connector."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or not is_connector_path(path)
            or path in CONNECTOR_OPEN_PATHS
            or scope.get("method") == "OPTIONS"
        ):
            return await self.app(scope, receive, send)

        refusal = _body_refusal(scope)
        if refusal is not None:
            status, code, message = refusal
            return await _reply(send, status, {"error": code, "message": message}, [])

        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        try:
            caller = get_connector_access_service().resolve(
                client_ip, _header(scope, b"authorization")
            )
        except ConnectorAccessDenied as denied:
            logger.info("connector_access_denied", code=denied.code, path=path)
            return await _reply(
                send, 401, {"error": denied.code, "message": denied.message}, WWW_AUTHENTICATE
            )

        allowed, retry_after = await rate_limiter(
            f"connector:minute:{caller.caller_id}", caller.per_minute, MINUTE
        )
        if allowed and caller.daily_quota is not None:
            allowed, retry_after = await rate_limiter(
                f"connector:day:{caller.caller_id}", caller.daily_quota, DAY
            )
        if not allowed:
            # The caller's address stays out of the application log.
            logger.warning("connector_rate_limited", caller_kind=caller.caller_id.split(":", 1)[0])
            return await _reply(
                send,
                429,
                {
                    "error": "rate_limited",
                    "message": "Too many requests to the law connector; try again later.",
                    "retry_after_seconds": retry_after,
                },
                [(b"retry-after", str(retry_after).encode())],
            )
        return await self.app(scope, receive, send)
