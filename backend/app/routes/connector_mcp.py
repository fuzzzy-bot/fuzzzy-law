"""
Law connector MCP server — "Fuzzzy Law — Georgian law sources".

A remote MCP server (Streamable HTTP at /mcp) that ChatGPT, Claude and other
agents add as a connector. Every tool is read-only and returns sources only:
exact law text, its official matsne.gov.ge link and version date. The user's
own AI writes the answer. Tools are thin: the logic is in
``LawConnectorService``, shared with the REST mirror. Besides the tools the
server offers ready-made prompts and three read-only resources (what is held,
the answer rules, free legal help); their wording is in ``connector_guidance``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from pydantic import BeforeValidator, Field
from starlette.applications import Starlette

from app.config.settings import settings
from app.middleware.connector_access_middleware import ConnectorAccessMiddleware
from app.routes import connector_router
from app.schemas.connector_schema import (
    MAX_ARTICLE_CHARS,
    MAX_CHAPTER_CHARS,
    MAX_CLAIM_CHARS,
    MAX_CODE_CHARS,
    MAX_DATE_CHARS,
    MAX_ID_CHARS,
    MAX_QUERY_CHARS,
    MAX_QUOTE_CHARS,
    CodeList,
    CodeStructure,
    CourtDecisionText,
    CourtName,
    CourtPracticeResult,
    CoverageResult,
    FetchResult,
    GetArticleResult,
    LawChangesResult,
    LegalAidResult,
    SearchLawResult,
    SearchResults,
    VerifyCitationResult,
)
from app.services.connector_guidance import (
    ANSWER_RULES,
    PROMPTS,
    SERVER_INSTRUCTIONS,
    render_prompt,
)
from app.services.law_connector_service import LawConnectorService, get_law_connector_service

SERVER_NAME = "fuzzzy-law"
SERVER_TITLE = "Fuzzzy Law — Georgian law sources"
SERVER_VERSION = "1.1.0"
MAX_SITUATION_CHARS = 6000
READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)

# Tool descriptions, English then Georgian: the caller's AI reads them to
# decide when to call a tool, and users see them when adding the connector.
TOOL_DESCRIPTIONS = {
    "list_codes": (
        "List the Georgian codes available, with article counts, official links and "
        "version dates. ხელმისაწვდომი კოდექსების სია: მუხლების რაოდენობა, ოფიციალური "
        "ბმული და ვერსიის თარიღი."
    ),
    "search_law": (
        "Search Georgian law articles by words. Search in Georgian, with the terms the law "
        "itself uses. Returns matching articles with an exact text snippet, code, article "
        "number, official matsne.gov.ge link and version date. found=false means nothing "
        "matched: say so, never guess. კანონის მუხლების ძიება სიტყვებით: ზუსტი ამონარიდი, "
        "კოდექსი, მუხლის ნომერი, ოფიციალური ბმული და თარიღი."
    ),
    "get_article": (
        "Get the full exact text of one article, with its paragraphs, official link, "
        "version date and the previous and next article. Use it to check deadlines, "
        "amounts and ages before stating them. Pass as_of (a date) to read the wording "
        "that stood on that day. ერთი მუხლის სრული ზუსტი ტექსტი, ოფიციალური ბმული და "
        "რედაქციის თარიღი; as_of თარიღით მიიღებ იმ დღის რედაქციას."
    ),
    "list_changes": (
        "List the articles of a law that were amended, added or removed since a date, by "
        "consolidated version on matsne.gov.ge, with a link to each version. Use it to see "
        "whether a rule was different when the events happened. კანონის ცვლილებები "
        "მითითებული თარიღიდან: რომელი მუხლი შეიცვალა, დაემატა ან ამოიღეს და რომელ რედაქციაში."
    ),
    "browse_code": (
        "Show a code's structure: its chapters, or the article numbers and titles of one "
        "chapter. კოდექსის სტრუქტურა: თავები ან ერთი თავის მუხლების ნომრები და სათაურები."
    ),
    "find_court_practice": (
        "Find real decisions of Georgian courts on an issue: case number, court, date, "
        "exact snippet and link when stored. get_coverage lists the courts held; pass court "
        "to search one of them only. status none_found or source_unavailable means you "
        "must not mention court practice. სასამართლო პრაქტიკა: რეალური "
        "გადაწყვეტილებები, საქმის ნომერი, თარიღი."
    ),
    "get_court_decision": (
        "Read a stored court decision in full, twenty passages per call, by the id from "
        "find_court_practice or its printed case number. Read it before you describe what "
        "the court decided. The text is as the court published it: the Supreme Court prints "
        "parties as initials, the Constitutional Court prints their names. გადაწყვეტილების "
        "სრული ტექსტი ნაწილ-ნაწილ, იმ სახით, როგორც სასამართლომ გამოაქვეყნა."
    ),
    "verify_citation": (
        "Check a citation: does the article (and paragraph) exist, is it repealed, and what "
        "does it actually say. Pass quote to check a quotation word for word. Includes a "
        "word-and-number overlap check, not a legal judgement. ციტატის შემოწმება: არსებობს "
        "თუ არა მუხლი, რას ამბობს სინამდვილეში და ზუსტია თუ არა მოყვანილი ციტატა."
    ),
    "get_coverage": (
        "What this service holds: the laws with their version dates and how far back their "
        "earlier wordings go, the court decisions and their date range, and what is not "
        "held. Call it when unsure whether a topic is covered. რა ინახება სერვისში: "
        "კანონები და მათი რედაქციების თარიღები, სასამართლო გადაწყვეტილებები და ის, რაც "
        "არ ინახება."
    ),
    "find_legal_aid": (
        "Where a person in Georgia can get free legal help: the state Legal Aid Service, the "
        "Public Defender and others, with phone, hours and website. Give these when the "
        "matter is serious, a deadline is running or the person cannot pay a lawyer. სად "
        "მიიღებს ადამიანი უფასო იურიდიულ დახმარებას საქართველოში: ტელეფონი, სამუშაო "
        "საათები და ვებგვერდი."
    ),
    "search": (
        "Search Georgian law articles and court decisions. Returns ids, titles and official "
        "links; call fetch with an id for the full text. კანონებისა და გადაწყვეტილებების "
        "ძიება."
    ),
    "fetch": (
        "Fetch the full text, official link and version details behind a search result id. "
        "ძიების შედეგის სრული ტექსტი და ოფიციალური ბმული."
    ),
}

RESOURCE_COVERAGE = "fuzzzy-law://coverage"
RESOURCE_ANSWER_RULES = "fuzzzy-law://answer-rules"
RESOURCE_LEGAL_AID = "fuzzzy-law://legal-aid"


def _number_as_text(value: Any) -> Any:
    """An article or paragraph sent as a number (47) read as the text "47"."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value) if isinstance(value, int | float) else value


NumberAsText = BeforeValidator(_number_as_text)

CodeArg = Annotated[str, Field(max_length=MAX_CODE_CHARS, description=(
    "Code id from list_codes (e.g. civil_code, labour_code) or its Georgian name "
    "(e.g. შრომის კოდექსი)."
))]
ArticleArg = Annotated[str, NumberAsText, Field(
    max_length=MAX_ARTICLE_CHARS, description=(
        "Article number as printed, e.g. 369, 48 or 166¹ (166-1 also works). A paragraph goes "
        "in its own argument. Check that article_number in the reply is the one you asked for.")
)]
OptionalArticle = Annotated[str | None, NumberAsText, Field(
    max_length=MAX_ARTICLE_CHARS, description="Optional: only this article, e.g. 47."
)]
DateArg = Annotated[str, Field(
    max_length=MAX_DATE_CHARS, description="A date as YYYY-MM-DD, e.g. 2025-03-01."
)]
OptionalDate = Annotated[str | None, Field(max_length=MAX_DATE_CHARS, description=(
    "Optional date as YYYY-MM-DD: return the wording that stood on that day instead of "
    "the current one."
))]
SituationArg = Annotated[str, Field(
    max_length=MAX_SITUATION_CHARS, description="What happened, in your own words."
)]
QueryArg = Annotated[str, Field(max_length=MAX_QUERY_CHARS, description=(
    "What to look for, best in Georgian legal terms, e.g. 'სააპელაციო საჩივრის ვადა'."
))]
OptionalCode = Annotated[str | None, Field(
    max_length=MAX_CODE_CHARS, description="Optional: limit to one code (id or name)."
)]
OptionalParagraph = Annotated[str | None, NumberAsText, Field(
    max_length=MAX_ARTICLE_CHARS, description="Optional paragraph number, e.g. 1."
)]
OptionalChapter = Annotated[str | None, Field(
    max_length=MAX_CHAPTER_CHARS, description="Optional chapter to list articles of."
)]


def build_connector_mcp_server(service: LawConnectorService | None = None) -> MCPServer:
    """A fresh MCP server instance (one per app: its session manager runs once)."""
    mcp = MCPServer(
        name=SERVER_NAME,
        title=SERVER_TITLE,
        description="Exact Georgian law texts with official links, for grounded answers.",
        instructions=SERVER_INSTRUCTIONS,
        website_url="https://matsne.gov.ge",
        version=SERVER_VERSION,
    )

    def svc() -> LawConnectorService:
        return service or get_law_connector_service()

    def tool(name: str):
        return mcp.tool(name=name, description=TOOL_DESCRIPTIONS[name], annotations=READ_ONLY)

    @tool("list_codes")
    def list_codes() -> CodeList:
        return svc().list_codes()

    @tool("search_law")
    def search_law(
        query: QueryArg,
        code: OptionalCode = None,
        limit: Annotated[int, Field(ge=1, le=25, description="How many articles.")] = 8,
    ) -> SearchLawResult:
        return svc().search_law(query, code, limit)

    @tool("get_article")
    def get_article(
        code: CodeArg,
        article: ArticleArg,
        paragraph: OptionalParagraph = None,
        as_of: OptionalDate = None,
    ) -> GetArticleResult:
        return svc().get_article(code, article, paragraph, as_of)

    @tool("list_changes")
    def list_changes(
        code: CodeArg,
        since: DateArg,
        article: OptionalArticle = None,
    ) -> LawChangesResult:
        return svc().list_changes(code, since, article)

    @tool("browse_code")
    def browse_code(
        code: CodeArg,
        chapter: OptionalChapter = None,
        offset: Annotated[int, Field(ge=0, description="Skip this many articles.")] = 0,
        limit: Annotated[int, Field(ge=1, le=300, description="Articles per page.")] = 200,
    ) -> CodeStructure:
        return svc().browse_code(code, chapter, offset, limit)

    @tool("find_court_practice")
    def find_court_practice(
        query: QueryArg,
        limit: Annotated[int, Field(ge=1, le=10, description="How many decisions.")] = 5,
        court: Annotated[CourtName | None, Field(description=(
            "Optional: search only the Supreme Court (supreme) or only the Constitutional "
            "Court (constitutional)."
        ))] = None,
    ) -> CourtPracticeResult:
        return svc().find_court_practice(query, limit, court)

    @tool("get_court_decision")
    def get_court_decision(
        id: Annotated[str, Field(max_length=MAX_ID_CHARS, description=(
            "A decision id from find_court_practice (case:court_practice:ას-398-398-2018) "
            "or a printed case number (ას-398-398-2018, or 3/1/1459 for a Constitutional "
            "Court judgment)."
        ))],
        from_passage: Annotated[int, Field(
            ge=0, description="Passage to start from; use next_passage to read on."
        )] = 0,
    ) -> CourtDecisionText:
        return svc().get_court_decision(id, from_passage)

    @tool("verify_citation")
    def verify_citation(
        code: CodeArg,
        article: ArticleArg,
        claim: Annotated[str, Field(
            max_length=MAX_CLAIM_CHARS, description="What your answer says this article provides."
        )],
        paragraph: OptionalParagraph = None,
        quote: Annotated[str | None, Field(max_length=MAX_QUOTE_CHARS, description=(
            "Optional: words you quote from the article, to check they are in it word for "
            "word. Join left-out parts with …"
        ))] = None,
    ) -> VerifyCitationResult:
        return svc().verify_citation(code, article, claim, paragraph, quote)

    @tool("get_coverage")
    def get_coverage() -> CoverageResult:
        return svc().get_coverage()

    @tool("find_legal_aid")
    def find_legal_aid() -> LegalAidResult:
        return svc().legal_aid()

    @tool("search")
    def search(query: QueryArg) -> SearchResults:
        return svc().search(query)

    @tool("fetch")
    def fetch(
        id: Annotated[str, Field(
            max_length=MAX_ID_CHARS, description="An id from search, e.g. article:civil_code:138."
        )],
    ) -> FetchResult:
        result = svc().fetch(id)
        if result is None:
            raise ValueError(f"No document with id '{id}'. Use an id returned by search.")
        return result

    # ── Ready-made prompts ───────────────────────────────────
    def prompt(name: str):
        text = PROMPTS[name]
        return mcp.prompt(name=name, title=text.title, description=text.description)

    @prompt("intake")
    def intake(situation: SituationArg) -> str:
        return render_prompt("intake", situation=situation)

    @prompt("case_analysis")
    def case_analysis(situation: SituationArg) -> str:
        return render_prompt("case_analysis", situation=situation)

    @prompt("document_drafting")
    def document_drafting(
        document: Annotated[str, Field(max_length=MAX_CHAPTER_CHARS, description=(
            "The document you need, e.g. a claim to court, a complaint to an employer."
        ))],
        situation: SituationArg,
    ) -> str:
        return render_prompt("document_drafting", document=document, situation=situation)

    @prompt("deadline_check")
    def deadline_check(
        situation: SituationArg,
        event_date: Annotated[str, Field(max_length=40, description=(
            "The day it happened or the document reached you, e.g. 2026-10-02."
        ))] = "",
    ) -> str:
        return render_prompt("deadline_check", situation=situation, event_date=event_date)

    # ── Read-only resources ──────────────────────────────────
    @mcp.resource(
        RESOURCE_COVERAGE, name="coverage", title="What is held / რა ინახება",
        description="The laws and court decisions held, their dates, and what is not held.",
        mime_type="application/json",
    )
    def coverage_resource() -> str:
        return svc().get_coverage().model_dump_json(indent=1)

    @mcp.resource(
        RESOURCE_ANSWER_RULES, name="answer-rules", title="Answer rules / პასუხის წესები",
        description="How an AI should answer from these sources, in English and Georgian.",
        mime_type="text/plain",
    )
    def answer_rules_resource() -> str:
        return ANSWER_RULES

    @mcp.resource(
        RESOURCE_LEGAL_AID, name="legal-aid",
        title="Free legal help / უფასო იურიდიული დახმარება",
        description="Where a person in Georgia can get free legal help, with contacts.",
        mime_type="application/json",
    )
    def legal_aid_resource() -> str:
        return svc().legal_aid().model_dump_json(indent=1)

    return mcp


def connector_mcp_app(mcp: MCPServer) -> Starlette:
    """The Streamable HTTP app serving ``mcp`` at /mcp (stateless, JSON responses)."""
    hosts = settings.connector_allowed_host_list
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(hosts),
        allowed_hosts=hosts,
        allowed_origins=[f"https://{h}" for h in hosts],
    )
    return mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        max_request_body_size=settings.connector_max_body_bytes,
        transport_security=security,
    )


def install_law_connector(app: FastAPI) -> MCPServer:
    """Add the connector to ``app``: REST mirror, MCP endpoint and access control.

    The returned server's ``session_manager.run()`` must be entered in the
    app's lifespan; it is also kept on ``app.state.connector_mcp`` for that.
    """
    mcp = build_connector_mcp_server()
    app.include_router(connector_router.router)
    app.include_router(connector_router.page_router)
    app.router.routes.extend(connector_mcp_app(mcp).routes)
    app.add_middleware(ConnectorAccessMiddleware)
    app.state.connector_mcp = mcp
    return mcp
