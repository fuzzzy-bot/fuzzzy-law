"""
Test fixtures shared by the connector tests: small real-text stores built in a
temporary folder, so no download and no server data are needed.
"""

from __future__ import annotations

import pytest

# ── Law connector: a small real-text article store ───────────

# Same schema as law_corpus/scripts/build_article_store.py (the backend never
# imports the corpus project, so the DDL is restated here).
_ARTICLE_STORE_DDL = """
CREATE TABLE codes (document_id TEXT PRIMARY KEY, code_name TEXT NOT NULL, title_en TEXT,
    document_number TEXT, source_url TEXT NOT NULL, article_count INTEGER NOT NULL);
CREATE TABLE articles (article_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
    code_name TEXT NOT NULL, article_number TEXT NOT NULL, article_norm TEXT NOT NULL,
    article_title TEXT, book TEXT, part TEXT, chapter TEXT, content_ka TEXT NOT NULL,
    paragraphs_json TEXT NOT NULL, cross_references_json TEXT NOT NULL,
    article_url TEXT NOT NULL, is_repealed INTEGER NOT NULL DEFAULT 0, effective_date TEXT);
CREATE VIRTUAL TABLE articles_fts USING fts5(article_id UNINDEXED, code_name,
    article_number, article_title, content_ka);
"""


def build_connector_article_store(
    path, *, with_version_fields: bool = False, without_links: bool = False
):
    """Write an article store from tests/fixtures/connector_article_store.json.

    The fixture holds real articles copied from the store the live server
    serves (Civil Procedure Code 368-370, Labour Code 47-48, Civil Code
    137-139 and a repealed article). ``with_version_fields`` adds the version
    columns a newer store build carries; ``without_links`` blanks every stored
    link so the matsne link must be rebuilt from the document id.
    """
    import json
    import sqlite3
    from pathlib import Path

    data = json.loads(
        (Path(__file__).parent / "fixtures" / "connector_article_store.json").read_text("utf-8")
    )
    conn = sqlite3.connect(path)
    conn.executescript(_ARTICLE_STORE_DDL)
    if with_version_fields:
        conn.execute("ALTER TABLE codes ADD COLUMN version_date TEXT")
        conn.execute("ALTER TABLE articles ADD COLUMN in_force_since TEXT")
    for code in data["codes"]:
        if without_links:
            code = code | {"source_url": "", "document_number": None}
        columns = list(code)
        if with_version_fields:
            code = code | {"version_date": "2026-09-30"}
            columns.append("version_date")
        conn.execute(
            f"INSERT INTO codes ({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
            [code[c] for c in columns],
        )
    for art in data["articles"]:
        if without_links:
            art = art | {"article_url": ""}
        if with_version_fields:
            art = art | {"in_force_since": "2024-01-01"}
        columns = list(art)
        conn.execute(
            f"INSERT INTO articles ({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
            [art[c] for c in columns],
        )
        conn.execute(
            "INSERT INTO articles_fts VALUES (?, ?, ?, ?, ?)",
            (art["article_id"], art["code_name"], art["article_number"],
             art["article_title"], art["content_ka"]),
        )
    conn.commit()
    conn.close()
    return path


# ── Law connector: a small court store ───────────────────────

# Same schema as law_corpus/scripts/build_court_store.py (restated for the
# same reason as the article store above).
_COURT_STORE_DDL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE decisions (decision_id TEXT PRIMARY KEY, collection TEXT NOT NULL,
    case_number TEXT NOT NULL, category TEXT, decision_type TEXT, decision_date TEXT,
    year TEXT, source_url TEXT, source_file TEXT NOT NULL, passage_count INTEGER NOT NULL,
    char_count INTEGER NOT NULL);
CREATE TABLE passages (passage_id INTEGER PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES decisions(decision_id), seq INTEGER NOT NULL,
    text TEXT NOT NULL);
CREATE INDEX idx_passages_decision ON passages(decision_id, seq);
CREATE VIRTUAL TABLE passages_fts USING fts5(
    text, content='passages', content_rowid='passage_id', detail=none);
"""

# Passages in the layout the Supreme Court publishes (heading first, parties
# as initials); the case numbers are invented.
COURT_FIXTURE_DECISIONS = [
    {
        "collection": "court_practice", "case_number": "AS-664-2023", "category": "civil",
        "decision_type": "განჩინება", "decision_date": "2023-05-12", "source_url": None,
        "passages": [
            "განჩინება\nსაქართველოს სახელით\n#AS-664-2023\n12 მაისი, 2023 წ., ქ. თბილისი",
            "1. მოსარჩელე გ. ხ-ემ სარჩელი აღძრა სს `ბ-ას~ მიმართ.",
            "2. საკასაციო სასამართლო განმარტავს, რომ ხანდაზმულობის ვადის დენა "
            "წყდება სარჩელის შეტანით (სამოქალაქო კოდექსის 138-ე მუხლი).",
            "3. საკასაციო საჩივარი არ დაკმაყოფილდეს.",
        ],
    },
    {
        "collection": "grand_chamber", "case_number": "GC-12-2022", "category": "civil",
        "decision_type": "გადაწყვეტილება", "decision_date": "2022-06-03",
        "source_url": "https://www.supremecourt.ge/example-grand-chamber.pdf",
        "passages": [
            "გადაწყვეტილება\nსაქართველოს სახელით\nსაქმე №GC-12-2022\n3 ივნისი, 2022 წ.",
            "1. დიდი პალატა განმარტავს: ხანდაზმულობის ვადის დენის შეწყვეტა ვრცელდება "
            "სოლიდარულ მოვალეებზეც.",
        ],
    },
]


# A judgment in the layout the Constitutional Court publishes: the case title
# first, with the claimant's name in full. The number, the name and the link
# are invented.
CONSTITUTIONAL_FIXTURE_DECISION = {
    "collection": "constitutional_court", "case_number": "N3/1/9001,9002",
    "category": "constitutional", "decision_type": "გადაწყვეტილება",
    "decision_date": "2024-02-20",
    "source_url": "https://www.constcourt.ge/ka/judicial-acts?legal=99999",
    "passages": [
        "ნინო მაგალითაძე საქართველოს პარლამენტის წინააღმდეგ\nდოკუმენტის ტიპი გადაწყვეტილება\n"
        "ნომერი N3/1/9001,9002\nთარიღი 20 თებერვალი 2024",
        "1. საკონსტიტუციო სასამართლო განმარტავს, რომ ხანდაზმულობის ვადის დაწესება "
        "სასამართლოსადმი მიმართვის უფლების შეზღუდვაა და თანაზომიერი უნდა იყოს.",
        "2. სადავო ნორმა ძალადაკარგულად იქნეს ცნობილი.",
    ],
}
COURT_FIXTURE_WITH_CONSTITUTIONAL = [*COURT_FIXTURE_DECISIONS, CONSTITUTIONAL_FIXTURE_DECISION]


def build_court_store(path, decisions=None):
    """Write a court store holding ``decisions`` (COURT_FIXTURE_DECISIONS unless given)."""
    import sqlite3

    conn = sqlite3.connect(path)
    conn.executescript(_COURT_STORE_DDL)
    for d in decisions or COURT_FIXTURE_DECISIONS:
        decision_id = f"case:{d['collection']}:{d['case_number']}"
        conn.execute(
            "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (decision_id, d["collection"], d["case_number"], d["category"], d["decision_type"],
             d["decision_date"], d["decision_date"][:4], d["source_url"],
             f"{d['collection']}/{d['category']}/{d['case_number']}.txt",
             len(d["passages"]), sum(len(p) for p in d["passages"])),
        )
        conn.executemany(
            "INSERT INTO passages (decision_id, seq, text) VALUES (?,?,?)",
            [(decision_id, seq, text) for seq, text in enumerate(d["passages"])],
        )
    conn.execute("INSERT INTO passages_fts (rowid, text) SELECT passage_id, text FROM passages")
    conn.commit()
    conn.close()
    return path


# ── Law connector: a small real-text law history ─────────────

# Same schema as law_corpus/scripts/law_history.py (restated for the same
# reason as the article store above).
_LAW_HISTORY_DDL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE versions (document_id TEXT NOT NULL, publication_id INTEGER NOT NULL,
    version_date TEXT NOT NULL, version_url TEXT NOT NULL,
    PRIMARY KEY (document_id, publication_id));
CREATE TABLE article_versions (document_id TEXT NOT NULL, article_norm TEXT NOT NULL,
    from_publication INTEGER NOT NULL, closed_by_publication INTEGER,
    article_number TEXT NOT NULL, article_title TEXT, content_ka TEXT NOT NULL,
    paragraphs_json TEXT NOT NULL, is_repealed INTEGER NOT NULL, matsne_anchor TEXT,
    content_sha256 TEXT NOT NULL,
    PRIMARY KEY (document_id, article_norm, from_publication));
"""


def build_law_history(path):
    """Write a law history from tests/fixtures/connector_law_history.json.

    The fixture holds every consolidated version matsne.gov.ge lists since
    2024 for the Civil Code, the Civil Procedure Code and the Labour Code,
    and the real wordings of a handful of articles those versions amended,
    added or removed, as built by law_corpus/scripts/law_history.py.
    """
    import json
    import sqlite3
    from pathlib import Path

    data = json.loads(
        (Path(__file__).parent / "fixtures" / "connector_law_history.json").read_text("utf-8")
    )
    conn = sqlite3.connect(path)
    conn.executescript(_LAW_HISTORY_DDL)
    for table in ("versions", "article_versions"):
        for row in data[table]:
            columns = list(row)
            conn.execute(
                f"INSERT INTO {table} ({','.join(columns)}) "
                f"VALUES ({','.join('?' * len(columns))})",
                [row[c] for c in columns],
            )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def connector_store(tmp_path):
    from app.services.article_store_service import ArticleStoreService

    return ArticleStoreService(db_path=build_connector_article_store(tmp_path / "store.db"))


@pytest.fixture
def connector_service(connector_store, monkeypatch):
    """The connector service on the fixture store, with no court source."""
    from app.services import connector_rate_limiter
    from app.services import law_connector_service as module

    # Each test starts with empty request counts.
    monkeypatch.setattr(connector_rate_limiter, "_limiter",
                        connector_rate_limiter.SlidingWindowLimiter())
    service = module.LawConnectorService(store=connector_store)
    monkeypatch.setattr(module, "_connector_service", service)
    return service


@pytest.fixture
def connector_service_with_history(connector_store, monkeypatch, tmp_path):
    """The connector service on the fixture store with the fixture law history."""
    from app.services import connector_rate_limiter
    from app.services import law_connector_service as module
    from app.services.law_history_service import LawHistoryService

    monkeypatch.setattr(connector_rate_limiter, "_limiter",
                        connector_rate_limiter.SlidingWindowLimiter())
    history = LawHistoryService(build_law_history(tmp_path / "law_history.db"))
    service = module.LawConnectorService(store=connector_store, history=history)
    monkeypatch.setattr(module, "_connector_service", service)
    return service
