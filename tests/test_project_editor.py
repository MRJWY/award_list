import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import app.project_editor as editor
import integrations.google_sheets as sheets


@pytest.fixture(autouse=True)
def authenticated_editor(monkeypatch):
    monkeypatch.setattr(editor, "can_edit", lambda: True)


def editor_app():
    return AppTest.from_string('''
import pandas as pd
from app.project_editor import render_info_form, render_budget_form
from core.transforms import normalize_proposal_master
from core.yearly_budget import normalize_yearly_budget
row = normalize_proposal_master(pd.DataFrame([{
    "proposal_id": "TEST-A", "business_name": "샘플 사업", "project_name": "샘플 과제",
    "owner": "기존 담당", "product_code": "LOOKOUT", "status_name": "수주", "submission_deadline": "2026-05-01"
}])).iloc[0]
yearly = normalize_yearly_budget(pd.DataFrame([{
    "제안ID": "TEST-A", "연차": 1, "연차 시작일": "2026-01-01", "연차 종료일": "2026-12-31",
    "우리 정부지원금(천원)": 100, "우리 민간부담금(현금, 천원)": 0,
    "우리 민간부담금(현물, 천원)": 20
}]))
render_info_form(row, [{"code": "LOOKOUT"}, {"code": "TITAN"}])
render_budget_form(row, yearly)
'''.encode("ascii", "backslashreplace").decode("ascii")).run()


def field(app, label):
    return next(item for item in app.text_input if item.label == label)


def submit(app, label):
    return next(item for item in app.button if item.label == label).click().run()


def test_info_save_only_changed_fields_and_no_write_on_render(monkeypatch):
    calls = []
    monkeypatch.setattr(editor, "update_proposal_master_record", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(editor, "load_settings", lambda: object())
    monkeypatch.setattr(editor, "finish_save", lambda message: None)
    app = editor_app()
    assert not app.exception and not calls
    assert field(app, "제출 마감일").value == "2026-05-01"
    field(app, "담당자").set_value("새 담당")
    app = submit(app, "기본 정보 저장")
    assert not app.exception and len(calls) == 1
    assert calls[0][0][1:] == ("TEST-A", {"owner": "새 담당"})
    assert calls[0][1]["expected"] == {"owner": "기존 담당"}


def test_yearly_form_preserves_zero_blank_and_selected_year(monkeypatch):
    calls = []
    monkeypatch.setattr(editor, "upsert_yearly_budget_record", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(editor, "load_settings", lambda: object())
    monkeypatch.setattr(editor, "finish_save", lambda message: None)
    app = editor_app()
    field(app, "우리 정부지원금").set_value("200")
    app = submit(app, "연차별 예산 저장")
    assert not app.exception and len(calls) == 1
    args, kwargs = calls[0]
    assert args[1:3] == ("TEST-A", 1)
    assert args[3]["our_government_funding_kkrw"] == 200
    assert args[3]["our_private_cash_kkrw"] == 0
    assert args[3]["total_project_cost_kkrw"] is None
    assert kwargs["period_start"] == "2026-01-01"
    assert kwargs["expected"]["our_government_funding_kkrw"] == 100
    app.selectbox(key="editor_year_TEST-A").set_value(2).run()
    assert field(app, "우리 정부지원금").value == ""


@pytest.mark.parametrize("label,value", [("우리 정부지원금", "-1"), ("연차 시작일", "2027-01-01"), ("연차 종료일", "2026-02-30")])
def test_invalid_budget_never_writes(monkeypatch, label, value):
    calls = []
    monkeypatch.setattr(editor, "upsert_yearly_budget_record", lambda *args, **kwargs: calls.append(args))
    app = editor_app()
    field(app, label).set_value(value)
    app = submit(app, "연차별 예산 저장")
    assert not app.exception and app.error and not calls


def test_save_error_keeps_form_values(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("시트 연결 실패")
    monkeypatch.setattr(editor, "update_proposal_master_record", fail)
    app = editor_app()
    field(app, "사업명").set_value("입력 유지")
    app = submit(app, "기본 정보 저장")
    assert app.error and field(app, "사업명").value == "입력 유지"


def test_stale_snapshot_and_literal_values():
    sheets.assert_row_unchanged(["1,000", "담당"], {"our_government_funding_kkrw": 1, "owner": 2}, {"our_government_funding_kkrw": 1000.0})
    with pytest.raises(RuntimeError, match="다른 사용자"):
        sheets.assert_row_unchanged(["새 담당"], {"owner": 1}, {"owner": "기존 담당"})
    assert sheets._literal_sheet_value("notes", "=1+1") == "=1+1"
    assert sheets._literal_sheet_value("our_government_funding_kkrw", "200") == 200


def test_edit_link_escapes_identifiers_and_context():
    from app.portfolio import project_row, timeline_axis
    from core.transforms import normalize_proposal_master
    from core.yearly_budget import normalize_yearly_budget
    from datetime import date
    proposal = normalize_proposal_master(pd.DataFrame([{"proposal_id": 'A"&', "business_name": "샘플"}]))
    yearly = normalize_yearly_budget(pd.DataFrame())
    rendered = project_row(proposal.iloc[0], yearly, timeline_axis(proposal, yearly, date(2026, 1, 1)), date(2026, 1, 1))
    assert '?edit_project=A%22%26' in rendered and 'target="_self">수정</a>' in rendered


def test_master_writer_preserves_other_columns_and_checks_conflicts(monkeypatch):
    from types import SimpleNamespace
    from core.transforms import PROPOSAL_MASTER_COLUMNS
    headers = list(PROPOSAL_MASTER_COLUMNS)
    record = {"proposal_id": "TEST-A", "business_name": "기존 사업", "owner": "담당", "status_name": "수주", "awarded_yn": "Y"}

    class Worksheet:
        def __init__(self):
            self.rows = [headers, [record.get(key, "") for key in headers]]
            self.writes = 0

        def row_values(self, index):
            return list(self.rows[index - 1])

        def col_values(self, index):
            return [row[index - 1] for row in self.rows]

        def update_cells(self, cells, **kwargs):
            assert kwargs["value_input_option"] == "RAW"
            self.writes += 1
            for cell in cells:
                self.rows[cell.row - 1][cell.col - 1] = cell.value

    sheet = Worksheet()
    settings = SimpleNamespace(google_service_account_json_path="configured", google_service_account_json="",
                               google_sheet_id="test-sheet", google_worksheet_proposal_master="PROPOSAL_MASTER", app_timezone="Asia/Seoul")
    monkeypatch.setattr(sheets, "_open_workbook", lambda _: SimpleNamespace(worksheet=lambda _: sheet))
    monkeypatch.setattr(sheets, "append_sync_log_entry", lambda **kwargs: None)
    monkeypatch.setattr(sheets, "_update_cache_csv_row", lambda *args: None)
    sheets.update_proposal_master_record(settings, "TEST-A", {"business_name": "=literal"}, expected={"business_name": "기존 사업"})
    assert sheet.writes == 1
    assert sheet.rows[1][headers.index("business_name")] == "=literal"
    assert sheet.rows[1][headers.index("owner")] == "담당"
    with pytest.raises(RuntimeError, match="다른 사용자"):
        sheets.update_proposal_master_record(settings, "TEST-A", {"business_name": "덮어쓰기"}, expected={"business_name": "기존 사업"})
    assert sheet.writes == 1


def test_editor_access_denies_missing_wrong_expired_and_rotated_password(monkeypatch):
    from types import SimpleNamespace
    import app.edit_access as access
    state = {}
    monkeypatch.setattr(access, "st", SimpleNamespace(session_state=state))
    monkeypatch.setattr(access, "edit_password", lambda: "")
    assert not access.can_edit()
    monkeypatch.setattr(access, "edit_password", lambda: "synthetic-test-password")
    state["editor_password_input"] = "wrong"
    access.unlock_editor()
    assert not access.can_edit() and "editor_password_input" not in state
    state["editor_password_input"] = "synthetic-test-password"
    access.unlock_editor()
    assert access.can_edit() and "editor_password_input" not in state
    state["editor_access"]["expires"] = 0
    assert not access.can_edit()
    state["editor_password_input"] = "synthetic-test-password"
    access.unlock_editor()
    monkeypatch.setattr(access, "edit_password", lambda: "rotated-test-password")
    assert not access.can_edit()


@pytest.mark.parametrize("button,label", [("기본 정보 저장", "사업명"), ("연차별 예산 저장", "우리 정부지원금")])
def test_unauthenticated_save_is_blocked(monkeypatch, button, label):
    calls = []
    monkeypatch.setattr(editor, "can_edit", lambda: False)
    monkeypatch.setattr(editor, "update_proposal_master_record", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(editor, "upsert_yearly_budget_record", lambda *args, **kwargs: calls.append(args))
    app = editor_app()
    field(app, label).set_value("300")
    app = submit(app, button)
    assert not app.exception and app.error and not calls


def test_password_form_unlocks_without_retaining_plaintext(monkeypatch):
    import app.edit_access as access
    monkeypatch.setattr(access, "edit_password", lambda: "synthetic-test-password")
    app = AppTest.from_string('''
import streamlit as st
from app.edit_access import require_editor_access
if require_editor_access():
    st.success("unlocked")
''').run()
    assert not app.success
    app.text_input[0].set_value("wrong")
    app.button[0].click().run()
    assert app.error and not app.success
    app.text_input[0].set_value("synthetic-test-password")
    app.button[0].click().run()
    assert not app.exception and app.success[0].value == "unlocked"
    assert "editor_password_input" not in app.session_state
