"""Tests for reading the Supreme Court's decision collections (download listing and split).

The typewriter-font lines are as the 2026 collections print them; the decisions' Georgian
text is as the 2010 collections and the converted 2026 ones read.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


extract = _load("extract_supreme_collections")
fetch = _load("fetch_supreme_court_collections")
build_court_store = _load("build_court_store")


class TestTypewriterFont:
    def test_converts_letter_for_letter(self):
        assert "saqarTvelos uzenaesi sasamarTlos".translate(extract.ACADNUSX) == \
            "საქართველოს უზენაესი სასამართლოს"
        assert "#as-847-2025".translate(extract.ACADNUSX) == "#ას-847-2025"
        assert "`m. h-ma~".translate(extract.ACADNUSX) == "„მ. ჰ-მა“"

    def test_only_fonts_that_read_as_typewriter_georgian_are_converted(self):
        spans = [
            ("F1", "krebulSi gamoqveynebulia erTgvarovani sasamarTlo praqtikis"),
            ("F1", "da rom saqmis masalebis Tanaxmad"),
            ("F4", "Decisions of the Supreme Court of Georgia on Civil Cases"),
            ("F6", "gj uhf;lfycrbv ltkfv"),
            ("F9", "საქართველოს უზენაესი სასამართლო"),
        ]
        assert extract.typewriter_fonts(spans) == {"F1"}


def _lines(*texts: str, page: int = 1) -> list:
    return [extract.Line(t, page) for t in texts]


class TestDecisionStarts:
    def test_heading_needs_the_kind_the_number_and_the_date(self):
        lines = _lines(
            "სარჩევი", "განჩინება", "საქართველოს სახელით", "#ას-1032-2022",
            "20 ოქტომბერი, 2022 წ., ქ. თბილისი", "1. მოსარჩელემ ...",
            # A citation of another case in the text is not a heading.
            "(იხ. სუსგ #ას-463-2024, 5.07.2024წ.)",
            "გადაწყვეტილება", "#ას-64-398-09", "3 ივნისი, 2010 წ., ქ. თბილისი",
        )
        assert extract.decision_starts(lines) == [(1, "ას-1032-2022"), (7, "ას-64-398-09")]

    def test_kind_without_a_number_is_not_a_heading(self):
        lines = _lines("განჩინება", "ამ საქმეზე სასამართლომ", "არ დააკმაყოფილა")
        assert extract.decision_starts(lines) == []


class TestFullNames:
    def test_parties_as_initials_are_fine(self):
        assert extract.full_names("მოსარჩელე გ. ხ-ემ სარჩელი აღძრა ნ. ბაქაქურის წინააღმდეგ") == 0

    def test_full_names_are_counted(self):
        assert extract.full_names("მოსარჩელე გიორგი ბერიძე და მოპასუხე ნინო კაპანაძე") == 2

    def test_cited_authors_and_broken_words_are_not_parties(self):
        text = ("(იხ. გიორგი ვაშაკიძე, სამოქალაქო კოდექსის კომენტარი, გვ. 12); "
                "[რედაქტორები: დავით კერესელიძე; სოფიო ჩაჩავა]; "
                "თანხა აღიარებუ- ლია მოსარჩელის მიერ")
        assert extract.full_names(text) == 0

    def test_judges_prosecutors_and_named_institutions_are_not_parties(self):
        text = ("საქართველოს უზენაესი სასამართლოს დიდი პალატა\nშემადგენლობა:\n"
                "ლადო ჭანტურია (თავმჯდომარე),\nმერაბ ტურავა,\nნანა კლარჯეიშვილი\n"
                "კასატორი – შპს „ე. თ.“\nრუსთავის რაიონული პროკუ-\nრატურის პროკურორ ლელა "
                "ჭეშმარიტაშვილის საკასაციო საჩივარი. პროკურორმა ლელა ჭეშმარიტაშვილმა "
                "მიუთითა; მოსამართლე მერაბ ტურავას განსხვავებული აზრი; ბარათი, რომელზეც "
                "დატანილია სსიპ გიორგი აბრამიშვილის სახელობის ჰოსპიტლის ბეჭედი")
        assert extract.full_names(text) == 0

    def test_cited_constitutional_court_case_titles_are_not_parties(self):
        text = ("იხილეთ საკონსტიტუციო სასამართლოს 2007 წლის 2 ივლისის #1/2/384 გადაწყვეტილება "
                "საქმეზე დავით ჯიმშელეიშვილი, ტარიელ გვეტაძე და ნელი დალალიშვილი; ასევე "
                "გადაწყვეტილება საქმეზე „საქართველოს მოქალაქეები _ ირაკლი ქემოკლიძე და დავით "
                "ხარაძე საქართველოს პარლამენტის წინააღმდეგ“")
        assert extract.full_names(text) == 0

    def test_a_party_named_beside_officials_still_counts(self):
        text = ("პროკურორ ლელა ჭეშმარიტაშვილის საჩივარი. მსჯავრდებული გიორგი ბერიძე და "
                "დაზარალებული ნინო კაპანაძე")
        assert extract.full_names(text) == 2


class TestListing:
    def test_pdf_links_are_absolute_and_unique(self):
        page = ('<a href="/uploads/files/1/collection/samoq/samoq-01-2026.pdf">№1</a>'
                '<a href="http://old.supremecourt.ge/files/upload-file/pdf/samoq2000-11-uni.pdf">'
                '<b>№11</b></a><a href="/uploads/files/1/collection/samoq/samoq-01-2026.pdf">'
                '№1</a>')
        assert fetch.pdf_links(page, "https://www.supremecourt.ge/decisions/x") == [
            ("https://www.supremecourt.ge/uploads/files/1/collection/samoq/samoq-01-2026.pdf",
             "№1"),
            ("http://old.supremecourt.ge/files/upload-file/pdf/samoq2000-11-uni.pdf", "№11"),
        ]

    def test_local_name_is_safe(self):
        url = "https://www.supremecourt.ge/uploads/files/1/x/sadisciplino%2026%20ivlisi.pdf"
        assert fetch.local_name(url) == "sadisciplino_26_ivlisi.pdf"


class TestStoreReadsTheLink:
    def test_details_file_gives_the_collection_page(self, tmp_path):
        folder = tmp_path / "civil"
        folder.mkdir()
        text = folder / "ას-1032-2022.txt"
        text.write_text(
            "გადაწყვეტილება\nსაქართველოს სახელით\n#ას-1032-2022\n"
            "20 ოქტომბერი, 2022 წ., ქ. თბილისი\n1. ტექსტი.\n", "utf-8")
        link = "https://www.supremecourt.ge/uploads/files/1/samoq-04-2026.pdf#page=72"
        text.with_suffix(".json").write_text(json.dumps({"source_url": link}), "utf-8")
        decision = build_court_store.parse_decision(text, "court_practice", "civil")
        assert decision.case_number == "ას-1032-2022"
        assert decision.decision_date == "2022-10-20"
        assert decision.source_url == link
