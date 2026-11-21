"""
Law connector schemas — what outside AI agents receive from the connector.

Every item that carries law or court text also carries where it came from
(``source_url``), how current it is (``version_date`` / ``in_force_since``,
with a ``version_note`` when the store does not record it) and the
not-legal-advice ``notice``. The connector returns sources only; the caller's
own AI writes the answer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Longest accepted inputs: enough for any real question, citation or id, and
# short enough that one request cannot make the server chew on a book.
MAX_QUERY_CHARS = 500
MAX_CODE_CHARS = 120
MAX_ARTICLE_CHARS = 20
MAX_CHAPTER_CHARS = 200
MAX_CLAIM_CHARS = 2000
MAX_ID_CHARS = 200
MAX_DATE_CHARS = 10
MAX_QUOTE_CHARS = 2000

NOT_LEGAL_ADVICE = (
    "ეს არის კანონის ტექსტი და წყარო, არა იურიდიული კონსულტაცია. ოფიციალური ტექსტი: "
    "matsne.gov.ge. This is law text and its source, not legal advice. The official "
    "text is on matsne.gov.ge; for important decisions consult a lawyer."
)

VERSION_UNKNOWN_NOTE = (
    "The date of this stored version is not recorded. Open source_url for the current "
    "consolidated text on matsne.gov.ge before relying on it."
)


class DataStamp(BaseModel):
    """How current the stored law texts behind an answer are."""

    data_current_as_of: str | None = Field(
        default=None,
        description="Date (ISO) the stored law texts were last confirmed against "
                    "matsne.gov.ge. Tell the person this date.",
    )
    freshness_warning: str | None = Field(
        default=None,
        description="Set when that check is overdue or its date is unknown; pass the "
                    "warning on with the answer.",
    )


class SourcedItem(BaseModel):
    """Fields every law-text result carries."""

    source_url: str = Field(description="Official matsne.gov.ge link for this text.")
    version_date: str | None = Field(
        default=None, description="Date of the consolidated version this text comes from."
    )
    in_force_since: str | None = Field(
        default=None, description="Date this article's current wording took effect, if known."
    )
    version_note: str | None = Field(
        default=None,
        description="Present when a version date is unknown or text may be incomplete.",
    )
    notice: str = Field(default=NOT_LEGAL_ADVICE)


class CodeSummary(SourcedItem):
    code: str = Field(description="Code identifier to pass to other tools, e.g. civil_code.")
    name: str = Field(description="Official Georgian name of the code.")
    article_count: int


class CodeList(DataStamp):
    codes: list[CodeSummary]
    notice: str = NOT_LEGAL_ADVICE


class ArticleHit(SourcedItem):
    id: str = Field(description="Stable id, usable with fetch: article:<code>:<number>.")
    code: str
    code_name: str
    article_number: str = Field(description="As printed in the law, e.g. 'მუხლი 369'.")
    article_title: str | None = None
    paragraph: str | None = Field(default=None, description="Paragraph the snippet is from.")
    snippet: str = Field(
        description="Exact text copied from the stored article (may be an excerpt)."
    )
    is_repealed: bool = False


class SearchLawResult(DataStamp):
    query: str
    found: bool
    results: list[ArticleHit]
    also_searched: list[str] = Field(
        default_factory=list,
        description="The law's own terms the search added for everyday words in the query.",
    )
    message: str | None = None
    notice: str = NOT_LEGAL_ADVICE


class Paragraph(BaseModel):
    number: str | None = None
    text: str


class ArticleRef(BaseModel):
    article_number: str
    article_title: str | None = None


class ArticleText(SourcedItem):
    id: str
    code: str
    code_name: str
    article_number: str
    article_title: str | None = None
    chapter: str | None = None
    text: str = Field(description="Full stored text of the article, unaltered.")
    paragraphs: list[Paragraph]
    requested_paragraph: Paragraph | None = None
    previous_article: ArticleRef | None = None
    next_article: ArticleRef | None = None
    is_repealed: bool = False
    as_of: str | None = Field(
        default=None,
        description="Set when an earlier date was asked for: the text is the wording of "
                    "the consolidated version matsne dates on or before this day, and "
                    "version_date and source_url are those of that version.",
    )
    wording_from: str | None = Field(
        default=None,
        description="Date of the version that introduced this wording; absent when it is "
                    "older than the stored history.",
    )
    replaced_on: str | None = Field(
        default=None,
        description="Date of the later version that changed or removed this wording; "
                    "absent when it is still the current one.",
    )
    history_note: str | None = Field(
        default=None, description="What to tell the person about an earlier-date answer."
    )


class GetArticleResult(DataStamp):
    found: bool
    article: ArticleText | None = None
    message: str | None = None
    notice: str = NOT_LEGAL_ADVICE


class LawChange(BaseModel):
    article_number: str = Field(description="As printed in the law, e.g. 'მუხლი 47'.")
    article_title: str | None = None
    change: Literal["amended", "added", "removed"]
    version_date: str = Field(
        description="Date matsne gives the consolidated version that carries the change."
    )
    version_url: str = Field(description="Official link to exactly that version.")


class LawChangesResult(DataStamp):
    found: bool
    code: str
    code_name: str | None = None
    since: str | None = None
    history_from: str | None = Field(
        default=None, description="Date of the oldest stored version; nothing earlier is known."
    )
    changes: list[LawChange] = Field(default_factory=list)
    total_changes: int = 0
    message: str | None = None
    notice: str = NOT_LEGAL_ADVICE


class ChapterSummary(BaseModel):
    chapter: str
    article_count: int
    first_article: str
    last_article: str


class CodeStructure(SourcedItem, DataStamp):
    found: bool
    code: str
    code_name: str | None = None
    chapters: list[ChapterSummary] = Field(default_factory=list)
    articles: list[ArticleRef] = Field(default_factory=list)
    total_articles: int = 0
    offset: int = 0
    message: str | None = None


# The courts a caller can keep a court-practice search to.
CourtName = Literal["supreme", "constitutional"]


class CourtDecision(BaseModel):
    id: str = Field(description="Stable id, usable with fetch: case:<collection>:<case id>.")
    case_number: str
    court: str
    collection: Literal["court_practice", "grand_chamber", "constitutional_court"]
    date: str | None = None
    year: str | None = None
    category: str | None = None
    decision_type: str | None = Field(
        default=None, description="As printed in the heading: განჩინება, განაჩენი, გადაწყვეტილება …"
    )
    passage: int | None = Field(
        default=None, description="Position of the snippet inside the decision (0 = heading)."
    )
    snippet: str = Field(description="Exact text copied from the stored decision.")
    source_url: str | None = Field(
        default=None, description="Link to the decision or the publication it was taken from."
    )
    link_note: str | None = None
    names_note: str | None = Field(
        default=None,
        description="Set when the court publishes this decision with the parties' names.",
    )
    notice: str = NOT_LEGAL_ADVICE


class CourtPracticeResult(DataStamp):
    query: str
    status: Literal["found", "none_found", "source_unavailable"]
    results: list[CourtDecision]
    message: str
    decisions_through: str | None = Field(
        default=None,
        description="Date of the newest stored decision of the courts searched; later "
                    "decisions are not covered.",
    )
    decisions_through_by_court: dict[str, str] = Field(
        default_factory=dict,
        description="The same date for each court searched, by court name.",
    )
    notice: str = NOT_LEGAL_ADVICE


class NumberedPassage(BaseModel):
    number: int = Field(description="Position inside the decision (0 = heading).")
    text: str = Field(description="Exact text copied from the stored decision.")


class CitedLawArticle(BaseModel):
    code: str
    code_name: str | None = None
    article_number: str = Field(description='As stored, e.g. "მუხლი 48".')
    mentions: int = Field(description="How often the decision cites this article.")
    status: Literal["changed", "unchanged", "unknown"] = Field(
        description="changed: a stored version dated after the decision changed or removed "
                    "this article. unchanged: no stored version since the decision changed "
                    "it. unknown: the stored wordings of this law begin after the decision "
                    "and none of them changed it, so an earlier change cannot be ruled out."
    )
    changed_on: list[str] = Field(
        default_factory=list, description="Dates of the versions that changed it, oldest first."
    )
    checked_from: str | None = Field(
        default=None, description="Date from which the stored wordings were compared."
    )
    repealed_now: bool = False


class LawSinceDecision(BaseModel):
    decision_date: str
    articles: list[CitedLawArticle]
    message: str


class CourtDecisionText(DataStamp):
    found: bool
    decision: CourtDecision | None = None
    passages: list[NumberedPassage] = Field(default_factory=list)
    total_passages: int = 0
    next_passage: int | None = Field(
        default=None, description="Pass as from_passage to read on; absent at the end."
    )
    law_since_decision: LawSinceDecision | None = Field(
        default=None,
        description="The stored law articles this decision cites and whether their wording "
                    "changed after the decision date.",
    )
    message: str | None = None
    notice: str = NOT_LEGAL_ADVICE


class LawCoverage(BaseModel):
    code: str
    name: str
    article_count: int
    version_date: str | None = Field(
        default=None, description="Date of the stored consolidated version."
    )
    source_url: str
    history_from: str | None = Field(
        default=None, description="Earliest date an earlier wording can be shown for."
    )
    history_versions: int = 0


class CourtCoverage(BaseModel):
    court: str
    collection: str
    decision_count: int
    earliest: str | None = None
    latest: str | None = None


class DataSourceNote(BaseModel):
    data: str = Field(description="Which kind of data this note is about.")
    source: str = Field(description="Where it comes from.")
    source_url: str
    how_collected: str
    how_kept_current: str
    last_updated: str | None = Field(
        default=None,
        description="Date (ISO) this data was last confirmed against its source or rebuilt.",
    )


class CoverageResult(DataStamp):
    laws: list[LawCoverage]
    court_decisions: list[CourtCoverage]
    how_data_is_kept: list[DataSourceNote] = Field(
        default_factory=list,
        description="Where each kind of data comes from, how it is collected and how it is "
                    "kept current. Use it when the person asks where the information comes "
                    "from or how up to date it is.",
    )
    not_covered: list[str] = Field(
        description="What this connector does not hold. Say so instead of answering "
                    "from memory when a question needs one of these."
    )
    notice: str = NOT_LEGAL_ADVICE


class LegalAidProvider(BaseModel):
    name: str
    helps_with: str
    free_for: str
    phone: str | None = None
    hours: str | None = None
    website: str
    email: str | None = None
    legal_basis: str | None = None
    checked_on: str | None = Field(
        default=None, description="Day a person last checked this contact against its source."
    )
    source: str | None = Field(default=None, description="Where it was checked.")


class LegalAidResult(BaseModel):
    providers: list[LegalAidProvider]
    emergency: str
    checked_on: str = Field(description="Date these contacts were last checked by a person.")
    message: str
    notice: str = NOT_LEGAL_ADVICE


class QuoteCheck(BaseModel):
    """Whether a quotation is in the stored text word for word."""

    verbatim: bool = Field(
        description="True only when the quote appears in the text exactly, apart from "
                    "spacing and quotation-mark style."
    )
    note: str


class LexicalCheck(BaseModel):
    """Word and number overlap between the claim and the article text."""

    label: str = (
        "Word and number overlap only. This is not a legal judgement; read the text."
    )
    numbers_in_claim: list[str]
    numbers_found_in_text: list[str]
    numbers_not_in_text: list[str]
    claim_terms_found: int
    claim_terms_total: int


class VerifyCitationResult(DataStamp):
    exists: bool
    code: str
    article: str
    claim: str
    paragraph_requested: str | None = None
    paragraph_exists: bool | None = None
    is_repealed: bool = False
    article_number: str | None = None
    article_title: str | None = None
    text: str | None = Field(
        default=None, description="What the article (or requested paragraph) actually says."
    )
    source_url: str | None = None
    version_date: str | None = None
    in_force_since: str | None = None
    version_note: str | None = None
    lexical_check: LexicalCheck | None = None
    quote_check: QuoteCheck | None = None
    message: str
    notice: str = NOT_LEGAL_ADVICE


class SearchResultItem(BaseModel):
    """ChatGPT search tool item: id, title, url."""

    id: str
    title: str
    url: str


class SearchResults(DataStamp):
    results: list[SearchResultItem]


class FetchResult(BaseModel):
    """ChatGPT fetch tool document."""

    id: str
    title: str
    text: str
    url: str
    metadata: dict[str, str] | None = None


class VerifyCitationRequest(BaseModel):
    code: str = Field(
        max_length=MAX_CODE_CHARS,
        description="Code id or Georgian name, e.g. civil_procedure_code.",
    )
    article: str = Field(
        max_length=MAX_ARTICLE_CHARS, description=(
            "Article number as printed, e.g. 369 or 166¹ (166-1 also works). A paragraph "
            "goes in its own argument.")
    )
    claim: str = Field(
        max_length=MAX_CLAIM_CHARS, description="What the answer claims the article says."
    )
    paragraph: str | None = Field(
        default=None, max_length=MAX_ARTICLE_CHARS,
        description="Paragraph number, if the claim cites one.",
    )
    quote: str | None = Field(
        default=None, max_length=MAX_QUOTE_CHARS,
        description="Words you are about to quote from the article, to check they are "
                    "in it word for word.",
    )
