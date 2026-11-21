"""Which articles of the stored laws a court decision cites, read from its own text.

Courts in Georgia keep citing older decisions, so an old decision is still worth reading.
What a reader needs to know is whether the articles it relied on still read the same. This
module finds those articles; the connector then compares them with the law history.

Only references it can tie to one stored law with confidence are returned:

- a law named in full in front of the article ("სამოქალაქო კოდექსის 1042-ე მუხლის"),
- "ამავე კოდექსის" / "ამავე კანონის" (the same law as the reference before it),
- a short form the decision defines itself ("(შემდგომში – სსკ)"), and otherwise the short
  forms the Supreme Court uses in that kind of case: "სსკ" is the Civil Code in a civil case
  and the Criminal Code in a criminal one; in an administrative case it is left unread.

Laws not held (the old Labour Laws Code, foreign codes) are skipped, never guessed.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.services.article_store_service import _normalize_article

# Stem of each stored law's name as it stands in front of an article number. Longest
# first, so "სამოქალაქო საპროცესო კოდექს" wins over "სამოქალაქო კოდექს".
LAW_STEMS: list[tuple[str, str]] = sorted([
    ("ადმინისტრაციულ სამართალდარღვევათა კოდექს", "admin_offences_code"),
    ("ადმინისტრაციული საპროცესო კოდექს", "admin_procedure_code"),
    ("ზოგადი ადმინისტრაციული კოდექს", "general_admin_code"),
    ("სისხლის სამართლის საპროცესო კოდექს", "criminal_procedure_code"),
    ("სისხლის სამართლის კოდექს", "criminal_code"),
    ("სამოქალაქო საპროცესო კოდექს", "civil_procedure_code"),
    ("სამოქალაქო კოდექს", "civil_code"),
    ("შრომის კოდექს", "labour_code"),
    ("საგადასახადო კოდექს", "tax_code"),
    ("საარჩევნო კოდექს", "election_code"),
    ("საბაჟო კოდექს", "customs_code"),
    ("ბავშვის უფლებათა კოდექს", "child_rights_code"),
    ("არასრულწლოვანთა მართლმსაჯულების კოდექს", "juvenile_justice_code"),
    ("კონსტიტუცი", "constitution"),
    ("მეწარმეთა შესახებ", "entrepreneurial_law"),
    ("მომხმარებლის უფლებების დაცვის შესახებ", "consumer_rights_law"),
    ("პერსონალურ მონაცემთა დაცვის შესახებ", "personal_data_law"),
    ("იურიდიული დახმარების შესახებ", "legal_aid_law"),
    ("სააღსრულებო წარმოებათა შესახებ", "enforcement_law"),
    ("ოჯახში ძალადობის", "domestic_violence_law"),
    ("დისკრიმინაციის ყველა ფორმის აღმოფხვრის შესახებ", "anti_discrimination_law"),
    ("პაციენტის უფლებების შესახებ", "patient_rights_law"),
    ("სოციალური დახმარების შესახებ", "social_assistance_law"),
    ("სახელმწიფო პენსიის შესახებ", "state_pension_law"),
], key=lambda pair: -len(pair[0]))

# Short forms by kind of case, used only when the decision does not define its own.
SHORT_FORMS: dict[str, dict[str, str]] = {
    "civil": {"სკ": "civil_code", "სსკ": "civil_code", "სსსკ": "civil_procedure_code",
              "სშკ": "labour_code"},
    "criminal": {"სსკ": "criminal_code", "სსსკ": "criminal_procedure_code"},
    "administrative": {"სასკ": "admin_procedure_code", "სზაკ": "general_admin_code",
                       "სსსკ": "civil_procedure_code"},
}

# Short forms courts use for laws; one met in front of an article that the decision or its
# kind of case does not tie to a stored law stops the search (never fall back further).
KNOWN_SHORT_FORMS = {form for forms in SHORT_FORMS.values() for form in forms} | {
    "ასკ", "სსპკ", "ზაკ", "აპეკ", "გსკ", "შკკ", "სსკი"}

_STEM_RE = re.compile("|".join(re.escape(stem) for stem, _ in LAW_STEMS))
_STEM_IDS = dict(LAW_STEMS)
# A law named after another country ("გერმანიის სამოქალაქო კოდექსი") is not a stored law.
_FOREIGN_RE = re.compile(
    r"(?:გერმანი|საფრანგეთ|ავსტრი|შვეიცარი|იტალი|ესპანეთ|ნიდერლანდებ|ჰოლანდი|რუსეთ|უკრაინ"
    r"|ესტონი|ლიტვ|ლატვი|პოლონეთ|თურქეთ|სომხეთ|აზერბაიჯან|იაპონი|ინგლის|ბრიტანეთ|ამერიკ"
    r"|ჩეხეთ|საბერძნეთ|ბელგი|კანად|ევროპ|შვედეთ|ნორვეგი|დანი|ფინეთ|ისრაელ|მოლდოვ)[ა-ჰ-]*\s+$"
)
_SAME_LAW_RE = re.compile(r"(?:ამავე|იმავე|აღნიშნული|მითითებული)\s+(?:კოდექს|კანონ)")
_SHORT_RE = re.compile(r"(?<![ა-ჰ])([ა-ჰ]{2,5}კ)(?:-?ი[სთ]|-ში|-ზე)?(?![ა-ჰ])")
_DEFINITION_RE = re.compile(
    r"(" + _STEM_RE.pattern + r")[ა-ჰ]*\s*(?:[ა-ჰ]+\s+){0,2}?\(\s*(?:შემდგომში|შემდეგში|შემდგომ)"
    r"\s*[-–—:]?\s*[„\"]?([ა-ჰ]{2,5}კ)[“\"]?\s*\)"
)
_SUP = "¹²³⁴⁵⁶⁷⁸⁹⁰"
_NUM = r"(?:მე-)?\d+[" + _SUP + r"]*(?:\.\d+)*(?:-[ა-ჰ]+)?"
# One or more article numbers in front of "მუხლ…": "48-ე მუხლის", "361-ე, 394-ე და 412-ე მუხლები".
_ARTICLES_RE = re.compile(r"(" + _NUM + r"(?:\s*(?:,|და)\s*" + _NUM + r")*)\s+მუხლ")
_SEPARATOR_RE = re.compile(r"\s*(?:,|და)\s*")
_ONE_NUM_RE = re.compile(r"(?:მე-)?(\d+[" + _SUP + r"]*)")
# How far in front of an article number its law must be named.
LOOKBACK_CHARS = 90


@dataclass(frozen=True)
class CitedArticle:
    code: str           # stored law id, e.g. "civil_code"
    article_norm: str   # stored article key, e.g. "48", "166-1"
    mentions: int       # how often the decision cites it


def _stem_law(text: str, start: int, stem: str) -> str | None:
    """The stored law a name stands for, or None when another country's law is meant."""
    return None if _FOREIGN_RE.search(text[max(0, start - 30):start]) else _STEM_IDS[stem]


def _short_forms(text: str, category: str | None) -> dict[str, str | None]:
    """The decision's own definitions of short forms, over the usual ones for its kind."""
    forms: dict[str, str | None] = dict(SHORT_FORMS.get(category or "", {}))
    for match in _DEFINITION_RE.finditer(text):
        forms[match.group(2)] = _stem_law(text, match.start(), match.group(1))
    return forms


def _law_before(window: str, forms: dict[str, str | None], previous: str | None) -> str | None:
    """The stored law named last in ``window``, or None when it names none it can tie."""
    best: tuple[int, str | None] = (-1, None)
    for match in _STEM_RE.finditer(window):
        best = (match.start(), _stem_law(window, match.start(), match.group(0)))
    for match in _SHORT_RE.finditer(window):
        form = match.group(1)
        if match.start() > best[0] and (form in forms or form in KNOWN_SHORT_FORMS):
            best = (match.start(), forms.get(form))
    for match in _SAME_LAW_RE.finditer(window):
        if match.start() > best[0]:
            best = (match.start(), previous)
    return best[1]


def cited_articles(text: str, category: str | None = None, limit: int = 15) -> list[CitedArticle]:
    """Articles of stored laws the decision cites, most cited first."""
    forms = _short_forms(text, category)
    counts: Counter[tuple[str, str]] = Counter()
    previous: str | None = None
    for match in _ARTICLES_RE.finditer(text):
        window = text[max(0, match.start() - LOOKBACK_CHARS):match.start()]
        law = _law_before(window, forms, previous)
        if law is None:
            continue
        previous = law
        for item in _SEPARATOR_RE.split(match.group(1)):
            number = _ONE_NUM_RE.match(item)
            if number:
                counts[(law, _normalize_article(number.group(1)))] += 1
    return [CitedArticle(code, norm, n) for (code, norm), n in counts.most_common(limit)]
