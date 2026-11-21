"""Tests for the court store builder (scripts/build_court_store.py)."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "build_court_store", Path(__file__).resolve().parent.parent / "scripts" / "build_court_store.py"
)
build_court_store = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = build_court_store  # dataclasses look the module up by name
_SPEC.loader.exec_module(build_court_store)

DECISION = (
    "განჩინება\nსაქართველოს სახელით\n#ას-327-2020\n18 ივლისი, 2023 წ., ქ. თბილისი\n"
    "საქართველოს უზენაესი სასამართლოს სამოქალაქო საქმეთა\nპალატა\n"
    "დავის საგანი: თანხის დაკისრება\nაღწერილობითი ნაწილი:\n"
    "1. მოსარჩელე გ. ხ-ემ სარჩელი აღძრა სს `ბ-ას~ მიმართ და მოითხოვა თანხის დაკის-\n"
    "რება.\n[PAGE_2]\n2\n"
    "2. სსკ-ის 138-ე მუხლით, ხანდაზმულობის ვადის დენა წყდება სარჩელის შეტანით.\n"
)


class TestReadHeading:
    def test_case_number_date_and_type(self):
        heading = build_court_store.clean_lines(DECISION)[:build_court_store.HEADING_LINES]
        assert build_court_store.read_case_number(heading) == "ას-327-2020"
        assert build_court_store.read_date(heading) == "2023-07-18"
        assert build_court_store.read_type(heading) == "განჩინება"

    def test_case_number_shapes(self):
        read = build_court_store.read_case_number
        assert read(["#საქმე #1238აპ-24"]) == "1238აპ-24"
        assert read(["საქმე №ბს-493 (2კ-23)   5 მაისი, 2023 წ."]) == "ბს-493 (2კ-23)"
        assert read(["№ას-17-2021 12 მარტი, 2021 წელი"]) == "ას-17-2021"
        assert read(["#-ბს-100-95(კ-09)"]) == "ბს-100-95(კ-09)"  # a stray dash in front

    def test_a_number_that_cannot_be_trusted_is_not_a_case_number(self):
        read = build_court_store.read_case_number
        assert read(["#291-23"]) is None           # no letter: a misread or registry number
        assert read(["განჩინება", "საქართველოს სახელით"]) is None
        assert read(["# - "]) is None

    def test_date_needs_a_real_month(self):
        assert build_court_store.read_date(["18 ივლისი, 2023 წ."]) == "2023-07-18"
        assert build_court_store.read_date(["18 მუხლი, 2023"]) is None


class TestCleanAndSplit:
    def test_page_marks_numbers_and_print_hyphens_go(self):
        lines = build_court_store.clean_lines(DECISION)
        assert not any(line.startswith("[PAGE_") or line == "2" for line in lines)
        assert any("თანხის დაკისრება." in line for line in lines)

    def test_a_hyphen_inside_a_case_number_or_initials_stays(self):
        assert build_court_store.clean_lines("ხ-ემ\nსარჩელი")[0] == "ხ-ემ"
        assert build_court_store.clean_lines("138-\nე მუხლი") == ["138-", "ე მუხლი"]

    def test_passages_keep_every_word_and_stay_under_the_limit(self):
        lines = ["სათაური"] * build_court_store.HEADING_LINES + [
            f"{n}. " + "სასამართლომ განმარტა ხანდაზმულობის ვადა. " * 20 for n in range(1, 6)
        ]
        passages = build_court_store.split_passages(lines, limit=300)
        assert all(len(p) <= 300 for p in passages)
        assert " ".join(" ".join(passages).split()) == " ".join(" ".join(lines).split())


class TestBuild:
    def _texts(self, tmp_path: Path) -> Path:
        root = tmp_path / "extracted"
        (root / "civil").mkdir(parents=True)
        (root / "civil" / "ას-327-2020.txt").write_text(DECISION, encoding="utf-8")
        (root / "civil" / "copy.txt").write_text(DECISION + "3. დამატება.\n", encoding="utf-8")
        (root / "civil" / "case_7.txt").write_text(
            "განჩინება\nსაქართველოს სახელით\n1. ხანდაზმულობის ვადა.\n", encoding="utf-8"
        )
        return root

    def test_only_decisions_with_a_printed_case_number_are_stored(self, tmp_path):
        report = {"skipped_no_case_number": [], "duplicates": []}
        decisions = build_court_store.collect(self._texts(tmp_path), "court_practice", report)
        assert [d.decision_id for d in decisions] == ["case:court_practice:ას-327-2020"]
        assert report["skipped_no_case_number"] == ["court_practice/civil/case_7.txt"]
        assert len(report["duplicates"]) == 1
        assert "დამატება" in decisions[0].passages[-1]      # the longer copy is the one kept

    def test_store_is_searchable_and_replaces_the_old_file_whole(self, tmp_path):
        report = {"skipped_no_case_number": [], "duplicates": []}
        decisions = build_court_store.collect(self._texts(tmp_path), "court_practice", report)
        out = tmp_path / "store" / "court_store.db"
        out.parent.mkdir()
        out.write_text("old", encoding="utf-8")
        build_court_store.write_store(decisions, out)
        assert not out.with_suffix(".building").exists()
        conn = sqlite3.connect(out)
        row = conn.execute(
            "SELECT case_number, category, decision_type, decision_date, year, passage_count "
            "FROM decisions"
        ).fetchone()
        assert row[:5] == ("ას-327-2020", "civil", "განჩინება", "2023-07-18", "2023")
        assert row[5] == conn.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        hits = conn.execute(
            "SELECT p.text FROM passages_fts f JOIN passages p ON p.passage_id = f.rowid "
            "WHERE passages_fts MATCH '\"ხანდაზმულობ\"*'"
        ).fetchall()
        assert hits and "ხანდაზმულობის ვადის დენა" in hits[0][0]
        assert dict(conn.execute("SELECT key, value FROM meta"))["decision_count"] == "1"
        conn.close()


CONSTITUTIONAL_TEXT = (
    "ნიკო სანიმუშოშვილი საქართველოს პარლამენტის წინააღმდეგ\nდოკუმენტის ტიპი გადაწყვეტილება\n"
    "ნომერი N1/2/882\nთარიღი 24 ივნისი 2026\nკოლეგიის შემადგენლობა:\n"
    "ვასილ როინიშვილი – სხდომის თავმჯდომარე;\nI\nაღწერილობითი ნაწილი\n"
    "1. საქართველოს საკონსტიტუციო სასამართლოს 2017 წლის 27 მარტს კონსტიტუციური სარჩელით "
    "(რეგისტრაციის №882) მომართა ნიკო სანიმუშოშვილმა.\n"
    "2. მოსარჩელის განმარტებით, სადავო ნორმა არღვევს პიროვნების თავისუფალი განვითარების უფლე-\n"
    "ბას.\n"
)
CONSTITUTIONAL_DETAILS = {
    "case_number": "N1/2/882",
    "decision_date": "2026-06-24",
    "decision_type": "გადაწყვეტილება",
    "case_title": "ნიკო სანიმუშოშვილი საქართველოს პარლამენტის წინააღმდეგ",
    "source_url": "https://www.constcourt.ge/ka/judicial-acts?legal=20023",
}


class TestConstitutionalCourt:
    def _saved(self, tmp_path: Path) -> Path:
        root = tmp_path / "constitutional_court"
        (root / "judgment").mkdir(parents=True)
        (root / "judgment" / "20023.txt").write_text(CONSTITUTIONAL_TEXT, encoding="utf-8")
        (root / "judgment" / "20023.json").write_text(
            json.dumps(CONSTITUTIONAL_DETAILS, ensure_ascii=False), encoding="utf-8")
        (root / "judgment" / "19616.txt").write_text(CONSTITUTIONAL_TEXT, encoding="utf-8")
        (root / "ruling").mkdir()
        (root / "ruling" / "20028.txt").write_text(CONSTITUTIONAL_TEXT, encoding="utf-8")
        (root / "ruling" / "20028.json").write_text(
            json.dumps({**CONSTITUTIONAL_DETAILS, "case_number": ""}), encoding="utf-8")
        return root

    def _collect(self, tmp_path: Path) -> tuple[list, dict]:
        report = {"skipped_no_case_number": [], "duplicates": []}
        decisions = build_court_store.collect(
            self._saved(tmp_path), build_court_store.CONSTITUTIONAL_COLLECTION, report)
        return decisions, report

    def test_heading_fields_come_from_the_details_file(self, tmp_path):
        decisions, _ = self._collect(tmp_path)
        assert len(decisions) == 1
        decision = decisions[0]
        assert decision.decision_id == "case:constitutional_court:N1/2/882"
        assert decision.collection == "constitutional_court"
        assert decision.category == "constitutional"
        assert decision.decision_type == "გადაწყვეტილება"
        assert decision.decision_date == "2026-06-24"
        assert decision.source_url == CONSTITUTIONAL_DETAILS["source_url"]
        assert decision.source_file == "constitutional_court/judgment/20023.txt"

    def test_a_number_is_never_read_out_of_the_text(self, tmp_path):
        _, report = self._collect(tmp_path)
        assert report["skipped_no_case_number"] == [
            "constitutional_court/judgment/19616.txt",       # no details file
            "constitutional_court/ruling/20028.txt",         # details without a number
        ]

    def test_text_is_stored_as_the_court_published_it(self, tmp_path):
        decisions, _ = self._collect(tmp_path)
        stored = " ".join(" ".join(decisions[0].passages).split())
        assert stored == " ".join(CONSTITUTIONAL_TEXT.split())      # "უფლე-" keeps its hyphen
        assert all(len(p) <= build_court_store.PASSAGE_CHARS for p in decisions[0].passages)

    def test_store_holds_the_third_collection_with_its_official_link(self, tmp_path, monkeypatch):
        supreme = tmp_path / "extracted"
        (supreme / "civil").mkdir(parents=True)
        (supreme / "civil" / "ას-327-2020.txt").write_text(DECISION, encoding="utf-8")
        out = tmp_path / "court_store.db"
        report_file = tmp_path / "report.json"
        monkeypatch.setattr(sys, "argv", [
            "build_court_store.py", "--court-practice-dir", str(supreme),
            "--constitutional-court-dir", str(self._saved(tmp_path)),
            "--out", str(out), "--report", str(report_file),
        ])
        assert build_court_store.main() == 0

        report = json.loads(report_file.read_text(encoding="utf-8"))
        assert report["by_collection"] == {
            "court_practice": 1, "grand_chamber": 0, "constitutional_court": 1}
        conn = sqlite3.connect(out)
        rows = conn.execute(
            "SELECT collection, case_number, category, decision_type, decision_date, year, "
            "source_url FROM decisions ORDER BY collection"
        ).fetchall()
        assert rows == [
            ("constitutional_court", "N1/2/882", "constitutional", "გადაწყვეტილება", "2026-06-24",
             "2026", "https://www.constcourt.ge/ka/judicial-acts?legal=20023"),
            ("court_practice", "ას-327-2020", "civil", "განჩინება", "2023-07-18", "2023", None),
        ]
        hits = conn.execute(
            "SELECT d.case_number FROM passages_fts f JOIN passages p ON p.passage_id = f.rowid "
            "JOIN decisions d ON d.decision_id = p.decision_id "
            "WHERE passages_fts MATCH '\"სანიმუშოშვილ\"*'"
        ).fetchall()
        assert hits and {row[0] for row in hits} == {"N1/2/882"}
        conn.close()
