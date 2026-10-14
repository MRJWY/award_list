"""Project and ministry overview with a separately scoped calendar-year budget."""
from __future__ import annotations

import html
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
import streamlit as st

from core.business_logic import status_stage_masks
from core.yearly_budget import summarize_calendar_budget


def eok(value: object) -> str:
    if pd.isna(value):
        return "미입력"
    amount = (Decimal(str(value)) / Decimal("100000")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:,.2f}<small>억원</small>"


def render_calendar_budget(proposals: pd.DataFrame, yearly: pd.DataFrame, year: int = 2026) -> pd.DataFrame:
    heading, control = st.columns([3, 1], vertical_alignment="center")
    heading.markdown(f'<div class="eyebrow">ANNUAL BUDGET / {year}</div><h2 class="overview-title">{year}년 사업비</h2>', unsafe_allow_html=True)
    scope = control.radio("사업비·과제 조회 범위", ["수주 과제", "전체 과제"], horizontal=True, key="calendar_budget_scope")
    scoped = proposals.loc[status_stage_masks(proposals)["awarded"]] if scope == "수주 과제" else proposals
    result = summarize_calendar_budget(scoped, yearly, year)
    totals, entered, count = result["totals"], result["entered"], result["period_count"]
    specs = [
        ("우리 사업비", "our_project_cost_kkrw", "정부지원금 + 민간 현금·현물"),
        ("우리 정부지원금", "our_government_funding_kkrw", "우리 회사 배정 지원금"),
    ]
    cards = []
    for label, key, caption in specs:
        coverage = f"{int(entered[key])}/{count}개 연차 입력" if count else "해당 연도에 확인된 연차 없음"
        if 0 < int(entered[key]) < count:
            coverage += " · 일부 입력"
        cards.append(f'<div class="budget-stat"><div class="budget-label">{label}</div><div class="budget-value">{eok(totals[key])}</div><div class="budget-caption">{caption}<br>{coverage}</div></div>')
    st.markdown(
        '<section class="budget-stage">'
        f'<div class="budget-topline"><span>{year} · CALENDAR YEAR</span><span>{scope} · {result["project_count"]}개 과제</span></div>'
        '<div class="budget-grid">' + ''.join(cards) + '</div>'
        '<div class="budget-footer">우리 민간부담금 &nbsp; '
        f'현금 {eok(totals["our_private_cash_kkrw"])} &nbsp; / &nbsp; 현물 {eok(totals["our_private_in_kind_kkrw"])}</div></section>',
        unsafe_allow_html=True,
    )
    st.caption(f"현재 필터 · {scope} 기준. 시작일과 종료일이 모두 {year}년인 연차의 입력 금액만 합산합니다. 우리 사업비는 세 항목이 모두 입력된 연차만 포함합니다.")
    excluded = []
    if result["unknown_period_count"]:
        excluded.append(f'기간 미확인 {result["unknown_period_count"]}개 연차')
    if result["cross_year_count"]:
        excluded.append(f'여러 연도에 걸친 {result["cross_year_count"]}개 연차')
    if result["without_period_count"]:
        excluded.append(f'연차 미등록 {result["without_period_count"]}개 과제')
    if excluded:
        st.caption("집계 제외 · " + " / ".join(excluded) + " — 날짜나 연도별 배분이 확인되면 반영됩니다.")
    with st.expander(f"{year}년 사업비 산출 내역"):
        rows = result["rows"].merge(proposals[["proposal_id", "project_name"]].drop_duplicates("proposal_id"), on="proposal_id", how="left")
        display = rows[["project_name", "project_year", "period_start", "period_end", "our_government_funding_kkrw", "our_private_cash_kkrw", "our_private_in_kind_kkrw", "our_project_cost_kkrw"]].rename(columns={
            "project_name": "과제명", "project_year": "연차", "period_start": "시작일", "period_end": "종료일",
            "our_government_funding_kkrw": "우리 정부지원금",
            "our_private_cash_kkrw": "우리 현금", "our_private_in_kind_kkrw": "우리 현물", "our_project_cost_kkrw": "우리 사업비",
        })
        st.caption("단위: 천원 · 빈칸은 미입력입니다. 실제 입력된 0원은 0으로 표시합니다.")
        st.dataframe(display, hide_index=True, use_container_width=True)

    return scoped


def build_ministry_distribution(proposals: pd.DataFrame) -> pd.DataFrame:
    ministries = proposals["ministry"].fillna("").astype(str).str.strip().replace("", "부처 미입력")
    counts = ministries.value_counts().rename_axis("ministry").reset_index(name="count")
    counts["share"] = counts["count"] / max(len(proposals), 1) * 100
    return counts.sort_values(["count", "ministry"], ascending=[False, True]).reset_index(drop=True)


def render_portfolio(proposals: pd.DataFrame) -> None:
    st.markdown('<div class="eyebrow">PROJECT PORTFOLIO</div><h3 class="overview-title">어느 부처의 어떤 과제를 맡고 있나요?</h3>', unsafe_allow_html=True)
    st.caption("상단의 수주 과제 / 전체 과제 선택과 필터가 함께 적용됩니다. 부처별 비중은 금액이 아닌 과제 건수 기준입니다.")
    if proposals.empty:
        st.info("현재 조회 범위에 해당하는 과제가 없습니다. 상단에서 전체 과제를 선택하거나 필터를 조정해 주세요.")
        return
    distribution = build_ministry_distribution(proposals)
    named_ministries = distribution.loc[distribution["ministry"].ne("부처 미입력")]
    st.markdown(f'<div class="portfolio-summary"><span>조회 과제 <strong>{len(proposals)}건</strong></span><span>담당 부처 <strong>{len(named_ministries)}개</strong></span></div>', unsafe_allow_html=True)
    left, right = st.columns([1, 1.5], gap="large")
    with left:
        st.markdown("#### 부처별 과제 분포")
        bars = ['<div class="ministry-bars">']
        for _, row in distribution.iterrows():
            label = html.escape(row["ministry"])
            bars.append(f'<div class="ministry-row"><div class="ministry-label"><strong>{label}</strong><span>{int(row["count"])}건 · {row["share"]:.1f}%</span></div><div class="ministry-track"><div class="ministry-fill" style="width:{row["share"]:.4f}%"></div></div></div>')
        st.markdown(''.join(bars) + '</div>', unsafe_allow_html=True)
        st.caption(f"분모: 현재 조회 과제 {len(proposals)}건 · 부처 미입력 과제도 포함합니다.")
    with right:
        st.markdown("#### 과제 한눈에 보기")
        choice = st.selectbox("부처별 과제 보기", ["모든 부처", *distribution["ministry"].tolist()], key="portfolio_ministry")
        ministries = proposals["ministry"].fillna("").astype(str).str.strip().replace("", "부처 미입력")
        visible = proposals if choice == "모든 부처" else proposals.loc[ministries.eq(choice)]
        st.caption(f"{choice} · {len(visible)}건")
        with st.container(height=400, border=False):
            cards = ['<div class="portfolio-projects">']
            for _, row in visible.sort_values(["ministry", "project_name"]).iterrows():
                def label(column: str) -> str:
                    value = row.get(column)
                    return html.escape(str(value).strip()) if pd.notna(value) and str(value).strip() else "미입력"
                cards.append(f'<article class="portfolio-project"><div class="project-business">{label("business_name")}</div><div class="project-name">{label("project_name")}</div><div class="project-tags"><span>{label("ministry")}</span><span>{label("product_code")}</span><span>{label("status_name")}</span><span>담당 {label("owner")}</span></div></article>')
            st.markdown(''.join(cards) + '</div>', unsafe_allow_html=True)
