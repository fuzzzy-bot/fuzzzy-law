"""
Court Store Service — full-text lookups over stored court decisions.

Reads the SQLite store built by law_corpus/scripts/build_court_store.py. A
decision is in the store only if its own heading printed a case number, and
its text is the court's published wording cut into passages: the Supreme Court
prints parties as initials, the Constitutional Court prints their names.
Search is plain word matching; no model is called.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from app.utils.logger import get_logger

logger = get_logger(__name__)

_TOKEN = re.compile(r"[\wა-ჿ]+")
_CASE_NUMBER_NOISE = re.compile(r"[\s#№]+")
# The Constitutional Court writes its number sign as a Latin N: "N3/1/1459".
_LATIN_NUMBER_SIGN = re.compile(r"^n(?=\d)")
MAX_QUERY_TERMS = 12


def _stem_terms(query: str) -> list[str]:
    """FTS5 prefix terms: Georgian words lose their case ending, numbers stay whole."""
    terms: list[str] = []
    for token in _TOKEN.findall(query.lower()):
        if token.isdigit():
            terms.append(f'"{token}"')
        elif len(token) >= 6:
            terms.append(f'"{token[:-2]}"*')
        elif len(token) >= 4:
            terms.append(f'"{token[:-1]}"*')
    return list(dict.fromkeys(terms))[:MAX_QUERY_TERMS]


def normalize_case_number(case_number: str) -> str:
    """'# ას-1001-2018 ' and 'ას-1001-2018' are the same case."""
    return _LATIN_NUMBER_SIGN.sub("", _CASE_NUMBER_NOISE.sub("", case_number).lower())


def case_number_keys(case_number: str) -> set[str]:
    """Every number a stored decision answers to.

    A Constitutional Court judgment on joined claims prints one number for all
    of them, 'N3/1/1459,1491'; it is found by that and by '3/1/1459' or
    '3/1/1491' alone.
    """
    whole = normalize_case_number(case_number)
    keys = {whole}
    head, slash, claims = whole.rpartition("/")
    if slash and "," in claims:
        keys.update(f"{head}/{claim}" for claim in claims.split(",") if claim)
    return keys


class CourtStoreService:
    """Read-only lookups against the court decision store."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def is_available(self) -> bool:
        return self._db_path.exists()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self._db_path}?mode=ro&immutable=1", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def search(
        self, query: str, limit: int = 5, collections: tuple[str, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Decisions whose text matches the query, best first.

        Each result is the decision row plus ``passage`` (its best-matching
        passage) and ``passage_seq``. Decisions containing every query word in
        one passage come before those containing only some. ``collections``
        keeps the search to those collections.
        """
        if not self.is_available:
            return []
        terms = _stem_terms(query)
        if not terms:
            return []
        found: dict[str, dict[str, Any]] = {}
        only, params = "", []
        if collections:
            only = f"AND d.collection IN ({', '.join('?' * len(collections))}) "
            params = list(collections)
        try:
            with self._connect() as conn:
                for joiner in (" AND ", " OR "):
                    rows = conn.execute(
                        "SELECT d.*, p.seq AS passage_seq, p.text AS passage "
                        "FROM passages_fts f "
                        "JOIN passages p ON p.passage_id = f.rowid "
                        "JOIN decisions d ON d.decision_id = p.decision_id "
                        f"WHERE passages_fts MATCH ? {only}"
                        "ORDER BY bm25(passages_fts) LIMIT ?",
                        (joiner.join(terms), *params, limit * 8),
                    ).fetchall()
                    for row in rows:
                        found.setdefault(row["decision_id"], dict(row))
                    if len(found) >= limit:
                        break
        except sqlite3.OperationalError as e:
            logger.warning("court_store_search_failed", error_type=type(e).__name__)
            return []
        return list(found.values())[:limit]

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        """The decision with this id (``case:<collection>:<case number>``)."""
        if not self.is_available:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)
            ).fetchone()
        return dict(row) if row else None

    def find_by_case_number(self, case_number: str) -> list[dict[str, Any]]:
        """Decisions whose printed case number is ``case_number`` or joins it."""
        wanted = normalize_case_number(case_number)
        if not self.is_available or not wanted:
            return []
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM decisions").fetchall()
        return [dict(r) for r in rows if wanted in case_number_keys(r["case_number"])]

    def get_passages(self, decision_id: str, offset: int = 0, limit: int = 10) -> list[str]:
        """Consecutive passages of a decision, in reading order."""
        if not self.is_available:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT text FROM passages WHERE decision_id = ? ORDER BY seq LIMIT ? OFFSET ?",
                (decision_id, limit, offset),
            ).fetchall()
        return [r["text"] for r in rows]

    def latest_decision_date(self, collections: tuple[str, ...] | None = None) -> str | None:
        """Date of the newest stored decision, of these collections when given."""
        dates = [row["latest"] for row in self.summary()
                 if row["latest"] and (not collections or row["collection"] in collections)]
        return max(dates) if dates else None

    def built_on(self) -> str | None:
        """The day (ISO) the decision store was built, when the file records it."""
        if not self.is_available:
            return None
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT value FROM meta WHERE key = 'built_at'").fetchone()
        except sqlite3.Error:
            return None
        return row["value"][:10] if row and row["value"] else None

    def summary(self) -> list[dict[str, Any]]:
        """Decision counts and date range per collection."""
        if not self.is_available:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT collection, COUNT(*) AS decision_count, "
                "MIN(decision_date) AS earliest, MAX(decision_date) AS latest "
                "FROM decisions GROUP BY collection ORDER BY collection"
            ).fetchall()
        return [dict(r) for r in rows]
