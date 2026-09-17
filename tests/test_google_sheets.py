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


class CapacityWorksheetStub:
    def __init__(self, column_values: list[str], row_count: int, col_count: int) -> None:
        self._column_values = list(column_values)
        self.row_count = row_count
        self.col_count = col_count
        self.resize_calls: list[tuple[int, int]] = []

    def col_values(self, column_index: int) -> list[str]:
        assert column_index == 1
        return list(self._column_values)

    def resize(self, *, rows: int, cols: int) -> None:
        self.row_count = rows
        self.col_count = cols
        self.resize_calls.append((rows, cols))


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


def test_prepare_worksheet_for_append_resizes_when_next_row_exceeds_grid() -> None:
    worksheet = CapacityWorksheetStub(
        column_values=["header"] + [f"row-{index}" for index in range(1, 201)],
        row_count=201,
        col_count=65,
    )

    google_sheets._prepare_worksheet_for_append(worksheet, ["value"] * 65)

    assert worksheet.resize_calls == [(202, 65)]


def test_prepare_worksheet_for_append_resizes_when_row_width_exceeds_grid() -> None:
    worksheet = CapacityWorksheetStub(
        column_values=["header", "row-1"],
        row_count=100,
        col_count=3,
    )

    google_sheets._prepare_worksheet_for_append(worksheet, ["a", "b", "c", "d", "e"])

    assert worksheet.resize_calls == [(100, 5)]


def test_prepare_worksheet_for_append_skips_resize_when_grid_is_already_large_enough() -> None:
    worksheet = CapacityWorksheetStub(
        column_values=["header", "row-1"],
        row_count=500,
        col_count=20,
    )

    google_sheets._prepare_worksheet_for_append(worksheet, ["a", "b", "c"])

    assert worksheet.resize_calls == []
