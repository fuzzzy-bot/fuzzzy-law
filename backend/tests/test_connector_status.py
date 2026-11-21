"""
The date stamp on connector answers, and picking up a replaced store.

Every answer says when the stored law texts were last confirmed against
matsne.gov.ge and warns once that check is overdue; a store file swapped in by
the daily refresh is served without a restart.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date

import pytest

from app.config.settings import settings
from app.services import law_connector_service as connector_module
from app.services.article_store_service import ArticleStoreService
from app.services.connector_status_service import (
    UNKNOWN_WARNING,
    ConnectorStatusService,
    file_signature,
)
from app.services.law_connector_service import LawConnectorService
from tests.conftest import build_connector_article_store, build_court_store

TODAY = date(2026, 11, 14)


def write_status(folder, last_success_at: str) -> None:
    (folder / "status.json").write_text(
        json.dumps({"last_success_at": last_success_at}), encoding="utf-8"
    )


@pytest.fixture
def store(tmp_path) -> ArticleStoreService:
    return ArticleStoreService(db_path=build_connector_article_store(tmp_path / "store.db"))


@pytest.fixture
def status(store) -> ConnectorStatusService:
    return ConnectorStatusService(store, stale_after_days=3, today=lambda: TODAY)


class TestStatus:
    def test_date_comes_from_the_last_successful_check(self, tmp_path, status):
        write_status(tmp_path, "2026-11-13T03:10:00Z")
        current = status.current()
        assert current.current_as_of == "2026-11-13"
        assert current.warning is None

    def test_still_fresh_on_the_last_allowed_day(self, tmp_path, status):
        write_status(tmp_path, "2026-11-11T23:59:00Z")
        assert status.current().warning is None

    def test_overdue_check_warns_with_the_date_and_age(self, tmp_path, status):
        write_status(tmp_path, "2026-11-10T03:10:00Z")
        current = status.current()
        assert current.current_as_of == "2026-11-10"
        assert "2026-11-10" in current.warning
        assert "4 days" in current.warning

    def test_no_record_at_all_is_said_plainly(self, status):
        current = status.current()
        assert current.current_as_of is None
        assert current.warning == UNKNOWN_WARNING

    def test_without_a_status_file_the_oldest_download_counts(self, store, status):
        conn = sqlite3.connect(store.db_path)
        conn.execute("ALTER TABLE codes ADD COLUMN retrieved_at TEXT")
        conn.execute("UPDATE codes SET retrieved_at = '2026-11-13T00:47:37.727715Z'")
        conn.execute(
            "UPDATE codes SET retrieved_at = '2026-11-12T22:00:00Z' "
            "WHERE document_id = 'labour_code'"
        )
        conn.commit()
        conn.close()
        assert status.current().current_as_of == "2026-11-12"

    def test_one_code_without_a_download_date_makes_the_date_unknown(self, store, status):
        conn = sqlite3.connect(store.db_path)
        conn.execute("ALTER TABLE codes ADD COLUMN retrieved_at TEXT")
        conn.execute(
            "UPDATE codes SET retrieved_at = '2026-11-13T00:00:00Z' "
            "WHERE document_id = 'labour_code'"
        )
        conn.commit()
        conn.close()
        assert status.current().current_as_of is None

    @pytest.mark.parametrize("content", ["{not json", "[]", '{"last_success_at": "soon"}'])
    def test_unreadable_status_file_is_not_trusted(self, tmp_path, status, content):
        (tmp_path / "status.json").write_text(content, encoding="utf-8")
        assert status.current().current_as_of is None

    def test_a_new_status_file_is_picked_up(self, tmp_path, status):
        write_status(tmp_path, "2026-11-12T03:10:00Z")
        assert status.current().current_as_of == "2026-11-12"
        fresh = tmp_path / "status.json.new"
        fresh.write_text(json.dumps({"last_success_at": "2026-11-14T03:10:00Z"}), "utf-8")
        os.replace(fresh, tmp_path / "status.json")
        assert status.current().current_as_of == "2026-11-14"

    def test_refresh_that_never_ran_is_said_so(self, status):
        assert status.refresh_state() == "never_ran"

    @pytest.mark.parametrize(
        ("last_run_at", "last_run_ok", "expected"),
        [
            ("2026-11-14T03:00:00Z", True, "ok"),
            ("2026-11-13T03:00:00Z", True, "ok"),
            ("2026-11-12T03:00:00Z", True, "overdue"),
            ("2026-11-14T03:00:00Z", False, "failing"),
            ("2026-11-14T03:00:00Z", None, "failing"),
        ],
    )
    def test_refresh_state_follows_the_last_run(
        self, tmp_path, status, last_run_at, last_run_ok, expected
    ):
        (tmp_path / "status.json").write_text(
            json.dumps({"last_run_at": last_run_at, "last_run_ok": last_run_ok,
                        "last_success_at": "2026-11-12T03:00:00Z"}),
            encoding="utf-8",
        )
        assert status.refresh_state() == expected
        assert status.current().current_as_of == "2026-11-12"

    def test_file_signature_of_a_missing_file_is_none(self, tmp_path):
        assert file_signature(tmp_path / "absent.db") is None


@pytest.fixture
def service(tmp_path, store) -> LawConnectorService:
    build_court_store(tmp_path / "court_store.db")
    write_status(tmp_path, "2026-11-13T03:10:00Z")
    status = ConnectorStatusService(store, stale_after_days=3, today=lambda: TODAY)
    return LawConnectorService(store=store, status=status)


class TestEveryAnswerIsDated:
    @pytest.mark.parametrize("call", [
        lambda s: s.list_codes(),
        lambda s: s.search_law("ზეპირი მოსმენა"),
        lambda s: s.search_law("zzzz"),
        lambda s: s.get_article("civil_code", "138"),
        lambda s: s.get_article("civil_code", "99999"),
        lambda s: s.browse_code("labour_code"),
        lambda s: s.browse_code("no_such_code"),
        lambda s: s.verify_citation("civil_code", "138", "უძრავი ნივთი"),
        lambda s: s.find_court_practice("ხანდაზმულობა"),
        lambda s: s.find_court_practice("zzzz"),
        lambda s: s.search("ხანდაზმულობა"),
    ])
    def test_tool_answer_carries_the_date(self, service, call):
        result = call(service)
        assert result.data_current_as_of == "2026-11-13"
        assert result.freshness_warning is None

    def test_fetch_carries_the_date_in_its_metadata(self, service):
        document = service.fetch("article:civil_code:138")
        assert document.metadata["data_current_as_of"] == "2026-11-13"
        assert "freshness_warning" not in document.metadata

    def test_overdue_check_warns_on_every_answer(self, tmp_path, service):
        write_status(tmp_path, "2026-11-01T03:10:00Z")
        assert "2026-11-01" in service.get_article("civil_code", "138").freshness_warning
        assert "2026-11-01" in service.fetch("article:civil_code:138").metadata[
            "freshness_warning"
        ]

    def test_court_answers_say_how_far_the_decisions_reach(self, service):
        newest = max(d["decision_date"] for d in _court_fixture())
        assert service.find_court_practice("ხანდაზმულობა").decisions_through == newest
        assert service.find_court_practice("zzzz").decisions_through == newest
        case_id = service.find_court_practice("ხანდაზმულობა").results[0].id
        assert service.fetch(case_id).metadata["decisions_through"] == newest


def _court_fixture() -> list[dict]:
    from tests.conftest import COURT_FIXTURE_DECISIONS

    return COURT_FIXTURE_DECISIONS


class TestReplacedStore:
    def test_a_swapped_in_store_is_served_without_a_restart(self, tmp_path, service, store):
        assert service.get_article("civil_code", "138").found
        assert service.list_codes().codes[0].version_date is None

        rebuilt = build_connector_article_store(
            tmp_path / "store.db.building", with_version_fields=True
        )
        conn = sqlite3.connect(rebuilt)
        conn.execute("DELETE FROM articles WHERE document_id = 'civil_code'")
        conn.commit()
        conn.close()
        os.replace(rebuilt, store.db_path)

        assert not service.get_article("civil_code", "138").found
        assert service.list_codes().codes[0].version_date == "2026-09-30"
        assert service.get_article("labour_code", "47").article.in_force_since == "2024-01-01"

    def test_an_unchanged_store_keeps_what_it_remembered(self, service, store):
        service.list_codes()
        remembered = service._codes
        service.list_codes()
        assert service._codes is remembered


class TestDataFolderSetting:
    def test_the_shared_service_reads_the_configured_folder(self, tmp_path, monkeypatch):
        build_connector_article_store(tmp_path / "article_store.db")
        build_court_store(tmp_path / "court_store.db")
        write_status(tmp_path, "2026-11-13T03:10:00Z")
        monkeypatch.setattr(settings, "connector_data_dir", tmp_path)
        monkeypatch.setattr(connector_module, "_connector_service", None)

        service = connector_module.get_law_connector_service()

        assert service.get_article("civil_code", "138").found
        assert service.find_court_practice("ხანდაზმულობა").status == "found"
        assert service.list_codes().data_current_as_of == "2026-11-13"
