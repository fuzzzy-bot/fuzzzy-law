#!/usr/bin/env python3
"""
Download the Supreme Court of Georgia's published decision collections.

The court publishes its decisions as monthly collections (PDF), one listing page per
chamber, with the parties shown as initials. These pages and files are open to robots;
the court's case search (``/ka/getCases``) is not, and this script never touches it or
any other address robots.txt disallows.

    python scripts/fetch_supreme_court_collections.py --work-dir WORK [--chambers civil ...]

Writes ``WORK/supreme_collections/<chamber>/<file>.pdf`` and ``manifest.json`` (one entry
per listed file: address, chamber, label, status, size, sha256). One request at a time,
never under 10 s apart, one honest user agent, GET only. A file already saved is not
downloaded again, so a stopped run resumes where it left off. Five failures in a row stop
the run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
from urllib.robotparser import RobotFileParser

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

import httpx  # noqa: E402

from pipeline.config import settings  # noqa: E402

BASE_URL = "https://www.supremecourt.ge"
# Listing pages: one per chamber. Disciplinary and qualification chamber pages are left
# out: they concern judges, not the questions people bring.
LISTINGS = {
    "civil": "/decisions/samoqalaqo-samartlis-saqmeebze",
    "criminal": "/decisions/siskhlis-samartlis-saqmeebze",
    "administrative": "/decisions/administratsiuli-samartlis-saqmeebze",
    "grand_chamber_civil": "/decisions-grand-chamber/samoqalaqo-samartlis-saqmeebze-didi-palata",
    "grand_chamber_criminal": "/decisions-grand-chamber/siskhlis-samartlis-saqmeebze-didi-palata",
    "grand_chamber_administrative": (
        "/decisions-grand-chamber/administratsiul-da-skhva-kategoriis-saqmeebze-didi-palata"),
}
MIN_DELAY_SECONDS = 10.0
FAILURES_IN_A_ROW_THAT_STOP_THE_RUN = 5
TIMEOUT_SECONDS = 120.0

_PDF_LINK = re.compile(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


@dataclass
class Listed:
    chamber: str
    url: str
    label: str
    file: str
    status: str = "pending"      # pending | saved | missing | failed | disallowed
    bytes: int = 0
    sha256: str | None = None
    http_status: int | None = None


def pdf_links(html_text: str, page_url: str) -> list[tuple[str, str]]:
    """(absolute address, link text) of every PDF a listing page links, in page order."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href, text in _PDF_LINK.findall(html_text):
        url = urljoin(page_url, unescape(href).strip())
        if url not in seen:
            seen.add(url)
            found.append((url, _SPACE.sub(" ", _TAGS.sub(" ", unescape(text))).strip()))
    return found


def local_name(url: str) -> str:
    """A safe file name from the address's last part."""
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    return re.sub(r"[^\w.\-]+", "_", name)


class PoliteClient:
    """GET only, robots.txt per host, at least MIN_DELAY_SECONDS between any two requests."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": settings.scrape_user_agent}, timeout=TIMEOUT_SECONDS,
            follow_redirects=True)
        self._robots: dict[str, RobotFileParser] = {}
        self._last = 0.0

    def _wait(self) -> None:
        pause = self._last + MIN_DELAY_SECONDS - time.monotonic()
        if pause > 0:
            time.sleep(pause)
        self._last = time.monotonic()

    def allowed(self, url: str) -> bool:
        host = urlparse(url)
        key = f"{host.scheme}://{host.netloc}"
        if key not in self._robots:
            parser = RobotFileParser()
            self._wait()
            response = self._client.get(key + "/robots.txt")
            # No robots.txt (404) allows everything; any other failure allows nothing.
            if response.status_code == 404:
                parser.parse([])
            elif response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                parser.parse(["User-agent: *", "Disallow: /"])
            self._robots[key] = parser
        return self._robots[key].can_fetch(settings.scrape_user_agent, url)

    def get(self, url: str) -> httpx.Response:
        self._wait()
        return self._client.get(url)


def run(work_dir: Path, chambers: list[str]) -> dict[str, int]:
    out = work_dir / "supreme_collections"
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    known = {e["url"]: Listed(**e) for e in json.loads(manifest_path.read_text("utf-8"))} \
        if manifest_path.exists() else {}
    client = PoliteClient()

    def save() -> None:
        manifest_path.write_text(json.dumps(
            [asdict(e) for e in known.values()], ensure_ascii=False, indent=1), "utf-8")

    for chamber in chambers:
        page = BASE_URL + LISTINGS[chamber]
        if not client.allowed(page):
            print(f"robots.txt disallows {page}; skipped", flush=True)
            continue
        response = client.get(page)
        response.raise_for_status()
        links = pdf_links(response.text, page)
        print(f"{chamber}: {len(links)} files listed", flush=True)
        for url, label in links:
            if url not in known:
                known[url] = Listed(chamber, url, label, f"{chamber}/{local_name(url)}")
        save()

    failures = 0
    todo = [e for e in known.values()
            if e.chamber in chambers and e.status in ("pending", "failed")]
    for done, entry in enumerate(todo, 1):
        target = out / entry.file
        if target.exists() and target.stat().st_size:
            entry.status, entry.bytes = "saved", target.stat().st_size
            continue
        if not client.allowed(entry.url):
            entry.status = "disallowed"
            save()
            continue
        try:
            response = client.get(entry.url)
        except httpx.HTTPError as error:
            entry.status, failures = "failed", failures + 1
            print(f"failed {entry.url}: {type(error).__name__}", flush=True)
        else:
            entry.http_status = response.status_code
            body = response.content
            if response.status_code == 200 and body[:5] == b"%PDF-":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                entry.status, entry.bytes = "saved", len(body)
                entry.sha256 = hashlib.sha256(body).hexdigest()
                failures = 0
            elif response.status_code == 404 or (response.status_code == 200
                                                 and body[:5] != b"%PDF-"):
                entry.status, failures = "missing", 0
            else:
                entry.status, failures = "failed", failures + 1
        save()
        print(f"[{done}/{len(todo)}] {entry.status} {entry.file} ({entry.bytes} bytes)", flush=True)
        if failures >= FAILURES_IN_A_ROW_THAT_STOP_THE_RUN:
            print("Five failures in a row; stopping. Run again later to resume.", flush=True)
            break

    counts: dict[str, int] = {}
    for entry in known.values():
        counts[entry.status] = counts.get(entry.status, 0) + 1
    print(json.dumps(counts), flush=True)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--chambers", nargs="*", default=list(LISTINGS), choices=list(LISTINGS))
    args = parser.parse_args()
    run(args.work_dir, args.chambers)


if __name__ == "__main__":
    main()
