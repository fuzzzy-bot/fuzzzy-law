"""
Law History Service — how an article read on an earlier date, and what changed.

Reads the SQLite file built by law_corpus/scripts/law_history.py: the
consolidated versions matsne.gov.ge has published for each stored law, and for
every article the stretch of versions in which its wording stayed the same.

A date is answered from the newest version matsne dates on or before it. That
date is the day of the consolidated version, not always the day the amendment
took effect, so every answer says which version it comes from and links to
exactly that version on matsne.gov.ge.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.utils.logger import get_logger

logger = get_logger(__name__)

HISTORY_FILE = "law_history.db"
MAX_CHANGES = 300


class LawHistoryService:
    """Read-only lookups against the law history file."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def is_available(self) -> bool:
        return self._db_path.exists()

    def _connect(self) -> sqlite3.Connection:
        # Opened anew for every lookup: the daily refresh replaces the whole file.
        conn = sqlite3.connect(f"file:{self._db_path}?mode=ro&immutable=1", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def reach(self, document_id: str) -> dict[str, Any] | None:
        """First and last stored version dates of a law and how many versions are held."""
        if not self.is_available:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MIN(version_date) AS earliest, MAX(version_date) AS latest, "
                "COUNT(*) AS versions FROM versions WHERE document_id = ?", (document_id,)
            ).fetchone()
        return dict(row) if row and row["versions"] else None

    def coverage(self) -> list[dict[str, Any]]:
        """``reach`` of every law in the file."""
        if not self.is_available:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT document_id, MIN(version_date) AS earliest, MAX(version_date) AS latest, "
                "COUNT(*) AS versions FROM versions GROUP BY document_id ORDER BY document_id"
            ).fetchall()
        return [dict(r) for r in rows]

    def version_on(self, document_id: str, as_of: str) -> dict[str, Any] | None:
        """The newest stored version of a law dated on or before ``as_of`` (ISO date)."""
        if not self.is_available:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM versions WHERE document_id = ? AND version_date <= ? "
                "ORDER BY publication_id DESC LIMIT 1", (document_id, as_of)
            ).fetchone()
        return dict(row) if row else None

    def article_on(self, document_id: str, article_norm: str, as_of: str) -> dict[str, Any] | None:
        """An article's wording in the version of ``as_of``.

        Returns ``None`` when no stored version is that old. Otherwise a dict
        with ``version`` (the version answered from) and ``article`` (``None``
        when that version has no such article), plus ``wording_from`` and
        ``replaced_by``: the versions that introduced and ended this wording,
        the first being ``None`` when it is older than the stored history.
        """
        version = self.version_on(document_id, as_of)
        if version is None:
            return None
        number = version["publication_id"]
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM article_versions WHERE document_id = ? AND article_norm = ? "
                "AND from_publication <= ? "
                "AND (closed_by_publication IS NULL OR closed_by_publication > ?) "
                "ORDER BY from_publication DESC LIMIT 1",
                (document_id, article_norm, number, number),
            ).fetchone()
            if row is None:
                return {"version": version, "article": None,
                        "wording_from": None, "replaced_by": None}
            first = conn.execute(
                "SELECT MIN(publication_id) FROM versions WHERE document_id = ?", (document_id,)
            ).fetchone()[0]
            wording_from = None
            if row["from_publication"] != first:
                wording_from = self._version(conn, document_id, row["from_publication"])
            replaced_by = None
            if row["closed_by_publication"] is not None:
                replaced_by = self._version(conn, document_id, row["closed_by_publication"])
        article = dict(row)
        article["paragraphs"] = json.loads(article.pop("paragraphs_json"))
        article["is_repealed"] = bool(article["is_repealed"])
        return {"version": version, "article": article,
                "wording_from": wording_from, "replaced_by": replaced_by}

    @staticmethod
    def _version(conn: sqlite3.Connection, document_id: str, number: int) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT * FROM versions WHERE document_id = ? AND publication_id = ?",
            (document_id, number),
        ).fetchone()
        return dict(row) if row else None

    def changes(
        self, document_id: str, since: str, article_norm: str | None = None
    ) -> list[dict[str, Any]]:
        """Articles whose wording changed in versions dated on or after ``since``.

        One entry per article and version, oldest first: ``change`` is
        ``amended``, ``added`` or ``removed``. The first stored version is the
        starting point and is never itself listed as a change.
        """
        if not self.is_available:
            return []
        with self._connect() as conn:
            first = conn.execute(
                "SELECT MIN(publication_id) FROM versions WHERE document_id = ?", (document_id,)
            ).fetchone()[0]
            if first is None:
                return []
            versions = {
                r["publication_id"]: dict(r) for r in conn.execute(
                    "SELECT * FROM versions WHERE document_id = ? AND version_date >= ? "
                    "AND publication_id > ?", (document_id, since, first))
            }
            sql = "SELECT article_norm, article_number, article_title, from_publication, " \
                  "closed_by_publication FROM article_versions WHERE document_id = ?"
            params: list[Any] = [document_id]
            if article_norm:
                sql += " AND article_norm = ?"
                params.append(article_norm)
            rows = [dict(r) for r in conn.execute(sql, params)]

        opened = {(r["article_norm"], r["from_publication"]) for r in rows}
        closed = {(r["article_norm"], r["closed_by_publication"]) for r in rows}
        found: list[dict[str, Any]] = []
        for row in rows:
            norm = row["article_norm"]
            start, end = row["from_publication"], row["closed_by_publication"]
            if start in versions:
                kind = "amended" if (norm, start) in closed else "added"
                found.append(self._change(row, kind, versions[start]))
            if end in versions and (norm, end) not in opened:
                found.append(self._change(row, "removed", versions[end]))
        found.sort(key=lambda c: (c["publication_id"], _article_order(c["article_norm"])))
        return found

    @staticmethod
    def _change(row: dict[str, Any], kind: str, version: dict[str, Any]) -> dict[str, Any]:
        return {
            "article_norm": row["article_norm"],
            "article_number": row["article_number"],
            "article_title": row["article_title"],
            "change": kind,
            "publication_id": version["publication_id"],
            "version_date": version["version_date"],
            "version_url": version["version_url"],
        }


def _article_order(norm: str) -> tuple[int, int]:
    """Sort key putting '166-1' after '166' and before '167'."""
    head, _, tail = norm.partition("-")
    return (int(head) if head.isdigit() else 0, int(tail) if tail.isdigit() else 0)
