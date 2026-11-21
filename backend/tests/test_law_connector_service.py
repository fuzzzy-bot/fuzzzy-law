"""
Tests for the law connector service — every tool, on real stored law text.

The fixture store holds real articles copied from the store the live server
serves, including Civil Procedure Code art. 369 with its first paragraph
missing (the gap the 2026-10-24 compliance test found), so the tests also
prove the connector says so instead of hiding it.
"""

from __future__ import annotations

from app.schemas.connector_schema import NOT_LEGAL_ADVICE, VERSION_UNKNOWN_NOTE
from app.services.article_store_service import ArticleStoreService
from app.services.court_store_service import CourtStoreService
from app.services.law_connector_service import LawConnectorService
from tests.conftest import (
    COURT_FIXTURE_WITH_CONSTITUTIONAL,
    build_connector_article_store,
    build_court_store,
)

MATSNE = "https://matsne.gov.ge/ka/document/view/"


def _with_court(store, tmp_path) -> LawConnectorService:
    court = CourtStoreService(build_court_store(tmp_path / "court_store.db"))
    return LawConnectorService(store=store, court=court)


def _with_three_courts(store, tmp_path) -> LawConnectorService:
    court = CourtStoreService(
        build_court_store(tmp_path / "court_store.db", COURT_FIXTURE_WITH_CONSTITUTIONAL))
    return LawConnectorService(store=store, court=court)


class TestListCodes:
    def test_lists_codes_with_links_and_counts(self, connector_service):
        result = connector_service.list_codes()
        by_code = {c.code: c for c in result.codes}
        assert set(by_code) == {"civil_code", "civil_procedure_code", "labour_code"}
        assert by_code["labour_code"].source_url == MATSNE + "1155567"
        assert by_code["civil_code"].article_count > 0
        assert by_code["civil_code"].version_date is None
        assert by_code["civil_code"].version_note == VERSION_UNKNOWN_NOTE


class TestSearchLaw:
    def test_finds_appeal_deadline_article_with_exact_snippet(
        self, connector_service, connector_store
    ):
        result = connector_service.search_law("სააპელაციო საჩივრის შეტანის ვადა")
        assert result.found
        top = result.results[0]
        assert top.id == "article:civil_procedure_code:369"
        assert top.article_number == "მუხლი 369"
        stored = connector_store.get_article("civil_procedure_code", "369")["content_ka"]
        assert top.snippet.removesuffix(" …") in stored
        assert top.source_url == MATSNE + "29962#article_369"

    def test_inflected_words_still_match(self, connector_service):
        """'ხანდაზმულობას' is not literally in the text; its stem is."""
        result = connector_service.search_law("ხანდაზმულობას როდის წყვეტს სარჩელი")
        assert result.found
        assert any(h.code == "civil_code" for h in result.results)

    def test_code_filter(self, connector_service):
        result = connector_service.search_law("ვადა", code="labour_code")
        assert result.results
        assert all(h.code == "labour_code" for h in result.results)

    def test_unknown_code_is_reported(self, connector_service):
        result = connector_service.search_law("ვადა", code="space_law")
        assert not result.found
        assert "list_codes" in result.message

    def test_nothing_found_says_so(self, connector_service):
        result = connector_service.search_law("კრიპტოვალუტა ბლოკჩეინი")
        assert not result.found
        assert result.results == []
        assert "Do not answer from memory" in result.message

    def test_everyday_words_are_also_searched_in_the_laws_own_terms(self, connector_service):
        """'They fired me' holds none of the Labour Code's words for ending a contract."""
        result = connector_service.search_law("სამსახურიდან გამათავისუფლეს, რა ვქნა")
        assert result.also_searched == ["შრომითი ხელშეკრულების შეწყვეტის საფუძვლები"]
        assert result.results[0].id == "article:labour_code:47"

    def test_law_terms_lead_but_do_not_replace_the_words_asked(self, connector_service):
        result = connector_service.search_law("ქირა და სააპელაციო საჩივრის შეტანის ვადა")
        assert result.also_searched == ["ქირავნობის ხელშეკრულების მოშლა"]
        assert "article:civil_procedure_code:369" in [h.id for h in result.results]

    def test_question_in_the_laws_own_terms_is_searched_once(self, connector_service):
        result = connector_service.search_law("სააპელაციო საჩივრის შეტანის ვადა")
        assert result.also_searched == []

    def test_limit_is_capped(self, connector_service):
        assert len(connector_service.search_law("ვადა", limit=500).results) <= 25


class TestGetArticle:
    def test_full_text_paragraphs_and_neighbours(self, connector_service, connector_store):
        result = connector_service.get_article("civil_code", "138")
        assert result.found
        art = result.article
        assert art.text == connector_store.get_article("civil_code", "138")["content_ka"]
        assert art.previous_article.article_number == "მუხლი 137"
        assert art.next_article.article_number == "მუხლი 139"
        assert art.source_url == MATSNE + "31702#article_138"

    def test_georgian_code_name_and_article_forms(self, connector_service):
        assert connector_service.get_article("შრომის კოდექსი", "მუხლი 48").found
        assert connector_service.get_article("labour_code", "48-ე").found

    def test_requested_paragraph(self, connector_service):
        art = connector_service.get_article("labour_code", "48", paragraph="1").article
        assert art.requested_paragraph is not None
        assert art.requested_paragraph.number == "1"

    def test_missing_paragraph_is_reported(self, connector_service):
        result = connector_service.get_article("labour_code", "48", paragraph="99")
        assert result.found
        assert "Paragraph 99" in result.message

    def test_missing_first_paragraph_is_flagged(self, connector_service):
        """Art. 369 is stored without part 1 (the 14-day term): say so."""
        art = connector_service.get_article("civil_procedure_code", "369").article
        assert "starts at paragraph 2" in art.version_note

    def test_an_unclear_number_is_refused_never_cut_to_another_article(self, connector_service):
        # "48 1" and "48.1" must not quietly become article 48 (as "14^1" once became 14).
        for unclear in ("48 1", "48.1", "48, 49", "XLVIII"):
            result = connector_service.get_article("labour_code", unclear)
            assert not result.found and result.article is None
            assert "166¹" in result.message
            check = connector_service.verify_citation("labour_code", unclear, claim="x")
            assert check.exists is False and "not one article number" in check.message

    def test_superscript_forms_ask_for_the_same_article(self):
        from app.services.article_store_service import requested_article
        assert {requested_article(a) for a in ("166¹", "166-1", "166^1", "მუხლი 166¹")} == {
            "166-1"}
        assert requested_article("Article 48") == requested_article("48-ე მუხლი") == "48"
        assert requested_article("141") == "141"  # a different article, never 14¹

    def test_unknown_article_is_not_invented(self, connector_service):
        result = connector_service.get_article("civil_code", "99999")
        assert not result.found
        assert "do not cite it" in result.message

    def test_unknown_code_never_falls_back_to_another_code(self, connector_service):
        result = connector_service.get_article("nonexistent_code", "138")
        assert not result.found
        assert "Unknown code" in result.message


class TestBrowseCode:
    def test_lists_articles_when_no_chapters(self, connector_service):
        result = connector_service.browse_code("civil_code")
        assert result.found
        numbers = [a.article_number for a in result.articles]
        assert numbers == ["მუხლი 137", "მუხლი 138", "მუხლი 139"]

    def test_repealed_articles_are_left_out(self, connector_service):
        numbers = [a.article_number for a in connector_service.browse_code("civil_code").articles]
        assert "მუხლი 1110" not in numbers

    def test_paging(self, connector_service):
        result = connector_service.browse_code("civil_code", limit=2)
        assert len(result.articles) == 2
        assert "offset=2" in result.message

    def test_unknown_code(self, connector_service):
        assert not connector_service.browse_code("moon_code").found


class TestVerifyCitation:
    def test_exists_and_returns_actual_text(self, connector_service):
        result = connector_service.verify_citation(
            "labour_code", "48", "30 დღის ვადაში წერილობითი დასაბუთების მოთხოვნა"
        )
        assert result.exists
        assert result.text
        assert result.lexical_check.numbers_found_in_text == ["30"]

    def test_number_missing_from_text_is_shown(self, connector_service):
        result = connector_service.verify_citation(
            "civil_procedure_code", "369", "სააპელაციო საჩივრის ვადა 14 დღეა"
        )
        assert result.exists
        assert result.lexical_check.numbers_not_in_text == ["14"]
        assert "not a legal judgement" in result.lexical_check.label

    def test_invented_article(self, connector_service):
        result = connector_service.verify_citation("civil_code", "4242", "anything")
        assert not result.exists
        assert result.text is None

    def test_repealed_article(self, connector_service):
        result = connector_service.verify_citation("civil_code", "1110", "anything")
        assert result.exists
        assert result.is_repealed
        assert "repealed" in result.message

    def test_paragraph_that_does_not_exist(self, connector_service):
        result = connector_service.verify_citation("labour_code", "48", "x", paragraph="77")
        assert result.exists
        assert result.paragraph_exists is False


class TestQuoteCheck:
    CLAIM = "სარჩელის შეტანა წყვეტს ხანდაზმულობას"

    def _check(self, service, quote: str):
        return service.verify_citation("civil_code", "138", self.CLAIM, quote=quote).quote_check

    def test_no_quote_no_check(self, connector_service):
        result = connector_service.verify_citation("civil_code", "138", self.CLAIM)
        assert result.quote_check is None

    def test_exact_words_pass(self, connector_service, connector_store):
        stored = connector_store.get_article("civil_code", "138")["content_ka"]
        check = self._check(connector_service, stored[:90])
        assert check.verbatim is True

    def test_quotation_marks_and_spacing_do_not_matter(self, connector_service):
        check = self._check(
            connector_service, "«ხანდაზმულობის  ვადის დენა წყდება,\nთუ უფლებამოსილი პირი»")
        assert check.verbatim is True

    def test_left_out_middle_is_allowed_when_marked(self, connector_service):
        check = self._check(
            connector_service, "ხანდაზმულობის ვადის დენა წყდება … შეიტანს სარჩელს")
        assert check.verbatim is True

    def test_parts_in_the_wrong_order_fail(self, connector_service):
        check = self._check(
            connector_service, "შეიტანს სარჩელს … ხანდაზმულობის ვადის დენა წყდება")
        assert check.verbatim is False

    def test_changed_wording_fails_and_says_not_to_quote_it(self, connector_service):
        check = self._check(connector_service, "ხანდაზმულობის ვადის დენა ჩერდება")
        assert check.verbatim is False
        assert "Do not present" in check.note

    def test_empty_quote_fails(self, connector_service):
        assert self._check(connector_service, " … ").verbatim is False

    def test_quote_is_checked_against_the_whole_article_not_one_paragraph(self, connector_service):
        result = connector_service.verify_citation(
            "labour_code", "48", "30 დღით ადრე გაფრთხილება", paragraph="1",
            quote="არანაკლებ 30 კალენდარული დღით ადრე")
        assert result.paragraph_exists and result.quote_check.verbatim is True


class TestCourtPractice:
    def test_source_unavailable_is_honest(self, connector_service):
        result = connector_service.find_court_practice("ხანდაზმულობა")
        assert result.status == "source_unavailable"
        assert result.results == []
        assert "do not cite" in result.message

    def test_finds_real_decisions_grouped_by_case(self, connector_store, tmp_path):
        service = _with_court(connector_store, tmp_path)
        result = service.find_court_practice("ხანდაზმულობის ვადის შეწყვეტა")
        assert result.status == "found"
        ids = [d.id for d in result.results]
        assert ids.count("case:court_practice:AS-664-2023") == 1
        decision = next(d for d in result.results if d.collection == "court_practice")
        assert decision.case_number == "AS-664-2023"
        assert decision.date == "2023-05-12" and decision.year == "2023"
        assert decision.decision_type == "განჩინება"
        assert "ხანდაზმულობის ვადის დენა" in decision.snippet
        assert decision.source_url is None and "supremecourt.ge" in decision.link_note
        chamber = next(d for d in result.results if d.collection == "grand_chamber")
        assert chamber.source_url.startswith("https://www.supremecourt.ge/")

    def test_none_found(self, connector_store, tmp_path):
        service = _with_court(connector_store, tmp_path)
        result = service.find_court_practice("საავტორო უფლებები პროგრამულ უზრუნველყოფაზე")
        assert result.status == "none_found"
        assert "invent case numbers" in result.message

    def test_parties_stay_as_the_court_published_them(self, connector_store, tmp_path):
        service = _with_court(connector_store, tmp_path)
        doc = service.fetch("case:court_practice:AS-664-2023")
        assert "გ. ხ-ემ" in doc.text

    def test_fetch_case_joins_passages_in_order(self, connector_store, tmp_path):
        service = _with_court(connector_store, tmp_path)
        doc = service.fetch("case:court_practice:AS-664-2023")
        assert doc.text.index("ხანდაზმულობის") < doc.text.index("არ დაკმაყოფილდეს")
        assert doc.metadata["date"] == "2023-05-12"
        assert "part_note" not in doc.metadata

    def test_search_id_opens_the_decision_at_the_matching_passage(
        self, connector_store, tmp_path, monkeypatch
    ):
        from app.services import law_connector_service as module

        monkeypatch.setattr(module, "FETCH_PASSAGES", 1)
        monkeypatch.setattr(module, "FETCH_PASSAGES_BEFORE", 0)
        service = _with_court(connector_store, tmp_path)
        total = service._court.get_decision("case:court_practice:AS-664-2023")["passage_count"]
        doc = service.fetch(f"case:court_practice:AS-664-2023@{total - 1}")
        assert doc.id == "case:court_practice:AS-664-2023"
        assert "არ დაკმაყოფილდეს" in doc.text
        assert f"passages {total - 1}-{total - 1} of 0-{total - 1}" in doc.metadata["part_note"]

    def test_fetch_unknown_case(self, connector_store, tmp_path):
        service = _with_court(connector_store, tmp_path)
        assert service.fetch("case:court_practice:AS-1-1900") is None
        assert service.fetch("case:nowhere:AS-664-2023") is None


class TestCourtDecision:
    ID = "case:court_practice:AS-664-2023"

    def test_reads_the_decision_as_published_with_numbered_passages(
        self, connector_store, tmp_path
    ):
        service = _with_court(connector_store, tmp_path)
        result = service.get_court_decision(self.ID)
        assert result.found and result.decision.case_number == "AS-664-2023"
        assert [p.number for p in result.passages] == [0, 1, 2, 3]
        assert "გ. ხ-ემ" in result.passages[1].text
        assert result.total_passages == 4 and result.next_passage is None
        assert result.message is None
        assert result.notice == NOT_LEGAL_ADVICE

    def test_long_decision_is_read_in_runs(self, connector_store, tmp_path, monkeypatch):
        from app.services import law_connector_service as module

        monkeypatch.setattr(module, "DECISION_PASSAGES_PER_CALL", 2)
        service = _with_court(connector_store, tmp_path)
        first = service.get_court_decision(self.ID)
        assert [p.number for p in first.passages] == [0, 1]
        assert first.next_passage == 2
        assert "from_passage=2" in first.message
        assert "have not read" in first.message
        rest = service.get_court_decision(self.ID, from_passage=first.next_passage)
        assert [p.number for p in rest.passages] == [2, 3]
        assert "არ დაკმაყოფილდეს" in rest.passages[-1].text
        assert rest.next_passage is None

    def test_printed_case_number_finds_the_decision(self, connector_store, tmp_path):
        service = _with_court(connector_store, tmp_path)
        result = service.get_court_decision("№ as-664-2023")
        assert result.found and result.decision.id == self.ID

    def test_search_id_with_passage_mark_starts_there(self, connector_store, tmp_path):
        service = _with_court(connector_store, tmp_path)
        result = service.get_court_decision(f"{self.ID}@2")
        assert result.passages[0].number == 2

    def test_start_past_the_end_gives_the_last_passage(self, connector_store, tmp_path):
        service = _with_court(connector_store, tmp_path)
        result = service.get_court_decision(self.ID, from_passage=999)
        assert [p.number for p in result.passages] == [3]

    def test_unknown_decision_is_not_described(self, connector_store, tmp_path):
        service = _with_court(connector_store, tmp_path)
        for unknown in ("case:court_practice:AS-1-1900", "AS-1-1900", "  "):
            result = service.get_court_decision(unknown)
            assert not result.found and result.passages == []
            assert "Do not describe" in result.message

    def test_no_court_source(self, connector_service):
        assert not connector_service.get_court_decision(self.ID).found


class TestConstitutionalCourt:
    """The third collection: judgments the Constitutional Court publishes with names."""

    ID = "case:constitutional_court:N3/1/9001,9002"

    def test_found_beside_supreme_court_decisions_and_named(self, connector_store, tmp_path):
        service = _with_three_courts(connector_store, tmp_path)
        result = service.find_court_practice("ხანდაზმულობის ვადის")
        by_id = {d.id: d for d in result.results}
        assert set(by_id) == {
            self.ID, "case:court_practice:AS-664-2023", "case:grand_chamber:GC-12-2022"}
        judgment = by_id[self.ID]
        assert "Constitutional Court of Georgia" in judgment.court
        assert judgment.source_url.startswith("https://www.constcourt.ge/")
        assert judgment.link_note is None
        assert "as the court published it" in judgment.names_note
        assert by_id["case:court_practice:AS-664-2023"].names_note is None
        assert "name the court" in result.message

    def test_search_can_be_kept_to_one_court(self, connector_store, tmp_path):
        service = _with_three_courts(connector_store, tmp_path)
        only = service.find_court_practice("ხანდაზმულობის ვადის", court="constitutional")
        assert [d.id for d in only.results] == [self.ID]
        assert only.decisions_through == "2024-02-20"
        assert list(only.decisions_through_by_court.values()) == ["2024-02-20"]
        supreme = service.find_court_practice("ხანდაზმულობის ვადის", court="supreme")
        assert {d.collection for d in supreme.results} == {"court_practice", "grand_chamber"}
        assert supreme.decisions_through == "2023-05-12"

    def test_each_court_says_how_far_its_decisions_reach(self, connector_store, tmp_path):
        service = _with_three_courts(connector_store, tmp_path)
        reach = service.find_court_practice("ხანდაზმულობის ვადის").decisions_through_by_court
        assert reach == {
            "საქართველოს უზენაესი სასამართლო (Supreme Court of Georgia)": "2023-05-12",
            "საქართველოს უზენაესი სასამართლოს დიდი პალატა "
            "(Supreme Court of Georgia, Grand Chamber)": "2022-06-03",
            "საქართველოს საკონსტიტუციო სასამართლო (Constitutional Court of Georgia)": "2024-02-20",
        }
        supreme_case = service.fetch("case:court_practice:AS-664-2023")
        assert supreme_case.metadata["decisions_through"] == "2023-05-12"
        judgment = service.fetch(self.ID)
        assert judgment.metadata["decisions_through"] == "2024-02-20"
        assert "names_note" in judgment.metadata and "names_note" not in supreme_case.metadata

    def test_read_by_any_of_its_joined_numbers(self, connector_store, tmp_path):
        service = _with_three_courts(connector_store, tmp_path)
        for asked in ("3/1/9002", "N3/1/9001,9002", self.ID):
            text = service.get_court_decision(asked)
            assert text.found and text.decision.id == self.ID, asked
        assert "ნინო მაგალითაძე" in text.passages[0].text
        assert text.decision.names_note

    def test_asking_for_a_court_that_is_not_held_says_so(self, connector_store, tmp_path):
        service = _with_court(connector_store, tmp_path)
        result = service.find_court_practice("ხანდაზმულობის ვადის", court="constitutional")
        assert result.status == "none_found" and result.results == []
        assert "No decisions of that court are held" in result.message
        assert result.decisions_through is None

    def test_coverage_names_the_court_and_what_of_it_is_missing(self, connector_store, tmp_path):
        held = _with_three_courts(connector_store, tmp_path).get_coverage()
        assert "constitutional_court" in {c.collection for c in held.court_decisions}
        assert "Constitutional Court decisions." not in held.not_covered
        assert any("only judgments" in line for line in held.not_covered)
        (tmp_path / "other").mkdir()
        absent = _with_court(connector_store, tmp_path / "other").get_coverage()
        assert "Constitutional Court decisions." in absent.not_covered


class TestCoverage:
    def test_names_every_law_and_court_held(self, connector_store, tmp_path):
        service = _with_court(connector_store, tmp_path)
        result = service.get_coverage()
        assert [law.code for law in result.laws] == [
            "civil_code", "civil_procedure_code", "labour_code"]
        assert all(law.source_url.startswith(MATSNE) for law in result.laws)
        by_collection = {c.collection: c for c in result.court_decisions}
        assert by_collection["court_practice"].decision_count == 1
        assert by_collection["court_practice"].latest == "2023-05-12"
        assert by_collection["grand_chamber"].earliest == "2022-06-03"

    def test_says_what_is_not_held(self, connector_service):
        result = connector_service.get_coverage()
        assert result.court_decisions == []
        assert any("Constitutional Court" in line for line in result.not_covered)
        assert any("courts of appeal" in line for line in result.not_covered)

    def test_without_history_no_law_claims_earlier_wordings(self, connector_service):
        result = connector_service.get_coverage()
        assert all(law.history_from is None and law.history_versions == 0 for law in result.laws)

    def test_says_where_each_kind_of_data_comes_from_and_how_it_stays_current(
        self, connector_store, tmp_path
    ):
        import sqlite3
        service = _with_three_courts(connector_store, tmp_path)
        conn = sqlite3.connect(tmp_path / "court_store.db")  # as build_court_store.py records it
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('built_at', '2026-11-15T15:38:16Z')")
        conn.commit()
        conn.close()
        notes = {n.data: n for n in service.get_coverage().how_data_is_kept}
        laws = notes["Law texts (current version)"]
        assert laws.source_url == "https://matsne.gov.ge"
        assert "Every night" in laws.how_kept_current and "50" in laws.how_kept_current
        supreme = notes["Supreme Court decisions (including the Grand Chamber)"]
        assert supreme.last_updated == "2026-11-15"
        assert "Not yet updated automatically" in supreme.how_kept_current
        assert "initials" in supreme.how_collected
        assert notes["Constitutional Court judgments"].last_updated == "2026-11-15"
        # No law history here, so no note claims earlier wordings.
        assert "Earlier wordings of articles" not in notes

    def test_without_courts_only_the_laws_are_described(self, connector_service):
        notes = connector_service.get_coverage().how_data_is_kept
        assert [n.data for n in notes] == ["Law texts (current version)"]

    def test_says_the_supreme_court_collections_are_a_selection(self, connector_service):
        assert any("not proof that the court never ruled" in line
                   for line in connector_service.get_coverage().not_covered)


class TestLegalAid:
    def test_gives_the_state_service_first_with_contacts_and_legal_basis(self, connector_service):
        result = connector_service.legal_aid()
        service = result.providers[0]
        assert "იურიდიული დახმარების სამსახური" in service.name
        assert service.phone.startswith("1485")
        assert service.website == "https://www.legalaid.ge"
        assert "matsne.gov.ge/ka/document/view/21604" in service.legal_basis

    def test_every_provider_has_a_website_and_says_who_it_is_free_for(self, connector_service):
        for provider in connector_service.legal_aid().providers:
            assert provider.website.startswith("https://")
            assert provider.free_for and provider.helps_with

    def test_carries_the_date_checked_and_promises_nothing(self, connector_service):
        from datetime import date

        result = connector_service.legal_aid()
        assert date.fromisoformat(result.checked_on) <= date.today()
        assert "Do not promise" in result.message
        assert "112" in result.emergency
        assert result.notice == NOT_LEGAL_ADVICE


class TestSearchAndFetch:
    def test_search_returns_ids_titles_urls(self, connector_service):
        result = connector_service.search("ხანდაზმულობის ვადის დენის შეწყვეტა")
        assert result.results
        for item in result.results:
            assert item.id and item.title and item.url.startswith("https://")

    def test_fetch_article(self, connector_service):
        doc = connector_service.fetch("article:civil_code:138")
        assert "138" in doc.title
        assert doc.url == MATSNE + "31702#article_138"
        assert doc.metadata["notice"] == NOT_LEGAL_ADVICE

    def test_fetch_unknown_id(self, connector_service):
        assert connector_service.fetch("article:nope:1") is None
        assert connector_service.fetch("bogus") is None


class TestNewStoreFields:
    def test_version_fields_are_picked_up(self, tmp_path):
        store = ArticleStoreService(
            db_path=build_connector_article_store(tmp_path / "v.db", with_version_fields=True)
        )
        service = LawConnectorService(store=store)
        art = service.get_article("civil_code", "138").article
        assert art.version_date == "2026-09-30"
        assert art.in_force_since == "2024-01-01"
        assert art.version_note is None
        assert service.list_codes().codes[0].version_date == "2026-09-30"

    def test_missing_links_are_rebuilt_from_document_id(self, tmp_path):
        store = ArticleStoreService(
            db_path=build_connector_article_store(tmp_path / "n.db", without_links=True)
        )
        service = LawConnectorService(store=store)
        assert service.get_article("civil_code", "138").article.source_url == (
            MATSNE + "31702#article_138"
        )


class TestGroundedness:
    """Every item the connector returns names its source and carries the notice."""

    QUERIES = ["სააპელაციო საჩივრის ვადა", "შრომითი ხელშეკრულების შეწყვეტა", "ხანდაზმულობა"]

    def test_every_returned_item_has_a_source_link(self, connector_store, tmp_path):
        service = _with_court(connector_store, tmp_path)
        items = []
        for q in self.QUERIES:
            items += service.search_law(q).results
            items += service.find_court_practice(q).results
            for hit in service.search(q).results:
                assert hit.url.startswith("https://")
                assert service.fetch(hit.id).url.startswith("https://")
        items += [c for c in service.list_codes().codes]
        items.append(service.get_article("labour_code", "48").article)
        assert items
        for item in items:
            link = item.source_url or ("supremecourt.ge" in (getattr(item, "link_note", "") or ""))
            assert link, item
            assert item.notice == NOT_LEGAL_ADVICE
        for hit in [i for i in items if hasattr(i, "version_note") and hasattr(i, "version_date")]:
            assert hit.version_date or hit.in_force_since or hit.version_note
