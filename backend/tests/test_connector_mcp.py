"""
MCP protocol tests for the law connector, using the official MCP Python SDK client.

In-process: the SDK's ``Client`` connects straight to the server object.
Over HTTP: JSON-RPC posts to /mcp on the app with the connector enabled,
which is how ChatGPT and Claude reach it.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from app.config.settings import settings
from app.routes.connector_mcp import TOOL_DESCRIPTIONS, build_connector_mcp_server

EXPECTED_TOOLS = {
    "list_codes", "search_law", "get_article", "browse_code",
    "find_court_practice", "verify_citation", "search", "fetch",
    "list_changes", "get_court_decision", "get_coverage", "find_legal_aid",
}
GEORGIAN = range(0x10D0, 0x1100)


def _has_georgian(text: str) -> bool:
    return any(ord(ch) in GEORGIAN for ch in text)


@pytest.fixture
def mcp_server(connector_service):
    return build_connector_mcp_server(connector_service)


class TestListTools:
    async def test_all_tools_listed_read_only_and_bilingual(self, mcp_server):
        async with Client(mcp_server) as client:
            tools = (await client.list_tools()).tools
        assert {t.name for t in tools} == EXPECTED_TOOLS
        for tool in tools:
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.destructive_hint is False
            assert tool.output_schema, tool.name
            assert tool.description == TOOL_DESCRIPTIONS[tool.name]
            assert _has_georgian(tool.description), tool.name

    async def test_server_instructions_carry_the_grounding_rules(self, mcp_server):
        async with Client(mcp_server) as client:
            instructions = client.instructions
        assert "never invent" in instructions
        assert "get_article" in instructions


class TestCallTool:
    async def _call(self, server, name, args):
        async with Client(server) as client:
            result = await client.call_tool(name, args)
        assert not result.is_error, result.content
        # ChatGPT reads the JSON text copy; both must agree.
        assert json.loads(result.content[0].text) == result.structured_content
        return result.structured_content

    async def test_list_codes(self, mcp_server):
        data = await self._call(mcp_server, "list_codes", {})
        assert {c["code"] for c in data["codes"]} >= {"civil_code", "labour_code"}

    async def test_search_law(self, mcp_server):
        data = await self._call(mcp_server, "search_law", {"query": "სააპელაციო საჩივრის ვადა"})
        assert data["found"]
        assert data["results"][0]["source_url"].startswith("https://matsne.gov.ge/")

    async def test_get_article(self, mcp_server):
        data = await self._call(mcp_server, "get_article", {"code": "civil_code", "article": "138"})
        assert data["article"]["article_number"] == "მუხლი 138"

    async def test_browse_code(self, mcp_server):
        data = await self._call(mcp_server, "browse_code", {"code": "labour_code"})
        assert data["total_articles"] == 2

    async def test_find_court_practice(self, mcp_server):
        data = await self._call(mcp_server, "find_court_practice", {"query": "ხანდაზმულობა"})
        assert data["status"] == "source_unavailable"
        one_court = await self._call(
            mcp_server, "find_court_practice", {"query": "ხანდაზმულობა", "court": "supreme"})
        assert one_court["status"] == "source_unavailable"

    async def test_verify_citation(self, mcp_server):
        data = await self._call(mcp_server, "verify_citation", {
            "code": "civil_procedure_code", "article": "369", "claim": "ვადა 14 დღეა",
        })
        assert data["exists"] and data["lexical_check"]["numbers_not_in_text"] == ["14"]

    async def test_search_and_fetch_pair(self, mcp_server):
        hits = await self._call(mcp_server, "search", {"query": "ხანდაზმულობის ვადა"})
        first = hits["results"][0]
        assert set(first) == {"id", "title", "url"}
        doc = await self._call(mcp_server, "fetch", {"id": first["id"]})
        assert set(doc) >= {"id", "title", "text", "url"}
        assert doc["url"] == first["url"]

    async def test_article_number_sent_as_a_number_is_accepted(self, mcp_server):
        """AI clients often send 138 rather than "138"."""
        data = await self._call(mcp_server, "get_article", {
            "code": "civil_code", "article": 138, "paragraph": 1.0,
        })
        assert data["article"]["article_number"] == "მუხლი 138"
        assert "Paragraph 1 " in data["message"]

    async def test_verify_citation_checks_a_quote(self, mcp_server):
        data = await self._call(mcp_server, "verify_citation", {
            "code": "civil_code", "article": 138, "claim": "სარჩელი წყვეტს ხანდაზმულობას",
            "quote": "ხანდაზმულობის ვადის დენა ჩერდება",
        })
        assert data["quote_check"]["verbatim"] is False

    async def test_get_article_as_of_without_history_says_so(self, mcp_server):
        data = await self._call(mcp_server, "get_article", {
            "code": "labour_code", "article": "47", "as_of": "2025-03-01",
        })
        assert data["found"] is False and data["article"] is None
        assert "Earlier wordings" in data["message"]

    async def test_list_changes_without_history_says_so(self, mcp_server):
        data = await self._call(mcp_server, "list_changes", {
            "code": "labour_code", "since": "2025-01-01",
        })
        assert data["found"] is False and data["changes"] == []

    async def test_get_court_decision_unknown(self, mcp_server):
        data = await self._call(mcp_server, "get_court_decision", {"id": "AS-1-1900"})
        assert data["found"] is False

    async def test_get_coverage(self, mcp_server):
        data = await self._call(mcp_server, "get_coverage", {})
        assert len(data["laws"]) == 3 and data["not_covered"]

    async def test_find_legal_aid(self, mcp_server):
        data = await self._call(mcp_server, "find_legal_aid", {})
        assert data["providers"][0]["phone"].startswith("1485")
        assert data["checked_on"]

    async def test_fetch_unknown_id_is_a_tool_error(self, mcp_server):
        async with Client(mcp_server) as client:
            result = await client.call_tool("fetch", {"id": "article:nope:1"})
        assert result.is_error

    async def test_missing_argument_is_a_tool_error(self, mcp_server):
        async with Client(mcp_server) as client:
            result = await client.call_tool("get_article", {"code": "civil_code"})
        assert result.is_error


class TestPrompts:
    async def test_four_prompts_listed_in_both_languages(self, mcp_server):
        async with Client(mcp_server) as client:
            prompts = {p.name: p for p in (await client.list_prompts()).prompts}
        assert set(prompts) == {"intake", "case_analysis", "document_drafting", "deadline_check"}
        for prompt in prompts.values():
            assert _has_georgian(prompt.title) and _has_georgian(prompt.description), prompt.name
        required = {a.name: a.required for a in prompts["deadline_check"].arguments}
        assert required == {"situation": True, "event_date": False}

    async def _text(self, server, name: str, args: dict) -> str:
        async with Client(server) as client:
            result = await client.get_prompt(name, args)
        assert [m.role for m in result.messages] == ["user"]
        return result.messages[0].content.text

    async def test_intake_asks_before_it_concludes(self, mcp_server):
        text = await self._text(mcp_server, "intake", {"situation": "სამსახურიდან გამათავისუფლეს"})
        assert "სამსახურიდან გამათავისუფლეს" in text
        assert "Do not give the full analysis yet" in text
        assert "not legal advice" in text

    async def test_case_analysis_asks_for_both_sides(self, mcp_server):
        text = await self._text(mcp_server, "case_analysis", {"situation": "ვალი არ დამიბრუნეს"})
        assert "For me / against me / depends on evidence" in text
        assert "get_court_decision" in text and "verify_citation" in text

    async def test_document_drafting_keeps_to_the_facts_given(self, mcp_server):
        text = await self._text(mcp_server, "document_drafting", {
            "document": "სარჩელი", "situation": "ვალი არ დამიბრუნეს",
        })
        assert "Draft this document for me under Georgian law: სარჩელი" in text
        assert "Write nothing false and nothing I did not tell you" in text
        assert "find_legal_aid" in text

    async def test_deadline_check_without_a_date_says_it_is_missing(self, mcp_server):
        text = await self._text(mcp_server, "deadline_check", {"situation": "გადაწყვეტილება"})
        assert "handed to me: [not given]" in text
        assert "State no number that is not in the text" in text

    async def test_braces_in_a_persons_words_are_kept_as_written(self, mcp_server):
        text = await self._text(mcp_server, "intake", {"situation": "ხელშეკრულება {event_date}"})
        assert "ხელშეკრულება {event_date}" in text


class TestResources:
    async def test_three_resources_listed(self, mcp_server):
        async with Client(mcp_server) as client:
            resources = {str(r.uri): r for r in (await client.list_resources()).resources}
        assert set(resources) == {
            "fuzzzy-law://coverage", "fuzzzy-law://answer-rules", "fuzzzy-law://legal-aid"}
        assert resources["fuzzzy-law://answer-rules"].mime_type == "text/plain"

    async def _read(self, server, uri: str) -> str:
        async with Client(server) as client:
            return (await client.read_resource(uri)).contents[0].text

    async def test_coverage_resource_is_the_tools_answer(self, mcp_server, connector_service):
        data = json.loads(await self._read(mcp_server, "fuzzzy-law://coverage"))
        assert data == connector_service.get_coverage().model_dump(mode="json")

    async def test_answer_rules_resource(self, mcp_server):
        from app.services.connector_guidance import ANSWER_RULES

        assert await self._read(mcp_server, "fuzzzy-law://answer-rules") == ANSWER_RULES

    async def test_legal_aid_resource(self, mcp_server):
        data = json.loads(await self._read(mcp_server, "fuzzzy-law://legal-aid"))
        assert data["providers"][0]["website"] == "https://www.legalaid.ge"


def _rpc(client: TestClient, method: str, params: dict, rpc_id: int = 1):
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params},
        headers={"accept": "application/json, text/event-stream"},
    )


class TestHttpEndpoint:
    def test_standalone_app_serves_mcp(self, connector_service):
        from app.connector_main import create_connector_app

        with TestClient(create_connector_app()) as client:
            assert _rpc(client, "tools/list", {}).status_code == 200

    def test_wrong_host_rejected_when_hosts_configured(self, connector_service, monkeypatch):
        monkeypatch.setattr(settings, "connector_allowed_hosts", "law-api.example.ge")
        from app.connector_main import create_connector_app

        with TestClient(create_connector_app()) as client:
            assert _rpc(client, "tools/list", {}).status_code == 421
            ok = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                headers={"accept": "application/json, text/event-stream",
                         "host": "law-api.example.ge"},
            )
            assert ok.status_code == 200
