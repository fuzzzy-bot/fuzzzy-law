"""Tests for the history of law versions (scripts/law_history.py) and its daily update."""

from __future__ import annotations

import random
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import daily_refresh as dr  # noqa: E402
import law_history as lh  # noqa: E402
import verify_article_store  # noqa: E402

from pipeline.models.scrape_result import ContentFormat, ScrapeResult  # noqa: E402
from pipeline.scraper.matsne_scraper import (  # noqa: E402
    CONSOLIDATED_LABEL,
    SEED_LAWS,
    MatsneScraper,
)

LAWS = {law["document_id"]: law for law in SEED_LAWS}
LABOUR_LAW = LAWS["labour_code"]
NOW = datetime(2026, 11, 14, 3, 0, tzinfo=UTC)

# The versions matsne lists for the test law: number → day/month/year.
VERSIONS = {8: "02/10/2023", 9: "15/03/2024", 10: "24/06/2026", 11: "01/11/2026"}
LABOUR = {n: f"შრომის წესი ნომერი {n} მოქმედებს." for n in range(1, 7)}


def _page_html(articles: dict[int, str], publication: int = 10) -> str:
    """A matsne law page showing ``publication``, with every version in its switcher."""
    options = "".join(
        f'<option value="{number}"{" selected" if number == publication else ""}>'
        f"{day} - {CONSOLIDATED_LABEL}</option>"
        for number, day in VERSIONS.items()
    )
    body = "".join(
        f'<p class="muxlixml"><a class="oldStyleDocumentPart" name="part_{n}">'
        f"მუხლი {n}. სათაური {n}</a></p>"
        f'<p class="abzacixml">1. {text}</p>'
        for n, text in articles.items()
    )
    return (
        "<html><body>"
        f'<select id="publication-switcher">{options}</select>'
        f'<div class="document" id="maindoc"><p class="sataurixml">კანონი</p>{body}</div>'
        "</body></html>"
    )


def _rows(articles: dict[int, str], publication: int = 10) -> dict[str, dict]:
    return lh.article_rows(LABOUR_LAW, _page_html(articles, publication).encode("utf-8"))


def _publication(number: int) -> lh.Publication:
    day, month, year = VERSIONS[number].split("/")
    return lh.Publication(number, f"{year}-{month}-{day}")


def _add(conn: sqlite3.Connection, number: int, articles: dict[int, str]) -> dict[str, int]:
    return lh.add_version(
        conn, "labour_code", _publication(number), LABOUR_LAW["url"], _rows(articles, number))


def _wordings(conn: sqlite3.Connection, article: str) -> list[tuple]:
    return conn.execute(
        "SELECT from_publication, closed_by_publication, content_ka FROM article_versions "
        "WHERE document_id = 'labour_code' AND article_norm = ? ORDER BY from_publication",
        (article,)).fetchall()


@pytest.fixture()
def conn(tmp_path: Path):
    connection = lh.create(tmp_path / lh.HISTORY_FILE)
    yield connection
    connection.close()


# ── Reading the version list ─────────────────────────────────


def test_versions_are_read_from_the_page_oldest_first() -> None:
    found = lh.list_publications(_page_html(LABOUR))

    assert found == [_publication(n) for n in (8, 9, 10, 11)]
    assert found[0].version_date == "2023-10-02"


def test_wanted_versions_start_with_the_one_in_force_on_the_first_day() -> None:
    found = lh.list_publications(_page_html(LABOUR))

    wanted = lh.wanted_publications(found, "2024-01-01")

    # Version 8 is dated before 2024 but was the law on 1 January 2024.
    assert [p.publication_id for p in wanted] == [8, 9, 10, 11]
    assert [p.publication_id for p in lh.wanted_publications(found, "2026-01-01")] == [9, 10, 11]
    assert [p.publication_id for p in lh.wanted_publications(found, "2020-01-01")] == [8, 9, 10, 11]


def test_option_without_a_date_is_not_a_version() -> None:
    html = ('<select id="publication-switcher"><option value="0">აირჩიეთ</option>'
            f'<option value="7">05/05/2022 - {CONSOLIDATED_LABEL}</option></select>')

    assert lh.list_publications(html) == [lh.Publication(7, "2022-05-05")]


# ── Recording versions ───────────────────────────────────────


def test_first_version_stores_every_article_as_current(conn: sqlite3.Connection) -> None:
    counts = _add(conn, 8, LABOUR)

    assert counts == {"changed": 0, "added": 6, "removed": 0}
    assert _wordings(conn, "3") == [(8, None, "1. შრომის წესი ნომერი 3 მოქმედებს.")]
    assert conn.execute("SELECT version_date, version_url FROM versions").fetchall() == [
        ("2023-10-02", f"{LABOUR_LAW['url']}?publication=8")]


def test_amended_article_keeps_its_old_wording_with_the_version_that_ended_it(
    conn: sqlite3.Connection,
) -> None:
    _add(conn, 8, LABOUR)

    counts = _add(conn, 9, {**LABOUR, 3: "შრომის წესი ნომერი 3 შეიცვალა."})

    assert counts == {"changed": 1, "added": 0, "removed": 0}
    assert _wordings(conn, "3") == [
        (8, 9, "1. შრომის წესი ნომერი 3 მოქმედებს."),
        (9, None, "1. შრომის წესი ნომერი 3 შეიცვალა."),
    ]
    assert _wordings(conn, "2") == [(8, None, "1. შრომის წესი ნომერი 2 მოქმედებს.")]


def test_added_and_removed_articles_are_recorded(conn: sqlite3.Connection) -> None:
    _add(conn, 8, LABOUR)
    without_five = {n: text for n, text in LABOUR.items() if n != 5}

    counts = _add(conn, 9, {**without_five, 7: "ახალი მუხლი დაემატა."})

    assert counts == {"changed": 0, "added": 1, "removed": 1}
    assert _wordings(conn, "7") == [(9, None, "1. ახალი მუხლი დაემატა.")]
    assert _wordings(conn, "5") == [(8, 9, "1. შრომის წესი ნომერი 5 მოქმედებს.")]


def test_unchanged_version_adds_no_wordings(conn: sqlite3.Connection) -> None:
    _add(conn, 8, LABOUR)

    counts = _add(conn, 9, LABOUR)

    assert counts == {"changed": 0, "added": 0, "removed": 0}
    assert conn.execute("SELECT COUNT(*) FROM article_versions").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM versions").fetchone()[0] == 2


def test_adding_the_newest_version_again_replaces_what_it_recorded(
    conn: sqlite3.Connection,
) -> None:
    _add(conn, 8, LABOUR)
    _add(conn, 9, {**LABOUR, 3: "პირველი წაკითხვა."})

    counts = _add(conn, 9, {**LABOUR, 3: "შესწორებული წაკითხვა."})

    assert counts == {"changed": 1, "added": 0, "removed": 0}
    assert _wordings(conn, "3") == [
        (8, 9, "1. შრომის წესი ნომერი 3 მოქმედებს."),
        (9, None, "1. შესწორებული წაკითხვა."),
    ]
    assert conn.execute("SELECT COUNT(*) FROM versions").fetchone()[0] == 2


def test_older_version_cannot_be_added_after_a_newer_one(conn: sqlite3.Connection) -> None:
    _add(conn, 9, LABOUR)

    with pytest.raises(lh.OutOfOrderError):
        _add(conn, 8, LABOUR)

    assert conn.execute("SELECT publication_id FROM versions").fetchall() == [(9,)]


def test_laws_keep_separate_histories(conn: sqlite3.Connection) -> None:
    _add(conn, 9, LABOUR)
    constitution = LAWS["constitution"]

    lh.add_version(conn, "constitution", _publication(8), constitution["url"],
                   lh.article_rows(constitution, _page_html({1: "დებულება."}, 8).encode("utf-8")))

    assert conn.execute(
        "SELECT COUNT(*) FROM article_versions WHERE document_id = 'constitution'"
    ).fetchone()[0] == 1
    assert _wordings(conn, "1") == [(9, None, "1. შრომის წესი ნომერი 1 მოქმედებს.")]


# ── Building from saved pages ────────────────────────────────


def _saved_pages(work: Path, versions: dict[int, dict[int, str]], current: int) -> None:
    raw = work / "georgian_laws" / "raw" / "html"
    raw.mkdir(parents=True)
    (raw / "labour_code.html").write_text(_page_html(versions[current], current), "utf-8")
    old = work / "georgian_laws" / "history" / "html" / "labour_code"
    old.mkdir(parents=True)
    for number, articles in versions.items():
        if number != current:
            (old / f"{number}.html").write_text(_page_html(articles, number), "utf-8")


def test_build_reads_saved_pages_in_order(tmp_path: Path) -> None:
    amended = {**LABOUR, 3: "შრომის წესი ნომერი 3 შეიცვალა."}
    _saved_pages(tmp_path, {8: LABOUR, 9: LABOUR, 10: amended, 11: amended}, current=11)
    out = tmp_path / "data" / lh.HISTORY_FILE

    report = lh.build(tmp_path, out, "2024-01-01")

    assert report["missing_pages"] == []
    assert report["laws"]["labour_code"] == {
        "versions": 4, "from": "2023-10-02", "to": "2026-11-01"}
    conn = sqlite3.connect(out)
    assert _wordings(conn, "3") == [
        (8, 10, "1. შრომის წესი ნომერი 3 მოქმედებს."),
        (10, None, "1. შრომის წესი ნომერი 3 შეიცვალა."),
    ]
    assert dict(conn.execute("SELECT key, value FROM meta"))["history_since"] == "2024-01-01"
    conn.close()
    assert not out.with_suffix(".building").exists()


def test_build_reports_a_version_whose_page_was_not_saved(tmp_path: Path) -> None:
    _saved_pages(tmp_path, {8: LABOUR, 10: LABOUR, 11: LABOUR}, current=11)

    report = lh.build(tmp_path, tmp_path / lh.HISTORY_FILE, "2024-01-01")

    assert report["missing_pages"] == ["labour_code:9"]
    assert report["laws"]["labour_code"]["versions"] == 3


# ── Today's version ──────────────────────────────────────────


def test_todays_version_is_added_to_the_served_file(tmp_path: Path) -> None:
    history = tmp_path / lh.HISTORY_FILE
    conn = lh.create(history)
    _add(conn, 10, LABOUR)
    conn.commit()
    conn.close()
    page = _page_html({**LABOUR, 3: "შრომის წესი ნომერი 3 შეიცვალა."}, 11).encode("utf-8")

    counts = lh.add_current_version(history, LABOUR_LAW, _publication(11), page)

    assert counts == {"changed": 1, "added": 0, "removed": 0}
    conn = sqlite3.connect(history)
    assert [row[:2] for row in _wordings(conn, "3")] == [(10, 11), (11, None)]
    conn.close()
    assert not history.with_suffix(".building").exists()


def test_failed_addition_leaves_the_served_file_as_it_was(tmp_path: Path) -> None:
    history = tmp_path / lh.HISTORY_FILE
    conn = lh.create(history)
    _add(conn, 10, LABOUR)
    conn.commit()
    conn.close()
    before = history.read_bytes()

    with pytest.raises(lh.OutOfOrderError):
        lh.add_current_version(
            history, LABOUR_LAW, _publication(9), _page_html(LABOUR, 9).encode("utf-8"))

    assert history.read_bytes() == before
    assert not history.with_suffix(".building").exists()


# ── The daily refresh keeps the history current ──────────────


def _page(html: str) -> dr.Page:
    result = ScrapeResult(
        url=LABOUR_LAW["url"], document_id="labour_code", content=html.encode("utf-8"),
        content_format=ContentFormat.HTML, encoding="utf-8",
        scraped_at=datetime(2026, 11, 1, 3, 0, tzinfo=UTC), content_hash="h",
    )
    return dr.Page(LABOUR_LAW, result, MatsneScraper.law_metadata(LABOUR_LAW, result))


@pytest.fixture()
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """A served store of one small law at version 10, with its history file."""
    monkeypatch.setattr(verify_article_store, "SPOT_CHECKS", [])
    data, work = tmp_path / "data", tmp_path / "work"
    parsed = work / "georgian_laws" / "parsed"
    data.mkdir()
    parsed.mkdir(parents=True)
    dr.parse_page(_page(_page_html(LABOUR, 10)), parsed / "labour_code.json")
    dr.build_article_store.build(parsed, data / dr.STORE_FILE)
    conn = lh.create(data / lh.HISTORY_FILE)
    _add(conn, 10, LABOUR)
    conn.commit()
    conn.close()
    return {"data": data, "work": work}


def _refresh(site: dict, html: str) -> dict:
    return dr.run(site["data"], site["work"], samples=50, rng=random.Random(1),  # noqa: S311
                  fetch=lambda laws: {"labour_code": _page(html)}, now=lambda: NOW)


def test_refresh_adds_a_new_version_to_the_history(site: dict) -> None:
    amended = {**LABOUR, 3: "შრომის წესი ნომერი 3 შეიცვალა.", 7: "ახალი მუხლი დაემატა."}

    status = _refresh(site, _page_html(amended, 11))

    assert status["last_run_ok"] is True
    assert status["updated"] == ["labour_code"]
    assert status["history_updated"] == ["labour_code"]
    conn = sqlite3.connect(site["data"] / lh.HISTORY_FILE)
    assert [row[:2] for row in _wordings(conn, "3")] == [(10, 11), (11, None)]
    assert [row[:2] for row in _wordings(conn, "7")] == [(11, None)]
    assert conn.execute(
        "SELECT version_date FROM versions WHERE publication_id = 11").fetchone()[0] == "2026-11-01"
    conn.close()


def test_refresh_without_changes_leaves_the_history_alone(site: dict) -> None:
    before = (site["data"] / lh.HISTORY_FILE).read_bytes()

    status = _refresh(site, _page_html(LABOUR, 10))

    assert status["history_updated"] == []
    assert (site["data"] / lh.HISTORY_FILE).read_bytes() == before


def test_refresh_makes_up_a_version_the_history_missed(site: dict) -> None:
    amended = _page_html({**LABOUR, 3: "შრომის წესი ნომერი 3 შეიცვალა."}, 11)
    held_back = site["data"] / "held_back.db"
    (site["data"] / lh.HISTORY_FILE).rename(held_back)
    assert _refresh(site, amended)["history_updated"] == []  # the day the history was away
    held_back.rename(site["data"] / lh.HISTORY_FILE)

    status = _refresh(site, amended)

    assert status["updated"] == []
    assert status["history_updated"] == ["labour_code"]
    conn = sqlite3.connect(site["data"] / lh.HISTORY_FILE)
    assert [row[:2] for row in _wordings(conn, "3")] == [(10, 11), (11, None)]
    conn.close()


def test_refresh_rejecting_a_page_keeps_it_out_of_the_history(site: dict) -> None:
    before = (site["data"] / lh.HISTORY_FILE).read_bytes()

    status = _refresh(site, _page_html({1: LABOUR[1]}, 11))  # the page lost most articles

    assert status["updated"] == [] and status["last_run_ok"] is False
    assert status["history_updated"] == []
    assert (site["data"] / lh.HISTORY_FILE).read_bytes() == before


def test_refresh_without_a_history_file_still_updates_the_store(site: dict) -> None:
    (site["data"] / lh.HISTORY_FILE).unlink()

    status = _refresh(site, _page_html({**LABOUR, 3: "შეიცვალა."}, 11))

    assert status["last_run_ok"] is True
    assert status["updated"] == ["labour_code"]
    assert status["history_updated"] == []
    assert not (site["data"] / lh.HISTORY_FILE).exists()


def test_history_that_cannot_be_updated_is_reported_and_the_store_still_served(
    site: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*args: object) -> dict:
        raise sqlite3.DatabaseError("file is not a database")

    monkeypatch.setattr(lh, "add_current_version", broken)

    status = _refresh(site, _page_html({**LABOUR, 3: "შრომის წესი ნომერი 3 შეიცვალა."}, 11))

    assert status["updated"] == ["labour_code"]
    assert status["history_updated"] == []
    assert any("law history" in problem for problem in status["problems"])
    assert status["last_run_ok"] is False
    store = sqlite3.connect(site["data"] / dr.STORE_FILE)
    assert "შეიცვალა" in store.execute(
        "SELECT content_ka FROM articles WHERE article_norm = '3'").fetchone()[0]
    store.close()
