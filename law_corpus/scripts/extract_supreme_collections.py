#!/usr/bin/env python3
"""
Split the Supreme Court's decision collections (PDF) into one text file per decision.

Reads what ``fetch_supreme_court_collections.py`` saved and writes, for the court store
builder (``build_court_store.py``):

    OUT/court_practice/<civil|criminal|administrative>/<case number>.txt
    OUT/grand_chamber/<civil|criminal|administrative>/<case number>.txt

with a details file beside each text (``.json``: the collection's address with the page
the decision starts on, the collection's label, the case number read from the heading).

A decision starts where its heading does: the kind of act on its own line (განჩინება,
გადაწყვეტილება, განაჩენი, დადგენილება), and within the next lines the case number after
"#" or "№" and the date. It runs until the next heading. Nothing is rewritten: the text is
what the collection prints, line by line, with "[PAGE_N]" marks the builder removes.

Older collections are set in Unicode Georgian. Newer ones use the old Georgian typewriter
font (AcadNusx and its kin), whose letters come out of the PDF as Latin ones. Such text is
converted letter for letter, font by font: a font is converted only when its text reads as
that typewriter Georgian, so English and other lines in the same file stay as printed.

Decisions are published with the parties as initials. A decision whose text still carries
people's full names is left out and named in the report (``--report``).

    python scripts/extract_supreme_collections.py --work-dir WORK --out OUT --report R.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

# The typewriter font's Latin keys and the Georgian letters they print.
ACADNUSX = str.maketrans({
    "a": "ა", "b": "ბ", "g": "გ", "d": "დ", "e": "ე", "v": "ვ", "z": "ზ", "T": "თ",
    "i": "ი", "k": "კ", "l": "ლ", "m": "მ", "n": "ნ", "o": "ო", "p": "პ", "J": "ჟ",
    "r": "რ", "s": "ს", "t": "ტ", "u": "უ", "f": "ფ", "q": "ქ", "R": "ღ", "y": "ყ",
    "S": "შ", "C": "ჩ", "c": "ც", "Z": "ძ", "w": "წ", "W": "ჭ", "x": "ხ", "j": "ჯ",
    "h": "ჰ", "`": "„", "~": "“",
})
# Words that are very common in Georgian typed in that font, and rare in English.
_TYPEWRITER_WORDS = frozenset({
    "da", "rom", "ar", "aris", "ki", "am", "Tu", "mier", "an", "saqmis", "sasamarTlos",
    "saqarTvelos", "sasamarTlo", "Tanaxmad", "mxaris", "kanonis", "muxlis", "palatis",
})
_MID_WORD_KEY = re.compile(r"[a-z][TSCRWZJ]")
_TOKEN = re.compile(r"[A-Za-z`~\[\];,']+")

DECISION_TYPES = ("განჩინება", "განაჩენი", "გადაწყვეტილება", "დადგენილება")
CHAMBER_CATEGORY = {
    "civil": ("court_practice", "civil"),
    "criminal": ("court_practice", "criminal"),
    "administrative": ("court_practice", "administrative"),
    "grand_chamber_civil": ("grand_chamber", "civil"),
    "grand_chamber_criminal": ("grand_chamber", "criminal"),
    "grand_chamber_administrative": ("grand_chamber", "administrative"),
}
_CASE_LINE = re.compile(r"^(?:საქმე\s*)?[#№]\s*([^\s,;]+)")
_DATE = re.compile(r"(\d{1,2})\s+([ა-ჰ]+),?\s+(\d{4})")
HEADING_LOOKAHEAD = 4

# Full names: a common given name followed by a surname. Judges and parties are printed
# with initials in these collections, so a full name means the text was not anonymised.
GIVEN_NAMES = (  # noqa: SIM905 - a word list reads better than 60 quoted names
    "გიორგი დავით დავითი ნიკოლოზ ალექსანდრე ლევან ზურაბ ირაკლი თამაზ მამუკა გოჩა ზაზა "
    "ვახტანგ ვლადიმერ ვალერი ბესიკ ბესარიონ ლაშა დიმიტრი შოთა ნოდარ ომარ რევაზ "
    "ავთანდილ მერაბ ელგუჯა ჯემალ გურამ კახაბერ ტარიელ ბადრი ნიკა ლუკა სანდრო თორნიკე "
    "ნინო მარიამ თამარ ნათია ეკატერინე ქეთევან მაია ნანა ლია ხათუნა ირმა მანანა ნატო "
    "ნათელა ლალი ციალა მზია ლელა თეა სოფიო ანა ელენე ნესტან ლამარა"
).split()
_FULL_NAME = re.compile(
    r"(?<![ა-ჰ])(?:" + "|".join(GIVEN_NAMES) + r")(?:ს|მა|ის|ი)?\s+[ა-ჰ]{3,}"
    r"(?:შვილ|ძე|ძის|ია|იას|ავა|უა|ანი|ური|ელი)[ა-ჰ]*"
)
FULL_NAMES_THAT_EXCLUDE = 2
# Scholars are cited by full name ("იხ. გიორგი ვაშაკიძე, ... კომენტარი, გვ. 12"); a name
# with such a citation around it is an author, not a party.
_CITED_BEFORE = re.compile(
    r"(?:იხ|შდრ|შეად|/|წიგნში)[^)]{0,25}$|(?:რედაქტორ|ავტორ)[^\]).]{0,150}$"
    # The title of another court's published case, as the Constitutional Court names its
    # cases after the people who brought them: საქმეზე „X და Y საქართველოს პარლამენტის
    # წინააღმდეგ“, or "#1/2/384 გადაწყვეტილება საქმეზე X, Y".
    r"|საქმეზე\s*[`„\"][^“\"~`]{0,140}$|#\s*\d+/\d+/\d+[^.;]{0,60}საქმეზე[^“\"~.;]{0,140}$")
# A word broken across lines ("აღიარებუ- ლია") is not a name.
_BROKEN_WORD = re.compile(r"[ა-ჰ]-\s$")
_CITED_AFTER = re.compile(
    r"^[^.]{0,250}?(?:გვ\.|კომენტარ|გამომცემლობა|სახელმძღვანელო|ჟურნალ|წიგნში|\d{4}\s*წ?\.?,\s*გვ)"
    r"|^[^(]{0,40}/")
# Judges, prosecutors and court staff are named in full by design; they are officials
# acting in office, not parties. A name in such a role, or a surname named in such a
# role elsewhere in the decision, does not count. Nor does an institution named after a
# person ("გიორგი აბრამიშვილის სახელობის ჰოსპიტალი").
_OFFICIAL_BEFORE = re.compile(
    r"(?:პროკურორ|პროკურატურის|მოსამართლე|თავმჯდომარე|მომხსენებელ|მდივან|მოადგილ)[ა-ჰ]*"
    r"\s*[-–—_,:]?\s*$")
_OFFICIAL_AFTER = re.compile(r"^[ა-ჰ]*\s*(?:\((?:თავმჯდომარე|მომხსენებელი)\)|სახელობის)")
_COMPOSITION = re.compile(
    r"შემადგენლობა(.{0,700}?)(?:მდივან|კასატორ|მოსარჩელე|მოპასუხე|მსჯავრდებულ|ბრალდებულ"
    r"|აპელანტ|განმცხადებ|დავის საგანი|საქმის განხილვის|$)", re.S)


@dataclass
class Line:
    text: str
    page: int  # 1-based


@dataclass
class Report:
    files: int = 0
    unreadable: list[str] = field(default_factory=list)
    converted_fonts: dict[str, list[str]] = field(default_factory=dict)
    decisions: Counter = field(default_factory=Counter)
    duplicates: list[str] = field(default_factory=list)
    names_not_hidden: list[str] = field(default_factory=list)


def typewriter_fonts(spans: list[tuple[str, str]]) -> set[str]:
    """Fonts of a file whose text reads as Georgian typed in the typewriter font."""
    words: dict[str, Counter] = defaultdict(Counter)
    for font, text in spans:
        if re.search(r"[ა-ჰ]", text):
            continue
        for token in _TOKEN.findall(text):
            counts = words[font]
            counts["tokens"] += 1
            counts["common"] += token in _TYPEWRITER_WORDS
            counts["keyed"] += bool(_MID_WORD_KEY.search(token))
    return {
        font for font, c in words.items()
        if c["tokens"] and (c["common"] + c["keyed"]) / c["tokens"] >= 0.08
    }


def read_lines(pdf_path: Path) -> tuple[list[Line], list[str]]:
    """The file's text lines in reading order, typewriter text converted to Georgian."""
    doc = pymupdf.open(pdf_path)
    pages = [page.get_text("dict") for page in doc]
    spans = [(s["font"], s["text"]) for p in pages for b in p["blocks"]
             for ln in b.get("lines", []) for s in ln["spans"]]
    convert = typewriter_fonts(spans)
    lines: list[Line] = []
    for number, page in enumerate(pages, 1):
        lines.append(Line(f"[PAGE_{number}]", number))
        for block in page["blocks"]:
            for ln in block.get("lines", []):
                text = "".join(
                    s["text"].translate(ACADNUSX) if s["font"] in convert else s["text"]
                    for s in ln["spans"])
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    lines.append(Line(text, number))
    return lines, sorted(convert)


def decision_starts(lines: list[Line]) -> list[tuple[int, str]]:
    """(line index, case number) of each decision heading."""
    starts: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if line.text.replace(" ", "").strip("*") not in DECISION_TYPES:
            continue
        ahead = [ln.text for ln in lines[i + 1:i + 1 + HEADING_LOOKAHEAD]
                 if not ln.text.startswith("[PAGE_")]
        for j, text in enumerate(ahead):
            match = _CASE_LINE.match(text)
            if match and any(_DATE.search(t) for t in ahead[j:j + 2]):
                starts.append((i, match.group(1).strip(" .")))
                break
    return starts


def safe_name(case_number: str) -> str:
    return re.sub(r"[^\wა-ჰ\-]+", "_", case_number).strip("_") or "case"


def _surname(name: str) -> str:
    """The surname without its case ending (at most three letters, keeping four)."""
    word = name.split()[-1]
    return word[:max(4, len(word) - 3)]


def official_surnames(text: str) -> set[str]:
    """Surnames the decision gives to judges, prosecutors and court staff."""
    found: set[str] = set()
    for block in _COMPOSITION.finditer(text):
        found |= {_surname(m.group(0)) for m in _FULL_NAME.finditer(block.group(1))}
    for match in _FULL_NAME.finditer(text):
        if _OFFICIAL_BEFORE.search(text[max(0, match.start() - 60):match.start()]):
            found.add(_surname(match.group(0)))
    return found


def full_names(text: str) -> int:
    """Full names in the text that are not officials or authors of cited legal writing."""
    text = re.sub(r"-\n", "", text)  # words broken across lines, as "პრო-\nკურორ"
    officials = official_surnames(text)
    count = 0
    for match in _FULL_NAME.finditer(text):
        surname = match.group(0).split()[-1]
        if any(surname.startswith(stem) for stem in officials) or _OFFICIAL_AFTER.match(
                text[match.end():match.end() + 40]):
            continue
        before = text[max(0, match.start() - 160):match.start()]
        if _BROKEN_WORD.search(before):
            continue
        after = text[match.end():match.end() + 260]
        if not (_CITED_BEFORE.search(before[-40:]) or _CITED_BEFORE.search(before)
                or _CITED_AFTER.search(after)):
            count += 1
    return count


def extract(work_dir: Path, out: Path, report: Report) -> None:
    base = work_dir / "supreme_collections"
    manifest = json.loads((base / "manifest.json").read_text("utf-8"))
    written: dict[Path, int] = {}
    for entry in manifest:
        if entry["status"] != "saved" or entry["chamber"] not in CHAMBER_CATEGORY:
            continue
        report.files += 1
        collection, category = CHAMBER_CATEGORY[entry["chamber"]]
        try:
            lines, converted = read_lines(base / entry["file"])
        except Exception as error:  # a broken file is reported, never guessed at
            report.unreadable.append(f"{entry['file']}: {type(error).__name__}")
            continue
        if converted:
            report.converted_fonts[entry["file"]] = converted
        starts = decision_starts(lines)
        for k, (index, case_number) in enumerate(starts):
            end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
            chunk = lines[index:end]
            text = "\n".join(ln.text for ln in chunk)
            label = f"{entry['file']}#{case_number}"
            if full_names(text) >= FULL_NAMES_THAT_EXCLUDE:
                report.names_not_hidden.append(label)
                continue
            target = out / collection / category / f"{safe_name(case_number)}.txt"
            if target in written:
                report.duplicates.append(label)
                if written[target] >= len(text):
                    continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text + "\n", "utf-8")
            target.with_suffix(".json").write_text(json.dumps({
                "case_number": case_number,
                "source_url": f"{entry['url']}#page={chunk[0].page}",
                "collection_label": entry["label"],
                "collection_file": entry["file"],
            }, ensure_ascii=False, indent=1), "utf-8")
            written[target] = len(text)
            report.decisions[f"{collection}/{category}"] += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = Report()
    extract(args.work_dir, args.out, report)
    summary = {
        "files": report.files, "decisions": dict(report.decisions),
        "unreadable": report.unreadable, "duplicates": len(report.duplicates),
        "names_not_hidden": report.names_not_hidden,
        "files_with_typewriter_font": len(report.converted_fonts),
    }
    if args.report:
        args.report.write_text(json.dumps(
            summary | {"duplicate_list": report.duplicates,
                       "converted_fonts": report.converted_fonts},
            ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps(summary, ensure_ascii=False)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
