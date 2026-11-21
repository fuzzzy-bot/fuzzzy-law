# Architecture

Short version: a nightly job turns official web pages into SQLite files; a small read-only server
answers questions about those files over MCP and HTTP; the person's own AI writes the answer.

```
matsne.gov.ge ──► daily refresh (law_corpus/, 01:17 UTC, one-shot container)
supremecourt.ge ─► court collection scripts (by hand)        │
constcourt.ge ──►                                            ▼
                                       data folder: article_store.db, law_history.db,
                                                    court_store.db, status.json
                                                             │ read-only
                                                             ▼
                          connector (backend/, one process, 512 MB limit, no database server)
                              /mcp  MCP Streamable HTTP: 12 tools, 4 prompts, 3 resources
                              /api/v1/connector/*  REST mirror (for GPT Actions)
                              /coverage  human-readable page, /healthz, /healthz/data
                                                             │ HTTPS via nginx
                                                             ▼
                     the person's assistant (Claude, ChatGPT, Gemini CLI, ...) writes the answer
```

## The connector (`backend/`)

- `app/connector_main.py` builds the FastAPI app: the MCP server, the REST router, health checks.
- `app/routes/connector_mcp.py`: the MCP tools, prompts and resources, and their descriptions.
- `app/routes/connector_router.py`: the REST mirror and its OpenAPI document.
- `app/services/law_connector_service.py`: every answer; reads the three SQLite files through
  `article_store_service.py`, `law_history_service.py` and `court_store_service.py`.
- `app/services/connector_guidance.py`: everything the server tells an assistant (instructions,
  answer rules, prompts, the send-this message). `scripts/write_client_files.py` writes the generated
  files from it; tests fail if they drift.
- `app/services/connector_reference.py`: hand-checked facts (free legal help, what is not held,
  how the data is kept), each with the date it was checked.
- `app/middleware/`: per-caller request limits, body size limit, errors logged without their text.

It never calls a model and stores nothing a person asks. Search is SQLite full-text search with
Georgian word-ending trimming and a small table of everyday words mapped to the law's terms.

## The data pipeline (`law_corpus/`)

- `pipeline/scraper/`: polite download from matsne.gov.ge (robots.txt, 10 s between requests, one
  honest user agent, retries that also wait their turn).
- `pipeline/parser/`: matsne's HTML into articles and paragraphs.
- `scripts/daily_refresh.py`: the nightly job; rebuilds the store beside the served one, verifies it
  (every article, every line, 50 random articles word for word) and swaps it in only when every check
  passes; adds new versions to `law_history.db`; writes `status.json`.
- `scripts/law_history.py`: downloads and builds earlier wordings.
- `scripts/fetch_supreme_court_collections.py`, `extract_supreme_collections.py`,
  `fetch_constitutional_court.py`, `build_court_store.py`: the court decisions.

## Deployment

The public service runs both as containers on one small shared server: the connector
(`backend/docker-compose.connector.yml`, read-only file system, no capabilities, 512 MB) behind nginx
(`backend/scripts/nginx.connector.conf.example`), and the refresh as a one-shot job started by cron.
See [run your own](run-your-own.md).
