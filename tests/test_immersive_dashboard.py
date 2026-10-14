import pandas as pd
from streamlit.testing.v1 import AppTest

import app.main as dashboard
from core.business_logic import add_deadline_health_columns
from core.transforms import normalize_proposal_master
from core.yearly_budget import normalize_yearly_budget
from app.immersive import build_ministry_distribution


def test_dashboard_filters_budget_scope_and_ministry_projects(monkeypatch):
    proposals = add_deadline_health_columns(normalize_proposal_master(pd.DataFrame([
        {"proposal_id": "A", "project_name": "Alpha", "ministry": "국토부", "product_code": "LOOKOUT", "status_name": "수주", "total_project_cost_kkrw": 100000},
        {"proposal_id": "B", "project_name": "Beta", "ministry": "산업부", "product_code": "TITAN", "status_name": "제출 완료", "total_project_cost_kkrw": 200000},
    ])))
    yearly = normalize_yearly_budget(pd.DataFrame([
        {"제안ID": "A", "연차": 1, "연차 시작일": "2026-01-01", "연차 종료일": "2026-12-31", "우리 정부지원금(천원)": 50000, "우리 민간부담금(현금, 천원)": 0, "우리 민간부담금(현물, 천원)": 0},
        {"제안ID": "B", "연차": 1, "연차 시작일": "2026-01-01", "연차 종료일": "2026-12-31", "우리 정부지원금(천원)": 100000, "우리 민간부담금(현금, 천원)": 0, "우리 민간부담금(현물, 천원)": 0},
    ]))
    monkeypatch.setattr(dashboard, "load_dashboard_data", lambda *args: (proposals, yearly, None, "google_sheet", "", {}, []))
    app = AppTest.from_file("streamlit_app.py", default_timeout=20).run()
    assert not app.exception
    assert len(app.tabs) == 3
    budget = lambda: next(item.value for item in app.markdown if 'class="budget-stage"' in item.value)
    assert "0.50<small>억원" in budget()
    assert "전체 사업비" not in budget()
    assert not app.get("plotly_chart")
    cards = lambda: next(item.value for item in app.markdown if 'class="portfolio-projects"' in item.value)
    bars = lambda: next(item.value for item in app.markdown if 'class="ministry-bars"' in item.value)
    assert "Alpha" in cards() and "Beta" not in cards()
    assert "100.0%" in bars()
    app.radio[0].set_value("전체 과제").run()
    assert not app.exception
    assert "1.50<small>억원" in budget()
    assert "Alpha" in cards() and "Beta" in cards()
    assert "50.0%" in bars()
    app.selectbox(key="portfolio_ministry").set_value("산업부").run()
    assert not app.exception
    assert "Beta" in cards() and "Alpha" not in cards()
    app.selectbox(key="portfolio_ministry").set_value("모든 부처").run()
    app.text_input[0].set_value("Alpha").run()
    assert not app.exception
    assert "0.50<small>억원" in budget()
    app.text_input[0].set_value("no-match").run()
    assert not app.exception
    assert any("필터 조건" in warning.value for warning in app.warning)


def test_ministry_distribution_keeps_missing_ministries_in_denominator():
    result = build_ministry_distribution(pd.DataFrame({"ministry": ["국토부", " 국토부 ", "", None]}))
    assert result["count"].sum() == 4
    assert result["share"].sum() == 100
    assert dict(zip(result["ministry"], result["count"])) == {"국토부": 2, "부처 미입력": 2}
