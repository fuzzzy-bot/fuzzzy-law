"""
Write a small sample data folder from the test fixtures, so the connector can
run right after cloning: a few real articles of three laws, their earlier
wordings and a few court decisions. It is NOT the full data set.

Run from backend/ (needs requirements-dev.txt for pytest):
    python scripts/make_sample_data.py sample-data
then start the connector with CONNECTOR_DATA_DIR=sample-data.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from tests.conftest import (  # noqa: E402
    build_connector_article_store,
    build_court_store,
    build_law_history,
)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "sample-data")
    out.mkdir(parents=True, exist_ok=True)
    for name in ("article_store.db", "law_history.db", "court_store.db"):
        (out / name).unlink(missing_ok=True)
    build_connector_article_store(out / "article_store.db", with_version_fields=True)
    build_law_history(out / "law_history.db")
    build_court_store(out / "court_store.db")
    now = datetime.now(UTC).isoformat(timespec="seconds")
    status = {"last_run_at": now, "last_run_ok": True, "last_success_at": now}
    (out / "status.json").write_text(json.dumps(status, indent=1) + "\n", encoding="utf-8")
    print(f"sample data written to {out.resolve()}")


if __name__ == "__main__":
    main()
