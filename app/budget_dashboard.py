"""Three company-budget indicators for the minimal dashboard."""
from __future__ import annotations

import html
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
import streamlit as st

from core.yearly_budget import summarize_calendar_budget


def budget_indicators(proposals: pd.DataFrame, yearly: pd.DataFrame) -> list[dict[str, object]]:
    ids = set(proposals["proposal_id"].dropna().astype(str))
    visible = yearly.loc[yearly["proposal_id"].isin(ids) & yearly["project_year"].gt(0)].copy()
    annual = summarize_calendar_budget(proposals, visible, 2026)

    def coverage(rows: pd.DataFrame, column: str) -> str:
        entered = int(rows[column].notna().sum())
        if not len(rows):
            return "입력된 연차 없음"
        return f"{entered}/{len(rows)}개 연차 입력" + (" · 일부 입력" if entered < len(rows) else "")

    annual_exclusions = annual["unknown_period_count"] + annual["cross_year_count"]
    missing_projects = len(ids - set(visible["proposal_id"]))
    total_note = f" · 연차 미등록 {missing_projects}건" if missing_projects else ""
    annual_note = f" · 기간 미확인·연도 걸침 {annual_exclusions}개 제외" if annual_exclusions else ""
    return [
        {"title": "우리 총 사업비", "value": visible["our_project_cost_kkrw"].sum(min_count=1),
         "caption": "전체 연차 · 정부지원금 + 현금 + 현물", "coverage": coverage(visible, "our_project_cost_kkrw") + total_note},
        {"title": "정부지원 사업비", "value": visible["our_government_funding_kkrw"].sum(min_count=1),
         "caption": "전체 연차 · 우리 회사 정부지원금", "coverage": coverage(visible, "our_government_funding_kkrw") + total_note},
        {"title": "2026년 사업비", "value": annual["totals"]["our_project_cost_kkrw"],
         "caption": "2026년 · 우리 회사 사업비", "coverage": coverage(annual["rows"], "our_project_cost_kkrw") + annual_note + total_note},
    ]


def render_budget_cards(proposals: pd.DataFrame, yearly: pd.DataFrame) -> None:
    cards = []
    for index, item in enumerate(budget_indicators(proposals, yearly)):
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
    st.caption("수주 과제 · 입력된 우리 회사 예산 기준. 2026년은 시작·종료일이 모두 2026년인 연차만 포함합니다.")
