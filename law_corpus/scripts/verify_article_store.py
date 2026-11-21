#!/usr/bin/env python3
"""
Verify an article store (SQLite + FTS5) against the matsne pages it was built from.

Checks, per code:
  - provenance: version date, publication number, versioned URL, retrieval time
  - counts: articles in the store vs article headings found on the matsne page
    (counted independently of the parser: from the page text, and from the
    blocks matsne itself marks as an article, whatever tag or punctuation
    they are written with)
  - integrity: one row in force per article number, no empty live article,
    superscript numbers kept apart (126¹ ≠ 1261), FTS index complete
  - faithfulness: every stored line appears word for word in the page text
  - completeness: every line of article text on the page is in the store
  - spot checks: the articles the 2026-10-24 compliance run found broken

Exit code 0 when everything passes, 1 otherwise. Writes a JSON report with
``--json``. Needs only the standard library plus beautifulsoup4/lxml (for
``--raw-dir``).

Usage:
    python scripts/verify_article_store.py --store data/georgian_laws/article_store.db \\
        --raw-dir data/georgian_laws/raw/html [--json report.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import NamedTuple

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

_SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹"

# Articles the compliance run found broken, with words matsne prints in them.
SPOT_CHECKS: list[dict[str, str]] = [
    {"code": "civil_procedure_code", "article": "369", "contains": "სააპელაციო საჩივრის შეტანის ვადაა 14 დღე",
     "why": "appeal deadline (part 1) was missing"},
    {"code": "admin_offences_code", "article": "272", "contains": "ზემდგომ ორგანოში (ზემდგომ თანამდებობის პირთან)",
     "why": "was cut short and filed under the wrong chapter"},
    {"code": "criminal_code", "article": "381", "contains": "სისხლის სამართლის საერთაშორისო სასამართლოს",
     "why": "was cut short (note missing)"},
    {"code": "criminal_code", "article": "126-1", "contains": "ოჯახის ერთი წევრის მიერ ოჯახის სხვა წევრის მიმართ ძალადობა",
     "why": "superscript article 126¹ was stored as 1261"},
    {"code": "civil_code", "article": "49-1", "contains": "ერთობლივი საინვესტიციო ფონდის",
     "why": "49¹ was stored as 491 and shadowed the real article 491"},
    {"code": "civil_code", "article": "491", "contains": "მყიდველს შეუძლია ნივთის ნაკლის გამო",
     "why": "real article 491 was hidden behind 49¹"},
    {"code": "labour_code", "article": "48", "contains": "30 კალენდარული დღის",
     "why": "dismissal reasons deadline (regression guard)"},
]

_HEADING_RE = re.compile(r"^(\[?)\s*მ\s*უხლის?\s*(\d+)\s*([" + _SUP + r"]*)\s*(?:[.\-–—]|\()")
# A block matsne marks as an article (``muxlixml`` class or a document-part
# anchor) is a heading even when the full stop after its number is missing.
_MARKED_HEADING_RE = re.compile(
    r"^(\[?)\s*მ\s*უხლის?\s*(\d+)\s*([" + _SUP + r"]*)(?=\s|$|[.\-–—(])")


# Classes matsne gives to lines that are not the text of an article: the
# headings of books, parts and chapters and their names, the law's own
# heading and signature, and amendment notes.
_STRUCTURE_CLASSES = {
    "cignixml", "wignixml", "karixml", "nawilixml", "tavixml", "taviixml",
    "cignisataurixml", "karisataurixml", "tavisataurixml",
}
_NOT_ARTICLE_TEXT_CLASSES = {
    "sataurixml", "mimgebixml", "khelmoceraxml", "zogadinacilixml",
    "gansakutrebulinacilixml", "mypetit",
}
# Table-layout pages: the tables holding the law's name and its signature.
_OUTSIDE_ARTICLES_RE = re.compile(r";(?:HEADER|FOOTER):\d+;_(?:Title|Content)$")
# A sub-heading inside a chapter ("III. …") or the label of an annex, when
# matsne writes it as a bare ``<div>``.
_LABEL_RE = re.compile(r"^(?:[IVXLCDM]+\.\s|დანართი\s*(?:№|N)\s*\d)")
_IGNORED_IN_COMPARISON = re.compile(r"[\s\[\]]+")


class PageLine(NamedTuple):
    """One line of a matsne page, as the parser normalises its text."""

    text: str
    marked: bool                 # matsne marks it as an article heading
    classes: frozenset[str] = frozenset()
    bare_div: bool = False       # a <div> with no class, outside any table
    outside_articles: bool = False   # in the law's header or signature table


def _page_lines(html_path: Path) -> list[PageLine]:
    """Page text in reading order, one entry per line.

    A line is every ``<p>``, ``<div>`` or table cell with no block nested in
    it, so text matsne wrote in a ``<div>`` or a cell is seen here whether or
    not the parser read it.
    """
    from bs4 import BeautifulSoup

    from pipeline.parser.html_parser import element_text

    soup = BeautifulSoup(html_path.read_text("utf-8", errors="replace"), "lxml")
    root = soup.find(id="maindoc") or soup
    blocks = [
        block for block in root.find_all(["p", "div", "td"])
        if block.find(["p", "div", "td", "table"]) is None and block.find_parent("p") is None
    ]
    if not blocks:
        return [PageLine(text, False)] if (text := element_text(root)) else []
    lines: list[PageLine] = []
    for block in blocks:
        classes = frozenset(c.lower() for c in (block.get("class") or []))
        marked = "muxlixml" in classes or block.find("a", class_="oldStyleDocumentPart") is not None
        in_table = block.find_parent("table") is not None
        outside = block.find_parent("table", id=_OUTSIDE_ARTICLES_RE) is not None
        text = element_text(block)
        if text:
            lines.append(PageLine(
                text, marked, classes,
                bare_div=block.name == "div" and not classes and not in_table,
                outside_articles=outside,
            ))
    return lines


def _page_text_lines(html_path: Path) -> list[str]:
    """Page text in reading order, one line per block, as the parser normalises it."""
    return [line.text for line in _page_lines(html_path)]


def _heading_match(line: PageLine) -> re.Match[str] | None:
    """The line read as an article heading, or ``None`` when it is not one."""
    m = (_MARKED_HEADING_RE if line.marked else _HEADING_RE).match(line.text)
    if not m or (len(line.text) > 600 and not line.marked):
        return None
    return m


def _headings_on_page(lines: list[PageLine]) -> tuple[set[str], set[str]]:
    """Article numbers (lookup form) of current and future (bracketed) headings."""
    current: set[str] = set()
    future: set[str] = set()
    sup_digits = str.maketrans(_SUP, "0123456789")
    for line in lines:
        m = _heading_match(line)
        if not m:
            continue
        number = m.group(2) + (f"-{m.group(3).translate(sup_digits)}" if m.group(3) else "")
        (future if m.group(1) else current).add(number)
    return current, future


def _lines_lost(lines: list[PageLine], stored_text: str) -> list[str]:
    """Lines of article text on the page that are nowhere in the stored law.

    Article text is what stands under an article heading, up to the next
    heading of an article, chapter, part or book. Left out of the comparison:
    the headings themselves, amendment notes, the law's name and signature,
    and a short bare ``<div>`` that is a sub-heading, an annex label or a
    part of the document matsne anchors. Spacing and the square brackets of
    a future wording are ignored.
    """
    from pipeline.parser.html_parser import AMENDMENT_NOTE_RE, BOOK_RE, CHAPTER_RE, PART_RE

    stored = _IGNORED_IN_COMPARISON.sub("", stored_text)
    lost: list[str] = []
    in_article = False
    for line in lines:
        text = line.text
        if _heading_match(line):
            in_article = True
            continue
        structure = bool(line.classes & _STRUCTURE_CLASSES) or (
            len(text) < 300 and any(p.match(text) for p in (CHAPTER_RE, PART_RE, BOOK_RE)))
        if structure:
            in_article = False
            continue
        if not in_article or line.outside_articles or line.classes & _NOT_ARTICLE_TEXT_CLASSES:
            continue
        if len(text) < 400 and AMENDMENT_NOTE_RE.match(text):
            continue
        if line.bare_div and len(text) < 200 and (line.marked or _LABEL_RE.match(text)):
            continue
        if _IGNORED_IN_COMPARISON.sub("", text) not in stored:
            lost.append(text)
    return lost


def verify(store: Path, raw_dir: Path | None) -> dict:
    conn = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    failures: list[str] = []
    report: dict = {"store": str(store), "codes": {}, "spot_checks": [], "failures": failures}

    report["schema_version"] = conn.execute("PRAGMA user_version").fetchone()[0]
    columns = {r[1] for r in conn.execute("PRAGMA table_info(articles)")}
    for col in ("official_url", "version_date", "in_force", "matsne_anchor"):
        if col not in columns:
            failures.append(f"articles table lacks column {col}")

    fts = conn.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    report["articles_total"] = total
    if fts != total:
        failures.append(f"FTS index has {fts} rows for {total} articles")

    for code in conn.execute("SELECT * FROM codes ORDER BY document_id"):
        doc = code["document_id"]
        rows = conn.execute("SELECT * FROM articles WHERE document_id = ?", (doc,)).fetchall()
        live = [r for r in rows if r["in_force"]]
        info = {
            "code_name": code["code_name"],
            "source_url": code["source_url"],
            "version_date": code["version_date"],
            "publication_id": code["publication_id"],
            "version_url": code["version_url"],
            "retrieved_at": code["retrieved_at"],
            "articles": len(rows),
            "in_force_rows": len(live),
            "future_wordings": len(rows) - len(live),
            "repealed_placeholders": sum(1 for r in rows if r["is_repealed"]),
        }
        for field in ("version_date", "publication_id", "version_url", "retrieved_at"):
            if not code[field]:
                failures.append(f"{doc}: no {field}")

        norms = [r["article_norm"] for r in live]
        duplicates = sorted({n for n in norms if norms.count(n) > 1})
        empty = [r["article_number"] for r in live if not r["content_ka"].strip() and not r["is_repealed"]]
        flattened = [r["article_number"] for r in rows
                     if any(c in r["article_number"] for c in _SUP) and "-" not in r["article_norm"]]
        no_link = [r["article_number"] for r in rows if not r["official_url"]]
        info.update({"duplicate_numbers": duplicates, "empty_articles": empty,
                     "flattened_superscripts": flattened, "without_official_link": len(no_link)})
        for label, bad in (("duplicate article numbers in force", duplicates),
                           ("empty articles", empty), ("flattened superscript numbers", flattened)):
            if bad:
                failures.append(f"{doc}: {label}: {bad[:10]}")

        html = raw_dir / f"{doc}.html" if raw_dir else None
        if html and html.exists():
            lines = _page_lines(html)
            page_text = "\n".join(line.text for line in lines)
            current, future = _headings_on_page(lines)
            stored_current = {r["article_norm"] for r in live}
            stored_future = {r["article_norm"] for r in rows if not r["in_force"]}
            info["headings_on_matsne"] = len(current)
            info["future_headings_on_matsne"] = len(future)
            info["missing_from_store"] = sorted(current - stored_current)
            info["not_on_matsne"] = sorted(stored_current - current)
            info["future_missing_from_store"] = sorted(future - stored_future - stored_current)
            if info["missing_from_store"]:
                failures.append(f"{doc}: {len(info['missing_from_store'])} matsne articles missing: "
                                f"{info['missing_from_store'][:10]}")
            if info["not_on_matsne"]:
                failures.append(f"{doc}: stored articles with no matsne heading: {info['not_on_matsne'][:10]}")
            unmatched = [(r["article_number"], line[:80]) for r in rows
                         for line in r["content_ka"].split("\n") if line and line not in page_text]
            info["lines_not_word_for_word"] = len(unmatched)
            info["lines_not_word_for_word_examples"] = unmatched[:5]
            if unmatched:
                failures.append(f"{doc}: {len(unmatched)} stored lines differ from the matsne text")
            lost = _lines_lost(lines, "\n".join(r["content_ka"] for r in rows))
            info["matsne_lines_not_in_store"] = len(lost)
            info["matsne_lines_not_in_store_examples"] = [line[:80] for line in lost[:5]]
            if lost:
                failures.append(
                    f"{doc}: {len(lost)} lines of the matsne text are not in the store: "
                    f"{[line[:60] for line in lost[:3]]}")
        report["codes"][doc] = info

    for check in SPOT_CHECKS:
        row = conn.execute(
            "SELECT * FROM articles WHERE document_id = ? AND article_norm = ? "
            "ORDER BY in_force DESC LIMIT 1",
            (check["code"], check["article"]),
        ).fetchone()
        ok = row is not None and check["contains"] in row["content_ka"]
        report["spot_checks"].append({
            **check,
            "ok": ok,
            "article_number": row["article_number"] if row else None,
            "official_url": row["official_url"] if row else None,
            "version_date": row["version_date"] if row else None,
            "text": row["content_ka"] if row else None,
        })
        if not ok:
            failures.append(f"spot check {check['code']} {check['article']}: {check['why']}")

    conn.close()
    report["passed"] = not failures
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--raw-dir", type=Path, help="matsne HTML pages the store was built from")
    ap.add_argument("--json", type=Path, help="write the full report here")
    args = ap.parse_args()

    report = verify(args.store, args.raw_dir)
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Store {args.store} (schema version {report['schema_version']}), {report['articles_total']} articles")
    for doc, info in report["codes"].items():
        on_page = info.get("headings_on_matsne", "?")
        print(f"  {doc:26} {info['in_force_rows']:5} in force (matsne headings: {on_page}), "
              f"{info['future_wordings']} future, version {info['version_date']}")
    for check in report["spot_checks"]:
        print(f"  {'OK  ' if check['ok'] else 'FAIL'} {check['code']} {check['article']}: {check['why']}")
    if report["failures"]:
        print(f"FAILED ({len(report['failures'])}):")
        for failure in report["failures"]:
            print(f"  - {failure}")
        sys.exit(1)
    print("PASSED")


if __name__ == "__main__":
    main()
