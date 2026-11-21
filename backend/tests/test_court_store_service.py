"""Tests for the court store service — word search over stored decisions."""

from __future__ import annotations

import pytest

from app.services.court_store_service import (
    MAX_QUERY_TERMS,
    CourtStoreService,
    _stem_terms,
    case_number_keys,
    normalize_case_number,
)
from tests.conftest import COURT_FIXTURE_WITH_CONSTITUTIONAL, build_court_store

CIVIL = "case:court_practice:AS-664-2023"
CHAMBER = "case:grand_chamber:GC-12-2022"
CONSTITUTIONAL = "case:constitutional_court:N3/1/9001,9002"


@pytest.fixture
def court_store(tmp_path) -> CourtStoreService:
    return CourtStoreService(build_court_store(tmp_path / "court_store.db"))


@pytest.fixture
def three_courts(tmp_path) -> CourtStoreService:
    return CourtStoreService(
        build_court_store(tmp_path / "court_store.db", COURT_FIXTURE_WITH_CONSTITUTIONAL))


class TestQueryTerms:
    def test_georgian_words_lose_their_ending_and_numbers_stay_whole(self):
        assert _stem_terms("ხანდაზმულობის ვადა 138") == ['"ხანდაზმულობ"*', '"ვად"*', '"138"']

    def test_short_words_and_search_syntax_are_dropped(self):
        assert _stem_terms('და "OR" NEAR( * ^ :') == ['"nea"*']

    def test_term_count_is_capped(self):
        assert len(_stem_terms(" ".join(f"სიტყვა{i}ები" for i in range(40)))) == MAX_QUERY_TERMS


class TestSearch:
    def test_inflected_words_find_the_decision_once(self, court_store):
        rows = court_store.search("ხანდაზმულობა ვადები შეტანა")
        assert [r["decision_id"] for r in rows].count(CIVIL) == 1
        hit = next(r for r in rows if r["decision_id"] == CIVIL)
        assert hit["passage_seq"] == 2
        assert "ხანდაზმულობის ვადის დენა" in hit["passage"]

    def test_all_words_in_one_passage_rank_before_some_words(self, court_store):
        rows = court_store.search("ხანდაზმულობის სოლიდარულ მოვალეებზე")
        assert [r["decision_id"] for r in rows] == [CHAMBER, CIVIL]

    def test_limit(self, court_store):
        assert len(court_store.search("ხანდაზმულობის", limit=1)) == 1

    def test_nothing_matches(self, court_store):
        assert court_store.search("საავტორო უფლებები") == []
        assert court_store.search("") == []
        assert court_store.search('" ) (') == []

    def test_missing_store_finds_nothing(self, tmp_path):
        store = CourtStoreService(tmp_path / "absent.db")
        assert not store.is_available
        assert store.search("ხანდაზმულობა") == []
        assert store.get_decision(CIVIL) is None
        assert store.get_passages(CIVIL) == []
        assert store.find_by_case_number("AS-664-2023") == []
        assert store.summary() == []


class TestDecisions:
    def test_get_decision(self, court_store):
        row = court_store.get_decision(CIVIL)
        assert row["case_number"] == "AS-664-2023"
        assert row["decision_date"] == "2023-05-12"
        assert row["passage_count"] == 4
        assert court_store.get_decision("case:court_practice:AS-1-1900") is None

    def test_case_number_lookup_ignores_spacing_marks_and_letter_case(self, court_store):
        assert normalize_case_number("# AS-664-2023 ") == normalize_case_number("as-664-2023")
        found = court_store.find_by_case_number("№ as-664-2023")
        assert [r["decision_id"] for r in found] == [CIVIL]
        assert court_store.find_by_case_number("AS-664") == []
        assert court_store.find_by_case_number("#") == []

    def test_a_joined_constitutional_number_answers_to_each_claim(self, three_courts):
        assert case_number_keys("N3/1/9001, 9002") == {"3/1/9001,9002", "3/1/9001", "3/1/9002"}
        assert case_number_keys("AS-664-2023") == {"as-664-2023"}
        for asked in ("N3/1/9001,9002", "3/1/9001", "№3/1/9002", "n 3/1/9001, 9002"):
            found = three_courts.find_by_case_number(asked)
            assert [r["decision_id"] for r in found] == [CONSTITUTIONAL], asked
        assert three_courts.find_by_case_number("3/1/900") == []
        assert three_courts.find_by_case_number("9001") == []

    def test_search_can_be_kept_to_some_collections(self, three_courts):
        every = {r["decision_id"] for r in three_courts.search("ხანდაზმულობის ვადის")}
        assert every == {CIVIL, CHAMBER, CONSTITUTIONAL}
        only = three_courts.search("ხანდაზმულობის ვადის", collections=("constitutional_court",))
        assert [r["decision_id"] for r in only] == [CONSTITUTIONAL]
        supreme = three_courts.search(
            "ხანდაზმულობის ვადის", collections=("court_practice", "grand_chamber"))
        assert {r["decision_id"] for r in supreme} == {CIVIL, CHAMBER}

    def test_newest_date_can_be_asked_for_one_court(self, three_courts):
        assert three_courts.latest_decision_date() == "2024-02-20"
        supreme = ("court_practice", "grand_chamber")
        assert three_courts.latest_decision_date(supreme) == "2023-05-12"
        assert three_courts.latest_decision_date(("nowhere",)) is None

    def test_passages_come_in_reading_order_and_page(self, court_store):
        every = court_store.get_passages(CIVIL)
        assert len(every) == 4 and every[0].startswith("განჩინება")
        assert court_store.get_passages(CIVIL, offset=1, limit=2) == every[1:3]
        assert court_store.get_passages(CIVIL, offset=10) == []

    def test_summary_counts_per_collection(self, court_store):
        assert court_store.summary() == [
            {"collection": "court_practice", "decision_count": 1,
             "earliest": "2023-05-12", "latest": "2023-05-12"},
            {"collection": "grand_chamber", "decision_count": 1,
             "earliest": "2022-06-03", "latest": "2022-06-03"},
        ]
