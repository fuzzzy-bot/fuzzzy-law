#!/usr/bin/env python3
"""
Daily refresh of the article store the public law connector serves.

One run, once a day:
  1. downloads the current consolidated page of every stored law from
     matsne.gov.ge (one request per law, robots.txt honoured, never under
     10 s apart, one honest user agent);
  2. finds the laws whose stored text is no longer what matsne shows: a new
     publication number, or any stored line that is not on the page word for
     word;
  3. re-reads those laws, builds a new store beside the served one, verifies
     it against the downloaded pages and only then moves it into place;
  4. takes a random sample of stored articles and confirms each one word for
     word against the downloaded pages;
  5. adds each law's new version to ``law_history.db`` beside the store, when
     that file is there, so earlier wordings stay readable by date;
  6. writes ``status.json`` beside the store. ``last_success_at`` moves only
     when every law was read, the store matches and the sample has no
     mismatch; the connector dates its answers with it.

The served store is never edited in place and is left untouched whenever a
check fails. Exit code 0 on success, 1 when a problem needs a person.

    python scripts/daily_refresh.py --data-dir /srv/connector/data \\
        --work-dir /srv/connector/work [--samples 50] [--reread-all] \\
        [--add-law consumer_rights_law ...]

``--reread-all`` re-reads every law from today's page even when nothing looks
changed. It is for the run after a repair to the page reader, so the served
store takes the repair for every law; the same checks decide whether the
rebuilt store is served.

``--add-law`` takes a law the store does not hold yet, by its name in the
scraper's list of laws: its page is downloaded and read in the same run, and
it joins the store only if the rebuilt store passes the same checks.

``--work-dir`` holds ``georgian_laws/raw/html``, ``raw/metadata`` and
``parsed`` in the pipeline's layout: the pages and parsed laws the served
store was built from.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import random
import shutil
import sqlite3
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import build_article_store  # noqa: E402
import law_history  # noqa: E402
import verify_article_store  # noqa: E402

from pipeline.models.scrape_result import ScrapeResult  # noqa: E402
from pipeline.parser.html_parser import HtmlLegalParser  # noqa: E402
from pipeline.scraper.matsne_scraper import SEED_LAWS, MatsneScraper  # noqa: E402
from pipeline.scraper.rate_limiter import RateLimiter  # noqa: E402
from pipeline.scraper.session_manager import SessionManager  # noqa: E402
from pipeline.utils.logger import get_logger, setup_logging  # noqa: E402

logger = get_logger("daily_refresh")

STORE_FILE = "article_store.db"
STATUS_FILE = "status.json"
MIN_DELAY_SECONDS = 10.0
DEFAULT_SAMPLES = 50
# A refreshed law that lost more than this share of its articles is treated as
# a misread page, not as an amendment.
MIN_ARTICLE_SHARE = 0.8
MAX_PROBLEMS_KEPT = 20


@dataclass
class Page:
    """One law's page as downloaded now, or the reason it could not be."""

    law: dict[str, Any]
    result: ScrapeResult | None = None
    metadata: dict[str, Any] | None = None
    error: str | None = None


Fetcher = Callable[[list[dict[str, Any]]], dict[str, Page]]
Verifier = Callable[[Path, Path | None], dict]


class AlreadyRunningError(RuntimeError):
    """Another refresh holds the lock."""


def fetch_pages(laws: list[dict[str, Any]]) -> dict[str, Page]:
    """Download each law's current consolidated page, politely and in turn."""

    async def _fetch() -> dict[str, Page]:
        pages: dict[str, Page] = {}
        limiter = RateLimiter(min_delay=MIN_DELAY_SECONDS)
        async with SessionManager(limiter, timeout=120.0) as session:
            scraper = MatsneScraper(session)
            for law in laws:
                doc = law["document_id"]
                try:
                    result = await scraper.fetch_document(law["url"], doc)
                    pages[doc] = Page(law, result, MatsneScraper.law_metadata(law, result))
                except Exception as exc:  # one unreadable law must not stop the others
                    pages[doc] = Page(law, error=f"{type(exc).__name__}: {exc}"[:300])
                    logger.error("Could not read %s from matsne: %s", doc, pages[doc].error)
        return pages

    return asyncio.run(_fetch())


def stored_codes(store: Path) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return {r["document_id"]: dict(r) for r in conn.execute(
            "SELECT document_id, publication_id, version_date, article_count FROM codes")}
    finally:
        conn.close()


def codes_differing(report: dict) -> set[str]:
    """Laws whose stored text is not exactly what the downloaded page shows."""
    return {
        doc for doc, info in report["codes"].items()
        if info.get("lines_not_word_for_word") or info.get("missing_from_store")
        or info.get("not_on_matsne")
    }


def drift_sample(store: Path, html_dir: Path, samples: int, rng: random.Random) -> dict:
    """Check random stored articles in force, word for word, against the pages."""
    conn = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT article_id, document_id, article_number, content_ka FROM articles "
            "WHERE is_repealed = 0 AND in_force = 1 AND TRIM(content_ka) != '' ORDER BY article_id"
        ).fetchall()
    finally:
        conn.close()
    rows = [r for r in rows if (html_dir / f"{r['document_id']}.html").exists()]
    sample = rng.sample(rows, min(samples, len(rows)))

    page_text: dict[str, str] = {}
    mismatches: list[dict[str, str]] = []
    for row in sample:
        doc = row["document_id"]
        if doc not in page_text:
            lines = verify_article_store._page_text_lines(html_dir / f"{doc}.html")
            page_text[doc] = "\n".join(lines)
        missing = [line for line in row["content_ka"].split("\n")
                   if line and line not in page_text[doc]]
        if missing:
            mismatches.append({"article_id": row["article_id"], "document_id": doc,
                               "article_number": row["article_number"], "line": missing[0][:120]})
    return {"sampled": len(sample), "mismatches": mismatches}


def parse_page(page: Page, out: Path) -> int:
    """Parse a downloaded page into ``out``; returns the number of articles read."""
    document = HtmlLegalParser().parse(page.result, page.metadata)
    out.write_text(
        document.model_dump_json(indent=2, exclude={"raw_html", "raw_text"}), encoding="utf-8")
    return document.article_count


def write_json(path: Path, payload: dict) -> None:
    """Write beside ``path`` and move into place, so a reader never sees half a file."""
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def read_status(path: Path) -> dict:
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return status if isinstance(status, dict) else {}


def record_history(
    history: Path, pages: dict[str, Page], served: dict[str, dict[str, Any]], updated: list[str]
) -> tuple[list[str], list[str]]:
    """Add to the law history file every served version it does not hold yet.

    A law is recorded when the store now serves the version its page shows and
    either the store was just updated from that page or the history's newest
    version of the law is another one, so a day the history missed is made up
    on the next run. Returns the laws recorded and a problem line for each that
    could not be. The served article store is never touched here.
    """
    recorded: list[str] = []
    problems: list[str] = []
    if not history.exists():
        return recorded, problems
    try:
        conn = sqlite3.connect(f"file:{history}?mode=ro", uri=True)
        try:
            newest = dict(conn.execute(
                "SELECT document_id, MAX(publication_id) FROM versions GROUP BY document_id"))
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return recorded, [f"the law history file could not be read ({type(exc).__name__}: {exc})"]
    for doc in sorted(pages):
        page = pages[doc]
        metadata = page.metadata or {}
        number = str(metadata.get("publication_id") or "")
        if page.result is None or not number.isdigit():
            continue
        if number != str((served.get(doc) or {}).get("publication_id")):
            continue  # the store does not serve this page; the history follows the store
        if doc not in updated and newest.get(doc) == int(number):
            continue
        try:
            day = str(metadata.get("version_date") or "")[:10]
            if len(day) != 10:
                raise ValueError("the page gives no version date")
            law_history.add_current_version(
                history, page.law, law_history.Publication(int(number), day), page.result.content)
            recorded.append(doc)
        except Exception as exc:  # noqa: BLE001 - one law's history must not stop the others
            logger.error("History of %s not updated: %s", doc, type(exc).__name__)
            problems.append(
                f"{doc}: its new version was not added to the law history "
                f"({type(exc).__name__}: {exc})")
    return recorded, problems


def _utc_now() -> datetime:
    return datetime.now(UTC)


def run(
    data_dir: Path,
    work_dir: Path,
    samples: int = DEFAULT_SAMPLES,
    rng: random.Random | None = None,
    fetch: Fetcher = fetch_pages,
    verifier: Verifier | None = None,
    now: Callable[[], datetime] = _utc_now,
    reread_all: bool = False,
    add_laws: Sequence[str] = (),
) -> dict:
    """One refresh run; returns the status it wrote to ``status.json``.

    With ``reread_all`` every law that could be downloaded is re-read from
    its page, not only the laws that look changed. ``add_laws`` names laws the
    store does not hold yet; each is read from its page and joins the store
    when the rebuilt store passes the checks.
    """
    verifier = verifier or verify_article_store.verify
    rng = rng or random.Random()  # noqa: S311 - picks a sample, guards nothing
    store = data_dir / STORE_FILE
    status_path = data_dir / STATUS_FILE
    corpus_dir = work_dir / "georgian_laws"
    parsed_dir = corpus_dir / "parsed"
    incoming_html = work_dir / "incoming" / "html"
    staged_parsed = work_dir / "staging" / "parsed"
    candidate = data_dir / (STORE_FILE + ".candidate")

    work_dir.mkdir(parents=True, exist_ok=True)
    lock = open(work_dir / "refresh.lock", "w")  # noqa: SIM115 - held for the whole run
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        lock.close()
        raise AlreadyRunningError("another refresh is running") from exc

    try:
        started = now()
        previous = read_status(status_path)
        problems: list[str] = []
        codes = stored_codes(store)
        seeds = {law["document_id"]: law for law in SEED_LAWS}
        new_laws = sorted(set(add_laws) - set(codes))
        laws = [seeds[doc] for doc in sorted({*codes, *new_laws}) if doc in seeds]
        for doc in sorted(set(codes) - set(seeds)):
            problems.append(f"{doc}: no matsne address is known for this stored law")
        for doc in sorted(set(new_laws) - set(seeds)):
            problems.append(f"{doc}: cannot be added, no matsne address is known for it")

        # 1. Download today's pages.
        shutil.rmtree(work_dir / "incoming", ignore_errors=True)
        incoming_html.mkdir(parents=True)
        pages = fetch(laws)
        per_code: dict[str, dict[str, Any]] = {}
        refresh: set[str] = set()
        for law in laws:
            doc = law["document_id"]
            page = pages.get(doc) or Page(law, error="not downloaded")
            stored = codes.get(doc)
            entry: dict[str, Any] = {
                "stored_publication": stored["publication_id"] if stored else None,
                "stored_version_date": stored["version_date"] if stored else None,
            }
            per_code[doc] = entry
            if page.error or page.result is None or page.metadata is None:
                entry["status"] = "error"
                problems.append(f"{doc}: could not be read from matsne ({page.error})")
                continue
            entry["matsne_publication"] = page.metadata.get("publication_id")
            entry["matsne_version_date"] = page.metadata.get("version_date")
            if not page.metadata.get("publication_id"):
                entry["status"] = "error"
                problems.append(f"{doc}: the matsne page shows no publication number")
                continue
            (incoming_html / f"{doc}.html").write_bytes(page.result.content)
            if page.metadata.get("lost_force_notice"):
                entry["status"] = "lost force"
                entry["lost_force_notice"] = page.metadata["lost_force_notice"]
                problems.append(f"{doc}: matsne marks this law as no longer in force")
            elif stored is None:
                entry["status"] = "added"
                refresh.add(doc)
            elif page.metadata["publication_id"] != stored["publication_id"]:
                entry["status"] = "changed"
                refresh.add(doc)
            elif reread_all:
                entry["status"] = "re-read"
                refresh.add(doc)
            else:
                entry["status"] = "current"

        # 2. Every stored line of every downloaded law, against its page.
        before = verifier(store, incoming_html)
        for doc in sorted(codes_differing(before)):
            if per_code.get(doc, {}).get("status") == "current":
                per_code[doc]["status"] = "text differs"
                refresh.add(doc)

        # 3. Rebuild with the changed laws re-read, verify, then swap.
        served = store
        updated: list[str] = []
        if refresh:
            rebuild_problems: list[str] = []
            shutil.rmtree(work_dir / "staging", ignore_errors=True)
            shutil.copytree(parsed_dir, staged_parsed)
            for doc in sorted(refresh):
                count = parse_page(pages[doc], staged_parsed / f"{doc}.json")
                per_code[doc]["articles"] = count
                if doc not in codes:
                    if not count:
                        rebuild_problems.append(f"{doc}: no article could be read from its page")
                elif count < MIN_ARTICLE_SHARE * (codes[doc]["article_count"] or 0):
                    rebuild_problems.append(
                        f"{doc}: the new page gave {count} articles, the stored law has "
                        f"{codes[doc]['article_count']}")
            candidate.unlink(missing_ok=True)
            build_article_store.build(staged_parsed, candidate)
            lost = sorted(set(codes) - set(stored_codes(candidate)))
            if lost:
                rebuild_problems.append(f"the rebuilt store lost laws: {lost}")
            rebuild_problems.extend(verifier(candidate, incoming_html)["failures"])
            if rebuild_problems:
                problems.extend(f"rebuilt store rejected: {p}" for p in rebuild_problems)
                candidate.unlink(missing_ok=True)
            else:
                served = candidate

        # 4. Random sample of the store that will be served.
        drift = drift_sample(served, incoming_html, samples, rng)
        for miss in drift["mismatches"]:
            problems.append(f"sampled article {miss['article_id']} differs from matsne")

        if served is candidate and not drift["mismatches"]:
            os.replace(candidate, store)
            for doc in sorted(refresh):
                os.replace(staged_parsed / f"{doc}.json", parsed_dir / f"{doc}.json")
            updated = sorted(refresh)
        candidate.unlink(missing_ok=True)

        # 5. Versions the history does not hold yet join the earlier wordings.
        history_updated, history_problems = record_history(
            data_dir / law_history.HISTORY_FILE, pages, stored_codes(store), updated)
        problems.extend(history_problems)

        # The saved pages follow the served store, law by law.
        if not refresh or updated:
            raw_html = corpus_dir / "raw" / "html"
            raw_meta = corpus_dir / "raw" / "metadata"
            raw_html.mkdir(parents=True, exist_ok=True)
            raw_meta.mkdir(parents=True, exist_ok=True)
            for doc, page in pages.items():
                source = incoming_html / f"{doc}.html"
                if source.exists() and page.metadata is not None:
                    os.replace(source, raw_html / f"{doc}.html")
                    write_json(raw_meta / f"{doc}.json", page.metadata)
        shutil.rmtree(work_dir / "staging", ignore_errors=True)

        finished = now()
        ok = not problems
        status = {
            "last_run_at": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_run_ok": ok,
            "last_success_at": (
                finished.strftime("%Y-%m-%dT%H:%M:%SZ") if ok else previous.get("last_success_at")
            ),
            "duration_seconds": int((finished - started).total_seconds()),
            "laws_checked": sum(1 for e in per_code.values() if e["status"] != "error"),
            "laws_total": len(per_code),
            "updated": updated,
            "history_updated": history_updated,
            "drift": drift,
            "problems": problems[:MAX_PROBLEMS_KEPT],
            "codes": per_code,
        }
        write_json(status_path, status)
        return status
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, required=True,
                    help="holds the served article_store.db")
    ap.add_argument("--work-dir", type=Path, required=True,
                    help="pages and parsed laws behind the store")
    ap.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    ap.add_argument("--reread-all", action="store_true",
                    help="re-read every law from today's page, after a repair to the page reader")
    ap.add_argument("--add-law", nargs="+", default=[], metavar="LAW",
                    help="laws to add to the store, by their name in the scraper's list")
    args = ap.parse_args()

    setup_logging("INFO")
    try:
        status = run(args.data_dir, args.work_dir, samples=args.samples,
                     reread_all=args.reread_all, add_laws=args.add_law)
    except AlreadyRunningError as exc:
        logger.error("%s", exc)
        return 1
    logger.info(
        "Refresh %s: %d of %d laws checked, updated %s, sample %d with %d mismatches",
        "succeeded" if status["last_run_ok"] else "FAILED", status["laws_checked"],
        status["laws_total"], status["updated"] or "none", status["drift"]["sampled"],
        len(status["drift"]["mismatches"]),
    )
    for problem in status["problems"]:
        logger.error("  %s", problem)
    return 0 if status["last_run_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
