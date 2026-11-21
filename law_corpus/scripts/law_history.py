#!/usr/bin/env python3
"""
Law history: how each article of the stored laws read in earlier consolidated
versions on matsne.gov.ge, so the public connector can answer "what did this
article say on a given date" and "what changed since a date".

matsne numbers the consolidated versions of a law (``?publication=N``) and
dates each one. The history file keeps, per article, one row for every stretch
of versions in which its wording stayed the same:

    versions          one row per stored version of a law (number, date, link)
    article_versions  an article's wording from one version until the version
                      that changed or removed it (``closed_by_publication``)

Two steps, both resumable:

    python scripts/law_history.py fetch --work-dir WORK [--since 2024-01-01]
    python scripts/law_history.py build --work-dir WORK --out DATA/law_history.db

``fetch`` downloads the versions dated on or after ``--since`` plus the one
before it, one request at a time: robots.txt honoured, never under 10 s apart,
one honest user agent, nothing written to matsne. Pages already saved are not
downloaded again. ``build`` reads the saved pages with the same parser the
article store uses. The daily refresh then adds each new version as it appears
(``add_current_version``).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import build_article_store  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

from pipeline.config import settings  # noqa: E402
from pipeline.models.scrape_result import ContentFormat, ScrapeResult  # noqa: E402
from pipeline.parser.html_parser import HtmlLegalParser  # noqa: E402
from pipeline.scraper.matsne_scraper import SEED_LAWS, MatsneScraper  # noqa: E402
from pipeline.scraper.rate_limiter import RateLimiter  # noqa: E402
from pipeline.scraper.session_manager import SessionManager  # noqa: E402
from pipeline.utils.deduplicator import content_hash  # noqa: E402
from pipeline.utils.logger import get_logger, setup_logging  # noqa: E402

logger = get_logger("law_history")

HISTORY_FILE = "law_history.db"
SCHEMA_VERSION = 1
MIN_DELAY_SECONDS = 10.0
DEFAULT_SINCE = "2024-01-01"
REMOVED_MARK = "ამოღებულია"

DDL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE versions (
    document_id    TEXT NOT NULL,
    publication_id INTEGER NOT NULL,       -- matsne's number of the consolidated version
    version_date   TEXT NOT NULL,          -- ISO date matsne gives that version
    version_url    TEXT NOT NULL,          -- official page of exactly that version
    PRIMARY KEY (document_id, publication_id)
);
CREATE TABLE article_versions (
    document_id      TEXT NOT NULL,
    article_norm     TEXT NOT NULL,        -- "48", "166-1"
    from_publication INTEGER NOT NULL,     -- first stored version with this wording
    closed_by_publication INTEGER,         -- version that changed or removed it; NULL = current
    article_number   TEXT NOT NULL,        -- "მუხლი 48"
    article_title    TEXT,
    content_ka       TEXT NOT NULL,
    paragraphs_json  TEXT NOT NULL,
    is_repealed      INTEGER NOT NULL,
    matsne_anchor    TEXT,
    content_sha256   TEXT NOT NULL,
    PRIMARY KEY (document_id, article_norm, from_publication)
);
CREATE INDEX idx_article_versions_closed
    ON article_versions(document_id, closed_by_publication);
"""


@dataclass(frozen=True)
class Publication:
    """One consolidated version as listed in a matsne page's version switcher."""

    publication_id: int
    version_date: str


class OutOfOrderError(ValueError):
    """A version older than the newest stored one cannot be added afterwards."""


# ── Reading matsne pages ─────────────────────────────────────


def list_publications(html_text: str) -> list[Publication]:
    """Every version the page's switcher lists, oldest first."""
    soup = BeautifulSoup(html_text, "lxml")
    found: list[Publication] = []
    for option in soup.select("#publication-switcher option"):
        value = (option.get("value") or "").strip()
        day = option.get_text(strip=True)[:10].split("/")
        if value.isdigit() and len(day) == 3 and all(part.isdigit() for part in day):
            found.append(Publication(int(value), f"{day[2]}-{day[1]}-{day[0]}"))
    return sorted(found, key=lambda p: p.publication_id)


def wanted_publications(publications: list[Publication], since: str) -> list[Publication]:
    """Versions dated on or after ``since`` and the one in force when it began."""
    earlier = [p for p in publications if p.version_date < since]
    start = max((p.publication_id for p in earlier), default=0)
    return [p for p in publications if p.publication_id >= start]


def scrape_result(document_id: str, url: str, content: bytes) -> ScrapeResult:
    """A saved page in the form the parser reads."""
    return ScrapeResult(
        url=url, document_id=document_id, content=content, content_format=ContentFormat.HTML,
        encoding="utf-8", http_status=200, scraped_at=datetime.now(UTC),
        content_hash=content_hash(content.decode("utf-8", errors="replace")), cached=True,
    )


def article_rows(law: dict[str, Any], content: bytes) -> dict[str, dict[str, Any]]:
    """The article of each number as the store would serve it, parsed from a page.

    A number can appear more than once on a page (a removed placeholder, a
    wording not yet in force); the row kept is the one the article store's
    lookup prefers: in force, not a removed placeholder, shortest id.
    """
    result = scrape_result(law["document_id"], law["url"], content)
    document = HtmlLegalParser().parse(result, MatsneScraper.law_metadata(law, result))
    parsed = json.loads(document.model_dump_json(exclude={"raw_html", "raw_text"}))
    best: dict[str, tuple[tuple[int, int, int], dict[str, Any]]] = {}
    for art in parsed.get("articles", []):
        norm = build_article_store._article_norm(
            art.get("article_id", ""), art.get("article_number", ""))
        if not norm:
            continue
        title = art.get("article_title") or ""
        rank = (
            0 if art.get("in_force") is not False else 1,
            1 if REMOVED_MARK in title else 0,
            len(art.get("article_id", "")),
        )
        if norm not in best or rank < best[norm][0]:
            best[norm] = (rank, art)
    return {norm: art for norm, (_, art) in best.items()}


def _sha(art: dict[str, Any]) -> str:
    text = "\n".join([
        art.get("article_number", ""), art.get("article_title") or "",
        art.get("content_ka") or "", "1" if art.get("is_repealed") else "0",
    ])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── The history file ─────────────────────────────────────────


def create(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.executescript(DDL)
    conn.execute("INSERT INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    return conn


def add_version(
    conn: sqlite3.Connection,
    document_id: str,
    publication: Publication,
    source_url: str,
    rows: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Record a law's version; returns how many articles it changed, added and removed.

    Versions are added oldest first. Adding the newest stored version again
    replaces what was recorded for it (matsne corrects a page now and then).
    """
    number = publication.publication_id
    latest = conn.execute(
        "SELECT MAX(publication_id) FROM versions WHERE document_id = ?", (document_id,)
    ).fetchone()[0]
    if latest is not None and number < latest:
        raise OutOfOrderError(
            f"{document_id}: version {number} is older than stored version {latest}")
    if latest == number:
        conn.execute(
            "DELETE FROM article_versions WHERE document_id = ? AND from_publication = ?",
            (document_id, number))
        conn.execute(
            "UPDATE article_versions SET closed_by_publication = NULL "
            "WHERE document_id = ? AND closed_by_publication = ?", (document_id, number))
        conn.execute(
            "DELETE FROM versions WHERE document_id = ? AND publication_id = ?",
            (document_id, number))

    current = {
        row[0]: row[1] for row in conn.execute(
            "SELECT article_norm, content_sha256 FROM article_versions "
            "WHERE document_id = ? AND closed_by_publication IS NULL", (document_id,))
    }
    counts = {"changed": 0, "added": 0, "removed": 0}
    for norm, art in rows.items():
        sha = _sha(art)
        if current.get(norm) == sha:
            continue
        if norm in current:
            counts["changed"] += 1
            conn.execute(
                "UPDATE article_versions SET closed_by_publication = ? WHERE document_id = ? "
                "AND article_norm = ? AND closed_by_publication IS NULL",
                (number, document_id, norm))
        else:
            counts["added"] += 1
        conn.execute(
            "INSERT INTO article_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (document_id, norm, number, None, art.get("article_number", ""),
             art.get("article_title"), art.get("content_ka") or "",
             json.dumps(art.get("paragraphs") or [], ensure_ascii=False),
             1 if art.get("is_repealed") else 0, art.get("matsne_anchor"), sha))
    for norm in set(current) - set(rows):
        counts["removed"] += 1
        conn.execute(
            "UPDATE article_versions SET closed_by_publication = ? WHERE document_id = ? "
            "AND article_norm = ? AND closed_by_publication IS NULL",
            (number, document_id, norm))
    conn.execute(
        "INSERT INTO versions VALUES (?,?,?,?)",
        (document_id, number, publication.version_date, f"{source_url}?publication={number}"))
    return counts


def _finish(conn: sqlite3.Connection, temporary: Path, out: Path) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta VALUES ('built_at', ?)",
        (datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),))
    conn.commit()
    conn.close()
    os.replace(temporary, out)


def add_current_version(
    history: Path, law: dict[str, Any], publication: Publication, content: bytes
) -> dict[str, int]:
    """Add the version a law's page shows today; the served file is swapped in one step."""
    temporary = history.with_suffix(".building")
    shutil.copyfile(history, temporary)
    conn = sqlite3.connect(temporary)
    try:
        counts = add_version(
            conn, law["document_id"], publication, law["url"], article_rows(law, content))
    except Exception:
        conn.close()
        temporary.unlink(missing_ok=True)
        raise
    _finish(conn, temporary, history)
    return counts


# ── Steps ────────────────────────────────────────────────────


def _history_dir(work_dir: Path, document_id: str) -> Path:
    return work_dir / "georgian_laws" / "history" / "html" / document_id


def _current_pages(work_dir: Path) -> dict[str, Path]:
    html_dir = work_dir / "georgian_laws" / "raw" / "html"
    return {path.stem: path for path in sorted(html_dir.glob("*.html"))}


def fetch(work_dir: Path, since: str, only: list[str] | None = None) -> dict[str, int]:
    """Download the wanted earlier versions of every law that has a saved page."""
    seeds = {law["document_id"]: law for law in SEED_LAWS}
    todo: list[tuple[dict[str, Any], Publication, Path]] = []
    for doc, page in _current_pages(work_dir).items():
        if doc not in seeds or (only and doc not in only):
            continue
        publications = list_publications(page.read_text(encoding="utf-8", errors="replace"))
        for publication in wanted_publications(publications, since)[:-1]:  # newest = saved page
            target = _history_dir(work_dir, doc) / f"{publication.publication_id}.html"
            if not target.exists():
                todo.append((seeds[doc], publication, target))
    logger.info("History pages to download: %d", len(todo))

    async def _run() -> dict[str, int]:
        done = {"downloaded": 0, "failed": 0}
        limiter = RateLimiter(min_delay=MIN_DELAY_SECONDS)
        async with SessionManager(limiter, timeout=180.0) as session:
            robots = await MatsneScraper(session)._ensure_robots()
            for law, publication, target in todo:
                url = f"{law['url']}?publication={publication.publication_id}"
                try:
                    if not robots.can_fetch(settings.scrape_user_agent, url):
                        raise PermissionError("robots.txt disallows this page")
                    response = await session.get(url)
                    shown = MatsneScraper.extract_version_info(
                        response.content.decode("utf-8", errors="replace"))["publication_id"]
                    if shown != str(publication.publication_id):
                        raise ValueError(f"the page shows version {shown}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    partial = target.with_suffix(".part")
                    partial.write_bytes(response.content)
                    os.replace(partial, target)
                    done["downloaded"] += 1
                    logger.info("Saved %s version %d (%s)", law["document_id"],
                                publication.publication_id, publication.version_date)
                except Exception as exc:  # one unreadable page must not stop the rest
                    done["failed"] += 1
                    logger.error("Could not save %s version %d: %s", law["document_id"],
                                 publication.publication_id, f"{type(exc).__name__}: {exc}"[:200])
        return done

    return asyncio.run(_run()) if todo else {"downloaded": 0, "failed": 0}


def build(work_dir: Path, out: Path, since: str) -> dict[str, Any]:
    """Build the history file from the saved pages; the old file stays until it is done."""
    seeds = {law["document_id"]: law for law in SEED_LAWS}
    temporary = out.with_suffix(".building")
    conn = create(temporary)
    report: dict[str, Any] = {"laws": {}, "missing_pages": []}
    for doc, current_page in _current_pages(work_dir).items():
        if doc not in seeds:
            continue
        law = seeds[doc]
        publications = list_publications(
            current_page.read_text(encoding="utf-8", errors="replace"))
        wanted = wanted_publications(publications, since)
        stored = 0
        for publication in wanted:
            page = _history_dir(work_dir, doc) / f"{publication.publication_id}.html"
            if publication == wanted[-1]:
                page = current_page
            if not page.exists():
                # A gap only widens the stretch an older wording is shown for,
                # so it is reported, never papered over.
                report["missing_pages"].append(f"{doc}:{publication.publication_id}")
                continue
            add_version(conn, doc, publication, law["url"], article_rows(law, page.read_bytes()))
            stored += 1
        conn.commit()
        report["laws"][doc] = {
            "versions": stored,
            "from": wanted[0].version_date if wanted else None,
            "to": wanted[-1].version_date if wanted else None,
        }
        logger.info("History of %s: %d versions", doc, stored)
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('history_since', ?)", (since,))
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('missing_pages', ?)",
                 (json.dumps(report["missing_pages"]),))
    conn.commit()  # VACUUM cannot run inside a transaction
    conn.execute("VACUUM")
    _finish(conn, temporary, out)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="step", required=True)
    for name in ("fetch", "build"):
        step = sub.add_parser(name)
        step.add_argument("--work-dir", type=Path, required=True)
        step.add_argument("--since", default=DEFAULT_SINCE, help="ISO date, default 2024-01-01")
    sub.choices["fetch"].add_argument("--only", nargs="*", help="law ids to limit the download to")
    sub.choices["build"].add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    setup_logging()
    if args.step == "fetch":
        result = fetch(args.work_dir, args.since, args.only)
        print(json.dumps(result))
        return 1 if result["failed"] else 0
    report = build(args.work_dir, args.out, args.since)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
