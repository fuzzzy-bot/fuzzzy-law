"""
Law connector error middleware — a 500 that records where, never what.

The public connector must not keep what people ask, and an exception message
can carry a piece of the request. So an unexpected error is logged as its type
and the code locations it passed through, without the message or any values.
Pure ASGI, so the MCP endpoint's responses pass through untouched.
"""

from __future__ import annotations

import json
import traceback

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.utils.logger import get_logger

logger = get_logger(__name__)

FRAMES_KEPT = 6
ERROR_BODY = json.dumps({
    "error": "internal_server_error",
    "message": "The law connector hit an unexpected error. Nothing was returned; "
               "do not answer from memory, try the call again.",
}).encode()


def error_location(exc: BaseException) -> str:
    """The innermost code locations of ``exc`` as 'file:line:function' joined by ' < '."""
    frames = traceback.extract_tb(exc.__traceback__)[-FRAMES_KEPT:]
    return " < ".join(
        f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}:{frame.name}"
        for frame in reversed(frames)
    )


class ConnectorErrorMiddleware:
    """Turn an unhandled exception into a JSON 500 and a value-free log line."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        started = False

        async def watched_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, watched_send)
        except Exception as exc:  # noqa: BLE001 - the last line of defence
            logger.error(
                "connector_unhandled_exception",
                path=scope.get("path", ""),
                method=scope.get("method", ""),
                error_type=type(exc).__name__,
                where=error_location(exc),
            )
            if started:
                raise
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(ERROR_BODY)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": ERROR_BODY})
