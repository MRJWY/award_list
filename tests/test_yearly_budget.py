import pandas as pd
import pytest

from core.yearly_budget import build_project_yearly_matrix, normalize_yearly_budget, validate_yearly_budget_amounts
from core.yearly_budget import YEARLY_BUDGET_SHEET_HEADERS
import integrations.google_sheets as google_sheets


def test_yearly_budget_keeps_project_year_separate_from_calendar_year() -> None:
    rows = pd.DataFrame([
        {
            "제안ID": "PROP-001",
            "연차": 2,
            "총사업비(천원)": "1,000",
            "우리 정부지원금(천원)": 300,
            "우리 민간부담금(현금, 천원)": 100,
            "우리 민간부담금(현물, 천원)": 50,
        }
    ])
    normalized = normalize_yearly_budget(rows)
    assert normalized.loc[0, "project_year"] == 2
    assert normalized.loc[0, "total_project_cost_kkrw"] == 1000
    assert normalized.loc[0, "our_project_cost_kkrw"] == 450


def test_our_total_is_missing_until_all_components_are_entered() -> None:
    rows = pd.DataFrame([{
        "제안ID": "PROP-001",
        "연차": 1,
        "총사업비(천원)": 1000,
        "우리 정부지원금(천원)": 300,
    }])
    normalized = normalize_yearly_budget(rows)
    assert pd.isna(normalized.loc[0, "our_project_cost_kkrw"])


def test_yearly_budget_rejects_our_allocation_above_project_total() -> None:
    with pytest.raises(ValueError, match="전체 총사업비"):
        validate_yearly_budget_amounts({
            "total_project_cost_kkrw": 100,
            "our_government_funding_kkrw": 90,
            "our_private_cash_kkrw": 20,
            "our_private_in_kind_kkrw": 0,
        })


def test_yearly_budget_accepts_zero_as_entered_amount() -> None:
    actual = validate_yearly_budget_amounts({
        "total_project_cost_kkrw": "1,000",
        "our_government_funding_kkrw": "500",
        "our_private_cash_kkrw": "0",
        "our_private_in_kind_kkrw": "100",
    })
    assert actual["our_private_cash_kkrw"] == 0


def test_project_matrix_puts_each_year_beside_the_project() -> None:
    proposals = pd.DataFrame([{
        "proposal_id": "PROP-011", "business_name": "사업 A", "project_name": "과제 A",
    }])
    yearly = normalize_yearly_budget(pd.DataFrame([
        {"제안ID": "PROP-011", "연차": 1, "연차 시작일": "2026-07-01", "연차 종료일": "2027-06-30", "총사업비(천원)": 1000,
         "우리 정부지원금(천원)": 300, "우리 민간부담금(현금, 천원)": 100,
         "우리 민간부담금(현물, 천원)": 50},
        {"제안ID": "PROP-011", "연차": 2, "연차 시작일": "2027-07-01", "연차 종료일": "2028-06-30", "총사업비(천원)": 2000,
         "우리 정부지원금(천원)": 600, "우리 민간부담금(현금, 천원)": 200,
         "우리 민간부담금(현물, 천원)": 100},
    ]))
    matrix = build_project_yearly_matrix(proposals, yearly)
    assert matrix.loc[0, "1차년도 기간"] == "2026-07-01 ~ 2027-06-30"
    assert matrix.loc[0, "2차년도 기간"] == "2027-07-01 ~ 2028-06-30"
    assert matrix.loc[0, "1차년도 우리사업비"] == 450
    assert matrix.loc[0, "2차년도 우리사업비"] == 900
    assert matrix.loc[0, "연차별 우리 합계"] == 1350
    assert pd.isna(matrix.loc[0, "3차년도 우리사업비"])


def test_yearly_budget_save_updates_same_proposal_and_year(monkeypatch) -> None:
    class Worksheet:
        row_count = 100
        col_count = 10

        def __init__(self, rows):
            self.rows = rows

        def row_values(self, index):
            return self.rows[index - 1]

        def col_values(self, index):
            return [row[index - 1] for row in self.rows if len(row) >= index and row[index - 1] != ""]

        def get_all_values(self):
            return self.rows

        def append_row(self, values, **kwargs):
            self.rows.append(values)

        def update_cells(self, cells, **kwargs):
            for cell in cells:
                self.rows[cell.row - 1][cell.col - 1] = cell.value

    master = Worksheet([["제안ID"], ["PROP-001"]])
    yearly = Worksheet([YEARLY_BUDGET_SHEET_HEADERS.copy()])

    class Workbook:
        def worksheet(self, name):
            return {"PROPOSAL_MASTER": master, "PROJECT_YEAR_BUDGET": yearly}[name]

    class Settings:
        google_service_account_json_path = "configured"
        google_service_account_json = ""
        google_sheet_id = "sheet-id"
        google_worksheet_proposal_master = "PROPOSAL_MASTER"
        google_worksheet_yearly_budget = "PROJECT_YEAR_BUDGET"
        app_timezone = "Asia/Seoul"

    monkeypatch.setattr(google_sheets, "_open_workbook", lambda settings: Workbook())
    monkeypatch.setattr(google_sheets, "append_sync_log_entry", lambda *args, **kwargs: None)
    amounts = {
        "total_project_cost_kkrw": 1000,
        "our_government_funding_kkrw": 300,
        "our_private_cash_kkrw": 100,
        "our_private_in_kind_kkrw": 50,
    }
    google_sheets.upsert_yearly_budget_record(Settings(), "PROP-001", 1, amounts)
    assert len(yearly.rows) == 2
    assert yearly.rows[1][:8] == ["PROP-001", "1", "", "", "1000", "300", "100", "50"]

    amounts["our_government_funding_kkrw"] = 350
    google_sheets.upsert_yearly_budget_record(Settings(), "PROP-001", 1, amounts)
    assert len(yearly.rows) == 2
    assert yearly.rows[1][5] == "350"
