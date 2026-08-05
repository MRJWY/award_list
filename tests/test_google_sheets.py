from pathlib import Path
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import integrations.google_sheets as google_sheets
from integrations.google_sheets import build_google_sheet_diagnostics, verify_proposal_master_row_updates


class StubWorksheet:
    def __init__(self, row_sequences: list[list[str]]) -> None:
        self._row_sequences = list(row_sequences)
        self._calls = 0

    def row_values(self, row_index: int) -> list[str]:
        assert row_index == 2
        index = self._calls if self._calls < len(self._row_sequences) else len(self._row_sequences) - 1
        self._calls += 1
        return self._row_sequences[index]


def test_verify_proposal_master_row_updates_accepts_matching_values() -> None:
    worksheet = StubWorksheet([["P-001", "수주", "Y", "1000"]])
    header_map = {
        "proposal_id": 1,
        "status_name": 2,
        "awarded_yn": 3,
        "total_project_cost_kkrw": 4,
    }

    verify_proposal_master_row_updates(
        worksheet=worksheet,
        target_row_index=2,
        header_map=header_map,
        applied_updates={
            "status_name": "수주",
            "awarded_yn": "Y",
            "total_project_cost_kkrw": "1000",
        },
        max_attempts=1,
        retry_delay_seconds=0,
    )


def test_verify_proposal_master_row_updates_retries_before_succeeding() -> None:
    worksheet = StubWorksheet(
        [
            ["P-001", "검토중", "N", "900"],
            ["P-001", "수주", "Y", "1000"],
        ]
    )
    header_map = {
        "proposal_id": 1,
        "status_name": 2,
        "awarded_yn": 3,
        "total_project_cost_kkrw": 4,
    }

    verify_proposal_master_row_updates(
        worksheet=worksheet,
        target_row_index=2,
        header_map=header_map,
        applied_updates={
            "status_name": "수주",
            "awarded_yn": "Y",
            "total_project_cost_kkrw": "1000",
        },
        max_attempts=2,
        retry_delay_seconds=0,
    )


def test_verify_proposal_master_row_updates_accepts_formatted_numeric_values() -> None:
    worksheet = StubWorksheet([["P-001", "?섏＜", "Y", "1,000"]])
    header_map = {
        "proposal_id": 1,
        "status_name": 2,
        "awarded_yn": 3,
        "total_project_cost_kkrw": 4,
    }

    verify_proposal_master_row_updates(
        worksheet=worksheet,
        target_row_index=2,
        header_map=header_map,
        applied_updates={
            "status_name": "?섏＜",
            "awarded_yn": "Y",
            "total_project_cost_kkrw": "1000",
        },
        max_attempts=1,
        retry_delay_seconds=0,
    )


def test_verify_proposal_master_row_updates_raises_on_persistent_mismatch() -> None:
    worksheet = StubWorksheet([["P-001", "검토중", "N", "900"]])
    header_map = {
        "proposal_id": 1,
        "status_name": 2,
        "awarded_yn": 3,
        "total_project_cost_kkrw": 4,
    }

    try:
        verify_proposal_master_row_updates(
            worksheet=worksheet,
            target_row_index=2,
            header_map=header_map,
            applied_updates={
                "status_name": "수주",
                "awarded_yn": "Y",
                "total_project_cost_kkrw": "1000",
            },
            max_attempts=2,
            retry_delay_seconds=0,
        )
    except RuntimeError as exc:
        message = str(exc)
        assert "status_name" in message
        assert "awarded_yn" in message
        assert "total_project_cost_kkrw" in message
    else:
        raise AssertionError("Expected RuntimeError for mismatched live row values.")


def test_build_google_sheet_diagnostics_includes_sheet_url() -> None:
    class SettingsStub:
        google_sheet_id = "sheet123"
        app_timezone = "Asia/Seoul"
        google_worksheet_proposal_master = "PROPOSAL_MASTER"
        google_worksheet_code_map_product = "CODE_MAP_PRODUCT"
        google_worksheet_code_map_status = "CODE_MAP_STATUS"
        google_worksheet_sync_log = "SYNC_LOG"
        google_service_account_json = ""
        google_service_account_json_path = ""

    diagnostics = build_google_sheet_diagnostics(SettingsStub())

    assert diagnostics["google_sheet_url"] == "https://docs.google.com/spreadsheets/d/sheet123/edit"
    assert diagnostics["app_timezone"] == "Asia/Seoul"


def test_current_timestamp_string_uses_configured_timezone(monkeypatch) -> None:
    class SettingsStub:
        app_timezone = "Asia/Seoul"

    fixed_utc = datetime(2026, 7, 26, 23, 47, 34, tzinfo=ZoneInfo("UTC"))

    def fake_current_datetime(settings) -> datetime:
        assert settings.app_timezone == "Asia/Seoul"
        return fixed_utc.astimezone(google_sheets._timezone_for_settings(settings))

    monkeypatch.setattr(google_sheets, "_current_datetime", fake_current_datetime)

    assert google_sheets._current_timestamp_string(SettingsStub()) == "2026-07-27 08:47:34"
