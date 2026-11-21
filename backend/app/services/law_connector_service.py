"""
Law Connector Service — Georgian law sources for outside AI agents.

Backs the MCP server and its REST mirror. It never calls a model: it returns
exact stored text with its official link and version date, and the caller's
own AI (ChatGPT, Claude, any agent) writes the answer from it. Statutes come
from the article store (the same deterministic store the app's own pipeline
grounds on); court decisions come from the court store by plain word match,
so the lookup works without anyone's model key.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypeVar

from app.config.settings import settings
from app.schemas.connector_schema import (
    VERSION_UNKNOWN_NOTE,
    ArticleHit,
    ArticleRef,
    ArticleText,
    ChapterSummary,
    CitedLawArticle,
    CodeList,
    CodeStructure,
    CodeSummary,
    CourtCoverage,
    CourtDecision,
    CourtDecisionText,
    CourtPracticeResult,
    CoverageResult,
    DataSourceNote,
    DataStamp,
    FetchResult,
    GetArticleResult,
    LawChange,
    LawChangesResult,
    LawCoverage,
    LawSinceDecision,
    LegalAidProvider,
    LegalAidResult,
    LexicalCheck,
    NumberedPassage,
    Paragraph,
    QuoteCheck,
    SearchLawResult,
    SearchResultItem,
    SearchResults,
    VerifyCitationResult,
)
from app.services.article_store_service import (
    ARTICLE_FORMAT_HINT,
    ArticleStoreService,
    _normalize_article,
    get_article_store_service,
    requested_article,
)
from app.services.connector_reference import (
    CONSTITUTIONAL_NOT_HELD,
    DATA_SOURCES,
    LEGAL_AID_CHECKED_ON,
    LEGAL_AID_EMERGENCY,
    LEGAL_AID_MESSAGE,
    LEGAL_AID_PROVIDERS,
    NOT_COVERED,
    law_terms_for,
)
from app.services.connector_status_service import ConnectorStatusService, file_signature
from app.services.court_store_service import CourtStoreService
from app.services.decision_citations import cited_articles
from app.services.law_history_service import HISTORY_FILE, LawHistoryService
from app.utils.logger import get_logger

logger = get_logger(__name__)

MATSNE_DOCUMENT_URL = "https://matsne.gov.ge/ka/document/view/{document_number}"

# matsne.gov.ge document numbers of the codes in the store, used to build the
# official link when a store row carries none.
MATSNE_DOCUMENT_NUMBERS = {
    "admin_offences_code": "28216",
    "admin_procedure_code": "16492",
    "civil_code": "31702",
    "civil_procedure_code": "29962",
    "constitution": "30346",
    "consumer_rights_law": "5420598",
    "criminal_code": "16426",
    "criminal_procedure_code": "90034",
    "customs_code": "4598501",
    "election_code": "1557168",
    "entrepreneurial_law": "5230186",
    "general_admin_code": "16270",
    "labour_code": "1155567",
    "personal_data_law": "5827307",
    "tax_code": "1043717",
    "legal_aid_law": "21604",
    "enforcement_law": "18442",
    "child_rights_code": "4613854",
    "domestic_violence_law": "26422",
    "anti_discrimination_law": "2339687",
    "patient_rights_law": "16978",
    "juvenile_justice_code": "2877281",
    "social_assistance_law": "23098",
    "state_pension_law": "27946",
}

CODE_VERSION_COLUMNS = ("version_date", "consolidated_version_date", "consolidated_date")
ARTICLE_IN_FORCE_COLUMNS = ("in_force_since", "effective_date")

CONSTITUTIONAL_COLLECTION = "constitutional_court"
COURT_COLLECTIONS = ("court_practice", "grand_chamber", CONSTITUTIONAL_COLLECTION)
COURT_NAMES = {
    "court_practice": "საქართველოს უზენაესი სასამართლო (Supreme Court of Georgia)",
    "grand_chamber": (
        "საქართველოს უზენაესი სასამართლოს დიდი პალატა (Supreme Court of Georgia, Grand Chamber)"
    ),
    CONSTITUTIONAL_COLLECTION: (
        "საქართველოს საკონსტიტუციო სასამართლო (Constitutional Court of Georgia)"
    ),
}
# What a caller may pass as ``court`` to search one court only.
COURT_FILTERS: dict[str, tuple[str, ...]] = {
    "supreme": ("court_practice", "grand_chamber"),
    "constitutional": (CONSTITUTIONAL_COLLECTION,),
}
COURT_SITE_URLS = {
    "court_practice": "https://www.supremecourt.ge",
    "grand_chamber": "https://www.supremecourt.ge",
    CONSTITUTIONAL_COLLECTION: "https://www.constcourt.ge",
}
COURT_LINK_NOTE = (
    "No direct link is stored for this decision. Look the case number up on "
    "{site} before citing it."
)
# The Supreme Court publishes parties as initials; the Constitutional Court
# publishes names. Both are stored exactly as published.
COURT_NAMES_NOTE = (
    "The Constitutional Court publishes its judgments with the parties' names; this "
    "text is as the court published it. Cite the case by its number and title, and do "
    "not use it to tell anything else about the people named."
)
# Stated in place of the plain "not held" line while only judgments are stored.
CONSTITUTIONAL_HELD_NOTE = (
    "Constitutional Court rulings and recording notices; of that court only judgments "
    "(გადაწყვეტილება) are held."
)
# Courts keep citing older decisions; the note says which cited articles changed since,
# without suggesting the decision is no longer worth using.
LAW_SINCE_DECISION_NOTE = (
    "Courts in Georgia still cite older decisions, so this one can still be used. These are "
    "the articles of the stored laws it cites, read from its text (most cited first, and the "
    "list can miss some), and whether their wording changed after {decision_date}. For a "
    "changed article, read the wording the court applied (get_article with as_of="
    "{decision_date}) and today's, and tell the person which one the decision rests on and "
    "how it differs. unknown: the stored wordings of that law begin after the decision."
)
COURT_STORE_FILE = "court_store.db"
ARTICLE_STORE_FILE = "article_store.db"

# A decision can run past 300,000 characters, so fetch returns a window of
# passages: the opening ones, or those around the passage a search pointed at.
FETCH_PASSAGES = 24
FETCH_PASSAGES_BEFORE = 6

SNIPPET_CHARS = 600
MAX_SEARCH_LIMIT = 25
MAX_BROWSE_LIMIT = 300
MAX_CHANGES_LISTED = 200
MAX_LAW_TERMS = 3
DECISION_PASSAGES_PER_CALL = 20

HISTORY_UNAVAILABLE = (
    "Earlier wordings of the laws are not available on this server. Say that only the "
    "current text was checked; open the law on matsne.gov.ge for its earlier versions."
)
HISTORY_NOTE = (
    "This is the wording in matsne.gov.ge's consolidated version dated {version_date}, "
    "the newest one dated on or before {as_of}. An amendment can take effect later "
    "than the date of its version and transitional provisions can apply, so name the "
    "version date and give the link when you rely on it."
)
REPLACED_NOTE = (
    " A later version dated {replaced_on} changed this article: call get_article "
    "without as_of for the current text."
)

_QUOTE_MARKS = str.maketrans({c: '"' for c in "„“”«»‘’'`~"} | {"–": "-", "—": "-", "‑": "-"})
_ELLIPSIS = re.compile(r"\s*(?:…|\.{3,})\s*")

_WORD = re.compile(r"[\wა-ჿ]+")
_NUMBER = re.compile(r"\d+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _stem(word: str) -> str:
    """Crude Georgian stem: drop the case ending so inflected forms match."""
    if len(word) >= 6:
        return word[:-2]
    if len(word) >= 4:
        return word[:-1]
    return word


def _excerpt(text: str, limit: int = SNIPPET_CHARS) -> str:
    """Leading part of ``text``, cut at a word boundary; the words are unaltered."""
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit)
    return text[: cut if cut > 0 else limit] + " …"


def _flat(text: str) -> str:
    """Text with spacing and quotation-mark style evened out, for comparing wording."""
    return " ".join(text.translate(_QUOTE_MARKS).split())


def _iso_date(value: str | None) -> str | None:
    """``value`` as an ISO date, or None when it is not one."""
    try:
        return date.fromisoformat((value or "").strip()).isoformat()
    except ValueError:
        return None


def _first_present(row: dict[str, Any], columns: tuple[str, ...]) -> str | None:
    for column in columns:
        value = row.get(column)
        if value:
            return str(value)
    return None


_Result = TypeVar("_Result")


def _stamped(tool: Callable[..., _Result]) -> Callable[..., _Result]:
    """Wrap a tool: pick up replaced store files first, date the answer after."""

    @functools.wraps(tool)
    def wrapper(self: LawConnectorService, *args: Any, **kwargs: Any) -> _Result:
        self._reload_if_store_replaced()
        return self._stamp(tool(self, *args, **kwargs))

    return wrapper


class LawConnectorService:
    """Read-only law and court-practice lookups that always name their source."""

    def __init__(
        self,
        store: ArticleStoreService | None = None,
        court: CourtStoreService | None = None,
        status: ConnectorStatusService | None = None,
        history: LawHistoryService | None = None,
    ) -> None:
        self._store = store or get_article_store_service()
        # The court store and the law history sit beside the article store unless given.
        self._court = court or CourtStoreService(self._store.db_path.with_name(COURT_STORE_FILE))
        self._history = history or LawHistoryService(
            self._store.db_path.with_name(HISTORY_FILE))
        self._status = status or ConnectorStatusService(self._store)
        self._store_signature = file_signature(self._store.db_path)
        self._codes: dict[str, dict[str, Any]] | None = None
        self._article_order: dict[str, list[ArticleRef]] = {}

    # ── Fresh data ───────────────────────────────────────────

    def _reload_if_store_replaced(self) -> None:
        """Drop everything remembered from the article store once its file changes.

        The daily refresh builds a new store and moves it into place; each
        lookup opens the file anew, so only what is cached here goes stale.
        """
        signature = file_signature(self._store.db_path)
        if signature == self._store_signature:
            return
        self._store_signature = signature
        self._store.reset_caches()
        self._codes = None
        self._article_order = {}
        logger.info("connector_store_reloaded", available=signature is not None)

    def refresh_state(self) -> str:
        """How the daily refresh of the law texts is doing (see the status service)."""
        return self._status.refresh_state()

    def _stamp(self, result: _Result) -> _Result:
        """Write the date the law texts were last confirmed onto a tool's answer."""
        status = self._status.current()
        if isinstance(result, DataStamp):
            result.data_current_as_of = status.current_as_of
            result.freshness_warning = status.warning
        elif isinstance(result, FetchResult):
            stamp = {
                "data_current_as_of": status.current_as_of,
                "freshness_warning": status.warning,
            }
            result.metadata = (result.metadata or {}) | {k: v for k, v in stamp.items() if v}
        return result

    # ── Sources and versions ─────────────────────────────────

    def _code_rows(self) -> dict[str, dict[str, Any]]:
        if self._codes is None:
            self._codes = {c["document_id"]: c for c in self._store.list_codes()}
        return self._codes

    def _code_url(self, document_id: str) -> str:
        code = self._code_rows().get(document_id, {})
        url = code.get("matsne_url") or code.get("source_url")
        if url:
            return str(url)
        number = code.get("document_number") or MATSNE_DOCUMENT_NUMBERS.get(document_id)
        if number:
            return MATSNE_DOCUMENT_URL.format(document_number=number)
        return "https://matsne.gov.ge"

    def _article_url(self, art: dict[str, Any]) -> str:
        # official_url opens the article on matsne; article_url is the store's own key.
        url = art.get("official_url") or art.get("matsne_url") or art.get("article_url")
        if url:
            return str(url)
        anchor = _normalize_article(art["article_number"])
        return f"{self._code_url(art['document_id'])}#article_{anchor}"

    def _version(self, art: dict[str, Any]) -> dict[str, str | None]:
        """version_date / in_force_since / version_note for an article."""
        code = self._code_rows().get(art["document_id"], {})
        version_date = art.get("version_date") or _first_present(code, CODE_VERSION_COLUMNS)
        in_force_since = _first_present(art, ARTICLE_IN_FORCE_COLUMNS)
        notes: list[str] = []
        if not version_date and not in_force_since:
            notes.append(VERSION_UNKNOWN_NOTE)
        gap = self._paragraph_gap(art)
        if gap:
            notes.append(gap)
        return {
            "version_date": str(version_date) if version_date else None,
            "in_force_since": in_force_since,
            "version_note": " ".join(notes) or None,
        }

    @staticmethod
    def _paragraph_gap(art: dict[str, Any]) -> str | None:
        """Flag a stored text whose numbered paragraphs do not start at 1."""
        numbers = [str(p.get("number")) for p in art.get("paragraphs") or [] if p.get("number")]
        if numbers and numbers[0].isdigit() and numbers[0] != "1":
            return (
                f"The stored text starts at paragraph {numbers[0]}; earlier paragraphs may "
                "be missing. Check source_url for the full article."
            )
        return None

    @staticmethod
    def _article_id(art: dict[str, Any]) -> str:
        return f"article:{art['document_id']}:{_normalize_article(art['article_number'])}"

    # ── Tools ────────────────────────────────────────────────

    @_stamped
    def list_codes(self) -> CodeList:
        """Every code in the store with its article count, link and version date."""
        codes = []
        for document_id, row in sorted(self._code_rows().items()):
            version_date = _first_present(row, CODE_VERSION_COLUMNS)
            codes.append(CodeSummary(
                code=document_id,
                name=row["code_name"],
                article_count=row.get("article_count") or 0,
                source_url=self._code_url(document_id),
                version_date=version_date,
                version_note=None if version_date else VERSION_UNKNOWN_NOTE,
            ))
        return CodeList(codes=codes)

    @_stamped
    def search_law(self, query: str, code: str | None = None, limit: int = 8) -> SearchLawResult:
        """Articles matching the query, best first, each with an exact snippet."""
        limit = max(1, min(limit, MAX_SEARCH_LIMIT))
        document_id = None
        if code:
            document_id = self._store.resolve_code(code)
            if document_id is None:
                return SearchLawResult(
                    query=query, found=False, results=[],
                    message=f"Unknown code '{code}'. Call list_codes for the available codes.",
                )
        law_terms = law_terms_for(query)
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()

        def take(found: list[dict[str, Any]], room: int) -> None:
            for row in found:
                if len(rows) >= room:
                    return
                if row["article_id"] not in seen:
                    seen.add(row["article_id"])
                    rows.append(row)

        # The law's own terms for everyday words lead (two articles each), then
        # articles holding every word asked, then those holding only some.
        for phrase in law_terms[:MAX_LAW_TERMS]:
            take(self._store.ranked_search(phrase, limit, document_id), min(len(rows) + 2, limit))
        take(self._store.ranked_search(query, limit, document_id), limit)
        take(self._store.ranked_search(query, limit * 2, document_id, match_any=True), limit)
        hits = [self._hit(r, query) for r in rows]
        return SearchLawResult(
            query=query,
            found=bool(hits),
            results=hits,
            also_searched=law_terms[:MAX_LAW_TERMS],
            message=None if hits else (
                "No article matched. Search in Georgian, with the words the law itself "
                "would use, or use browse_code. Do not answer from memory."
            ),
        )

    def _hit(self, art: dict[str, Any], query: str) -> ArticleHit:
        number, text = self._best_paragraph(art, query)
        return ArticleHit(
            id=self._article_id(art),
            code=art["document_id"],
            code_name=art["code_name"],
            article_number=art["article_number"],
            article_title=art.get("article_title"),
            paragraph=number,
            snippet=_excerpt(text),
            is_repealed=art.get("is_repealed", False),
            source_url=self._article_url(art),
            **self._version(art),
        )

    @staticmethod
    def _best_paragraph(art: dict[str, Any], query: str) -> tuple[str | None, str]:
        """The paragraph sharing most word stems with the query."""
        stems = {_stem(w) for w in _words(query) if len(w) >= 3}
        best: tuple[int, str | None, str] = (-1, None, art["content_ka"])
        for p in art.get("paragraphs") or []:
            text = p.get("text") or ""
            lowered = text.lower()
            score = sum(1 for s in stems if s in lowered)
            if score > best[0]:
                best = (score, p.get("number"), text)
        return best[1], best[2]

    @_stamped
    def get_article(
        self, code: str, article: str, paragraph: str | None = None, as_of: str | None = None
    ) -> GetArticleResult:
        """Full exact article text with link, version and neighbouring articles.

        ``as_of`` (an ISO date before today) gives the wording of that day instead.
        """
        asked = requested_article(article)
        if asked is None:
            return GetArticleResult(found=False, message=self._unclear_article_message(article))
        article = asked
        if as_of:
            day = _iso_date(as_of)
            if day is None:
                return GetArticleResult(
                    found=False, message=f"as_of must be a date like 2025-03-01, not '{as_of}'.")
            if day < datetime.now(UTC).date().isoformat():
                return self._article_on(code, article, paragraph, day)
        art = self._lookup(code, article, paragraph)
        if art is None:
            return GetArticleResult(found=False, message=self._not_found_message(code, article))
        document_id = art["document_id"]
        prev_ref, next_ref = self._neighbours(document_id, art["article_number"])
        requested = None
        if paragraph and art.get("paragraph"):
            found = art["paragraph"]
            requested = Paragraph(number=found.get("number"), text=found["text"])
        message = None
        if paragraph and requested is None:
            message = f"Paragraph {paragraph} is not in the stored text of this article."
        return GetArticleResult(
            found=True,
            message=message,
            article=ArticleText(
                id=self._article_id(art),
                code=document_id,
                code_name=art["code_name"],
                article_number=art["article_number"],
                article_title=art.get("article_title"),
                chapter=art.get("chapter"),
                text=art["content_ka"],
                paragraphs=[
                    Paragraph(number=p.get("number"), text=p.get("text") or "")
                    for p in art.get("paragraphs") or []
                ],
                requested_paragraph=requested,
                previous_article=prev_ref,
                next_article=next_ref,
                is_repealed=art.get("is_repealed", False),
                source_url=self._article_url(art),
                **self._version(art),
            ),
        )

    def _article_on(
        self, code: str, article: str, paragraph: str | None, as_of: str
    ) -> GetArticleResult:
        """An article as it read in the consolidated version of ``as_of``."""
        document_id = self._store.resolve_code(code)
        if document_id is None:
            return GetArticleResult(found=False, message=self._not_found_message(code, article))
        if not self._history.is_available:
            return GetArticleResult(found=False, message=HISTORY_UNAVAILABLE)
        norm = _normalize_article(article)
        held = self._history.article_on(document_id, norm, as_of)
        if held is None:
            reach = self._history.reach(document_id) or {}
            start = reach.get("earliest") or "a later date"
            return GetArticleResult(found=False, message=(
                f"The stored versions of this law start on {start}"
                f"; its wording on {as_of} is not held. Do not state it from memory. Earlier "
                f"versions are listed on {self._code_url(document_id)}."
            ))
        version, art = held["version"], held["article"]
        if art is None:
            return GetArticleResult(found=False, message=(
                f"Article {article} is not in the version of this law dated "
                f"{version['version_date']} (the newest on or before {as_of}). It may have "
                f"been added later or may not exist; do not cite it for that date. "
                f"That version: {version['version_url']}"
            ))
        code_row = self._code_rows().get(document_id, {})
        replaced_on = (held["replaced_by"] or {}).get("version_date")
        note = HISTORY_NOTE.format(version_date=version["version_date"], as_of=as_of)
        if replaced_on:
            note += REPLACED_NOTE.format(replaced_on=replaced_on)
        requested = None
        message = None
        if paragraph:
            wanted = str(paragraph).strip()
            match = next(
                (p for p in art["paragraphs"] if str(p.get("number")) == wanted), None)
            if match:
                requested = Paragraph(number=match.get("number"), text=match.get("text") or "")
            else:
                message = f"Paragraph {paragraph} is not in that version of this article."
        anchor = art.get("matsne_anchor")
        gap = self._paragraph_gap(art)
        return GetArticleResult(
            found=True,
            message=message,
            article=ArticleText(
                id=f"article:{document_id}:{norm}",
                code=document_id,
                code_name=code_row.get("code_name") or document_id,
                article_number=art["article_number"],
                article_title=art.get("article_title"),
                text=art["content_ka"],
                paragraphs=[
                    Paragraph(number=p.get("number"), text=p.get("text") or "")
                    for p in art["paragraphs"]
                ],
                requested_paragraph=requested,
                is_repealed=art["is_repealed"],
                source_url=version["version_url"] + (f"#{anchor}" if anchor else ""),
                version_date=version["version_date"],
                version_note=gap,
                as_of=as_of,
                wording_from=(held["wording_from"] or {}).get("version_date"),
                replaced_on=replaced_on,
                history_note=note,
            ),
        )

    @_stamped
    def list_changes(
        self, code: str, since: str, article: str | None = None
    ) -> LawChangesResult:
        """Articles of a law that changed in versions dated on or after ``since``."""
        document_id = self._store.resolve_code(code)
        if document_id is None:
            return LawChangesResult(
                found=False, code=code,
                message=f"Unknown code '{code}'. Call list_codes for the available codes.")
        base = {"code": document_id,
                "code_name": self._code_rows().get(document_id, {}).get("code_name")}
        day = _iso_date(since)
        if day is None:
            return LawChangesResult(
                found=False, message=f"since must be a date like 2025-03-01, not '{since}'.",
                **base)
        reach = self._history.reach(document_id) if self._history.is_available else None
        if reach is None:
            return LawChangesResult(found=False, since=day, message=HISTORY_UNAVAILABLE, **base)
        norm = requested_article(article) if article else None
        if article and norm is None:
            return LawChangesResult(
                found=False, since=day, message=self._unclear_article_message(article), **base)
        found = self._history.changes(document_id, day, norm)
        notes: list[str] = []
        if day < reach["earliest"]:
            notes.append(
                f"The stored versions start on {reach['earliest']}; earlier changes are not held.")
        if not found:
            what = f"article {article}" if article else "this law"
            notes.append(f"No stored version dated on or after {day} changed {what}.")
        if len(found) > MAX_CHANGES_LISTED:
            notes.append(
                f"Showing the newest {MAX_CHANGES_LISTED} of {len(found)} changes; pass "
                "article or a later since to narrow.")
        if found:
            notes.append(
                "A version's date is the date matsne gives it; the amendment can take "
                "effect later. Call get_article with as_of to read a wording.")
        return LawChangesResult(
            found=True,
            since=day,
            history_from=reach["earliest"],
            changes=[
                LawChange(
                    article_number=c["article_number"], article_title=c["article_title"],
                    change=c["change"], version_date=c["version_date"],
                    version_url=c["version_url"],
                )
                for c in found[-MAX_CHANGES_LISTED:]
            ],
            total_changes=len(found),
            message=" ".join(notes) or None,
            **base,
        )

    def _lookup(self, code: str, article: str, paragraph: str | None) -> dict[str, Any] | None:
        """Exact article, only within a known code (never a guess across codes)."""
        asked = requested_article(article)
        if self._store.resolve_code(code) is None or asked is None:
            return None
        return self._store.get_article(code, asked, paragraph)

    @staticmethod
    def _unclear_article_message(article: str) -> str:
        return f"'{article}' is not one article number. {ARTICLE_FORMAT_HINT}"

    def _not_found_message(self, code: str, article: str) -> str:
        if self._store.resolve_code(code) is None:
            return f"Unknown code '{code}'. Call list_codes for the available codes."
        return (
            f"Article {article} is not in the stored text of '{code}'. It may not exist; do "
            "not cite it. Check the official text on matsne.gov.ge."
        )

    def _ordered_articles(self, document_id: str) -> list[ArticleRef]:
        if document_id not in self._article_order:
            self._article_order[document_id] = [
                ArticleRef(article_number=a["article_number"], article_title=a.get("article_title"))
                for a in self._store.get_code_articles(document_id)
            ]
        return self._article_order[document_id]

    def _neighbours(
        self, document_id: str, article_number: str
    ) -> tuple[ArticleRef | None, ArticleRef | None]:
        refs = self._ordered_articles(document_id)
        for i, ref in enumerate(refs):
            if ref.article_number == article_number:
                prev_ref = refs[i - 1] if i > 0 else None
                next_ref = refs[i + 1] if i + 1 < len(refs) else None
                return prev_ref, next_ref
        return None, None

    @_stamped
    def browse_code(
        self, code: str, chapter: str | None = None, offset: int = 0, limit: int = 200
    ) -> CodeStructure:
        """Chapters of a code, or the article list (numbers and titles) of one chapter."""
        document_id = self._store.resolve_code(code)
        if document_id is None:
            return CodeStructure(
                found=False, code=code, source_url="https://matsne.gov.ge",
                message=f"Unknown code '{code}'. Call list_codes for the available codes.",
            )
        row = self._code_rows().get(document_id, {})
        version_date = _first_present(row, CODE_VERSION_COLUMNS)
        base = {
            "found": True,
            "code": document_id,
            "code_name": row.get("code_name"),
            "source_url": self._code_url(document_id),
            "version_date": version_date,
            "version_note": None if version_date else VERSION_UNKNOWN_NOTE,
        }
        articles = self._store.get_code_articles(document_id, chapter)
        chapters = self._chapters(articles) if not chapter else []
        if chapters:
            return CodeStructure(chapters=chapters, total_articles=len(articles), **base)
        limit = max(1, min(limit, MAX_BROWSE_LIMIT))
        page = articles[offset: offset + limit]
        message = None
        if offset + limit < len(articles):
            message = (
                f"Showing {len(page)} of {len(articles)}; "
                f"call again with offset={offset + limit}."
            )
        if not articles:
            message = f"No articles found in chapter '{chapter}'."
        return CodeStructure(
            articles=[
                ArticleRef(article_number=a["article_number"], article_title=a.get("article_title"))
                for a in page
            ],
            total_articles=len(articles),
            offset=offset,
            message=message,
            **base,
        )

    @staticmethod
    def _chapters(articles: list[dict[str, Any]]) -> list[ChapterSummary]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for a in articles:
            if a.get("chapter"):
                grouped.setdefault(a["chapter"], []).append(a)
        return [
            ChapterSummary(
                chapter=name,
                article_count=len(items),
                first_article=items[0]["article_number"],
                last_article=items[-1]["article_number"],
            )
            for name, items in grouped.items()
        ]

    @_stamped
    def verify_citation(
        self, code: str, article: str, claim: str, paragraph: str | None = None,
        quote: str | None = None,
    ) -> VerifyCitationResult:
        """Does the cited article exist, what does it say, and is a quote from it exact."""
        base = {"code": code, "article": article, "claim": claim, "paragraph_requested": paragraph}
        if requested_article(article) is None:
            return VerifyCitationResult(
                exists=False, message=self._unclear_article_message(article), **base)
        art = self._lookup(code, article, paragraph)
        if art is None:
            return VerifyCitationResult(
                exists=False, message=self._not_found_message(code, article), **base
            )
        text = art["content_ka"]
        paragraph_exists = None
        if paragraph:
            paragraph_exists = art.get("paragraph") is not None
            if paragraph_exists:
                text = art["paragraph"]["text"]
        message = "The article exists. Compare the claim with the text before relying on it."
        if art.get("is_repealed"):
            message = "The article is repealed (ამოღებულია). Do not rely on it as current law."
        elif paragraph and not paragraph_exists:
            message = f"The article exists, but paragraph {paragraph} is not in its stored text."
        return VerifyCitationResult(
            exists=True,
            paragraph_exists=paragraph_exists,
            is_repealed=art.get("is_repealed", False),
            article_number=art["article_number"],
            article_title=art.get("article_title"),
            text=text,
            source_url=self._article_url(art),
            lexical_check=self._lexical_check(claim, text),
            quote_check=self._quote_check(quote, art["content_ka"]) if quote else None,
            message=message,
            **self._version(art),
            **base,
        )

    @staticmethod
    def _quote_check(quote: str, text: str) -> QuoteCheck:
        """Is ``quote`` in the article word for word (parts joined by … in order)."""
        haystack = _flat(text)
        position = 0
        parts = [p for p in (_flat(part).strip(' "') for part in _ELLIPSIS.split(quote)) if p]
        for part in parts:
            position = haystack.find(part, position)
            if position < 0:
                return QuoteCheck(verbatim=False, note=(
                    "These words are not in the stored article as quoted. Do not present "
                    "them as a quotation; copy the wording from the text field instead."
                ))
            position += len(part)
        if not parts:
            return QuoteCheck(verbatim=False, note="The quote is empty.")
        return QuoteCheck(verbatim=True, note="The quote is in the stored article word for word.")

    @staticmethod
    def _lexical_check(claim: str, text: str) -> LexicalCheck:
        claim_numbers = list(dict.fromkeys(_NUMBER.findall(claim)))
        text_numbers = set(_NUMBER.findall(text))
        terms = {_stem(w) for w in _words(claim) if len(w) >= 4 and not w.isdigit()}
        lowered = text.lower()
        return LexicalCheck(
            numbers_in_claim=claim_numbers,
            numbers_found_in_text=[n for n in claim_numbers if n in text_numbers],
            numbers_not_in_text=[n for n in claim_numbers if n not in text_numbers],
            claim_terms_found=sum(1 for t in terms if t in lowered),
            claim_terms_total=len(terms),
        )

    # ── Court practice ───────────────────────────────────────

    @_stamped
    def find_court_practice(
        self, query: str, limit: int = 5, court: str | None = None
    ) -> CourtPracticeResult:
        """Real decisions whose text contains the query's key words, one entry per case.

        ``court`` ("supreme" or "constitutional") keeps the search to one court.
        """
        limit = max(1, min(limit, 10))
        if not self._court.is_available:
            return CourtPracticeResult(
                query=query, status="source_unavailable", results=[],
                message=(
                    "Court decisions are not available on this server. Say that no court "
                    "practice was checked; do not cite or describe any decision."
                ),
            )
        wanted = COURT_FILTERS.get(court) if court else None
        reach = {
            COURT_NAMES.get(row["collection"], row["collection"]): row["latest"]
            for row in self._court.summary()
            if row["latest"] and (wanted is None or row["collection"] in wanted)
        }
        through = max(reach.values()) if reach else None
        if wanted and not reach:
            return CourtPracticeResult(
                query=query, status="none_found", results=[],
                message=(
                    "No decisions of that court are held. Say so plainly; do not describe "
                    "its practice or invent case numbers."
                ),
            )
        decisions = [self._to_decision(row) for row in self._court.search(query, limit, wanted)]
        if not decisions:
            return CourtPracticeResult(
                query=query, status="none_found", results=[], decisions_through=through,
                decisions_through_by_court=reach,
                message=(
                    "No court decision matched. Say so plainly; do not mention court practice "
                    "or invent case numbers."
                ),
            )
        return CourtPracticeResult(
            query=query, status="found", results=decisions, decisions_through=through,
            decisions_through_by_court=reach,
            message=(
                "Quote only what the snippets say; cite the case number given and name the "
                "court that decided."
            ),
        )

    @staticmethod
    def _same_court(collection: str) -> tuple[str, ...]:
        """The collections that hold the same court's decisions as ``collection``."""
        return next((c for c in COURT_FILTERS.values() if collection in c), (collection,))

    @staticmethod
    def _to_decision(row: dict[str, Any]) -> CourtDecision:
        """A court store row as a sourced decision; the snippet is one whole passage."""
        url = row.get("source_url")
        return CourtDecision(
            id=row["decision_id"],
            case_number=row["case_number"],
            court=COURT_NAMES[row["collection"]],
            collection=row["collection"],
            date=row.get("decision_date"),
            year=row.get("year"),
            category=row.get("category"),
            decision_type=row.get("decision_type"),
            passage=row.get("passage_seq"),
            snippet=row.get("passage") or "",
            source_url=url or None,
            link_note=None if url else COURT_LINK_NOTE.format(
                site=COURT_SITE_URLS[row["collection"]].removeprefix("https://www.")),
            names_note=(
                COURT_NAMES_NOTE if row["collection"] == CONSTITUTIONAL_COLLECTION else None),
        )

    @_stamped
    def get_court_decision(self, id: str, from_passage: int = 0) -> CourtDecisionText:
        """A stored decision's own text, a run of passages at a time.

        ``id`` is a decision id from find_court_practice or a printed case number.
        """
        key, _, anchor = id.strip().partition("@")
        if from_passage == 0 and anchor.isdigit():
            from_passage = int(anchor)
        row = self._court.get_decision(key) if key.startswith("case:") else None
        others: list[str] = []
        if row is None and key and not key.startswith("case:"):
            matches = self._court.find_by_case_number(key)
            row = matches[0] if matches else None
            others = [m["decision_id"] for m in matches[1:]]
        if row is None:
            return CourtDecisionText(found=False, message=(
                f"No stored decision has the id or case number '{id}'. Do not describe or "
                "cite it; use an id returned by find_court_practice."
            ))
        total = row["passage_count"]
        first = max(0, min(from_passage, total - 1))
        texts = self._court.get_passages(
            row["decision_id"], offset=first, limit=DECISION_PASSAGES_PER_CALL)
        end = first + len(texts)
        notes: list[str] = []
        if end < total:
            notes.append(
                f"Passages {first}-{end - 1} of 0-{total - 1}. Call again with "
                f"from_passage={end} to read on; do not describe parts you have not read.")
        if others:
            notes.append("Other stored decisions print the same case number: " + ", ".join(others))
        return CourtDecisionText(
            found=True,
            decision=self._to_decision(row),
            passages=[NumberedPassage(number=first + i, text=t) for i, t in enumerate(texts)],
            total_passages=total,
            next_passage=end if end < total else None,
            law_since_decision=self._law_since_decision(row),
            message=" ".join(notes) or None,
        )

    def _law_since_decision(self, row: dict[str, Any]) -> LawSinceDecision | None:
        """The stored articles a decision cites and whether each changed after it."""
        decided = _iso_date(row.get("decision_date"))
        if decided is None or not self._history.is_available:
            return None
        text = "\n".join(self._court.get_passages(
            row["decision_id"], offset=0, limit=row["passage_count"]))
        day_after = (date.fromisoformat(decided) + timedelta(days=1)).isoformat()
        names = self._code_rows()
        found: list[CitedLawArticle] = []
        for cited in cited_articles(text, row.get("category")):
            reach = self._history.reach(cited.code)
            if reach is None:
                continue
            checked_from = max(decided, reach["earliest"])
            then = self._history.article_on(cited.code, cited.article_norm, checked_from)
            if then is None or then["article"] is None:
                continue  # not in the law at that time: a misread reference, left out
            changes = self._history.changes(cited.code, day_after, cited.article_norm)
            now = self._store.get_article(cited.code, cited.article_norm, None)
            if changes:
                status = "changed"
            else:
                status = "unchanged" if checked_from == decided else "unknown"
            found.append(CitedLawArticle(
                code=cited.code,
                code_name=names.get(cited.code, {}).get("code_name"),
                article_number=then["article"]["article_number"],
                mentions=cited.mentions,
                status=status,
                changed_on=sorted({c["version_date"] for c in changes}),
                checked_from=checked_from,
                repealed_now=now is None or bool(now.get("is_repealed")),
            ))
        if not found:
            return None
        return LawSinceDecision(
            decision_date=decided, articles=found,
            message=LAW_SINCE_DECISION_NOTE.format(decision_date=decided))

    # ── What is held, and where to get help ──────────────────

    @_stamped
    def get_coverage(self) -> CoverageResult:
        """The laws and court decisions held, how far back, and what is not held."""
        history = {h["document_id"]: h for h in self._history.coverage()}
        laws = [
            LawCoverage(
                code=document_id,
                name=row["code_name"],
                article_count=row.get("article_count") or 0,
                version_date=_first_present(row, CODE_VERSION_COLUMNS),
                source_url=self._code_url(document_id),
                history_from=history.get(document_id, {}).get("earliest"),
                history_versions=history.get(document_id, {}).get("versions", 0),
            )
            for document_id, row in sorted(self._code_rows().items())
        ]
        courts = [
            CourtCoverage(
                court=COURT_NAMES.get(row["collection"], row["collection"]),
                collection=row["collection"],
                decision_count=row["decision_count"],
                earliest=row["earliest"],
                latest=row["latest"],
            )
            for row in self._court.summary()
        ]
        not_covered = list(NOT_COVERED)
        if any(c.collection == CONSTITUTIONAL_COLLECTION for c in courts):
            not_covered[not_covered.index(CONSTITUTIONAL_NOT_HELD)] = CONSTITUTIONAL_HELD_NOTE
        return CoverageResult(laws=laws, court_decisions=courts, not_covered=not_covered,
                              how_data_is_kept=self._data_sources(laws, courts))

    def _data_sources(
        self, laws: list[LawCoverage], courts: list[CourtCoverage]
    ) -> list[DataSourceNote]:
        """How each kind of data held is collected and kept current, with its last date."""
        confirmed = self._status.current().current_as_of
        notes = [DataSourceNote(**DATA_SOURCES["laws"], last_updated=confirmed)]
        if any(law.history_from for law in laws):
            notes.append(DataSourceNote(**DATA_SOURCES["history"], last_updated=confirmed))
        held = {court.collection for court in courts}
        built = self._court.built_on()
        if held & {"court_practice", "grand_chamber"}:
            notes.append(DataSourceNote(**DATA_SOURCES["court_practice"], last_updated=built))
        if CONSTITUTIONAL_COLLECTION in held:
            notes.append(DataSourceNote(**DATA_SOURCES[CONSTITUTIONAL_COLLECTION],
                                        last_updated=built))
        return notes

    def legal_aid(self) -> LegalAidResult:
        """Where a person in Georgia can get free legal help."""
        return LegalAidResult(
            providers=[LegalAidProvider(**p) for p in LEGAL_AID_PROVIDERS],
            emergency=LEGAL_AID_EMERGENCY,
            checked_on=LEGAL_AID_CHECKED_ON,
            message=LEGAL_AID_MESSAGE,
        )

    # ── ChatGPT search / fetch pair ──────────────────────────

    @_stamped
    def search(self, query: str) -> SearchResults:
        """ChatGPT-compatible search: ids, titles and links of articles and decisions."""
        items = [
            SearchResultItem(
                id=hit.id,
                title=f"{hit.code_name}, {hit.article_number}"
                      + (f" — {hit.article_title}" if hit.article_title else ""),
                url=hit.source_url,
            )
            for hit in self.search_law(query, limit=8).results
        ]
        for decision in self.find_court_practice(query, limit=3).results:
            items.append(SearchResultItem(
                # "@<passage>" lets fetch open the decision where the match is.
                id=f"{decision.id}@{decision.passage}",
                title=f"{decision.court}, საქმე {decision.case_number}",
                url=decision.source_url or COURT_SITE_URLS[decision.collection],
            ))
        return SearchResults(results=items)

    @_stamped
    def fetch(self, id: str) -> FetchResult | None:
        """ChatGPT-compatible fetch: the full text behind a search result id."""
        kind, _, rest = id.partition(":")
        if kind == "article":
            code, _, article = rest.rpartition(":")
            result = self.get_article(code, article).article
            if result is None:
                return None
            return FetchResult(
                id=result.id,
                title=f"{result.code_name}, {result.article_number}"
                      + (f" — {result.article_title}" if result.article_title else ""),
                text=result.text,
                url=result.source_url,
                metadata={
                    k: v for k, v in {
                        "version_date": result.version_date,
                        "in_force_since": result.in_force_since,
                        "version_note": result.version_note,
                        "notice": result.notice,
                    }.items() if v
                },
            )
        if kind == "case":
            return self._fetch_case(rest)
        return None

    def _fetch_case(self, rest: str) -> FetchResult | None:
        """Part of a decision: its opening, or the passages around ``@<passage>``."""
        decision_key, _, anchor = rest.partition("@")
        row = self._court.get_decision(f"case:{decision_key}")
        if row is None:
            return None
        total = row["passage_count"]
        first = 0
        if anchor.isdigit():
            first = max(0, min(int(anchor), total - 1) - FETCH_PASSAGES_BEFORE)
        passages = self._court.get_passages(row["decision_id"], offset=first, limit=FETCH_PASSAGES)
        last = first + len(passages) - 1
        decision = self._to_decision(row)
        part_note = None
        if len(passages) < total:
            part_note = (
                f"This is part of the decision: passages {first}-{last} of 0-{total - 1}. "
                "Do not describe the parts you have not read."
            )
        return FetchResult(
            id=decision.id,
            title=f"{decision.court}, საქმე {decision.case_number}",
            text="\n\n".join(passages),
            url=decision.source_url or COURT_SITE_URLS[decision.collection],
            metadata={
                k: v for k, v in {
                    "date": decision.date,
                    "year": decision.year,
                    "decision_type": decision.decision_type,
                    "decisions_through": self._court.latest_decision_date(
                        self._same_court(decision.collection)),
                    "part_note": part_note,
                    "link_note": decision.link_note,
                    "names_note": decision.names_note,
                    "notice": decision.notice,
                }.items() if v
            },
        )


_connector_service: LawConnectorService | None = None


def get_law_connector_service() -> LawConnectorService:
    """The shared service, on the connector's own data folder when one is configured."""
    global _connector_service
    if _connector_service is None:
        store = None
        if settings.connector_data_dir is not None:
            store = ArticleStoreService(settings.connector_data_dir / ARTICLE_STORE_FILE)
        _connector_service = LawConnectorService(store=store)
    return _connector_service
