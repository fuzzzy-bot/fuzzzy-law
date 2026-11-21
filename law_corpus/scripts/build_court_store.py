#!/usr/bin/env python3
"""
Build the court decision store: a SQLite file with full-text search over
Supreme Court decisions, read by the public law connector.

Input is the extracted decision texts (one .txt per decision, as published by
the court with the parties already reduced to initials). A decision is stored
only when its own heading states a case number; a file whose number cannot be
read is skipped and named in the report, because the connector must never
show a case number the court did not print.

Constitutional Court decisions (``fetch_constitutional_court.py``) enter as a
third collection. Their text is stored as the court's page shows it, and their
case number, date, kind and official link are taken from the details file
saved beside each text, never read out of the text.

    python scripts/build_court_store.py \
        --court-practice-dir data/court_practice/extracted \
        --grand-chamber-dir data/grand_chamber/extracted \
        --constitutional-court-dir data/constitutional_court \
        --out data/connector/court_store.db --report court_store_report.json

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 1
PASSAGE_CHARS = 1200
HEADING_LINES = 8
CONSTITUTIONAL_COLLECTION = "constitutional_court"
CONSTITUTIONAL_CATEGORY = "constitutional"

DDL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE decisions (
    decision_id   TEXT PRIMARY KEY,        -- case:<collection>:<case number>
    collection    TEXT NOT NULL,           -- court_practice | grand_chamber | constitutional_court
    case_number   TEXT NOT NULL,           -- as printed in the decision heading
    category      TEXT,                    -- civil | criminal | administrative | constitutional
    decision_type TEXT,                    -- განჩინება | განაჩენი | გადაწყვეტილება ...
    decision_date TEXT,                    -- ISO date from the heading, if printed
    year          TEXT,
    source_url    TEXT,
    source_file   TEXT NOT NULL,
    passage_count INTEGER NOT NULL,
    char_count    INTEGER NOT NULL
);
CREATE TABLE passages (
    passage_id  INTEGER PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES decisions(decision_id),
    seq         INTEGER NOT NULL,
    text        TEXT NOT NULL
);
CREATE INDEX idx_passages_decision ON passages(decision_id, seq);
CREATE VIRTUAL TABLE passages_fts USING fts5(
    text, content='passages', content_rowid='passage_id', detail=none
);
"""

MONTHS = {
    "იანვარი": 1, "თებერვალი": 2, "მარტი": 3, "აპრილი": 4, "მაისი": 5, "ივნისი": 6,
    "ივლისი": 7, "აგვისტო": 8, "სექტემბერი": 9, "ოქტომბერი": 10, "ნოემბერი": 11,
    "დეკემბერი": 12,
}
DECISION_TYPES = ("განჩინება", "განაჩენი", "გადაწყვეტილება", "დადგენილება")

_PAGE_MARK = re.compile(r"^\[PAGE_\d+\]$")
_CASE_LINE = re.compile(r"^(საქმე\s*)?[#№]\s*(\S.*)$")
_REPEATED_LABEL = re.compile(r"^(?:(?:საქმე)?\s*[#№]\s*)+")
_DATE = re.compile(r"(\d{1,2})\s+([ა-ჰ]+),?\s+(\d{4})")
_PARAGRAPH_START = re.compile(r"^\d+(\.\d+)*[.)]\s")
_SENTENCE_END = re.compile(r"(?<=[.;:!?])\s+")
_GEORGIAN = re.compile(r"[ა-ჰ]")


@dataclass
class Decision:
    collection: str
    category: str
    case_number: str
    decision_type: str | None
    decision_date: str | None
    source_file: str
    passages: list[str]
    source_url: str | None = None

    @property
    def decision_id(self) -> str:
        return f"case:{self.collection}:{self.case_number}"

    @property
    def char_count(self) -> int:
        return sum(len(p) for p in self.passages)


def clean_lines(raw: str) -> list[str]:
    """Text lines without page markers, page numbers and print hyphenation."""
    lines: list[str] = []
    skip_page_number = False
    for line in raw.replace("\r", "").split("\n"):
        line = line.strip()
        if _PAGE_MARK.match(line):
            skip_page_number = True
            continue
        if not line:
            continue
        if skip_page_number and line.isdigit():
            skip_page_number = False
            continue
        skip_page_number = False
        if lines and lines[-1].endswith("-") and _GEORGIAN.match(line) \
                and len(lines[-1]) > 1 and _GEORGIAN.match(lines[-1][-2]):
            lines[-1] = lines[-1][:-1] + line
        else:
            lines.append(line)
    return lines


def read_case_number(heading: list[str]) -> str | None:
    """The case number printed in the heading, or None when there is none."""
    candidates: list[tuple[bool, str]] = []
    for line in heading:
        match = _CASE_LINE.match(line)
        if not match:
            continue
        # "#საქმე #1238აპ-24": the label printed twice is not part of the number.
        number = _REPEATED_LABEL.sub("", match.group(2).strip())
        date = _DATE.search(number)
        if date:
            number = number[: date.start()]
        # "#-ბს-100-95(კ-09)": some collections print a dash before the number.
        number = re.split(r"\s{2,}", number.strip())[0].strip(" ,.;").lstrip("-–—")
        # A number without any letter is a registry number or a misread print
        # ("29I-23" read as "291-23"); neither may be shown as the case number.
        valid = (
            3 <= len(number) <= 40
            and number[0].isalnum()
            and any(ch.isdigit() for ch in number)
            and any(ch.isalpha() for ch in number)
        )
        if valid:
            candidates.append((bool(match.group(1)), number))
    if not candidates:
        return None
    candidates.sort(key=lambda c: not c[0])
    return candidates[0][1]


def read_date(heading: list[str]) -> str | None:
    """ISO date printed in the heading ("3 ივნისი, 2016 წ."), or None."""
    for line in heading:
        for day, month, year in _DATE.findall(line):
            if month in MONTHS and 1 <= int(day) <= 31:
                return f"{int(year):04d}-{MONTHS[month]:02d}-{int(day):02d}"
    return None


def read_type(heading: list[str]) -> str | None:
    for line in heading:
        compact = line.replace(" ", "").strip("*")
        if compact in DECISION_TYPES:
            return compact
    return None


def split_passages(lines: list[str], limit: int = PASSAGE_CHARS) -> list[str]:
    """Join wrapped lines into paragraphs and pack them into passages."""
    paragraphs: list[str] = []
    for index, line in enumerate(lines):
        starts_paragraph = (
            index < HEADING_LINES or _PARAGRAPH_START.match(line) or not paragraphs
        )
        if starts_paragraph:
            paragraphs.append(line)
        else:
            paragraphs[-1] += " " + line

    pieces: list[str] = []
    for paragraph in paragraphs:
        while len(paragraph) > limit:
            ends = [m.end() for m in _SENTENCE_END.finditer(paragraph, 0, limit)]
            cut = ends[-1] if ends else (paragraph.rfind(" ", 0, limit) + 1 or limit)
            pieces.append(paragraph[:cut].rstrip())
            paragraph = paragraph[cut:]
        if paragraph:
            pieces.append(paragraph)

    passages: list[str] = []
    for piece in pieces:
        if passages and len(passages[-1]) + 1 + len(piece) <= limit:
            passages[-1] += "\n" + piece
        else:
            passages.append(piece)
    return passages


def parse_decision(path: Path, collection: str, category: str) -> Decision | None:
    lines = clean_lines(path.read_text(encoding="utf-8", errors="replace"))
    heading = lines[:HEADING_LINES]
    case_number = read_case_number(heading)
    if case_number is None:
        return None
    # A details file beside the text (extract_supreme_collections.py) gives the address of
    # the published collection and the page the decision starts on.
    details_file = path.with_suffix(".json")
    details = json.loads(details_file.read_text(encoding="utf-8")) if details_file.exists() else {}
    return Decision(
        collection=collection,
        category=category,
        case_number=case_number,
        decision_type=read_type(heading),
        decision_date=read_date(heading),
        source_file=f"{collection}/{category}/{path.name}",
        passages=split_passages(lines),
        source_url=details.get("source_url") or None,
    )


def parse_constitutional_decision(path: Path) -> Decision | None:
    """A Constitutional Court decision, described by the details file saved beside its text."""
    details_file = path.with_suffix(".json")
    details = json.loads(details_file.read_text(encoding="utf-8")) if details_file.exists() else {}
    case_number = (details.get("case_number") or "").strip()
    if not case_number:
        return None
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return Decision(
        collection=CONSTITUTIONAL_COLLECTION,
        category=CONSTITUTIONAL_CATEGORY,
        case_number=case_number,
        decision_type=details.get("decision_type") or None,
        decision_date=details.get("decision_date") or None,
        source_file=f"{CONSTITUTIONAL_COLLECTION}/{path.parent.name}/{path.name}",
        passages=split_passages([line for line in lines if line]),
        source_url=details.get("source_url") or None,
    )


def collect(directory: Path | None, collection: str, report: dict) -> list[Decision]:
    decisions: dict[str, Decision] = {}
    if directory is None:
        return []
    for path in sorted(directory.glob("*/*.txt")):
        if collection == CONSTITUTIONAL_COLLECTION:
            decision = parse_constitutional_decision(path)
        else:
            decision = parse_decision(path, collection, path.parent.name)
        if decision is None:
            report["skipped_no_case_number"].append(f"{collection}/{path.parent.name}/{path.name}")
            continue
        existing = decisions.get(decision.decision_id)
        if existing is not None:
            report["duplicates"].append(decision.source_file)
            if existing.char_count >= decision.char_count:
                continue
        decisions[decision.decision_id] = decision
    return list(decisions.values())


def write_store(decisions: list[Decision], out: Path) -> None:
    """Write the store beside ``out`` and move it into place in one step."""
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(".building")
    temporary.unlink(missing_ok=True)
    conn = sqlite3.connect(temporary)
    conn.executescript(DDL)
    for d in decisions:
        conn.execute(
            "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (d.decision_id, d.collection, d.case_number, d.category, d.decision_type,
             d.decision_date, d.decision_date[:4] if d.decision_date else None, d.source_url,
             d.source_file, len(d.passages), d.char_count),
        )
        conn.executemany(
            "INSERT INTO passages (decision_id, seq, text) VALUES (?,?,?)",
            [(d.decision_id, seq, text) for seq, text in enumerate(d.passages)],
        )
    conn.execute("INSERT INTO passages_fts (rowid, text) SELECT passage_id, text FROM passages")
    conn.executemany("INSERT INTO meta VALUES (?,?)", [
        ("schema_version", str(SCHEMA_VERSION)),
        ("built_at", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("decision_count", str(len(decisions))),
    ])
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    os.replace(temporary, out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--court-practice-dir", type=Path)
    parser.add_argument("--grand-chamber-dir", type=Path)
    parser.add_argument("--constitutional-court-dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    report: dict = {"skipped_no_case_number": [], "duplicates": []}
    decisions = collect(args.court_practice_dir, "court_practice", report)
    decisions += collect(args.grand_chamber_dir, "grand_chamber", report)
    decisions += collect(args.constitutional_court_dir, CONSTITUTIONAL_COLLECTION, report)
    if not decisions:
        print("No decision with a readable case number was found.", file=sys.stderr)
        return 1
    write_store(decisions, args.out)

    report["stored"] = len(decisions)
    report["without_date"] = sorted(d.source_file for d in decisions if not d.decision_date)
    report["by_collection"] = {
        name: sum(1 for d in decisions if d.collection == name)
        for name in ("court_practice", "grand_chamber", CONSTITUTIONAL_COLLECTION)
    }
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
