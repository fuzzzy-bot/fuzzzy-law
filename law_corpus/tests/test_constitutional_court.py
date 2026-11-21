"""Tests for the Constitutional Court downloader (scripts/fetch_constitutional_court.py)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_constitutional_court as fcc  # noqa: E402

from pipeline.config import settings  # noqa: E402
from pipeline.scraper.rate_limiter import RateLimiter  # noqa: E402

FIXTURES_DIR = Path(__file__).parent / "fixtures"
LISTING_HTML = (FIXTURES_DIR / "constcourt_listing.html").read_text("utf-8")
DECISION_HTML = (FIXTURES_DIR / "constcourt_decision.html").read_text("utf-8")
LISTED_IDS = [20023, 19616, 19611, 19492, 19473]
ONE_PAGE_LISTING = LISTING_HTML.split('<ul class="pagination">')[0]
ROBOTS_OPEN = "User-agent: *\nDisallow:\n"
JUDGMENTS_LIST = fcc.LISTING_URL.format(type_id=278, page=1)


def _decision_url(legal_id: int) -> str:
    return fcc.DECISION_URL.format(legal_id=legal_id)


class Site:
    """Stands in for constcourt.ge: serves the saved pages and records every request."""

    def __init__(self, robots: str = ROBOTS_OPEN, broken: tuple[int, ...] = ()) -> None:
        self.pages = {fcc.ROBOTS_URL: robots, JUDGMENTS_LIST: ONE_PAGE_LISTING}
        self.pages.update({_decision_url(legal_id): DECISION_HTML for legal_id in LISTED_IDS})
        self.broken = {_decision_url(legal_id) for legal_id in broken}
        self.requested: list[str] = []

    async def get(self, url: str, **_: object) -> httpx.Response:
        self.requested.append(url)
        request = httpx.Request("GET", url)
        if url in self.broken or url not in self.pages:
            response = httpx.Response(503, request=request, text="<html>secret body</html>")
            raise httpx.HTTPStatusError("503 for this page", request=request, response=response)
        return httpx.Response(200, request=request, text=self.pages[url])

    @property
    def decisions_requested(self) -> list[str]:
        return [url for url in self.requested if "legal=" in url]


@pytest.fixture()
def site(monkeypatch: pytest.MonkeyPatch) -> Site:
    fake = Site()
    monkeypatch.setattr(fcc.OneAttemptSession, "get", lambda self, url, **kw: fake.get(url, **kw))
    return fake


# ── Reading the court's pages ────────────────────────────────


def test_listing_gives_the_acts_in_page_order_and_the_last_page() -> None:
    listing = fcc.parse_listing(LISTING_HTML)
    assert listing.legal_ids == LISTED_IDS
    assert listing.last_page == 4


def test_listing_without_page_links_is_a_single_page() -> None:
    one_act = (
        '<div class="legal-act"><h5 class="legal-act-title"><a href="?legal=7">x</a></h5></div>'
    )
    assert fcc.parse_listing(one_act) == fcc.ListingPage(legal_ids=[7], last_page=1)


def test_decision_page_gives_the_heading_as_printed() -> None:
    decision = fcc.parse_decision_page(DECISION_HTML)
    assert decision.case_number == "N1/2/882"
    assert decision.decision_type == "გადაწყვეტილება"
    assert decision.date_as_printed == "24 ივნისი 2026"
    assert decision.decision_date == "2026-06-24"
    assert decision.case_title == "ნიკო სანიმუშოშვილი საქართველოს პარლამენტის წინააღმდეგ"


def test_decision_text_keeps_the_printed_lines() -> None:
    lines = fcc.parse_decision_page(DECISION_HTML).text.splitlines()
    assert lines[:3] == [
        "ნიკო სანიმუშოშვილი საქართველოს პარლამენტის წინააღმდეგ",
        "დოკუმენტის ტიპი გადაწყვეტილება",
        "ნომერი N1/2/882",
    ]
    assert "ვასილ როინიშვილი – სხდომის თავმჯდომარე;" in lines
    # A line break inside a heading is a new line, not a lost space.
    assert lines[lines.index("I") + 1] == "აღწერილობითი ნაწილი"
    assert "5. გადაწყვეტილება საბოლოოა და გასაჩივრებას ან გადასინჯვას არ ექვემდებარება." in lines
    assert lines[-1] == "გიორგი კვერენჩხილაძე"
    assert all(line == " ".join(line.split()) for line in lines)


def test_raised_numbers_stay_raised() -> None:
    text = fcc.parse_decision_page(DECISION_HTML).text
    assert "მე-3 მუხლის ჰ¹³ ქვეპუნქტის" in text
    assert "ჰ13" not in text


def test_text_is_only_what_the_page_shows() -> None:
    html_text = (
        '<div id="printablePageContent"><h1>სათაური</h1>'
        '<table class="legal-inner-table"><tr><td>ნომერი</td><td>№2/1/7</td></tr></table>'
        '<span class="legalactshowparagraph"><p>პირველი\n   სტრიქონი<br>მეორე</p>'
        "<!-- note --><script>var hidden = 1;</script>"
        "<table><tr><td>ა</td><td>ბ</td></tr></table></span></div>"
    )
    decision = fcc.parse_decision_page(html_text)
    assert decision.text == "სათაური\nნომერი №2/1/7\nპირველი სტრიქონი\nმეორე\nა ბ\n"
    assert decision.case_number == "№2/1/7"
    assert decision.decision_date is None


@pytest.mark.parametrize(
    ("html_text", "reason"),
    [
        ("<html><body>შესვლა</body></html>", "no act"),
        ('<div id="printablePageContent"><h1>x</h1><span class="legalactshowparagraph">'
         "<p>ტექსტი</p></span></div>", "no case number"),
        ('<div id="printablePageContent"><table class="legal-inner-table"><tr><td>ნომერი</td>'
         "<td>N1/1/1</td></tr></table></div>", "no text"),
    ],
)
def test_page_without_a_number_or_text_is_refused(html_text: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        fcc.parse_decision_page(html_text)


# ── The download ─────────────────────────────────────────────


def test_acts_are_saved_with_their_details(site: Site, tmp_path: Path) -> None:
    result = fcc.fetch(tmp_path, ["judgment"])
    assert result == {"downloaded": 5, "already_saved": 0, "failed": 0}
    assert site.requested[:2] == [fcc.ROBOTS_URL, JUDGMENTS_LIST]
    assert site.decisions_requested == [_decision_url(legal_id) for legal_id in LISTED_IDS]

    folder = tmp_path / "judgment"
    assert sorted(path.name for path in folder.iterdir()) == sorted(
        f"{legal_id}{suffix}" for legal_id in LISTED_IDS for suffix in (".txt", ".json"))
    text = (folder / "20023.txt").read_text("utf-8")
    assert text == fcc.parse_decision_page(DECISION_HTML).text
    details = json.loads((folder / "20023.json").read_text("utf-8"))
    fetched_at = details.pop("fetched_at")
    assert fetched_at.endswith("Z")
    assert details == {
        "case_number": "N1/2/882",
        "decision_date": "2026-06-24",
        "decision_date_as_printed": "24 ივნისი 2026",
        "decision_type": "გადაწყვეტილება",
        "case_title": "ნიკო სანიმუშოშვილი საქართველოს პარლამენტის წინააღმდეგ",
        "source_url": "https://www.constcourt.ge/ka/judicial-acts?legal=20023",
    }


def test_saved_acts_are_not_downloaded_again(site: Site, tmp_path: Path) -> None:
    fcc.fetch(tmp_path, ["judgment"], limit=2)
    assert len(site.decisions_requested) == 2
    site.requested.clear()

    result = fcc.fetch(tmp_path, ["judgment"])
    assert result == {"downloaded": 3, "already_saved": 2, "failed": 0}
    assert site.decisions_requested == [_decision_url(legal_id) for legal_id in LISTED_IDS[2:]]
    site.requested.clear()

    assert fcc.fetch(tmp_path, ["judgment"]) == {"downloaded": 0, "already_saved": 5, "failed": 0}
    assert site.requested == [fcc.ROBOTS_URL, JUDGMENTS_LIST]


def test_text_without_its_details_is_downloaded_again(site: Site, tmp_path: Path) -> None:
    fcc.fetch(tmp_path, ["judgment"], limit=1)
    (tmp_path / "judgment" / "20023.json").unlink()
    site.requested.clear()
    assert fcc.fetch(tmp_path, ["judgment"], limit=1)["downloaded"] == 1
    assert site.decisions_requested == [_decision_url(20023)]


def test_one_failed_page_does_not_stop_the_rest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    fake = Site(broken=(19616,))
    monkeypatch.setattr(fcc.OneAttemptSession, "get", lambda self, url, **kw: fake.get(url, **kw))
    result = fcc.fetch(tmp_path, ["judgment"])
    assert result == {"downloaded": 4, "already_saved": 0, "failed": 1}
    saved = {path.name for path in (tmp_path / "judgment").iterdir()}
    assert "19616.txt" not in saved and "19473.json" in saved
    assert not any(name.endswith(".part") for name in saved)
    assert "judgment 19616" in caplog.text
    assert "secret body" not in caplog.text


def test_a_site_that_keeps_failing_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    fake = Site(broken=tuple(LISTED_IDS))
    monkeypatch.setattr(fcc.OneAttemptSession, "get", lambda self, url, **kw: fake.get(url, **kw))
    monkeypatch.setattr(fcc, "FAILURES_IN_A_ROW_THAT_STOP_THE_RUN", 3)
    result = fcc.fetch(tmp_path, ["judgment", "ruling"])
    assert result == {"downloaded": 0, "already_saved": 0, "failed": 3}
    assert len(fake.decisions_requested) == 3
    assert fcc.LISTING_URL.format(type_id=279, page=1) not in fake.requested


def test_page_that_robots_disallows_is_never_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    fake = Site(robots="User-agent: *\nDisallow: /ka/judicial-acts\n")
    monkeypatch.setattr(fcc.OneAttemptSession, "get", lambda self, url, **kw: fake.get(url, **kw))
    result = fcc.fetch(tmp_path, ["judgment"])
    assert result == {"downloaded": 0, "already_saved": 0, "failed": 1}
    assert fake.requested == [fcc.ROBOTS_URL]
    assert not (tmp_path / "judgment").exists()


def test_kinds_are_taken_judgments_first_and_lists_page_by_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    fake = Site()
    rulings = [fcc.LISTING_URL.format(type_id=279, page=page) for page in (1, 2, 3)]
    fake.pages[rulings[0]] = LISTING_HTML.replace("legal=20023", "legal=20028")  # says 4 pages
    fake.pages[rulings[1]] = ONE_PAGE_LISTING.replace("legal=20023", "legal=20111")
    fake.pages[_decision_url(20028)] = fake.pages[_decision_url(20111)] = DECISION_HTML
    monkeypatch.setattr(fcc.OneAttemptSession, "get", lambda self, url, **kw: fake.get(url, **kw))

    result = fcc.fetch(tmp_path, ["ruling", "judgment"], limit=11)
    assert result == {"downloaded": 11, "already_saved": 0, "failed": 0}
    assert fake.requested.index(JUDGMENTS_LIST) < fake.requested.index(rulings[0])
    assert (tmp_path / "ruling" / "20028.txt").exists()
    assert (tmp_path / "ruling" / "20111.txt").exists()
    # The limit was reached on the second page, so the third is never asked for.
    assert rulings[1] in fake.requested and rulings[2] not in fake.requested


def test_pace_follows_robots_when_it_asks_for_more() -> None:
    class Session:
        rate_limiter = RateLimiter(min_delay=fcc.MIN_DELAY_SECONDS)

        async def get(self, url: str) -> httpx.Response:
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 30\nDisallow: /admin\n")

    session = Session()
    robots = asyncio.run(fcc.load_robots(session))
    assert session.rate_limiter.min_delay == 30.0
    assert not robots.can_fetch(settings.scrape_user_agent, f"{fcc.BASE_URL}/admin/x")
    assert robots.can_fetch(settings.scrape_user_agent, _decision_url(20023))


def test_pace_is_never_under_ten_seconds() -> None:
    assert fcc.MIN_DELAY_SECONDS >= 10.0
    limiter = RateLimiter(min_delay=fcc.MIN_DELAY_SECONDS)
    limiter.honour_crawl_delay(fcc.HOST, 2.0)
    assert limiter.min_delay == fcc.MIN_DELAY_SECONDS
