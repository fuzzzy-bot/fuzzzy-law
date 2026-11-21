"""
HTML parser for Georgian legal documents from matsne.gov.ge.

Converts raw HTML into structured ``LegalDocument`` objects with
articles, paragraphs, and metadata properly extracted.

matsne serves three page layouts; all are read from ``#maindoc``:
  1. Class-styled paragraphs: muxlixml (article), tavixml/tavisataurixml
     (chapter), karixml (part), cignixml (book), abzacixml (body).
     Body text also sits in MsoNormal, parlamdrst or unclassed ``<p>``.
     After an amendment matsne sometimes writes one of these as a ``<div>``
     instead of a ``<p>``; such a ``<div>`` is read the same way. A table
     inside an article is read cell by cell, one line per cell, whether the
     cell's text stands in a ``<p>``, a ``<div>`` or the cell itself.
  2. Old style: unclassed ``<p>`` with ``oldStyleDocumentPart`` anchors.
  3. Table layout: ``<table id="DOCUMENT:1;CHAPTER:1;ARTICLE:1;_Title">``
     headers followed by ``…_Content`` tables.

Amendment citations ("საქართველოს 2019 წლის … კანონი №4955 – ვებგვერდი …")
are skipped. Superscript numbers (``<sup>1</sup>``) keep their official
form in text ("259¹"); article ids and anchors use "259-1".
Bracketed headings ("[მუხლი 44². … (ამოქმედდეს 2027 წლის …)]") are
future wordings and are stored as not yet in force.

matsne's own slips in a heading are read as it meant them: an invisible
character inside a superscript ("306<sup>\u200b3</sup>") and a heading
marked as an article that lacks the full stop after its number
("მუხლი 21¹³⁷ მოსამართლის ბრძანება …").
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterator

from bs4 import BeautifulSoup, Tag

from pipeline.models.document_metadata import DocumentMetadata
from pipeline.models.legal_article import ArticleParagraph, LegalArticle
from pipeline.models.legal_document import LegalDocument
from pipeline.models.scrape_result import ContentFormat, ScrapeResult
from pipeline.parser.base_parser import BaseParser
from pipeline.parser.metadata_extractor import MetadataExtractor
from pipeline.utils.georgian_text import (
    normalise_georgian,
    normalise_superscripts,
    remove_whitespace,
    to_superscript,
)
from pipeline.utils.legal_reference_parser import parse_references
from pipeline.utils.logger import get_logger

logger = get_logger(__name__)

_SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹"

# Article heading: "მუხლი 369. სათაური", "[მუხლი 44². …", typo "მუხლის 218⁹."
ARTICLE_RE = re.compile(
    r"^\[?\s*მ\s*უხლის?\s*(\d+[" + _SUP + r"]*)\s*(?:[.\-–—]|(?=\s*\())\s*(.*)",
    re.UNICODE,
)

# A heading matsne marks as an article but writes without the full stop:
# "მუხლი 441", "მუხლი 21¹³⁷ მოსამართლის ბრძანება …".
UNPUNCTUATED_ARTICLE_RE = re.compile(
    r"^(\[?)\s*მ\s*უხლის?\s*(\d+[" + _SUP + r"]*)(?:\s+(.*))?$",
    re.UNICODE,
)

# Structural numbers: roman/arabic ("XLV", "VII¹") or ordinal words ("პირველი", "მეორე").
_LEVEL_NUMBER = r"([IVXLCDM\d]+[" + _SUP + r"]*|პირველი|მე[ა-ჰ]+)\b"

CHAPTER_RE = re.compile(
    r"^\[?\s*თავი\s+" + _LEVEL_NUMBER + r"\s*[.\-–—]?\s*(.*)",
    re.UNICODE,
)

BOOK_RE = re.compile(
    r"^\[?\s*წიგნი\s+" + _LEVEL_NUMBER + r"\s*[.\-–—]?\s*(.*)",
    re.UNICODE,
)

PART_RE = re.compile(
    r"^\[?\s*კარი\s+" + _LEVEL_NUMBER + r"\s*[.\-–—]?\s*(.*)",
    re.UNICODE,
)

# "(ამოქმედდეს 2027 წლის 1 იანვრიდან)" — matsne's note on a future wording.
PENDING_NOTE_RE = re.compile(r"\(ამოქმედდეს[^)]*\)")

# An amendment citation line placed under an article.
AMENDMENT_NOTE_RE = re.compile(
    r"^\(?\s*საქართველოს\s.{0,160}?№.{0,120}?(ვებგვერდი|სსმ|უწყებანი|მაცნე)",
    re.UNICODE,
)

_BOOK_CLASSES = {"cignixml", "wignixml"}
_PART_CLASSES = {"karixml", "nawilixml"}
_CHAPTER_CLASSES = {"tavixml", "taviixml"}
_TITLE_CLASSES = {
    "cignisataurixml": "book", "karisataurixml": "part", "tavisataurixml": "chapter",
}
# Headings and signatures that are neither structure we track nor body text.
_SKIP_CLASSES = {
    "sataurixml", "mimgebixml", "khelmoceraxml", "zogadinacilixml",
    "gansakutrebulinacilixml",
}
_NOTE_CLASSES = {"mypetit"}
# Table-layout pages: the content tables that stand outside every article.
_OUTSIDE_ARTICLES_RE = re.compile(r";(?:HEADER|FOOTER):\d+;_Content$")
# Classes that mark a <div> as law text when matsne writes it in place of a <p>.
_DIV_TEXT_CLASSES = (
    {"muxlixml", "abzacixml"} | _BOOK_CLASSES | _PART_CLASSES | _CHAPTER_CLASSES
    | set(_TITLE_CLASSES)
)


@dataclass
class _Block:
    """One piece of the document in reading order."""
    kind: str            # "book" | "part" | "chapter" | "title" | "article" | "body"
    text: str
    anchor: str | None = None
    title_of: str | None = None   # for kind == "title": which level it names


def element_text(el: Tag) -> str:
    """Visible text of *el* with ``<sup>`` digits kept as superscripts.

    Inline markup is joined as written (matsne splits words across spans);
    block elements and line breaks become spaces. matsne's editorial
    annotation links (a "#" pointing to case law or guides) are dropped.
    """
    for note in el.find_all("a", class_="urlWithAnnotation"):
        note.decompose()
    for sup in el.find_all("sup"):
        # matsne sometimes leaves a zero-width character beside the digits.
        digits = remove_whitespace(sup.get_text())
        if digits.isdigit():
            sup.replace_with(to_superscript(digits))
    for br in el.find_all("br"):
        br.replace_with(" ")
    for block in el.find_all(["div", "p", "td", "li"]):
        block.insert_after(" ")
    return normalise_georgian(el.get_text(), keep_superscripts=True)


def article_norm(number: str) -> str:
    """Official article number → lookup form: ``"259¹"`` → ``"259-1"``."""
    return normalise_superscripts(number)


class HtmlLegalParser(BaseParser):
    """Parse HTML legal documents from matsne.gov.ge."""

    def __init__(self) -> None:
        self._metadata_extractor = MetadataExtractor()

    def can_parse(self, result: ScrapeResult) -> bool:
        return result.content_format == ContentFormat.HTML

    def parse(
        self,
        result: ScrapeResult,
        seed_meta: dict | None = None,
    ) -> LegalDocument:
        """Parse a scraped matsne page into a LegalDocument."""
        html_text = result.content.decode(result.encoding, errors="replace")
        soup = BeautifulSoup(html_text, "lxml")

        metadata = self._metadata_extractor.extract(
            html_text, result.document_id, seed_meta,
        )
        articles = self._extract_articles(soup, result.document_id, metadata)

        logger.info(
            "Parsed %s: %d articles extracted",
            result.document_id, len(articles),
        )

        return LegalDocument(
            metadata=metadata,
            articles=articles,
            raw_html=html_text,
        )

    # ── Reading order ────────────────────────────────────────

    def _blocks(self, soup: BeautifulSoup) -> Iterator[_Block]:
        root = soup.find(id="maindoc") or soup
        if root.find("table", id=re.compile(r"ARTICLE:[^;]+;_Title$")):
            yield from self._table_blocks(root)
        else:
            yield from self._paragraph_blocks(root)

    def _paragraph_blocks(self, root: Tag) -> Iterator[_Block]:
        for p in root.find_all(["p", "div", "td"]):
            classes = {c.lower() for c in (p.get("class") or [])}
            anchor_el = p.find("a", class_="oldStyleDocumentPart")
            anchor = anchor_el.get("name") if anchor_el else None
            if p.name != "p" and not self._stands_for_paragraph(p, classes, anchor):
                continue
            text = element_text(p)
            if not text or classes & _SKIP_CLASSES:
                continue
            if classes & _NOTE_CLASSES or self._is_amendment_note(text):
                continue
            marked_article = "muxlixml" in classes or bool(anchor)
            heading = self._article_heading(text, marked_article)
            if classes & _BOOK_CLASSES or (anchor and BOOK_RE.match(text)):
                yield _Block("book", text, anchor)
            elif classes & _PART_CLASSES or (anchor and PART_RE.match(text)):
                yield _Block("part", text, anchor)
            elif (classes & _CHAPTER_CLASSES and not heading) or (anchor and CHAPTER_RE.match(text)):
                yield _Block("chapter", text, anchor)
            elif classes & set(_TITLE_CLASSES):
                level = _TITLE_CLASSES[next(iter(classes & set(_TITLE_CLASSES)))]
                yield _Block("title", text, anchor, title_of=level)
            elif heading and (marked_article or len(text) < 300):
                yield _Block("article", heading, anchor)
            else:
                yield _Block("body", text)

    @staticmethod
    def _article_heading(text: str, marked: bool) -> str | None:
        """*text* as an article heading ``ARTICLE_RE`` reads, or ``None``.

        A heading matsne itself marks as an article (``muxlixml`` class or a
        document-part anchor) is also accepted without the full stop after
        its number, and is given one.
        """
        if ARTICLE_RE.match(text):
            return text
        loose = UNPUNCTUATED_ARTICLE_RE.match(text) if marked else None
        if loose is None:
            return None
        bracket, number, rest = loose.groups()
        return f"{bracket}მუხლი {number}. {rest or ''}".rstrip()

    @staticmethod
    def _stands_for_paragraph(div: Tag, classes: set[str], anchor: str | None) -> bool:
        """Whether a ``<div>`` or table cell holds law text matsne normally writes as a ``<p>``.

        Only an element with no block nested in it. Inside a table it is a
        cell's text (a rate, a product, a district) and is read like the
        cells matsne writes as ``<p>``. Outside a table, only a ``<div>``
        that carries a law-text class or is an anchored article or structure
        heading; every other one is layout, a label or an amendment note.
        """
        if div.find(["p", "div", "td", "table"]) is not None:
            return False
        if div.find_parent("p") is not None:
            return False
        if div.name == "td" or div.find_parent("td") is not None:
            return True
        if classes & _DIV_TEXT_CLASSES:
            return True
        if not anchor:
            return False
        heading = " ".join(div.get_text().split())
        return len(heading) < 300 and any(
            pattern.match(heading)
            for pattern in (ARTICLE_RE, UNPUNCTUATED_ARTICLE_RE, CHAPTER_RE, PART_RE, BOOK_RE)
        )

    def _table_blocks(self, root: Tag) -> Iterator[_Block]:
        for table in root.find_all("table", id=True):
            table_id = table["id"]
            anchor = table_id.rsplit("_", 1)[0]
            if table_id.endswith("_Title"):
                text = element_text(table)
                if "ARTICLE:" in table_id and ARTICLE_RE.match(text):
                    yield _Block("article", text, anchor)
                elif "CHAPTER:" in table_id and CHAPTER_RE.match(text):
                    yield _Block("chapter", text, anchor)
            elif table_id.endswith("_Content"):
                if _OUTSIDE_ARTICLES_RE.search(table_id):
                    continue  # the law's name above and the signature below it
                for line in self._content_lines(table):
                    text = element_text(line)
                    if text and not self._is_amendment_note(text):
                        yield _Block("body", text)

    @staticmethod
    def _content_lines(table: Tag) -> list[Tag]:
        """The elements of a content table that each hold one line of law text.

        matsne writes a line as a ``<p>``, and often the first line of an
        article as a ``<div>`` beside the ``<p>`` elements, so both are read,
        in the order they stand on the page. Only an element with no block
        nested in it counts; a table with none is read whole.
        """
        lines = [
            el for el in table.find_all(["p", "div", "td"])
            if el.find(["p", "div", "td", "table"]) is None and el.find_parent("p") is None
        ]
        return lines or [table]

    @staticmethod
    def _is_amendment_note(text: str) -> bool:
        """An amendment citation line ("საქართველოს … კანონი №… – ვებგვერდი, …")."""
        return len(text) < 400 and bool(AMENDMENT_NOTE_RE.match(text))

    # ── Article assembly ─────────────────────────────────────

    def _extract_articles(
        self,
        soup: BeautifulSoup,
        document_id: str,
        metadata: DocumentMetadata,
    ) -> list[LegalArticle]:
        articles: list[LegalArticle] = []
        book = part = chapter = None
        header: _Block | None = None
        body: list[str] = []

        def flush() -> None:
            if header is not None:
                articles.append(self._build_article(
                    document_id, metadata, header, body, book, part, chapter,
                ))

        for block in self._blocks(soup):
            if block.kind == "body":
                if header is not None:
                    body.append(block.text)
                continue
            if block.kind == "title":
                if block.title_of == "book" and book:
                    book = f"{book} {block.text}"
                elif block.title_of == "part" and part:
                    part = f"{part} {block.text}"
                elif block.title_of == "chapter" and chapter:
                    chapter = f"{chapter} {block.text}"
                continue
            if block.kind == "article" and self._continues_open_article(block, header, body):
                body.append(block.text)
                continue
            flush()
            header, body = None, []
            if block.kind == "article":
                header = block
            elif block.kind == "book":
                book = self._level_label(BOOK_RE, block.text)
            elif block.kind == "part":
                part = self._level_label(PART_RE, block.text)
            elif block.kind == "chapter":
                chapter = self._level_label(CHAPTER_RE, block.text)
        flush()
        self._disambiguate_ids(articles)
        return articles

    @staticmethod
    def _level_label(pattern: re.Pattern[str], text: str) -> str:
        """"თავი XLV" → "XLV."; "თავი I - სფერო" → "I. სფერო" (title may follow later)."""
        m = pattern.match(text)
        if not m:
            return text
        title = m.group(2).strip()
        return f"{m.group(1)}." + (f" {title}" if title else "")

    @staticmethod
    def _continues_open_article(block: _Block, header: _Block | None, body: list[str]) -> bool:
        """A future wording of the open article's heading only, not a new article.

        matsne prints "[მუხლი 21⁴⁷. new title (ამოქმედდეს …)]" right under the
        current heading (shared body follows), or a closed "[მუხლი 657.
        (ამოღებულია) (ამოქმედდეს …)]" right after the current text.
        """
        if header is None or not block.text.startswith("["):
            return False
        same_number = ARTICLE_RE.match(block.text).group(1) == ARTICLE_RE.match(header.text).group(1)
        return same_number and (not body or block.text.endswith("]"))

    def _build_article(
        self,
        document_id: str,
        metadata: DocumentMetadata,
        header: _Block,
        body: list[str],
        book: str | None,
        part: str | None,
        chapter: str | None,
    ) -> LegalArticle:
        """Build a LegalArticle from its heading and body paragraphs."""
        m = ARTICLE_RE.match(header.text)
        number = m.group(1)
        title = m.group(2).strip()
        in_force = not header.text.startswith("[")
        if not in_force:
            title = title.rstrip("]").strip()
        content_ka = "\n".join(body).strip()
        if not in_force:
            content_ka = content_ka.rstrip("]").strip()

        norm = article_norm(number)
        refs = parse_references(content_ka)
        cross_ref_ids = [f"{document_id}.article_{r.article_number}" for r in refs]

        # Book is left out of the id: ids stay those of earlier corpus builds.
        parts = [document_id]
        if chapter:
            parts.append(f"chapter_{chapter.split('.')[0].strip()}")
        parts.append(f"article_{norm}")

        repealed_marker = (title + " " + content_ka[:40]).lstrip("[ (")
        # matsne cuts the word short on some headings: "მუხლი 95. (ამოღებული"
        cut_short = title.strip("[]() ") == "ამოღებული" and not content_ka
        is_repealed = cut_short or repealed_marker.startswith(("ამოღებულია", "ძალადაკარგულია"))
        return LegalArticle(
            article_id=".".join(parts),
            document_id=document_id,
            code_name=metadata.title_ka,
            book=book,
            part=part,
            chapter=chapter,
            article_number=f"მუხლი {number}",
            article_title=title or None,
            content_ka=content_ka,
            paragraphs=self._parse_paragraphs(content_ka),
            cross_references=cross_ref_ids,
            effective_date=metadata.effective_date,
            is_repealed=is_repealed,
            in_force=in_force,
            matsne_anchor=header.anchor,
        )

    @staticmethod
    def _disambiguate_ids(articles: list[LegalArticle]) -> None:
        """Give repeated ids (future wordings, re-used numbers) a stable suffix."""
        seen: Counter[str] = Counter()
        for art in articles:
            base = art.article_id + ("" if art.in_force else ".pending")
            seen[base] += 1
            art.article_id = base if seen[base] == 1 else f"{base}.{seen[base]}"

    @staticmethod
    def _parse_paragraphs(content: str) -> list[ArticleParagraph]:
        """
        Split article content into numbered paragraphs.

        Looks for patterns like:
          1. text...        → paragraph "1"
          ა) text...        → sub-point of the paragraph above it, or a
                              top-level paragraph when none precedes it
        A paragraph's text includes its sub-points, so a lookup of
        paragraph "1" returns all of it.
        """
        paragraphs: list[ArticleParagraph] = []
        num_pattern = re.compile(r"^\s*(\d+[" + _SUP + r"]*)\s*[.)]\s*(.*)", re.UNICODE)
        letter_pattern = re.compile(r"^\s*([ა-ჰ][" + _SUP + r"]*)\s*\)\s*(.*)", re.UNICODE)

        for line in content.split("\n"):
            stripped = line.strip()
            num_m = num_pattern.match(stripped)
            let_m = None if num_m else letter_pattern.match(stripped)
            current = paragraphs[-1] if paragraphs else None
            parent_is_numbered = current is not None and current.number[0].isdigit()
            if num_m:
                paragraphs.append(ArticleParagraph(number=num_m.group(1), text=num_m.group(2)))
            elif let_m and parent_is_numbered:
                current.sub_points.append(ArticleParagraph(number=let_m.group(1), text=let_m.group(2)))
                current.text = f"{current.text}\n{stripped}"
            elif let_m:
                paragraphs.append(ArticleParagraph(number=let_m.group(1), text=let_m.group(2)))
            elif current is not None:
                if current.sub_points:
                    current.sub_points[-1].text += f"\n{stripped}"
                current.text = f"{current.text}\n{stripped}"

        for para in paragraphs:
            para.text = para.text.strip()
        return paragraphs
