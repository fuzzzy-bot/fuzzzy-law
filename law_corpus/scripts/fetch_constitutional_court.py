#!/usr/bin/env python3
"""
Download the acts the Constitutional Court of Georgia publishes on
constcourt.ge, each exactly as its page shows it, for the court decision store
(``build_court_store.py --constitutional-court-dir``).

    python scripts/fetch_constitutional_court.py --out-dir WORK/constitutional_court \
        [--kinds judgment ruling] [--limit 30]

The court lists its acts by kind, newest first; the page of one act carries its
whole text. Kinds are downloaded in the order judgments on the merits, rulings,
recording notices, conclusions (then separate opinions when asked for), each
newest first. For every act two files are written under ``<out-dir>/<kind>/``:

    <id>.txt   the title, the heading table and the text, one printed line or
               paragraph per line; nothing is added, removed or reworded
    <id>.json  the case number, date, kind, title and official link, each as
               the page prints it (the date also as an ISO date)

One request at a time: robots.txt honoured, never under 10 s apart (slower when
robots.txt asks for it), one honest user agent, GET only. An act already saved
is not downloaded again, so an interrupted run is simply started again. A page
that cannot be read is logged and the run goes on; after several failures in a
row the run stops instead of pressing a site that keeps refusing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.robotparser import RobotFileParser

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import build_court_store  # noqa: E402
import httpx  # noqa: E402
from bs4 import BeautifulSoup, Comment, NavigableString, Tag  # noqa: E402

from pipeline.config import settings  # noqa: E402
from pipeline.scraper.rate_limiter import RateLimiter  # noqa: E402
from pipeline.scraper.session_manager import SessionManager  # noqa: E402
from pipeline.utils.georgian_text import to_superscript  # noqa: E402
from pipeline.utils.logger import get_logger, setup_logging  # noqa: E402

logger = get_logger("fetch_constitutional_court")

HOST = "www.constcourt.ge"
BASE_URL = f"https://{HOST}"
ROBOTS_URL = f"{BASE_URL}/robots.txt"
LISTING_URL = (
    BASE_URL + "/ka/judicial-acts?quantity=100&sort=desc&type%5B%5D={type_id}&page={page}"
)
DECISION_URL = BASE_URL + "/ka/judicial-acts?legal={legal_id}"
MIN_DELAY_SECONDS = 10.0
FAILURES_IN_A_ROW_THAT_STOP_THE_RUN = 5

KIND_LABEL = "დოკუმენტის ტიპი"
NUMBER_LABEL = "ნომერი"
DATE_LABEL = "თარიღი"


@dataclass(frozen=True)
class Kind:
    """A kind of act: the court's name for it, its number in the list filter, our folder."""

    name: str
    type_id: int
    folder: str


KINDS = (
    Kind("გადაწყვეტილება", 278, "judgment"),
    Kind("განჩინება", 279, "ruling"),
    Kind("საოქმო ჩანაწერი", 281, "recording_notice"),
    Kind("დასკვნა", 280, "conclusion"),
    Kind("განსხვავებული აზრი", 284, "dissenting_opinion"),
    Kind("თანმხვედრი აზრი", 1828, "concurring_opinion"),
)
DEFAULT_KINDS = ["judgment", "ruling", "recording_notice", "conclusion"]

_LEGAL_ID = re.compile(r"[?&]legal=(\d+)")
_WHITESPACE = re.compile(r"\s+")
_LINE_TAGS = frozenset({
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "table", "tr",
    "blockquote", "pre", "hr",
})
_CELL_TAGS = frozenset({"td", "th"})
_UNSEEN_TAGS = frozenset({"script", "style"})


@dataclass(frozen=True)
class ListingPage:
    """One page of the court's list of acts."""

    legal_ids: list[int]
    last_page: int


@dataclass(frozen=True)
class DecisionPage:
    """One act as its page prints it."""

    case_number: str
    decision_type: str
    date_as_printed: str
    case_title: str
    text: str

    @property
    def decision_date(self) -> str | None:
        """The printed date as an ISO date, or None when it is not a readable date."""
        return build_court_store.read_date([self.date_as_printed])


class OneAttemptSession(SessionManager):
    """The pipeline's polite session without its retries.

    A page that fails is downloaded by the next run instead, so a site that is
    struggling gets one request per page and no more.
    """

    async def _get_with_retry(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        assert self._client is not None
        await self.rate_limiter.acquire(self._host(url))
        response = await self._client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response


# ── Reading the court's pages ────────────────────────────────


def parse_listing(html_text: str) -> ListingPage:
    """The acts a list page shows, in its order, and the number of its last page."""
    soup = BeautifulSoup(html_text, "lxml")
    legal_ids: list[int] = []
    for link in soup.select("div.legal-act .legal-act-title a[href]"):
        match = _LEGAL_ID.search(link["href"])
        if match and int(match.group(1)) not in legal_ids:
            legal_ids.append(int(match.group(1)))
    page_numbers = [
        int(text) for text in (item.get_text(strip=True) for item in soup.select(".pagination li"))
        if text.isdigit()
    ]
    return ListingPage(legal_ids=legal_ids, last_page=max(page_numbers, default=1))


def _one_line(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _collect_text(node: Tag, pieces: list[str]) -> None:
    for child in node.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            pieces.append(_WHITESPACE.sub(" ", str(child)))
        elif child.name == "br":
            pieces.append("\n")
        elif child.name == "sup":
            pieces.append(to_superscript(child.get_text()))
        elif child.name not in _UNSEEN_TAGS:
            edge = "\n" if child.name in _LINE_TAGS else " " if child.name in _CELL_TAGS else ""
            pieces.append(edge)
            _collect_text(child, pieces)
            pieces.append(edge)


def published_lines(node: Tag) -> list[str]:
    """The text a reader sees in ``node``, one printed line or paragraph per line.

    Raised numbers (``174<sup>1</sup>``) stay raised (``174¹``), as in the law
    texts of this corpus, so they are not read as part of the number before.
    """
    pieces: list[str] = []
    _collect_text(node, pieces)
    lines = (_one_line(line) for line in "".join(pieces).split("\n"))
    return [line for line in lines if line]


def parse_decision_page(html_text: str) -> DecisionPage:
    """The act a page shows; ValueError when the page prints no number or no text."""
    soup = BeautifulSoup(html_text, "lxml")
    content = soup.find(id="printablePageContent")
    if content is None:
        raise ValueError("the page shows no act")
    printed: dict[str, str] = {}
    for row in content.select("table.legal-inner-table tr"):
        cells = [_one_line(cell.get_text()) for cell in row.find_all("td")]
        if len(cells) == 2:
            printed[cells[0]] = cells[1]
    if not printed.get(NUMBER_LABEL):
        raise ValueError("the page prints no case number")
    body = content.select_one(".legalactshowparagraph")
    if body is None or not body.get_text(strip=True):
        raise ValueError("the page shows no text of the act")
    title = content.find("h1")
    return DecisionPage(
        case_number=printed[NUMBER_LABEL],
        decision_type=printed.get(KIND_LABEL, ""),
        date_as_printed=printed.get(DATE_LABEL, ""),
        case_title=_one_line(title.get_text()) if title else "",
        text="\n".join(published_lines(content)) + "\n",
    )


# ── Saving ───────────────────────────────────────────────────


def _write_whole(target: Path, text: str) -> None:
    partial = target.with_name(target.name + ".part")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, target)


def is_saved(text_file: Path) -> bool:
    """Whether an act's text and its details are both on disk."""
    return text_file.exists() and text_file.with_suffix(".json").exists()


def save(text_file: Path, decision: DecisionPage, source_url: str) -> None:
    """Write an act's text, then its details; the details file marks it as saved."""
    text_file.parent.mkdir(parents=True, exist_ok=True)
    details = {
        "case_number": decision.case_number,
        "decision_date": decision.decision_date,
        "decision_date_as_printed": decision.date_as_printed,
        "decision_type": decision.decision_type,
        "case_title": decision.case_title,
        "source_url": source_url,
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _write_whole(text_file, decision.text)
    _write_whole(
        text_file.with_suffix(".json"), json.dumps(details, ensure_ascii=False, indent=2) + "\n")


# ── The download ─────────────────────────────────────────────


async def load_robots(session: SessionManager) -> RobotFileParser:
    """The site's robots.txt; a Crawl-delay longer than our pace becomes the pace."""
    response = await session.get(ROBOTS_URL)
    robots = RobotFileParser()
    robots.parse(response.text.splitlines())
    delay = robots.crawl_delay(settings.scrape_user_agent)
    if delay:
        session.rate_limiter.honour_crawl_delay(HOST, float(delay))
    return robots


class Download:
    """One run: walks the lists kind by kind and saves the acts not yet on disk."""

    def __init__(
        self, session: SessionManager, robots: RobotFileParser, out_dir: Path, limit: int | None,
    ) -> None:
        self.session = session
        self.robots = robots
        self.out_dir = out_dir
        self.limit = limit
        self.done = {"downloaded": 0, "already_saved": 0, "failed": 0}
        self.failures_in_a_row = 0

    @property
    def finished(self) -> bool:
        """True once the limit is reached or the site has failed too often in a row."""
        reached_limit = self.limit is not None and self.done["downloaded"] >= self.limit
        return reached_limit or self.failures_in_a_row >= FAILURES_IN_A_ROW_THAT_STOP_THE_RUN

    async def _page(self, url: str) -> str:
        if not self.robots.can_fetch(settings.scrape_user_agent, url):
            raise PermissionError("robots.txt disallows this page")
        response = await self.session.get(url)
        return response.content.decode("utf-8", errors="replace")

    def _failed(self, what: str, exc: Exception) -> None:
        self.done["failed"] += 1
        self.failures_in_a_row += 1
        logger.error("Could not save %s: %s", what, f"{type(exc).__name__}: {exc}"[:200])
        if self.failures_in_a_row >= FAILURES_IN_A_ROW_THAT_STOP_THE_RUN:
            logger.error("Stopping: %d pages in a row could not be saved",
                         self.failures_in_a_row)

    async def kind(self, kind: Kind) -> None:
        """Download every act of one kind that is not saved yet, newest first."""
        page = last_page = 1
        while page <= last_page and not self.finished:
            try:
                listing = parse_listing(
                    await self._page(LISTING_URL.format(type_id=kind.type_id, page=page)))
            except Exception as exc:  # the rest of this kind waits for the next run
                self._failed(f"the list of {kind.folder} acts, page {page}", exc)
                return
            last_page = listing.last_page
            for legal_id in listing.legal_ids:
                if self.finished:
                    return
                await self.act(kind, legal_id)
            page += 1

    async def act(self, kind: Kind, legal_id: int) -> None:
        """Download one act unless it is already saved."""
        text_file = self.out_dir / kind.folder / f"{legal_id}.txt"
        if is_saved(text_file):
            self.done["already_saved"] += 1
            return
        url = DECISION_URL.format(legal_id=legal_id)
        try:
            decision = parse_decision_page(await self._page(url))
            save(text_file, decision, url)
        except Exception as exc:  # one unreadable page must not stop the rest
            self._failed(f"{kind.folder} {legal_id}", exc)
            return
        self.failures_in_a_row = 0
        self.done["downloaded"] += 1
        logger.info("Saved %s %s of %s (%s)", kind.folder, decision.case_number,
                    decision.decision_date or decision.date_as_printed, url)


def fetch(out_dir: Path, kinds: list[str], limit: int | None = None) -> dict[str, int]:
    """Download the acts of the given kinds that are not saved yet; returns the counts."""

    async def _run() -> dict[str, int]:
        limiter = RateLimiter(min_delay=MIN_DELAY_SECONDS)
        async with OneAttemptSession(limiter, timeout=120.0) as session:
            download = Download(session, await load_robots(session), out_dir, limit)
            for kind in KINDS:
                if kind.folder in kinds:
                    await download.kind(kind)
            return download.done

    return asyncio.run(_run())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--kinds", nargs="+", choices=[kind.folder for kind in KINDS],
                        default=DEFAULT_KINDS, help="kinds of act, default: all but opinions")
    parser.add_argument("--limit", type=int, help="download at most this many acts in this run")
    args = parser.parse_args()
    setup_logging()
    result = fetch(args.out_dir, args.kinds, args.limit)
    print(json.dumps(result))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
