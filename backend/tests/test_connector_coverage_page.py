"""
Public coverage page tests — the page says what the connector holds and no more.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.services.connector_coverage_page import (
    CONTACT_EMAIL,
    OPERATOR,
    PAGE_HEADERS,
    render_coverage_page,
)

PUBLIC_URL = "https://law.example.org"


@pytest.fixture
def page(connector_service) -> str:
    return render_coverage_page(
        connector_service.get_coverage(), connector_service.legal_aid(), PUBLIC_URL)


@pytest.fixture
def client(connector_service):
    from app.connector_main import create_connector_app

    with TestClient(create_connector_app()) as c:
        yield c


class TestPage:
    def test_lists_every_law_the_tools_report(self, page, connector_service):
        coverage = connector_service.get_coverage()
        assert coverage.laws
        for law in coverage.laws:
            assert law.name in page
            assert f'<td class="num">{law.article_count}</td>' in page
            assert law.source_url in page

    def test_names_what_is_not_held(self, page, connector_service):
        for item in connector_service.get_coverage().not_covered:
            assert item in page

    def test_gives_the_connector_address(self, page):
        assert f"<code>{PUBLIC_URL}/mcp</code>" in page

    def test_says_it_is_not_legal_advice_and_who_runs_it(self, page):
        assert "legal information, not legal advice" in page
        assert OPERATOR in page
        assert f"mailto:{CONTACT_EMAIL}" in page

    def test_gives_the_free_legal_aid_contacts(self, page, connector_service):
        aid = connector_service.legal_aid()
        for provider in aid.providers:
            assert provider.website in page
        assert "1485" in page
        assert aid.checked_on in page

    def test_says_where_the_data_comes_from_and_how_it_stays_current(
        self, page, connector_service
    ):
        assert "how it stays current" in page
        for note in connector_service.get_coverage().how_data_is_kept:
            assert note.data in page
            assert note.source_url in page

    def test_says_what_is_kept(self, page):
        assert "does not store what people ask" in page
        assert "seven days" in page

    def test_undated_store_is_said_plainly(self, page, connector_service):
        coverage = connector_service.get_coverage()
        if coverage.data_current_as_of:
            assert coverage.data_current_as_of in page
        else:
            assert "is not known" in page
        if coverage.freshness_warning:
            assert 'class="warn"' in page

    def test_loads_nothing_from_outside(self, page):
        assert "<script" not in page.lower()
        assert not re.search(r"<(img|link|iframe|object|embed|form)\b", page, re.I)
        assert "url(" not in page and "@import" not in page

    def test_values_are_escaped(self, connector_service):
        coverage = connector_service.get_coverage()
        hostile = '<script>alert(1)</script>"&'
        coverage.laws[0].name = hostile
        coverage.not_covered.append(hostile)
        page = render_coverage_page(coverage, connector_service.legal_aid(), PUBLIC_URL)
        assert hostile not in page
        assert "&lt;script&gt;alert(1)&lt;/script&gt;&quot;&amp;" in page

    def test_public_address_is_escaped(self, connector_service):
        page = render_coverage_page(
            connector_service.get_coverage(), connector_service.legal_aid(),
            'https://x.example/"><b>')
        assert '"><b>' not in page


class TestServed:
    def test_served_as_html_with_a_closed_policy(self, client):
        response = client.get("/coverage")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        policy = response.headers["content-security-policy"]
        assert policy == PAGE_HEADERS["Content-Security-Policy"]
        assert "default-src 'none'" in policy
        assert "frame-ancestors 'none'" in policy
        assert "Georgian law for AI assistants" in response.text

    def test_not_in_the_gpt_action_document(self, client):
        assert "/coverage" not in client.get("/api/v1/connector/openapi.json").json()["paths"]

    def test_counts_against_the_request_limit(self, client, monkeypatch):
        from app.config.settings import settings

        monkeypatch.setattr(settings, "connector_rate_limit_per_minute", 2)
        codes = [client.get("/coverage").status_code for _ in range(4)]
        assert codes[:2] == [200, 200]
        assert 429 in codes[2:]
