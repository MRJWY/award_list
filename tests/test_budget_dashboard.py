import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import app.main as dashboard
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
    app = AppTest.from_file("streamlit_app.py", default_timeout=20).run()
    assert not app.exception
    assert len(app.text_input) == 1
    assert not app.tabs and not app.radio and not app.multiselect and not app.selectbox
    assert not app.expander and not app.button and not app.dataframe
    cards = lambda: next(m.value for m in app.markdown if 'class="simple-budget-grid"' in m.value)
    assert cards().count('<article') == 3
    assert "1.80<small>억원" in cards()
    assert "1.50<small>억원" in cards()
    assert "0.60<small>억원" in cards()
    app.text_input[0].set_value("국토부").run()
    assert not app.exception and "1.80<small>억원" in cards()
    app.text_input[0].set_value("[").run()
    assert not app.exception and "0.60<small>억원" in cards()
    app.text_input[0].set_value("Beta").run()
    assert not app.exception and any("수주 과제가 없습니다" in item.value for item in app.info)
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
