"""
Law connector REST mirror — the MCP tools as plain HTTP, for custom GPT Actions.

Same operations, same service, same responses as the MCP server. The
OpenAPI 3.1 document a GPT Action imports is served at
/api/v1/connector/openapi.json and contains only these operations.

Also the public coverage page at /coverage: what the connector holds, for a
person to read in a browser.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse

from app.config.settings import settings
from app.schemas.connector_schema import (
    MAX_ARTICLE_CHARS,
    MAX_CHAPTER_CHARS,
    MAX_CODE_CHARS,
    MAX_DATE_CHARS,
    MAX_ID_CHARS,
    MAX_QUERY_CHARS,
    CodeList,
    CodeStructure,
    CourtDecisionText,
    CourtName,
    CourtPracticeResult,
    CoverageResult,
    GetArticleResult,
    LawChangesResult,
    LegalAidResult,
    SearchLawResult,
    VerifyCitationRequest,
    VerifyCitationResult,
)
from app.services.connector_coverage_page import PAGE_HEADERS, render_coverage_page
from app.services.law_connector_service import get_law_connector_service

router = APIRouter(prefix="/api/v1/connector", tags=["law connector"])
page_router = APIRouter()
COVERAGE_PAGE_PATH = "/coverage"

OPENAPI_TITLE = "Fuzzzy Law — Georgian law sources"
OPENAPI_VERSION = "1.1.0"
OPENAPI_DESCRIPTION = (
    "Exact texts of Georgian laws with official matsne.gov.ge links and version dates, "
    "their earlier wordings, and published court decisions. Sources only: legal "
    "information, not legal advice."
)

CodeQuery = Annotated[str, Query(
    max_length=MAX_CODE_CHARS,
    description="Code id from listCodes (e.g. civil_code) or its Georgian name."
)]
ArticleQuery = Annotated[str, Query(
    max_length=MAX_ARTICLE_CHARS, description="Article number, e.g. 369 or 166¹."
)]


@router.get("/codes", operation_id="listCodes", summary="List available Georgian codes")
async def list_codes() -> CodeList:
    """Codes with article counts, official links and version dates."""
    return get_law_connector_service().list_codes()


@router.get("/search", operation_id="searchLaw", summary="Search Georgian law articles")
async def search_law(
    query: Annotated[str, Query(
        min_length=1, max_length=MAX_QUERY_CHARS,
        description="What to look for, best in Georgian legal terms.",
    )],
    code: Annotated[str | None, Query(
        max_length=MAX_CODE_CHARS, description="Optional: limit to one code."
    )] = None,
    limit: Annotated[int, Query(ge=1, le=25, description="How many articles.")] = 8,
) -> SearchLawResult:
    """Matching articles with exact snippet, link and version date.

    found=false means nothing matched.
    """
    return get_law_connector_service().search_law(query, code, limit)


@router.get("/articles", operation_id="getArticle", summary="Get one article's full text")
async def get_article(
    code: CodeQuery,
    article: ArticleQuery,
    paragraph: Annotated[str | None, Query(
        max_length=MAX_ARTICLE_CHARS, description="Optional paragraph number."
    )] = None,
    as_of: Annotated[str | None, Query(
        max_length=MAX_DATE_CHARS,
        description=(
            "Optional date (YYYY-MM-DD): the newest matsne version dated on or before that day."
        ),
    )] = None,
) -> GetArticleResult:
    """Full exact text, paragraphs, link, version date and neighbouring articles.

    Use it to check deadlines. With as_of, the wording of an earlier day.
    """
    return get_law_connector_service().get_article(code, article, paragraph, as_of)


@router.get("/changes", operation_id="listChanges", summary="List what changed in a law")
async def list_changes(
    code: CodeQuery,
    since: Annotated[str, Query(
        max_length=MAX_DATE_CHARS, description="Date (YYYY-MM-DD) to list changes from."
    )],
    article: Annotated[str | None, Query(
        max_length=MAX_ARTICLE_CHARS, description="Optional: only this article."
    )] = None,
) -> LawChangesResult:
    """Articles amended, added or removed since a date, with a link to each version."""
    return get_law_connector_service().list_changes(code, since, article)


@router.get("/structure", operation_id="browseCode", summary="Show a code's chapters or articles")
async def browse_code(
    code: CodeQuery,
    chapter: Annotated[str | None, Query(
        max_length=MAX_CHAPTER_CHARS, description="Optional chapter to list."
    )] = None,
    offset: Annotated[int, Query(ge=0, description="Paging offset.")] = 0,
    limit: Annotated[int, Query(ge=1, le=300, description="Articles per page.")] = 200,
) -> CodeStructure:
    """Chapters of a code, or article numbers and titles."""
    return get_law_connector_service().browse_code(code, chapter, offset, limit)


@router.get(
    "/court-practice", operation_id="findCourtPractice", summary="Find real court decisions"
)
async def find_court_practice(
    query: Annotated[str, Query(
        min_length=1, max_length=MAX_QUERY_CHARS, description="Legal issue in Georgian."
    )],
    limit: Annotated[int, Query(ge=1, le=10, description="How many decisions.")] = 5,
    court: Annotated[CourtName | None, Query(
        description="Optional: only this court, supreme or constitutional."
    )] = None,
) -> CourtPracticeResult:
    """Court decisions with case number, court, date and snippet.

    none_found means do not mention court practice.
    """
    return get_law_connector_service().find_court_practice(query, limit, court)


@router.get(
    "/court-decision", operation_id="getCourtDecision", summary="Read a court decision in full"
)
async def get_court_decision(
    id: Annotated[str, Query(
        min_length=1, max_length=MAX_ID_CHARS,
        description="Decision id from findCourtPractice, or a printed case number.",
    )],
    from_passage: Annotated[int, Query(ge=0, description="Passage to start from.")] = 0,
) -> CourtDecisionText:
    """A stored decision's own text, twenty passages per call, as the court published it."""
    return get_law_connector_service().get_court_decision(id, from_passage)


@router.post("/verify-citation", operation_id="verifyCitation", summary="Check a law citation")
async def verify_citation(body: VerifyCitationRequest) -> VerifyCitationResult:
    """Whether the article exists and what it says; with quote, whether the quote is exact."""
    return get_law_connector_service().verify_citation(
        body.code, body.article, body.claim, body.paragraph, body.quote
    )


@router.get("/coverage", operation_id="getCoverage", summary="What the service holds")
async def get_coverage() -> CoverageResult:
    """The laws and court decisions held, their dates, and what is not held."""
    return get_law_connector_service().get_coverage()


@router.get("/legal-aid", operation_id="findLegalAid", summary="Where to get free legal help")
async def find_legal_aid() -> LegalAidResult:
    """Free legal help in Georgia: who, for whom, phone, hours and website."""
    return get_law_connector_service().legal_aid()


def connector_openapi() -> dict:
    """OpenAPI 3.1 document of the connector operations only (for a GPT Action)."""
    return get_openapi(
        title=OPENAPI_TITLE,
        version=OPENAPI_VERSION,
        description=OPENAPI_DESCRIPTION,
        routes=router.routes,
        servers=[{"url": settings.connector_public_base_url.rstrip("/")}],
    )


@router.get("/openapi.json", include_in_schema=False)
async def openapi_document() -> dict:
    return connector_openapi()


@page_router.get(COVERAGE_PAGE_PATH, include_in_schema=False)
async def coverage_page() -> HTMLResponse:
    """What the connector holds, as a web page for people."""
    service = get_law_connector_service()
    page = render_coverage_page(
        service.get_coverage(), service.legal_aid(), settings.connector_public_base_url
    )
    return HTMLResponse(page, headers=PAGE_HEADERS)
