"""
Tests for reading a law as it stood on an earlier date and listing what changed.

The fixture history holds real rows built from matsne.gov.ge's consolidated
versions: every version of the Civil Code, the Civil Procedure Code and the
Labour Code since the end of 2023, and the wordings of six articles those
versions amended and two they added.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from app.routes.connector_mcp import build_connector_mcp_server
from app.services.law_connector_service import HISTORY_UNAVAILABLE
from app.services.law_history_service import LawHistoryService
from tests.conftest import build_law_history

CIVIL_CODE = "https://matsne.gov.ge/ka/document/view/31702"


@pytest.fixture
def history(tmp_path) -> LawHistoryService:
    return LawHistoryService(build_law_history(tmp_path / "law_history.db"))


class TestLawHistoryService:
    def test_reach_and_coverage(self, history):
        assert history.reach("civil_code") == {
            "earliest": "2023-12-15", "latest": "2026-06-25", "versions": 12}
        assert history.reach("tax_code") is None
        assert [c["document_id"] for c in history.coverage()] == [
            "civil_code", "civil_procedure_code", "labour_code"]

    def test_version_on_is_the_newest_dated_on_or_before(self, history):
        assert history.version_on("civil_code", "2025-06-25")["publication_id"] == 133
        assert history.version_on("civil_code", "2025-06-26")["publication_id"] == 134
        assert history.version_on("civil_code", "2023-12-14") is None

    def test_first_wording_has_no_known_start_and_names_what_replaced_it(self, history):
        held = history.article_on("civil_code", "1343", "2024-05-01")
        assert held["version"]["publication_id"] == 130
        assert held["article"]["from_publication"] == 129
        assert held["wording_from"] is None
        assert held["replaced_by"]["version_date"] == "2025-06-26"

    def test_current_wording_names_the_version_that_brought_it(self, history):
        held = history.article_on("civil_code", "1343", "2026-11-01")
        assert held["wording_from"]["version_date"] == "2026-06-23"
        assert held["replaced_by"] is None
        assert [p["number"] for p in held["article"]["paragraphs"]] == ["1", "2"]

    def test_article_not_yet_in_the_law_on_that_date(self, history):
        held = history.article_on("civil_procedure_code", "363-53", "2025-01-01")
        assert held["article"] is None and held["version"]["publication_id"] == 169
        assert history.article_on("civil_procedure_code", "363-53", "2025-07-01")["article"]

    def test_date_before_the_stored_history(self, history):
        assert history.article_on("civil_code", "1343", "2020-01-01") is None

    def test_changes_name_amended_and_added_articles_oldest_first(self, history):
        changes = history.changes("civil_code", "2024-01-01")
        assert [(c["article_norm"], c["change"], c["version_date"]) for c in changes] == [
            ("1120", "amended", "2024-09-17"),
            ("1343", "amended", "2025-06-26"),
            ("1343", "amended", "2025-09-19"),
            ("198", "amended", "2026-04-01"),
            ("1343", "amended", "2026-06-23"),
        ]
        assert changes[0]["version_url"] == CIVIL_CODE + "?publication=132"
        added = history.changes("labour_code", "2024-01-01", "14-1")
        assert [(c["change"], c["version_date"]) for c in added] == [("added", "2024-09-17")]

    def test_changes_respect_since_and_never_list_the_first_version(self, history):
        assert len(history.changes("civil_code", "2026-01-01")) == 2
        assert len(history.changes("civil_code", "2000-01-01")) == 5
        assert history.changes("civil_code", "2026-07-01") == []

    def test_removed_article_is_listed_as_removed(self, history):
        with sqlite3.connect(history.db_path) as conn:
            conn.execute(
                "UPDATE article_versions SET closed_by_publication = 140 "
                "WHERE document_id = 'civil_code' AND article_norm = '198' "
                "AND closed_by_publication IS NULL")
        changes = history.changes("civil_code", "2026-06-24")
        assert [(c["article_norm"], c["change"]) for c in changes] == [("198", "removed")]
        assert history.article_on("civil_code", "198", "2026-07-01")["article"] is None

    def test_missing_file_answers_nothing(self, tmp_path):
        absent = LawHistoryService(tmp_path / "none.db")
        assert absent.reach("civil_code") is None and absent.coverage() == []
        assert absent.version_on("civil_code", "2025-01-01") is None
        assert absent.changes("civil_code", "2025-01-01") == []


class TestArticleAsOf:
    def test_civil_code_1343_reads_differently_through_four_versions(
        self, connector_service_with_history
    ):
        get = connector_service_with_history.get_article
        first = get("civil_code", "1343", as_of="2025-01-01").article
        second = get("civil_code", "1343", as_of="2025-07-01").article
        third = get("civil_code", "1343", as_of="2025-10-01").article
        fourth = get("civil_code", "1343", as_of="2026-07-01").article

        assert "მოხუცთა, ინვალიდთა" in first.text
        assert "ხანდაზმულთა ან შეზღუდული შესაძლებლობის მქონე პირთა" in second.text
        assert "არაკონსტიტუციურად" not in second.text
        assert "არაკონსტიტუციურად იქნა ცნობილი" in third.text
        assert "ხანდაზმულთა" not in fourth.text
        assert [a.version_date for a in (first, second, third, fourth)] == [
            "2024-12-13", "2025-06-26", "2025-09-19", "2026-06-25"]
        assert first.wording_from is None and first.replaced_on == "2025-06-26"
        assert second.wording_from == "2025-06-26" and second.replaced_on == "2025-09-19"
        assert fourth.wording_from == "2026-06-23" and fourth.replaced_on is None

    def test_answer_links_to_exactly_that_version_and_says_what_the_date_means(
        self, connector_service_with_history
    ):
        result = connector_service_with_history.get_article(
            "civil_code", "1343", as_of="2025-01-01")
        article = result.article
        assert result.found and article.as_of == "2025-01-01"
        assert article.source_url == CIVIL_CODE + "?publication=133#part_1576"
        assert "2024-12-13" in article.history_note
        assert "take effect later" in article.history_note
        assert "2025-06-26 changed this article" in article.history_note
        assert article.code_name == "საქართველოს სამოქალაქო კოდექსი"

    def test_civil_code_1120_before_and_after_the_2024_amendment(
        self, connector_service_with_history
    ):
        get = connector_service_with_history.get_article
        added = "ერთი და იმავე ბიოლოგიური სქესის"
        assert added not in get("civil_code", "1120", as_of="2024-09-16").article.text
        assert added in get("civil_code", "1120", as_of="2024-09-17").article.text

    def test_civil_code_198_gains_a_paragraph_in_2026(self, connector_service_with_history):
        get = connector_service_with_history.get_article
        added = "ფაქტორინგის შესახებ"
        assert added not in get("civil_code", "198", as_of="2026-03-31").article.text
        assert added in get("civil_code", "198", as_of="2026-04-01").article.text

    def test_civil_procedure_105_and_414(self, connector_service_with_history):
        get = connector_service_with_history.get_article
        before = get("civil_procedure_code", "105", as_of="2024-02-20").article
        after = get("civil_procedure_code", "105", as_of="2024-02-21").article
        assert "მოწმის ჩვენების, მხარის ახსნა-განმარტების" not in before.text
        assert "მოწმის ჩვენების, მხარის ახსნა-განმარტების" in after.text
        ruling = "საკონსტიტუციო სასამართლოს 2025 წლის 7 მარტის გადაწყვეტილება №1/2/1731"
        assert ruling not in get("civil_procedure_code", "414", as_of="2025-03-06").article.text
        assert ruling in get("civil_procedure_code", "414", as_of="2025-03-07").article.text

    def test_labour_code_47_before_its_2024_correction(self, connector_service_with_history):
        get = connector_service_with_history.get_article
        assert "„დ) დასაქმებულის" in get("labour_code", "47", as_of="2024-09-16").article.text
        assert "„დ) დასაქმებულის" not in get("labour_code", "47", as_of="2024-09-17").article.text

    def test_requested_paragraph_comes_from_that_version(self, connector_service_with_history):
        result = connector_service_with_history.get_article(
            "civil_code", "1343", paragraph="1", as_of="2025-01-01")
        assert result.article.requested_paragraph.number == "1"
        assert "მოხუცთა" in result.article.requested_paragraph.text
        missing = connector_service_with_history.get_article(
            "civil_code", "1343", paragraph="9", as_of="2025-01-01")
        assert missing.found and missing.article.requested_paragraph is None
        assert "Paragraph 9 is not in that version" in missing.message

    def test_article_added_later_is_not_cited_for_an_earlier_date(
        self, connector_service_with_history
    ):
        result = connector_service_with_history.get_article(
            "labour_code", "14-1", as_of="2024-01-01")
        assert result.found is False and result.article is None
        assert "2023-11-30" in result.message and "do not cite it for that date" in result.message
        later = connector_service_with_history.get_article(
            "labour_code", "14¹", as_of="2025-01-01")
        assert later.article.article_number == "მუხლი 14¹"
        assert later.article.wording_from == "2024-09-17"

    def test_date_before_the_stored_versions_is_refused_not_guessed(
        self, connector_service_with_history
    ):
        result = connector_service_with_history.get_article(
            "civil_code", "1343", as_of="2019-05-01")
        assert result.found is False
        assert "start on 2023-12-15" in result.message
        assert "Do not state it from memory" in result.message

    def test_today_or_later_gives_the_current_stored_text(self, connector_service_with_history):
        result = connector_service_with_history.get_article(
            "labour_code", "47", as_of="2999-01-01")
        assert result.found and result.article.as_of is None

    def test_unknown_code(self, connector_service_with_history):
        assert connector_service_with_history.get_article(
            "no_such_code", "1", as_of="2025-01-01").found is False

    def test_server_without_history_says_so(self, connector_service):
        absent = connector_service.get_article("labour_code", "47", as_of="2025-01-01")
        assert absent.found is False and absent.message == HISTORY_UNAVAILABLE


class TestListChanges:
    def test_lists_what_changed_with_version_links(self, connector_service_with_history):
        result = connector_service_with_history.list_changes("civil_code", "2025-01-01")
        assert result.found and result.total_changes == 4
        assert result.history_from == "2023-12-15"
        assert [(c.article_number, c.change, c.version_date) for c in result.changes] == [
            ("მუხლი 1343", "amended", "2025-06-26"),
            ("მუხლი 1343", "amended", "2025-09-19"),
            ("მუხლი 198", "amended", "2026-04-01"),
            ("მუხლი 1343", "amended", "2026-06-23"),
        ]
        assert all(c.version_url.startswith(CIVIL_CODE + "?publication=") for c in result.changes)
        assert "take effect later" in result.message

    def test_one_article_and_an_added_article(self, connector_service_with_history):
        one = connector_service_with_history.list_changes("civil_code", "2024-01-01", "1120")
        assert [c.version_date for c in one.changes] == ["2024-09-17"]
        added = connector_service_with_history.list_changes(
            "civil_procedure_code", "2025-01-01", "363⁵³")
        assert [(c.change, c.version_date) for c in added.changes] == [("added", "2025-06-26")]

    def test_says_where_the_history_starts_and_when_nothing_changed(
        self, connector_service_with_history
    ):
        early = connector_service_with_history.list_changes("labour_code", "2015-01-01")
        assert "start on 2023-11-30" in early.message
        quiet = connector_service_with_history.list_changes("labour_code", "2026-10-01", "47")
        assert quiet.found and quiet.changes == []
        assert "No stored version dated on or after 2026-10-01 changed article 47" in quiet.message

    def test_bad_date_and_unknown_code(self, connector_service_with_history):
        assert connector_service_with_history.list_changes("civil_code", "soon").found is False
        assert connector_service_with_history.list_changes("nope", "2025-01-01").found is False

    def test_server_without_history_says_so(self, connector_service):
        absent = connector_service.list_changes("civil_code", "2025-01-01")
        assert absent.found is False and absent.message == HISTORY_UNAVAILABLE


class TestCoverageWithHistory:
    def test_each_law_says_how_far_back_its_wordings_reach(self, connector_service_with_history):
        laws = {law.code: law for law in connector_service_with_history.get_coverage().laws}
        assert laws["civil_code"].history_from == "2023-12-15"
        assert laws["civil_code"].history_versions == 12
        assert laws["labour_code"].history_from == "2023-11-30"
        assert laws["civil_procedure_code"].history_versions == 15


class TestOverTheWire:
    async def test_mcp_get_article_as_of_and_list_changes(self, connector_service_with_history):
        server = build_connector_mcp_server(connector_service_with_history)
        async with Client(server) as client:
            article = (await client.call_tool("get_article", {
                "code": "civil_code", "article": 1120, "as_of": "2024-01-01",
            })).structured_content
            changes = (await client.call_tool("list_changes", {
                "code": "civil_code", "since": "2024-01-01", "article": 1120,
            })).structured_content
        assert article["article"]["version_date"] == "2023-12-15"
        assert article["article"]["replaced_on"] == "2024-09-17"
        assert "ბიოლოგიური სქესის" not in article["article"]["text"]
        assert "freshness_warning" in article
        assert [c["change"] for c in changes["changes"]] == ["amended"]

    def test_rest_article_as_of_and_changes(self, connector_service_with_history):
        from app.connector_main import create_connector_app

        with TestClient(create_connector_app()) as client:
            article = client.get("/api/v1/connector/articles", params={
                "code": "labour_code", "article": "47", "as_of": "2024-01-01",
            }).json()
            changes = client.get("/api/v1/connector/changes", params={
                "code": "labour_code", "since": "2024-01-01",
            }).json()
        assert article["article"]["source_url"].endswith("?publication=26#part_173")
        assert article["article"]["wording_from"] is None
        assert {(c["article_number"], c["change"]) for c in changes["changes"]} == {
            ("მუხლი 47", "amended"), ("მუხლი 14¹", "added")}
