import pandas as pd
import pytest
from decimal import Decimal
from streamlit.testing.v1 import AppTest

import app.main as dashboard
import app.budget_dashboard as budget_dashboard
from app.budget_dashboard import budget_indicators
from core.business_logic import add_deadline_health_columns, filter_proposals
from core.transforms import normalize_proposal_master
from core.yearly_budget import normalize_yearly_budget


def data():
    proposals = add_deadline_health_columns(normalize_proposal_master(pd.DataFrame([
        {"proposal_id": "A", "project_name": "Alpha [R&D]", "product_code": "LOOKOUT", "ministry": "국토부", "owner": "김담당", "status_name": "수주", "total_project_cost_kkrw": 99999999},
        {"proposal_id": "B", "project_name": "Beta", "product_code": "TITAN", "ministry": "산업부", "status_name": "제출 완료"},
    ])))
    yearly = normalize_yearly_budget(pd.DataFrame([
        {"제안ID": "A", "연차": 1, "연차 시작일": "2026-01-01", "연차 종료일": "2026-12-31", "우리 정부지원금(천원)": 50000, "우리 민간부담금(현금, 천원)": 10000, "우리 민간부담금(현물, 천원)": 0},
        {"제안ID": "A", "연차": 2, "연차 시작일": "2027-01-01", "연차 종료일": "2027-12-31", "우리 정부지원금(천원)": 100000, "우리 민간부담금(현금, 천원)": 20000, "우리 민간부담금(현물, 천원)": 0},
        {"제안ID": "B", "연차": 1, "연차 시작일": "2026-01-01", "연차 종료일": "2026-12-31", "우리 정부지원금(천원)": 9000000, "우리 민간부담금(현금, 천원)": 0, "우리 민간부담금(현물, 천원)": 0},
    ]))
    return proposals, yearly


def test_only_three_company_budget_cards_and_one_search(monkeypatch):
    proposals, yearly = data()
    monkeypatch.setattr(dashboard, "load_dashboard_data", lambda *args: (proposals, yearly, None, "google_sheet", "", {}, []))
    monkeypatch.setattr(budget_dashboard, "load_annual_budget", lambda: {"year": 2026, "government_funding_kkrw": 230000, "as_of": "2026-10-13"})
    app = AppTest.from_file("streamlit_app.py", default_timeout=20).run()
    assert not app.exception
    assert len(app.text_input) == 1
    assert not app.tabs and not app.radio and not app.multiselect and not app.selectbox
    assert not app.expander and not app.button and not app.dataframe
    cards = lambda: next(m.value for m in app.markdown if 'class="simple-budget-grid"' in m.value)
    assert cards().count('<article') == 3
    assert "1.80<small>억원" in cards()
    assert "1.50<small>억원" in cards()
    assert "2.30<small>억원" in cards()
    assert "2026년 정부지원금" in cards() and "Excel 총괄표 · 전체 과제" in cards()
    app.text_input[0].set_value("국토부").run()
    assert not app.exception and "1.80<small>억원" in cards()
    app.text_input[0].set_value("[").run()
    assert not app.exception and "2.30<small>억원" in cards()
    app.text_input[0].set_value("Beta").run()
    assert not app.exception and any("수주 과제가 없습니다" in item.value for item in app.info)
    assert "2.30<small>억원" in cards() and cards().count('budget-missing') == 2
    app.text_input[0].set_value("").run()
    assert not app.exception and cards().count('<article') == 3


@pytest.mark.parametrize("keyword", ["LOOKOUT", "국토부", "김담당", "[R&D]", "Alpha"])
def test_unified_search_includes_replaced_filters_and_literal_symbols(keyword):
    proposals, _ = data()
    assert filter_proposals(proposals, keyword=keyword)["proposal_id"].tolist() == ["A"]


def test_company_budgets_keep_missing_and_zero_distinct():
    proposals, _ = data()
    yearly = normalize_yearly_budget(pd.DataFrame([
        {"제안ID": "A", "연차": 1, "연차 시작일": "2026-01-01", "연차 종료일": "2026-12-31", "우리 정부지원금(천원)": 0},
    ]))
    cards = budget_indicators(proposals, yearly)
    assert pd.isna(cards[0]["value"])
    assert cards[1]["value"] == 0
    assert pd.isna(cards[2]["value"])
    assert "연차 미등록 1건" in cards[0]["coverage"]


def test_excel_government_summary_is_independent_of_sheet_and_search():
    proposals, yearly = data()
    summary = {"year": 2026, "government_funding_kkrw": 230000, "as_of": "2026-10-13"}
    for visible in [proposals, proposals.iloc[:1], proposals.iloc[:0]]:
        cards = budget_indicators(visible, yearly, summary)
        assert cards[2]["value"] == 230000
        assert cards[2]["caption"] == "2026년 정부지원금"
    summary["government_funding_kkrw"] = 0
    assert budget_indicators(proposals, yearly, summary)[2]["value"] == 0


def test_private_streamlit_settings_and_environment_override(monkeypatch, tmp_path):
    settings = budget_dashboard.settings
    monkeypatch.setattr(settings, "ROOT_DIR", tmp_path)
    monkeypatch.delenv("ANNUAL_BUDGET_2026_GOVERNMENT_KKRW", raising=False)
    monkeypatch.delenv("ANNUAL_BUDGET_2026_AS_OF", raising=False)
    monkeypatch.setattr(settings, "_streamlit_secret", lambda name, default="": {
        "ANNUAL_BUDGET_2026_GOVERNMENT_KKRW": "230000.5",
        "ANNUAL_BUDGET_2026_AS_OF": "2026-10-01",
    }.get(name, default))
    assert budget_dashboard.load_annual_budget() == {
        "year": 2026, "government_funding_kkrw": Decimal("230000.5"), "as_of": "2026-10-01",
    }
    monkeypatch.setenv("ANNUAL_BUDGET_2026_GOVERNMENT_KKRW", "0")
    assert budget_dashboard.load_annual_budget()["government_funding_kkrw"] == 0


@pytest.mark.parametrize("amount,as_of", [
    ("", "2026-10-01"), ("100", ""), ("invalid", "2026-10-01"),
    ("NaN", "2026-10-01"), ("Infinity", "2026-10-01"),
    ("-1", "2026-10-01"), ("100", "2026-02-30"),
])
def test_missing_or_invalid_private_settings_do_not_fabricate_budget(monkeypatch, amount, as_of):
    monkeypatch.setattr(budget_dashboard.settings, "_load_env_file", lambda path: None)
    monkeypatch.setattr(budget_dashboard.settings, "_config_value", lambda name: {
        "ANNUAL_BUDGET_2026_GOVERNMENT_KKRW": amount,
        "ANNUAL_BUDGET_2026_AS_OF": as_of,
    }[name])
    assert budget_dashboard.load_annual_budget() == {}
