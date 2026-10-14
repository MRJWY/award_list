import pandas as pd
import pytest
from decimal import Decimal
from datetime import date
from streamlit.testing.v1 import AppTest

import app.main as dashboard
import app.budget_dashboard as budget_dashboard
from app.budget_dashboard import budget_indicators
from app.search_results import business_card, registered_period
from app.portfolio import ministry_summary, visible_projects, project_period, timeline_axis, timeline_html, project_row
from core.business_logic import add_deadline_health_columns, filter_proposals
from core.transforms import normalize_proposal_master
from core.yearly_budget import normalize_yearly_budget


def data():
    proposals = add_deadline_health_columns(normalize_proposal_master(pd.DataFrame([
        {"proposal_id": "A", "business_name": "실증 지원사업", "project_name": "Alpha [R&D]", "product_code": "LOOKOUT", "ministry": "국토부", "agency": "지원기관", "owner": "김담당", "status_name": "수주", "total_project_cost_kkrw": 99999999},
        {"proposal_id": "B", "project_name": "Beta", "product_code": "TITAN", "ministry": "산업부", "status_name": "제출 완료"},
    ])))
    yearly = normalize_yearly_budget(pd.DataFrame([
        {"제안ID": "A", "연차": 1, "연차 시작일": "2026-01-01", "연차 종료일": "2026-12-31", "우리 정부지원금(천원)": 50000, "우리 민간부담금(현금, 천원)": 10000, "우리 민간부담금(현물, 천원)": 0},
        {"제안ID": "A", "연차": 2, "연차 시작일": "2027-01-01", "연차 종료일": "2027-12-31", "우리 정부지원금(천원)": 100000, "우리 민간부담금(현금, 천원)": 20000, "우리 민간부담금(현물, 천원)": 0},
        {"제안ID": "B", "연차": 1, "연차 시작일": "2026-01-01", "연차 종료일": "2026-12-31", "우리 정부지원금(천원)": 9000000, "우리 민간부담금(현금, 천원)": 0, "우리 민간부담금(현물, 천원)": 0},
    ]))
    return proposals, yearly


def test_fixed_budget_cards_and_filterable_project_board(monkeypatch):
    proposals, yearly = data()
    monkeypatch.setattr(dashboard, "load_dashboard_data", lambda *args: (proposals, yearly, None, "google_sheet", "", {}, []))
    monkeypatch.setattr(budget_dashboard, "load_annual_budget", lambda: {"year": 2026, "government_funding_kkrw": 230000, "as_of": "2026-10-13"})
    # Streamlit 1.51's test runner cannot serialize pills on a second run.
    # Exercise each initial state here; real reruns are verified in the browser.
    def run_state(keyword="", ministry="전체"):
        instance = AppTest.from_file("streamlit_app.py", default_timeout=20)
        instance.session_state["dashboard_search"] = keyword
        instance.session_state["portfolio_ministry"] = ministry
        return instance.run()
    app = run_state()
    assert not app.exception
    assert len(app.text_input) == 1
    assert not app.tabs and not app.radio and not app.multiselect and not app.selectbox
    assert not app.expander and not app.button and not app.dataframe
    cards = lambda: next(m.value for m in app.markdown if 'class="simple-budget-grid"' in m.value)
    results = lambda: [m.value for m in app.markdown if 'class="portfolio-board"' in m.value]
    assert len(results()) == 1 and results()[0].count('<details') == 1
    assert '<summary' in results()[0] and '<table' in results()[0]
    assert cards().count('<article') == 3
    assert "1.80<small>억원" in cards()
    assert "1.50<small>억원" in cards()
    assert "2.30<small>억원" in cards()
    assert "2026년 정부지원금" in cards() and "Excel 총괄표 · 전체 과제" in cards()
    original_cards = cards()
    app = run_state("국토부")
    assert not app.exception and cards() == original_cards
    assert len(results()) == 1
    assert "Alpha [R&amp;D]" in results()[0] and "Beta" not in results()[0]
    for value in ["실증 지원사업", "지원기관", "김담당", "LOOKOUT", "2026.01.01 ~ 2027.12.31"]:
        assert value in results()[0]
    app = run_state("[")
    assert not app.exception and "2.30<small>억원" in cards()
    app = run_state("Beta")
    assert not app.exception and not app.info
    assert "Beta" in results()[0] and "제출 완료" in results()[0]
    assert cards() == original_cards
    app = run_state("Beta", "국토부")
    assert not results() and cards() == original_cards
    app = run_state("a")
    assert results()[0].count('<details') == 2
    app = run_state("no matching project")
    assert not results() and any("조건에 맞는 과제가 없습니다" in item.value for item in app.info)
    app = run_state()
    assert not app.exception and cards().count('<article') == 3
    assert results()[0].count('<details') == 1 and cards() == original_cards
    app = run_state("   ")
    assert results()[0].count('<details') == 1


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


def test_business_details_escape_sheet_text_and_do_not_invent_dates():
    proposals, yearly = data()
    row = proposals.iloc[0].copy()
    row["project_name"] = '<script>alert("test")</script>'
    row["agency"] = pd.NA
    yearly.loc[1, "period_end"] = "2026-01-01"  # Before this row's start.
    rendered = business_card(row, yearly)
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert "<NA>" not in rendered and "미입력" in rendered
    assert registered_period(yearly, "A") == "2026.01.01 ~ 2026.12.31 · 일부 연차 미확인"
    assert registered_period(yearly, "unknown") == "미입력"


def test_ministry_distribution_sums_each_project_once_and_preserves_unknowns():
    proposals, yearly = data()
    proposals.loc[0, "ministry"] = "중소기업벤처부"
    proposals.loc[1, "ministry"] = ""
    groups = {r["name"]: r for r in ministry_summary(proposals, yearly)}
    assert groups["중소벤처기업부"]["count"] == 1
    assert groups["중소벤처기업부"]["funding"] == 150000
    assert groups["부처 미확인"]["count"] == 1
    assert visible_projects(proposals, "", "전체").proposal_id.tolist() == ["A"]
    assert visible_projects(proposals, "Beta", "부처 미확인").proposal_id.tolist() == ["B"]


def test_common_timeline_and_partial_period_dont_imply_completion():
    proposals, yearly = data()
    today = date(2026, 10, 14)
    axis = timeline_axis(proposals, yearly, today)
    assert axis == (pd.Timestamp("2026-01-01"), pd.Timestamp("2028-01-01"))
    rendered = timeline_html(project_period(yearly, "A"), axis, today)
    assert 'today-line' in rendered and '2026.01 – 2027.12' in rendered
    yearly.loc[1, "period_end"] = ""
    assert not project_period(yearly, "A")[2]
    rendered = project_row(proposals.iloc[0], yearly, axis, today)
    assert "기간 일부 확인" in rendered and "기간 종료" not in rendered
    assert "기간 미확인" in timeline_html(project_period(yearly, "unknown"), axis, today)
