"""
Tests for reading which stored law articles a court decision cites, and for the
connector's note on whether those articles changed after the decision.

The sentences are written the way the Supreme Court and the Constitutional Court
print references in the stored decisions.
"""

from __future__ import annotations

import sqlite3

from app.services.court_store_service import CourtStoreService
from app.services.decision_citations import cited_articles
from app.services.law_connector_service import LawConnectorService
from app.services.law_history_service import LawHistoryService
from tests.conftest import build_court_store, build_law_history


def _found(text: str, category: str | None = None) -> set[tuple[str, str]]:
    return {(c.code, c.article_norm) for c in cited_articles(text, category)}


class TestCitedArticles:
    def test_full_law_names_and_paragraph_forms(self):
        text = ("სასამართლომ იხელმძღვანელა საქართველოს სამოქალაქო კოდექსის 1042-ე მუხლით და "
                "საქართველოს სამოქალაქო საპროცესო კოდექსის 92.1 მუხლის მოთხოვნებით.")
        assert _found(text, "civil") == {("civil_code", "1042"), ("civil_procedure_code", "92")}

    def test_several_numbers_before_one_word_article(self):
        text = "სსსკ-ის 361-ე, 394-ე და 412-ე მუხლები ითვალისწინებს"
        assert _found(text, "civil") == {
            ("civil_procedure_code", "361"), ("civil_procedure_code", "394"),
            ("civil_procedure_code", "412")}

    def test_short_forms_follow_the_kind_of_case(self):
        text = "სსკ-ის 177-ე მუხლის პირველი ნაწილით"
        assert _found(text, "criminal") == {("criminal_code", "177")}
        assert _found(text, "civil") == {("civil_code", "177")}

    def test_ambiguous_short_form_in_an_administrative_case_is_left_unread(self):
        text = "საქართველოს ზოგადი ადმინისტრაციული კოდექსის მიხედვით, სსკ-ის 262-ე მუხლის"
        assert _found(text, "administrative") == set()

    def test_the_decisions_own_definition_wins(self):
        text = ("საქართველოს შრომის კოდექსის (შემდგომში – სსკ) 37-ე მუხლი. "
                "ამასთან, სსკ-ის 38-ე მუხლის მიხედვით")
        assert _found(text, "civil") == {("labour_code", "37"), ("labour_code", "38")}

    def test_same_law_refers_back(self):
        text = ("საქართველოს შრომის კოდექსის 48-ე მუხლის მე-3 ნაწილი; ხოლო ამავე კოდექსის "
                "მე-4 მუხლის თანახმად")
        assert _found(text, "civil") == {("labour_code", "48"), ("labour_code", "4")}

    def test_laws_not_held_are_never_guessed(self):
        text = ("შრომის კანონთა კოდექსის 37-ე მუხლით, გერმანიის სამოქალაქო კოდექსის (შემდგომში "
                "– გსკ) 242-ე მუხლი; გსკ-ის 243-ე მუხლი")
        assert _found(text, "civil") == set()

    def test_quoted_law_and_constitution(self):
        text = ("„მეწარმეთა შესახებ“ საქართველოს კანონის მე-9 მუხლი ეწინააღმდეგება "
                "საქართველოს კონსტიტუციის 31-ე მუხლის პირველ პუნქტს")
        assert _found(text, "constitutional") == {
            ("entrepreneurial_law", "9"), ("constitution", "31")}

    def test_most_cited_first(self):
        text = "სსკ-ის 151-ე მუხლით. " * 3 + "სსკ-ის 111-ე მუხლით."
        assert [c.article_norm for c in cited_articles(text, "criminal")] == ["151", "111"]


def _service(store, tmp_path, decided: str, passages: list[str]) -> LawConnectorService:
    decision = {
        "collection": "court_practice", "case_number": "AS-1-2024", "category": "civil",
        "decision_type": "განჩინება", "decision_date": decided, "source_url": None,
        "passages": passages,
    }
    court = CourtStoreService(build_court_store(tmp_path / "court_store.db", [decision]))
    history_path = build_law_history(tmp_path / "law_history.db")
    # An article the fixture versions never changed, to show "unchanged" and "unknown".
    conn = sqlite3.connect(history_path)
    conn.execute(
        "INSERT INTO article_versions (document_id, article_norm, from_publication, "
        "closed_by_publication, article_number, article_title, content_ka, paragraphs_json, "
        "is_repealed, matsne_anchor, content_sha256) VALUES "
        "('civil_code','1',129,NULL,'მუხლი 1','ტესტი','ტექსტი','[]',0,NULL,'x')")
    conn.commit()
    conn.close()
    return LawConnectorService(store=store, court=court, history=LawHistoryService(history_path))


class TestLawSinceDecision:
    TEXT = ["განჩინება", "სსკ-ის 1343-ე მუხლით და სსკ-ის 1343-ე მუხლით, სსკ-ის 1-ლი მუხლი, "
            "სსკ-ის 1-ე მუხლი; სსსკ-ის 105-ე მუხლი; სსკ-ის 9999-ე მუხლი"]

    def test_lists_cited_articles_and_what_changed_after_the_decision(
        self, connector_store, tmp_path
    ):
        result = _service(connector_store, tmp_path, "2025-01-10", self.TEXT).get_court_decision(
            "case:court_practice:AS-1-2024")
        note = result.law_since_decision
        assert note is not None and note.decision_date == "2025-01-10"
        by_article = {(a.code, a.article_number): a for a in note.articles}
        changed = by_article[("civil_code", "მუხლი 1343")]
        assert changed.status == "changed" and changed.mentions == 2
        assert changed.changed_on == ["2025-06-26", "2025-09-19", "2026-06-23"]
        assert by_article[("civil_code", "მუხლი 1")].status == "unchanged"
        # Changed before the decision, not after it.
        assert by_article[("civil_procedure_code", "მუხლი 105")].status == "unchanged"
        assert all(a.article_number != "მუხლი 9999" for a in note.articles)  # no such article
        assert "still cite older decisions" in note.message
        assert "as_of=2025-01-10" in note.message

    def test_decision_older_than_the_stored_wordings(self, connector_store, tmp_path):
        result = _service(connector_store, tmp_path, "2019-05-01", self.TEXT).get_court_decision(
            "case:court_practice:AS-1-2024")
        by_article = {a.article_number: a for a in result.law_since_decision.articles}
        assert by_article["მუხლი 1"].status == "unknown"
        assert by_article["მუხლი 1"].checked_from == "2023-12-15"
        assert by_article["მუხლი 1343"].status == "changed"

    def test_no_note_without_a_law_history(self, connector_store, tmp_path):
        decision = {
            "collection": "court_practice", "case_number": "AS-2-2024", "category": "civil",
            "decision_type": "განჩინება", "decision_date": "2024-01-10", "source_url": None,
            "passages": self.TEXT,
        }
        court = CourtStoreService(build_court_store(tmp_path / "c.db", [decision]))
        service = LawConnectorService(
            store=connector_store, court=court,
            history=LawHistoryService(tmp_path / "missing.db"))
        assert service.get_court_decision("AS-2-2024").law_since_decision is None
