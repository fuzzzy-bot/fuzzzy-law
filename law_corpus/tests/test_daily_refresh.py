"""Tests for the daily refresh of the served article store (scripts/daily_refresh.py)."""

from __future__ import annotations

import json
import random
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import daily_refresh as dr  # noqa: E402
import verify_article_store  # noqa: E402

from pipeline.models.scrape_result import ContentFormat, ScrapeResult  # noqa: E402
from pipeline.scraper.matsne_scraper import (  # noqa: E402
    CONSOLIDATED_LABEL,
    SEED_LAWS,
    MatsneScraper,
)

LAWS = {law["document_id"]: law for law in SEED_LAWS}
EARLIER = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
NOW = datetime(2026, 11, 14, 3, 0, tzinfo=UTC)


def _page_html(articles: dict[int, str], publication: str = "10", lost_force: bool = False) -> str:
    notice = '<p>ძალადაკარგულია - 01.01.2027, №1</p>' if lost_force else ""
    body = "".join(
        f'<p class="muxlixml"><a class="oldStyleDocumentPart" name="part_{n}">'
        f"მუხლი {n}. სათაური {n}</a></p>"
        f'<p class="abzacixml">1. {text}</p>'
        for n, text in articles.items()
    )
    return (
        "<html><body>"
        '<select id="publication-switcher">'
        f'<option value="{publication}" selected>24/06/2026 - {CONSOLIDATED_LABEL}</option>'
        "</select>"
        f'<div class="document" id="maindoc">{notice}<p class="sataurixml">კანონი</p>{body}</div>'
        "</body></html>"
    )


def _page(doc: str, html: str) -> dr.Page:
    law = LAWS[doc]
    result = ScrapeResult(
        url=law["url"], document_id=doc, content=html.encode("utf-8"),
        content_format=ContentFormat.HTML, encoding="utf-8", scraped_at=EARLIER, content_hash="h",
    )
    return dr.Page(law, result, MatsneScraper.law_metadata(law, result))


def _fetcher(pages: dict[str, str | None]):
    def fetch(laws: list[dict]) -> dict[str, dr.Page]:
        return {
            law["document_id"]: (
                dr.Page(law, error="TimeoutError: no answer")
                if pages[law["document_id"]] is None
                else _page(law["document_id"], pages[law["document_id"]])
            )
            for law in laws
        }
    return fetch


LABOUR = {n: f"შრომის წესი ნომერი {n} მოქმედებს." for n in range(1, 7)}
CONSTITUTION = {n: f"კონსტიტუციის დებულება ნომერი {n}." for n in range(1, 5)}


@pytest.fixture()
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """A served store of two small laws, with the pages and parsed files behind it."""
    monkeypatch.setattr(verify_article_store, "SPOT_CHECKS", [])
    data, work = tmp_path / "data", tmp_path / "work"
    parsed = work / "georgian_laws" / "parsed"
    data.mkdir()
    parsed.mkdir(parents=True)
    pages = {"labour_code": _page_html(LABOUR), "constitution": _page_html(CONSTITUTION)}
    for doc, html in pages.items():
        dr.parse_page(_page(doc, html), parsed / f"{doc}.json")
    dr.build_article_store.build(parsed, data / dr.STORE_FILE)
    return {"data": data, "work": work, "parsed": parsed, "pages": pages}


def _run(site: dict, pages: dict[str, str | None], when: datetime = NOW) -> dict:
    return dr.run(site["data"], site["work"], samples=50, rng=random.Random(1),  # noqa: S311
                  fetch=_fetcher(pages), now=lambda: when)


def _article(site: dict, doc: str, number: str) -> str | None:
    conn = sqlite3.connect(site["data"] / dr.STORE_FILE)
    row = conn.execute(
        "SELECT content_ka FROM articles WHERE document_id = ? AND article_norm = ?", (doc, number)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def test_unchanged_laws_confirm_the_store_and_leave_it_alone(site: dict) -> None:
    store = site["data"] / dr.STORE_FILE
    before = store.stat().st_ino

    status = _run(site, site["pages"])

    assert status["last_run_ok"] is True
    assert status["last_success_at"] == "2026-11-14T03:00:00Z"
    assert status["updated"] == [] and status["problems"] == []
    assert status["drift"] == {"sampled": 10, "mismatches": []}
    assert {c["status"] for c in status["codes"].values()} == {"current"}
    assert store.stat().st_ino == before
    assert json.loads((site["data"] / dr.STATUS_FILE).read_text("utf-8")) == status


def test_new_publication_is_read_verified_and_served(site: dict) -> None:
    amended = {**LABOUR, 3: "შრომის წესი ნომერი 3 შეიცვალა.", 7: "ახალი მუხლი დაემატა."}
    pages = {**site["pages"], "labour_code": _page_html(amended, publication="11")}

    status = _run(site, pages)

    assert status["last_run_ok"] is True
    assert status["updated"] == ["labour_code"]
    assert status["codes"]["labour_code"]["status"] == "changed"
    assert status["codes"]["labour_code"]["matsne_publication"] == "11"
    assert "შეიცვალა" in _article(site, "labour_code", "3")
    assert "დაემატა" in _article(site, "labour_code", "7")
    assert dr.stored_codes(site["data"] / dr.STORE_FILE)["labour_code"]["publication_id"] == "11"
    assert '"publication_id": "11"' in (site["parsed"] / "labour_code.json").read_text("utf-8")
    saved_page = site["work"] / "georgian_laws" / "raw" / "html" / "labour_code.html"
    assert "შეიცვალა" in saved_page.read_text("utf-8")
    assert not (site["data"] / (dr.STORE_FILE + ".candidate")).exists()


def test_text_changed_under_the_same_publication_number_is_caught(site: dict) -> None:
    silently = {**CONSTITUTION, 2: "კონსტიტუციის დებულება ნომერი 2 ჩუმად შეიცვალა."}
    pages = {**site["pages"], "constitution": _page_html(silently)}

    status = _run(site, pages)

    assert status["last_run_ok"] is True
    assert status["codes"]["constitution"]["status"] == "text differs"
    assert status["updated"] == ["constitution"]
    assert "ჩუმად" in _article(site, "constitution", "2")


def test_article_swallowed_by_its_neighbour_is_found_and_restored(site: dict) -> None:
    # The store was built when article 6's heading was read as a line of article 5.
    heading = ('<p class="muxlixml"><a class="oldStyleDocumentPart" name="part_6">'
               "მუხლი 6. სათაური 6</a></p>")
    swallowed = _page_html(LABOUR).replace(heading, '<p class="abzacixml">მუხლი 6 სათაური 6</p>')
    dr.parse_page(_page("labour_code", swallowed), site["parsed"] / "labour_code.json")
    dr.build_article_store.build(site["parsed"], site["data"] / dr.STORE_FILE)
    assert _article(site, "labour_code", "6") is None
    # matsne marks the heading as an article, in a <div> and without the full stop.
    marked = _page_html(LABOUR).replace(
        heading,
        '<div class="muxlixml"><a class="oldStyleDocumentPart" name="part_6">'
        "მუხლი 6 სათაური 6</a></div>")

    status = _run(site, {**site["pages"], "labour_code": marked})

    assert status["last_run_ok"] is True
    assert status["codes"]["labour_code"]["status"] == "text differs"
    assert status["updated"] == ["labour_code"]
    assert _article(site, "labour_code", "6") == "1. შრომის წესი ნომერი 6 მოქმედებს."
    assert "მუხლი 6" not in _article(site, "labour_code", "5")


def test_reread_all_rebuilds_laws_that_look_unchanged(site: dict) -> None:
    store = site["data"] / dr.STORE_FILE
    before = store.stat().st_ino

    status = dr.run(site["data"], site["work"], samples=50, rng=random.Random(1),  # noqa: S311
                    fetch=_fetcher(site["pages"]), now=lambda: NOW, reread_all=True)

    assert status["last_run_ok"] is True
    assert status["updated"] == ["constitution", "labour_code"]
    assert {c["status"] for c in status["codes"].values()} == {"re-read"}
    assert store.stat().st_ino != before
    assert _article(site, "labour_code", "3") == "1. შრომის წესი ნომერი 3 მოქმედებს."


def test_reread_all_leaves_an_unreadable_law_alone(site: dict) -> None:
    status = dr.run(site["data"], site["work"], samples=50, rng=random.Random(1),  # noqa: S311
                    fetch=_fetcher({**site["pages"], "constitution": None}), now=lambda: NOW,
                    reread_all=True)

    assert status["last_run_ok"] is False
    assert status["updated"] == ["labour_code"]
    assert status["codes"]["constitution"]["status"] == "error"
    assert _article(site, "constitution", "2") == "1. კონსტიტუციის დებულება ნომერი 2."


CONSUMER = {n: f"მომხმარებლის უფლება ნომერი {n}." for n in range(1, 4)}


def test_added_law_is_read_verified_and_served(site: dict) -> None:
    pages = {**site["pages"], "consumer_rights_law": _page_html(CONSUMER, publication="7")}

    status = dr.run(site["data"], site["work"], samples=50, rng=random.Random(1),  # noqa: S311
                    fetch=_fetcher(pages), now=lambda: NOW, add_laws=["consumer_rights_law"])

    assert status["last_run_ok"] is True
    assert status["updated"] == ["consumer_rights_law"]
    assert status["codes"]["consumer_rights_law"]["status"] == "added"
    assert status["laws_total"] == 3 and status["laws_checked"] == 3
    assert _article(site, "consumer_rights_law", "2") == "1. მომხმარებლის უფლება ნომერი 2."
    assert _article(site, "labour_code", "3") == "1. შრომის წესი ნომერი 3 მოქმედებს."
    assert (site["parsed"] / "consumer_rights_law.json").exists()
    # The next ordinary run checks the added law like any stored one.
    again = _run(site, pages)
    assert again["codes"]["consumer_rights_law"]["status"] == "current"


def test_added_law_that_cannot_be_read_leaves_the_store_alone(site: dict) -> None:
    store = site["data"] / dr.STORE_FILE
    before = store.stat().st_ino

    status = dr.run(site["data"], site["work"], samples=50, rng=random.Random(1),  # noqa: S311
                    fetch=_fetcher({**site["pages"], "consumer_rights_law": None}),
                    now=lambda: NOW, add_laws=["consumer_rights_law", "no_such_law"])

    assert status["last_run_ok"] is False
    assert status["updated"] == []
    assert status["codes"]["consumer_rights_law"]["status"] == "error"
    assert any("no_such_law: cannot be added" in p for p in status["problems"])
    assert store.stat().st_ino == before
    assert "consumer_rights_law" not in dr.stored_codes(store)


def test_added_law_with_no_readable_article_is_rejected(site: dict) -> None:
    pages = {**site["pages"], "consumer_rights_law": _page_html({}, publication="7")}

    status = dr.run(site["data"], site["work"], samples=50, rng=random.Random(1),  # noqa: S311
                    fetch=_fetcher(pages), now=lambda: NOW, add_laws=["consumer_rights_law"])

    assert status["last_run_ok"] is False
    assert any("no article could be read" in p for p in status["problems"])
    assert "consumer_rights_law" not in dr.stored_codes(site["data"] / dr.STORE_FILE)


def test_unreadable_law_fails_the_run_and_keeps_the_last_success(site: dict) -> None:
    _run(site, site["pages"], when=EARLIER)

    status = _run(site, {**site["pages"], "labour_code": None})

    assert status["last_run_ok"] is False
    assert status["last_success_at"] == "2026-11-01T03:00:00Z"
    assert status["laws_checked"] == 1 and status["laws_total"] == 2
    assert status["codes"]["labour_code"]["status"] == "error"
    assert any("labour_code: could not be read" in p for p in status["problems"])


def test_other_laws_still_update_when_one_cannot_be_read(site: dict) -> None:
    amended = {**CONSTITUTION, 1: "კონსტიტუციის დებულება ნომერი 1 შეიცვალა."}
    pages = {"labour_code": None, "constitution": _page_html(amended, publication="11")}

    status = _run(site, pages)

    assert status["last_run_ok"] is False
    assert status["updated"] == ["constitution"]
    assert "შეიცვალა" in _article(site, "constitution", "1")


def test_page_that_lost_most_articles_is_rejected_and_the_store_kept(site: dict) -> None:
    store = site["data"] / dr.STORE_FILE
    before = store.read_bytes()
    truncated = {1: LABOUR[1], 2: LABOUR[2]}
    pages = {**site["pages"], "labour_code": _page_html(truncated, publication="11")}

    status = _run(site, pages)

    assert status["last_run_ok"] is False and status["updated"] == []
    assert any("rebuilt store rejected" in p and "2 articles" in p for p in status["problems"])
    assert store.read_bytes() == before
    assert '"publication_id": "10"' in (site["parsed"] / "labour_code.json").read_text("utf-8")
    assert not (site["data"] / (dr.STORE_FILE + ".candidate")).exists()


def test_law_marked_as_no_longer_in_force_is_reported(site: dict) -> None:
    pages = {**site["pages"], "labour_code": _page_html(LABOUR, lost_force=True)}

    status = _run(site, pages)

    assert status["last_run_ok"] is False
    assert status["codes"]["labour_code"]["status"] == "lost force"
    assert any("no longer in force" in p for p in status["problems"])


def test_second_run_at_the_same_time_is_refused(site: dict) -> None:
    def fetch_while_running(laws: list[dict]) -> dict[str, dr.Page]:
        with pytest.raises(dr.AlreadyRunningError):
            _run(site, site["pages"])
        return _fetcher(site["pages"])(laws)

    status = dr.run(site["data"], site["work"], fetch=fetch_while_running, now=lambda: NOW)

    assert status["last_run_ok"] is True
