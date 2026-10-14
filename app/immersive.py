"""Immersive overview and a separately scoped calendar-year budget."""
from __future__ import annotations

import html
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.business_logic import sort_status_values, status_stage_masks
from core.yearly_budget import summarize_calendar_budget


def eok(value: object) -> str:
    if pd.isna(value):
        return "미입력"
    amount = (Decimal(str(value)) / Decimal("100000")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:,.2f}<small>억원</small>"


def render_calendar_budget(proposals: pd.DataFrame, yearly: pd.DataFrame, year: int = 2026) -> None:
    heading, control = st.columns([3, 1], vertical_alignment="center")
    heading.markdown(f'<div class="eyebrow">ANNUAL BUDGET / {year}</div><h2 class="overview-title">{year}년 사업비</h2>', unsafe_allow_html=True)
    scope = control.radio("사업비 집계 범위", ["수주 과제", "전체 과제"], horizontal=True, key="calendar_budget_scope")
    scoped = proposals.loc[status_stage_masks(proposals)["awarded"]] if scope == "수주 과제" else proposals
    result = summarize_calendar_budget(scoped, yearly, year)
    totals, entered, count = result["totals"], result["entered"], result["period_count"]
    specs = [
        ("우리 사업비", "our_project_cost_kkrw", "정부지원금 + 민간 현금·현물"),
        ("전체 사업비 · 입력분", "total_project_cost_kkrw", "컨소시엄 전체 · 입력분 합계"),
        ("우리 정부지원금", "our_government_funding_kkrw", "우리 회사 배정 지원금"),
    ]
    cards = []
    for label, key, caption in specs:
        coverage = f"{int(entered[key])}/{count}개 연차 입력" if count else "해당 연도에 확인된 연차 없음"
        if 0 < int(entered[key]) < count:
            coverage += " · 일부 입력"
        cards.append(f'<div class="budget-stat"><div class="budget-label">{label}</div><div class="budget-value">{eok(totals[key])}</div><div class="budget-caption">{caption}<br>{coverage}</div></div>')
    st.markdown(
        '<section class="budget-stage"><div class="budget-orb" aria-hidden="true"></div>'
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
        display = rows[["project_name", "project_year", "period_start", "period_end", "total_project_cost_kkrw", "our_government_funding_kkrw", "our_private_cash_kkrw", "our_private_in_kind_kkrw", "our_project_cost_kkrw"]].rename(columns={
            "project_name": "과제명", "project_year": "연차", "period_start": "시작일", "period_end": "종료일",
            "total_project_cost_kkrw": "전체 사업비", "our_government_funding_kkrw": "우리 정부지원금",
            "our_private_cash_kkrw": "우리 현금", "our_private_in_kind_kkrw": "우리 현물", "our_project_cost_kkrw": "우리 사업비",
        })
        st.caption("단위: 천원 · 빈칸은 미입력입니다. 실제 입력된 0원은 0으로 표시합니다.")
        st.dataframe(display, hide_index=True, use_container_width=True)


def build_portfolio_figure(proposals: pd.DataFrame, flat: bool = False) -> go.Figure:
    frame = proposals.copy()
    statuses = sort_status_values(frame["status_name"].fillna("미입력").unique().tolist())
    products = sorted(frame["product_code"].fillna("미입력").replace("", "미입력").unique())
    palette = ["#8c80ff", "#30d9b1", "#ffbb69", "#73bcff", "#ed8bca", "#a8b7d5"]
    figure = go.Figure()
    for index, product in enumerate(products):
        group = frame.loc[frame["product_code"].fillna("미입력").replace("", "미입력").eq(product)]
        amounts = pd.to_numeric(group["total_project_cost_kkrw"], errors="coerce")
        # Missing budgets do not become zero-value points in the visualization.
        group = group.loc[amounts.notna()]
        amounts = amounts.loc[amounts.notna()] / 100000
        if group.empty:
            continue
        labels = [f'{html.escape(str(row.get("project_name", "")))}<br>{html.escape(product)} · {html.escape(str(row["status_name"]))}<br>전체 기간 사업비 {amount:.2f}억원' for (_, row), amount in zip(group.iterrows(), amounts)]
        shared = dict(name=product, mode="markers", text=labels, hovertemplate="%{text}<extra></extra>", marker=dict(size=12 if not flat else 18, color=palette[index % len(palette)], opacity=.9, line=dict(width=1, color="#ffffff")))
        x = [statuses.index(value) for value in group["status_name"].fillna("미입력")]
        if flat:
            figure.add_trace(go.Scatter(x=x, y=amounts.tolist(), **shared))
        else:
            figure.add_trace(go.Scatter3d(x=x, y=[index] * len(group), z=amounts.tolist(), **shared))
    axis = dict(gridcolor="#303952", zerolinecolor="#46516c", color="#aebbd5", showbackground=False)
    figure.update_layout(
        height=390, margin=dict(l=12, r=12, t=12, b=12), paper_bgcolor="#111a30", plot_bgcolor="#111a30",
        font=dict(color="#dce4f5", family="Arial, sans-serif"), legend=dict(orientation="h", y=1.02, x=0),
        uirevision="portfolio-flat" if flat else "portfolio-3d",
        scene=dict(bgcolor="#111a30", xaxis=dict(**axis, title="상태", tickvals=list(range(len(statuses))), ticktext=statuses),
                   yaxis=dict(**axis, title="제품", tickvals=list(range(len(products))), ticktext=products),
                   zaxis=dict(**axis, title="전체 기간 사업비 · 억원"), camera=dict(eye=dict(x=1.5, y=1.6, z=1.05)), aspectmode="cube"),
        xaxis=dict(title="상태", tickvals=list(range(len(statuses))), ticktext=statuses, gridcolor="#303952"),
        yaxis=dict(title="전체 기간 사업비 · 억원", gridcolor="#303952"),
    )
    return figure


def render_portfolio(proposals: pd.DataFrame) -> None:
    title, view = st.columns([3, 1])
    title.markdown('<div class="eyebrow">EXPLORE THE PORTFOLIO</div><h3 class="overview-title">과제를 입체적으로 탐색하세요</h3>', unsafe_allow_html=True)
    mode = view.radio("차트 보기", ["3D", "2D"], horizontal=True, label_visibility="collapsed")
    st.plotly_chart(build_portfolio_figure(proposals, flat=mode == "2D"), use_container_width=True, theme=None,
                    config={"displaylogo": False, "scrollZoom": False}, key="portfolio_chart")
    interaction = "드래그로 회전" if mode == "3D" else "드래그로 영역 확대"
    st.caption(f"{interaction} · 도구 모음으로 확대 · 점에 마우스를 올려 과제 확인 · 범례를 눌러 제품 표시/숨김. 사업비는 원본 과제의 전체 기간 금액입니다.")
    missing = int(proposals["total_project_cost_kkrw"].isna().sum())
    if missing:
        st.caption(f"사업비 미입력 {missing}개 과제는 차트에서 제외됩니다. 아래 과제 목록에서 확인할 수 있습니다.")
