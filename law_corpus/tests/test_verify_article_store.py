"""The store check must notice law text that is on the matsne page but not in the store."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import verify_article_store  # noqa: E402

from pipeline.models.scrape_result import ContentFormat, ScrapeResult  # noqa: E402
from pipeline.parser.html_parser import HtmlLegalParser  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _stored_text(fixture: str) -> str:
    """The article text the parser reads from a fixture page."""
    result = ScrapeResult(
        url="https://matsne.gov.ge/ka/document/view/1", document_id="law",
        content=(FIXTURES / fixture).read_bytes(), content_format=ContentFormat.HTML,
        encoding="utf-8", scraped_at=datetime.now(timezone.utc), content_hash="test",
    )
    document = HtmlLegalParser().parse(
        result, {"url": result.url, "title_ka": "x", "document_type": "code"})
    return "\n".join(article.content_ka for article in document.articles)


def test_first_line_written_beside_the_paragraphs_is_missed_when_not_stored() -> None:
    lines = verify_article_store._page_lines(FIXTURES / "matsne_table_layout.html")
    first_line = "1. მონაცემთა დამუშავება დასაშვებია, თუ არსებობს ერთ-ერთი შემდეგი საფუძველი:"
    stored = _stored_text("matsne_table_layout.html")
    assert first_line in stored

    assert verify_article_store._lines_lost(lines, stored.replace(first_line, "")) == [first_line]


def test_table_cell_is_missed_when_not_stored() -> None:
    lines = verify_article_store._page_lines(FIXTURES / "matsne_div_layout.html")
    stored = _stored_text("matsne_div_layout.html")

    assert verify_article_store._lines_lost(lines, stored.replace("ნორმა (%)", "")) == ["ნორმა (%)"]


def test_headings_notes_and_signature_are_not_expected_in_the_store() -> None:
    for fixture in ("matsne_table_layout.html", "matsne_div_layout.html",
                    "matsne_class_layout.html"):
        lines = verify_article_store._page_lines(FIXTURES / fixture)
        assert verify_article_store._lines_lost(lines, _stored_text(fixture)) == [], fixture
