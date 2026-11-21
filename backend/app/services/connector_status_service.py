"""
Connector Status Service — how current the stored law texts are.

The daily refresh compares every stored code with matsne.gov.ge and, when the
whole run succeeds, writes the time into ``status.json`` beside the stores.
Every connector answer carries that date, and a warning once the check has not
succeeded for too long, so the caller's AI can tell a person how fresh the
text is. Without a status file the date is that of the oldest stored download.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from app.config.settings import settings
from app.services.article_store_service import ArticleStoreService
from app.utils.logger import get_logger

logger = get_logger(__name__)

STATUS_FILE = "status.json"
REFRESH_STATES = ("ok", "failing", "overdue", "never_ran")

UNKNOWN_WARNING = (
    "It is not recorded when the stored law texts were last checked against "
    "matsne.gov.ge. Open source_url to confirm the current text before relying on it."
)
STALE_WARNING = (
    "The stored law texts were last confirmed against matsne.gov.ge on {day}, "
    "{age} days ago; a law may have changed since. Open source_url to confirm the "
    "current text before relying on it."
)


@dataclass(frozen=True)
class DataStatus:
    """The date the stored law texts were last confirmed, and a warning if that is old."""

    current_as_of: str | None
    warning: str | None


def file_signature(path: Path) -> tuple[int, int, int] | None:
    """Changes whenever the file at ``path`` is replaced or rewritten; None if absent."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size, stat.st_ino


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _to_date(value: object) -> date | None:
    """The calendar day of an ISO date or time; None when it is not one."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class ConnectorStatusService:
    """Reads the refresh status written beside the article store."""

    def __init__(
        self,
        store: ArticleStoreService,
        status_path: Path | None = None,
        stale_after_days: int | None = None,
        today: Callable[[], date] = _utc_today,
    ) -> None:
        self._store = store
        self._status_path = status_path or store.db_path.with_name(STATUS_FILE)
        self._stale_after_days = (
            settings.connector_stale_after_days if stale_after_days is None else stale_after_days
        )
        self._today = today
        self._signature: object = ()
        self._confirmed_on: date | None = None
        self._last_run: dict[str, object] = {}

    def current(self) -> DataStatus:
        """Today's answer to "how fresh is the stored law text?"."""
        confirmed_on = self._load_confirmed_on()
        if confirmed_on is None:
            return DataStatus(current_as_of=None, warning=UNKNOWN_WARNING)
        age = (self._today() - confirmed_on).days
        warning = None
        if age > self._stale_after_days:
            warning = STALE_WARNING.format(day=confirmed_on.isoformat(), age=age)
        return DataStatus(current_as_of=confirmed_on.isoformat(), warning=warning)

    def refresh_state(self) -> str:
        """How the daily refresh is doing: one of ``REFRESH_STATES``.

        ``never_ran`` without a status file, ``failing`` when the last run
        reported a problem, ``overdue`` when no run finished today or
        yesterday, otherwise ``ok``.
        """
        self._load_confirmed_on()
        last_run_on = _to_date(self._last_run.get("last_run_at"))
        if last_run_on is None:
            return "never_ran"
        if self._last_run.get("last_run_ok") is not True:
            return "failing"
        if (self._today() - last_run_on).days > 1:
            return "overdue"
        return "ok"

    def _load_confirmed_on(self) -> date | None:
        """Day of the last successful check, re-read only when a file changed."""
        signature = (file_signature(self._status_path), file_signature(self._store.db_path))
        if signature != self._signature:
            self._last_run = self._read_status_file()
            self._confirmed_on = (
                _to_date(self._last_run.get("last_success_at")) or self._oldest_download()
            )
            self._signature = signature
        return self._confirmed_on

    def _read_status_file(self) -> dict[str, object]:
        """What the last refresh recorded; empty when there is no readable record."""
        try:
            status = json.loads(self._status_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.warning("connector_status_unreadable", error_type=type(e).__name__)
            return {}
        return status if isinstance(status, dict) else {}

    def _oldest_download(self) -> date | None:
        """The earliest day any stored code was downloaded; None if one has no date."""
        days = [_to_date(row.get("retrieved_at")) for row in self._store.list_codes()]
        if not days or any(day is None for day in days):
            return None
        return min(day for day in days if day is not None)
