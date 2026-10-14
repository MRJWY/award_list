import pandas as pd

from core.yearly_budget import normalize_yearly_budget, summarize_calendar_budget


def test_calendar_budget_does_not_mix_years_or_prorate_unknown_periods():
    proposals = pd.DataFrame({"proposal_id": ["A", "B"]})
    rows = normalize_yearly_budget(pd.DataFrame([
        {"제안ID": "A", "연차": 2, "연차 시작일": "2026-01-01", "연차 종료일": "2026-12-31", "총사업비(천원)": 1000, "우리 정부지원금(천원)": 200, "우리 민간부담금(현금, 천원)": 0, "우리 민간부담금(현물, 천원)": 50},
        {"제안ID": "A", "연차": 3, "연차 시작일": "2027-01-01", "연차 종료일": "2027-12-31", "총사업비(천원)": 9000},
        {"제안ID": "A", "연차": 1, "연차 시작일": "2025-07-01", "연차 종료일": "2026-06-30", "총사업비(천원)": 8000},
        {"제안ID": "A", "연차": 4, "연차 종료일": "2026-12-31", "총사업비(천원)": 7000},
        {"제안ID": "filtered-out", "연차": 1, "연차 시작일": "2026-01-01", "연차 종료일": "2026-12-31", "총사업비(천원)": 6000},
    ]))
    result = summarize_calendar_budget(proposals, rows, 2026)
    assert result["totals"]["total_project_cost_kkrw"] == 1000
    assert result["totals"]["our_project_cost_kkrw"] == 250
    assert result["project_count"] == 1
    assert result["cross_year_count"] == 1
    assert result["unknown_period_count"] == 1
    assert result["without_period_count"] == 1


def test_calendar_budget_preserves_missing_zero_and_partial_coverage():
    proposals = pd.DataFrame({"proposal_id": ["A"]})
    rows = normalize_yearly_budget(pd.DataFrame([
        {"제안ID": "A", "연차": 1, "연차 시작일": "2026-01-01", "연차 종료일": "2026-06-30", "우리 정부지원금(천원)": 0},
        {"제안ID": "A", "연차": 2, "연차 시작일": "2026-07-01", "연차 종료일": "2026-12-31"},
    ]))
    result = summarize_calendar_budget(proposals, rows, 2026)
    assert result["totals"]["our_government_funding_kkrw"] == 0
    assert pd.isna(result["totals"]["our_project_cost_kkrw"])
    assert pd.isna(result["totals"]["total_project_cost_kkrw"])
    assert result["entered"]["our_government_funding_kkrw"] == 1
    assert result["period_count"] == 2


def test_calendar_budget_empty_and_invalid_periods():
    proposals = pd.DataFrame({"proposal_id": ["A"]})
    empty = summarize_calendar_budget(proposals, normalize_yearly_budget(pd.DataFrame()), 2026)
    assert empty["period_count"] == 0
    assert pd.isna(empty["totals"]["total_project_cost_kkrw"])
    rows = normalize_yearly_budget(pd.DataFrame([
        {"제안ID": "A", "연차": 1, "연차 시작일": "2026-12-31", "연차 종료일": "2026-01-01", "총사업비(천원)": 100},
    ]))
    result = summarize_calendar_budget(proposals, rows, 2026)
    assert result["period_count"] == 0
    assert result["unknown_period_count"] == 1
