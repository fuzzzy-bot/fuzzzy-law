"""
Access tests for the law connector: open with per-IP limits, API keys with
per-user quotas, request size limits, what the logs may hold, and isolation
from the app's own auth.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config.settings import settings
from app.middleware import connector_access_middleware
from app.services import connector_access_service
from app.services.connector_access_service import ConnectorAccessService, hash_key

CODES = "/api/v1/connector/codes"
MCP_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
MCP_HEADERS = {"accept": "application/json, text/event-stream"}


class FakeLimiter:
    """In-memory stand-in for the Redis sliding window (counts only)."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def __call__(self, key: str, limit: int, window: float) -> tuple[bool, int]:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key] <= limit, int(window)


@pytest.fixture
def limiter(monkeypatch):
    fake = FakeLimiter()
    monkeypatch.setattr(connector_access_middleware, "rate_limiter", fake)
    return fake


@pytest.fixture
def access(monkeypatch, tmp_path):
    """A fresh access service whose key file lives in tmp_path."""
    keys_file = tmp_path / "keys.json"
    service = ConnectorAccessService(keys_file=keys_file)
    monkeypatch.setattr(connector_access_service, "_access_service", service)
    return service, keys_file


@pytest.fixture
def client(connector_service, limiter, access):
    from app.connector_main import create_connector_app

    with TestClient(create_connector_app()) as c:
        yield c


class TestOpenMode:
    def test_open_by_default(self, client):
        assert settings.connector_access_mode == "open"
        assert client.get(CODES).status_code == 200

    def test_per_ip_limit(self, client, limiter, monkeypatch):
        monkeypatch.setattr(settings, "connector_rate_limit_per_minute", 3)
        statuses = [client.get(CODES).status_code for _ in range(5)]
        assert statuses == [200, 200, 200, 429, 429]
        assert set(limiter.counts) == {"connector:minute:ip:testclient"}

    def test_limit_covers_mcp_too(self, client, monkeypatch):
        monkeypatch.setattr(settings, "connector_rate_limit_per_minute", 1)
        assert client.post("/mcp", json=MCP_LIST, headers=MCP_HEADERS).status_code == 200
        limited = client.post("/mcp", json=MCP_LIST, headers=MCP_HEADERS)
        assert limited.status_code == 429
        assert limited.headers["retry-after"]

class TestBuiltInLimits:
    """The limiter the public server runs with: counted in this process's memory."""

    @pytest.fixture
    def real_client(self, connector_service, access):
        from app.connector_main import create_connector_app

        with TestClient(create_connector_app()) as c:
            yield c

    def test_per_ip_limit_is_enforced(self, real_client, monkeypatch):
        monkeypatch.setattr(settings, "connector_rate_limit_per_minute", 2)
        statuses = [real_client.get(CODES).status_code for _ in range(4)]
        assert statuses == [200, 200, 429, 429]
        limited = real_client.post("/mcp", json=MCP_LIST, headers=MCP_HEADERS)
        assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1

    def test_oversized_body_is_refused(self, real_client, monkeypatch):
        monkeypatch.setattr(settings, "connector_max_body_bytes", 200)
        big = dict(MCP_LIST, params={"padding": "x" * 500})
        response = real_client.post("/mcp", json=big, headers=MCP_HEADERS)
        assert response.status_code == 413
        assert response.json()["error"] == "request_too_large"
        assert real_client.post("/mcp", json=MCP_LIST, headers=MCP_HEADERS).status_code == 200

    def test_body_without_a_declared_length_is_refused(self, real_client):
        def chunks():
            yield json.dumps(MCP_LIST).encode()

        response = real_client.post(
            "/mcp", content=chunks(), headers=MCP_HEADERS | {"content-type": "application/json"}
        )
        assert response.status_code == 411
        assert response.json()["error"] == "length_required"

    def test_overlong_question_is_refused(self, real_client):
        assert real_client.get(
            "/api/v1/connector/search", params={"query": "ვ" * 501}
        ).status_code == 422
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "search_law", "arguments": {"query": "ვ" * 501}}}
        result = real_client.post("/mcp", json=call, headers=MCP_HEADERS).json()["result"]
        assert result["isError"] is True

    def test_rate_limit_log_does_not_hold_the_address(self, real_client, monkeypatch, caplog):
        monkeypatch.setattr(settings, "connector_rate_limit_per_minute", 1)
        with caplog.at_level(logging.INFO):
            real_client.get(CODES)
            assert real_client.get(CODES).status_code == 429
        assert "connector_rate_limited" in caplog.text
        assert "testclient" not in caplog.text


class TestCallerIdentity:
    def _caller(self, ip):
        return ConnectorAccessService().resolve(ip, "")

    def test_ipv4_caller_is_its_address(self):
        caller = self._caller("203.0.113.9")
        assert caller.caller_id == "ip:203.0.113.9"
        assert caller.per_minute == settings.connector_rate_limit_per_minute

    def test_ipv6_callers_in_one_64_are_one_caller(self):
        first = self._caller("2001:db8:1:2:aaaa::1")
        second = self._caller("2001:db8:1:2:bbbb::9")
        other = self._caller("2001:db8:1:3::1")
        assert first.caller_id == second.caller_id == "ip:2001:db8:1:2::/64"
        assert other.caller_id != first.caller_id

    def test_ipv4_written_as_ipv6_is_the_same_caller(self):
        assert self._caller("::ffff:203.0.113.9").caller_id == "ip:203.0.113.9"

    def test_provider_networks_get_the_shared_limit(self, monkeypatch):
        monkeypatch.setattr(
            settings, "connector_shared_ip_ranges", "198.51.100.0/24, 2001:db8:ffff::/48, nonsense"
        )
        monkeypatch.setattr(settings, "connector_shared_rate_limit_per_minute", 500)
        assert self._caller("198.51.100.77").per_minute == 500
        assert self._caller("2001:db8:ffff:1::5").per_minute == 500
        assert self._caller("198.51.101.1").per_minute == settings.connector_rate_limit_per_minute
        outside = self._caller("2001:db8:fffe::5")
        assert outside.per_minute == settings.connector_rate_limit_per_minute


class TestErrorsAndLogs:
    def test_unexpected_error_is_logged_without_its_message(
        self, connector_service, access, monkeypatch, caplog
    ):
        from app.connector_main import create_connector_app

        def broken(*args, **kwargs):
            raise RuntimeError("საიდუმლო კითხვა: my private question")

        monkeypatch.setattr(connector_service, "list_codes", broken)
        with caplog.at_level(logging.INFO), \
                TestClient(create_connector_app(), raise_server_exceptions=False) as c:
            response = c.get(CODES)
        assert response.status_code == 500
        assert response.json()["error"] == "internal_server_error"
        assert "private question" not in response.text
        assert "connector_unhandled_exception" in caplog.text
        assert "error_type=RuntimeError" in caplog.text
        assert "private question" not in caplog.text and "საიდუმლო" not in caplog.text

    def test_standalone_connector_loads_no_database_model_or_vector_code(self):
        """The public server is installed without these packages; importing one would crash it."""
        banned = ["anthropic", "chromadb", "google", "redis", "sqlalchemy", "asyncpg",
                  "firebase_admin", "numpy"]
        code = (
            "import sys, app.connector_main; "
            f"print(','.join(m for m in {banned!r} if m in sys.modules))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        assert result.stdout.strip() == ""


class TestApiKeyMode:
    @pytest.fixture(autouse=True)
    def _key_mode(self, monkeypatch, access):
        monkeypatch.setattr(settings, "connector_access_mode", "api_key")
        _, keys_file = access
        keys_file.write_text(json.dumps({
            hash_key("good-key"): {"user": "alice", "daily_quota": 2},
            hash_key("other-key"): {"user": "bob"},
        }))

    def test_missing_key_is_401_with_challenge(self, client):
        response = client.get(CODES)
        assert response.status_code == 401
        assert response.json()["error"] == "connector_auth_required"
        assert response.headers["www-authenticate"].startswith("Bearer")

    def test_wrong_key(self, client):
        response = client.get(CODES, headers={"Authorization": "Bearer nope"})
        assert response.status_code == 401
        assert response.json()["error"] == "connector_key_invalid"

    def test_valid_key_and_daily_quota(self, client, limiter):
        auth = {"Authorization": "Bearer good-key"}
        assert [client.get(CODES, headers=auth).status_code for _ in range(3)] == [200, 200, 429]
        assert "connector:day:key:alice" in limiter.counts

    def test_quotas_are_per_user(self, client):
        for _ in range(2):
            client.get(CODES, headers={"Authorization": "Bearer good-key"})
        assert client.get(CODES, headers={"Authorization": "Bearer other-key"}).status_code == 200

    def test_mcp_needs_the_key_too(self, client):
        assert client.post("/mcp", json=MCP_LIST, headers=MCP_HEADERS).status_code == 401
        ok = client.post(
            "/mcp", json=MCP_LIST, headers=MCP_HEADERS | {"Authorization": "Bearer other-key"}
        )
        assert ok.status_code == 200

    def test_oauth_mode_is_not_offered(self, monkeypatch):
        """Account sign-in is left for later; only open and api_key are valid modes."""
        import pydantic

        from app.config.settings import Settings

        with pytest.raises(pydantic.ValidationError):
            Settings(connector_access_mode="oauth")

    def test_only_hashes_are_stored(self, access):
        _, keys_file = access
        assert "good-key" not in keys_file.read_text()


class TestHealth:
    def test_health_reports_the_store_and_its_date(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["codes"] >= 3
        assert "data_current_as_of" in body

    def test_health_is_not_rate_limited(self, client, limiter, monkeypatch):
        monkeypatch.setattr(settings, "connector_rate_limit_per_minute", 1)
        assert [client.get("/healthz").status_code for _ in range(5)] == [200] * 5
        assert limiter.counts == {}

    def test_data_health_fails_until_a_refresh_has_succeeded(self, client):
        response = client.get("/healthz/data")
        assert response.status_code == 503
        assert response.json()["refresh"] == "never_ran"

    def test_data_health_passes_after_a_good_refresh(self, client, monkeypatch):
        from app.services.law_connector_service import get_law_connector_service

        monkeypatch.setattr(get_law_connector_service(), "refresh_state", lambda: "ok")
        response = client.get("/healthz/data")
        assert response.status_code == 200
        assert response.json()["refresh"] == "ok"

    def test_health_fails_without_a_law_store(self, tmp_path, limiter, access, monkeypatch):
        from app.connector_main import create_connector_app
        from app.services import law_connector_service as module
        from app.services.article_store_service import ArticleStoreService

        empty = module.LawConnectorService(store=ArticleStoreService(tmp_path / "absent.db"))
        monkeypatch.setattr(module, "_connector_service", empty)
        with TestClient(create_connector_app()) as c:
            response = c.get("/healthz")
        assert response.status_code == 503
        assert response.json()["status"] == "law_store_unavailable"
