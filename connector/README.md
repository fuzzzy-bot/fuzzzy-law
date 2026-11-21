# Fuzzzy Law connector: technical reference

The connector lets a person's own AI assistant answer Georgian law questions from real sources. It
returns the exact text of Georgian laws with the official matsne.gov.ge link and version date, how an
article read on an earlier date, published court decisions, and where to get free legal help. It never
writes advice and never calls a model: the person's AI writes the answer, guided by the rules the
connector sends it. Legal information, not legal advice.

Free and open: no account, no key. What it holds today is on its own page, `/coverage`.

| Piece | Where | For |
|---|---|---|
| MCP server "Fuzzzy Law — Georgian law sources" | `POST /mcp` (Streamable HTTP, stateless, JSON) | Claude custom connector, ChatGPT custom MCP server, Claude API MCP connector, OpenAI Responses `mcp` tool, any MCP client |
| REST mirror | `/api/v1/connector/*` | custom GPT Actions, plain HTTP agents |
| OpenAPI 3.1 for a GPT Action | `GET /api/v1/connector/openapi.json` (copy: `openapi.json`) | paste or import into the GPT editor |
| Coverage page | `GET /coverage` | a person reading in a browser: laws and court decisions held, their dates, where each kind of data comes from and how it stays current, what is not held |
| Health | `GET /healthz`, `GET /healthz/data` | is it up; did the last daily law check pass |
| Answer rules | sent as the MCP server instructions; the same text in `instructions/system_prompt.txt` | any assistant |
| Claude skill | `skill/georgian-law/SKILL.md` | Claude apps and Claude Code |
| Custom GPT instructions | `instructions/custom_gpt_instructions.txt` | the GPT editor's Instructions box |

`system_prompt.txt`, `custom_gpt_instructions.txt`, the skill file and `openapi.json` are written from
the code (`backend/app/services/connector_guidance.py`, `backend/app/routes/connector_router.py`);
tests keep the files and the code identical. Change the code, then regenerate the files; never edit
them by hand.

## Tools

All read-only (`readOnlyHint`), descriptions in English and Georgian.

| MCP tool | REST operation | Returns |
|---|---|---|
| `list_codes()` | `GET /codes` `listCodes` | the laws held: article counts, links, version dates |
| `search_law(query, code?, limit)` | `GET /search` `searchLaw` | articles with an exact snippet, law, article number, link, version date; `found=false` when nothing matched |
| `get_article(code, article, paragraph?, as_of?)` | `GET /articles` `getArticle` | full exact text, paragraphs, link, version date, previous and next article; with `as_of` (a date) the wording that stood on that day |
| `list_changes(code, since, article?)` | `GET /changes` `listChanges` | articles amended, added or removed since a date, with a link to each version |
| `browse_code(code, chapter?, offset, limit)` | `GET /structure` `browseCode` | chapters, or article numbers and titles |
| `find_court_practice(query, limit, court?)` | `GET /court-practice` `findCourtPractice` | decisions with case number, court, date, snippet; `none_found` said plainly |
| `get_court_decision(id, from_passage)` | `GET /court-decision` `getCourtDecision` | a stored decision's own text as the court published it, twenty passages per call, and `law_since_decision`: the stored law articles it cites and whether each changed after the decision date |
| `verify_citation(code, article, claim, paragraph?, quote?)` | `POST /verify-citation` `verifyCitation` | does the article exist, is it repealed, what it says; with `quote`, whether the quoted words are in it word for word |
| `get_coverage()` | `GET /coverage` `getCoverage` | laws and court decisions held, their dates, how far earlier wordings go back, `how_data_is_kept` (source, collection, updating, last date per kind of data), what is not held |
| `find_legal_aid()` | `GET /legal-aid` `findLegalAid` | free legal help in Georgia: who, for whom, phone, hours, website, and the day the contacts were last checked |
| `search(query)` / `fetch(id)` | — | the pair ChatGPT deep research and company knowledge expect |

Prompts (MCP): `intake`, `case_analysis`, `document_drafting`, `deadline_check`.
Resources (MCP): `coverage`, `answer-rules`, `legal-aid`.

Every answer carries `data_current_as_of` (the day the stored law texts were last confirmed against
matsne.gov.ge), a `freshness_warning` when that check is overdue or undated, `source_url`, the version
date (or a note that it is not recorded) and the not-legal-advice `notice`.

Search matches words (SQLite full text with Georgian word-ending trimming); there is no meaning
search, so a question works best in Georgian legal terms.

## Data

The service reads three SQLite files from one folder (`CONNECTOR_DATA_DIR`) and `status.json`:

| File | Holds | Written by |
|---|---|---|
| `article_store.db` | the current consolidated text of each law, article by article | `law_corpus/scripts/daily_refresh.py` |
| `law_history.db` | earlier wordings of each article, per consolidated version on matsne | `law_corpus/scripts/law_history.py`, then the daily refresh |
| `court_store.db` | published court decisions cut into passages | `law_corpus/scripts/build_court_store.py` |
| `status.json` | when the last daily check ran and whether it passed | the daily refresh |

A missing `law_history.db` or `court_store.db` is not an error: the tools then say that earlier
wordings or court decisions are not held.

The daily refresh downloads each stored law's current page from matsne.gov.ge (one request per law,
robots.txt honoured, never under 10 s apart, one honest user agent), rebuilds the store beside the
served one, checks it against the pages (every article matsne marks, every line of article text, and
50 random articles word for word) and swaps it in only when every check passes. A failed check leaves
the served store untouched and marks `status.json` not OK, which `/healthz/data` reports.

Court decisions are served in the form the court published them. The Supreme Court prints parties as
initials. The Constitutional Court prints the parties' names; a result from that collection carries a
`names_note` telling the assistant to cite the case by number and title and not to use it to tell
anything else about the people named.

Courts keep citing older decisions, so age is no reason to leave one out. `get_court_decision` reads
the references in the decision's own text (a law named in full, "ამავე კოდექსის", a short form the
decision defines, otherwise the Supreme Court's usual short forms for that kind of case; ambiguous or
foreign ones are skipped, `backend/app/services/decision_citations.py`) and compares each cited
article with the law history: `changed` (with the dates), `unchanged`, or `unknown` when the stored
wordings of that law begin after the decision.

## Privacy and limits

- The service does not store what people ask. The application log carries no query text and no caller
  address; an unexpected error is logged as its type and code location only.
- nginx in front logs the caller's network address and the path without the query string, kept seven
  days (`backend/scripts/nginx.connector.conf.example`, `logrotate.connector.example`).
- 30 requests a minute per caller address (IPv6 counted by /64), counted in memory. Networks AI
  providers call from on behalf of many people (`CONNECTOR_SHARED_IP_RANGES`) share a higher limit.
- Request bodies over 64 KB, or without a declared length, are refused.

## Run it

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/pip install --no-deps -r requirements-connector.txt
CONNECTOR_DATA_DIR=<folder with article_store.db ...> \
  .venv/bin/uvicorn app.connector_main:app --port 8010
```

Check it: `curl 'localhost:8010/api/v1/connector/articles?code=civil_code&article=138'`, or
`npx @modelcontextprotocol/inspector --cli http://localhost:8010/mcp --transport http --method tools/list`.

Hosted: `backend/Dockerfile.connector` and `backend/docker-compose.connector.yml` run the connector as
a non-root, read-only container on a local port behind nginx, and the daily refresh
(`law_corpus/Dockerfile.refresh`) as a one-shot job the host's scheduler starts once a day. Neither
needs a database server, Redis, a vector store or a model key.

## Settings (environment)

| Variable | Default | Meaning |
|---|---|---|
| `CONNECTOR_DATA_DIR` | unset | folder with the three data files and `status.json`; unset = `./data` |
| `CONNECTOR_PUBLIC_BASE_URL` | `http://localhost:8000` | public origin; goes into the OpenAPI `servers` and the coverage page |
| `CONNECTOR_ACCESS_MODE` | `open` | `open` (limit per caller address) or `api_key` (per-user quotas) |
| `CONNECTOR_RATE_LIMIT_PER_MINUTE` | `30` | per caller |
| `CONNECTOR_SHARED_IP_RANGES` | empty | networks (CIDR) of AI providers calling for many people at once |
| `CONNECTOR_SHARED_RATE_LIMIT_PER_MINUTE` | `600` | limit for one address inside those networks |
| `CONNECTOR_MAX_BODY_BYTES` | `65536` | largest request body accepted |
| `CONNECTOR_STALE_AFTER_DAYS` | `3` | days without a successful matsne check before every answer carries a warning |
| `CONNECTOR_ALLOWED_HOSTS` | empty | Host values `/mcp` accepts (DNS-rebinding protection) |
| `CONNECTOR_DAILY_QUOTA` | `1000` | key mode: requests a day per key holder |
| `CONNECTOR_API_KEYS_FILE` | `connector_api_keys.json` | key mode: `{"<sha256 of key>": {"user": "...", "daily_quota": N}}`, hashes only |

The list of provider networks is a dated snapshot of what Anthropic and OpenAI publish; it needs a
fresh look now and then.

## Access modes

- `open`: anyone, limited per caller address. This is how the public service runs.
- `api_key`: callers send `Authorization: Bearer <key>`. Works for a GPT Action and the Claude API MCP
  connector. ChatGPT's and Claude's connector screens do not take a static key.
- Not built: OAuth account sign-in.

## Tests

From `backend`: `pytest` (all of `backend/tests`). From `law_corpus`: `pytest` (all of
`law_corpus/tests`). Both need only the files in this repository; see the main README.
