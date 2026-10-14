import pandas as pd
from streamlit.testing.v1 import AppTest

import app.main as dashboard
from core.business_logic import add_deadline_health_columns
from core.transforms import normalize_proposal_master
from core.yearly_budget import normalize_yearly_budget


def test_dashboard_filters_scope_and_view_switch_without_errors(monkeypatch):
    proposals = add_deadline_health_columns(normalize_proposal_master(pd.DataFrame([
        {"proposal_id": "A", "project_name": "Alpha", "product_code": "LOOKOUT", "status_name": "수주", "total_project_cost_kkrw": 100000},
        {"proposal_id": "B", "project_name": "Beta", "product_code": "TITAN", "status_name": "제출 완료", "total_project_cost_kkrw": 200000},
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
    app.radio[0].set_value("전체 과제").run()
    assert not app.exception
    assert "1.50<small>억원" in budget()
    app.radio[1].set_value("2D").run()
    assert not app.exception
    app.text_input[0].set_value("Alpha").run()
    assert not app.exception
    assert "0.50<small>억원" in budget()
    app.text_input[0].set_value("no-match").run()
    assert not app.exception
    assert any("필터 조건" in warning.value for warning in app.warning)
