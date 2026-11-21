"""
Standalone law connector — the MCP server and REST mirror without the rest of the app.

Needs only two files, the article store and the court store beside it: no
database, no Redis, no vector store and no model key. Run:

    uvicorn app.connector_main:app --port 8010

or as a container with docker-compose.connector.yml. ``/healthz`` says whether
the law store can be read and ``/healthz/data`` whether the daily refresh of
the law texts is working; both sit outside the connector's public paths, so a
health check is neither rate limited nor counted as a caller.

The connector inside the main app is enabled with CONNECTOR_ENABLED=true instead.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.middleware.connector_error_middleware import ConnectorErrorMiddleware
from app.routes.connector_mcp import SERVER_TITLE, install_law_connector
from app.services.law_connector_service import get_law_connector_service
from app.utils.logger import get_logger, setup_logging


def create_connector_app() -> FastAPI:
    """Build an app serving only the law connector."""
    app = FastAPI(title=SERVER_TITLE, docs_url=None, redoc_url=None, lifespan=_lifespan)
    install_law_connector(app)
    app.add_middleware(ConnectorErrorMiddleware)
    app.add_api_route("/healthz", healthz, methods=["GET"], include_in_schema=False)
    app.add_api_route("/healthz/data", data_health, methods=["GET"], include_in_schema=False)
    return app


def healthz() -> JSONResponse:
    """200 while the law store can be read, 503 when it cannot."""
    codes = get_law_connector_service().list_codes()
    ready = bool(codes.codes)
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ok" if ready else "law_store_unavailable",
            "codes": len(codes.codes),
            "data_current_as_of": codes.data_current_as_of,
        },
    )


def data_health() -> JSONResponse:
    """200 while the daily refresh is succeeding, 503 when it failed or stopped running."""
    service = get_law_connector_service()
    state = service.refresh_state()
    return JSONResponse(
        status_code=200 if state == "ok" else 503,
        content={
            "refresh": state,
            "data_current_as_of": service.list_codes().data_current_as_of,
        },
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    setup_logging()
    # The MCP library logs a line per request at INFO; keep only its problems.
    logging.getLogger("mcp").setLevel(logging.WARNING)
    async with app.state.connector_mcp.session_manager.run():
        get_logger("app.connector_main").info(
            "law_connector_ready",
            access_mode=settings.connector_access_mode,  # gitleaks:allow (a mode name, not a key)
            standalone=True,
        )
        yield


app = create_connector_app()
