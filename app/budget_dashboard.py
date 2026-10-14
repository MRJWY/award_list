"""Three company-budget indicators for the minimal dashboard."""
from __future__ import annotations

import html
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd
import streamlit as st

from core import settings


def load_annual_budget() -> dict[str, object]:
    """Read the approved Excel total from private environment/Streamlit settings."""
    settings._load_env_file(settings.ROOT_DIR / ".env")
    raw_amount = settings._config_value("ANNUAL_BUDGET_2026_GOVERNMENT_KKRW")
    raw_date = settings._config_value("ANNUAL_BUDGET_2026_AS_OF")
    if not raw_amount or not raw_date:
        return {}
    try:
        amount = Decimal(raw_amount)
        as_of = date.fromisoformat(raw_date).isoformat()
    except (InvalidOperation, ValueError):
        return {}
    if not amount.is_finite() or amount < 0:
        return {}
    return {"year": 2026, "government_funding_kkrw": amount, "as_of": as_of}


def budget_indicators(proposals: pd.DataFrame, yearly: pd.DataFrame, annual_summary: dict[str, object] | None = None) -> list[dict[str, object]]:
    ids = set(proposals["proposal_id"].dropna().astype(str))
    visible = yearly.loc[yearly["proposal_id"].isin(ids) & yearly["project_year"].gt(0)].copy()
    annual_summary = annual_summary or {}

    def coverage(rows: pd.DataFrame, column: str) -> str:
        entered = int(rows.groupby("proposal_id")[column].apply(lambda values: values.notna().all()).sum())
        if not len(rows):
            return "입력된 예산 없음"
        return f"예산 확인 {entered}/{len(ids)}개 과제" + (" · 일부 미입력" if entered < len(ids) else "")

    missing_projects = len(ids - set(visible["proposal_id"]))
    total_note = f" · 연차 미등록 {missing_projects}건" if missing_projects else ""
    source_date = annual_summary.get("as_of", "")
    return [
        {"title": "우리 총 사업비", "value": visible["our_project_cost_kkrw"].sum(min_count=1),
         "caption": "전체 연차 · 정부지원금 + 현금 + 현물", "coverage": coverage(visible, "our_project_cost_kkrw") + total_note},
        {"title": "정부지원 사업비", "value": visible["our_government_funding_kkrw"].sum(min_count=1),
         "caption": "전체 연차 · 우리 회사 정부지원금", "coverage": coverage(visible, "our_government_funding_kkrw") + total_note},
        {"title": "2026년 사업비", "value": annual_summary.get("government_funding_kkrw", float("nan")),
         "caption": "2026년 정부지원금", "coverage": f"Excel 총괄표 · 전체 과제 · {source_date} 기준" if source_date else "Excel 합계 설정 필요"},
    ]


def render_budget_cards(proposals: pd.DataFrame, yearly: pd.DataFrame) -> None:
    cards = []
    for index, item in enumerate(budget_indicators(proposals, yearly, load_annual_budget())):
        if pd.isna(item["value"]):
            value = '<span class="budget-missing">미입력</span>'
        else:
            amount = (Decimal(str(item["value"])) / Decimal("100000")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            value = f'{amount:,.2f}<small>억원</small>'
        cards.append(
            f'<article class="simple-budget-card {"current-year" if index == 2 else ""}">'
            f'<h2>{html.escape(item["title"])}</h2><div class="simple-budget-value">{value}</div>'
            f'<p>{html.escape(item["caption"])}</p><div class="simple-budget-coverage">{html.escape(item["coverage"])}</div></article>'
        )
    st.markdown('<div class="simple-budget-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)
    st.caption("상단은 전체 예산으로 검색·부처 선택에 따라 변하지 않습니다. 앞의 두 금액은 수주 과제의 입력 예산, 2026년은 Excel 총괄표의 정부지원금 기준입니다.")
