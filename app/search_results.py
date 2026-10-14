"""Compact, read-only business information shown after a keyword search."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from core.transforms import normalize_text


def registered_period(yearly: pd.DataFrame, proposal_id: str) -> str:
    rows = yearly.loc[yearly["proposal_id"].eq(proposal_id) & yearly["project_year"].gt(0)]
    if rows.empty:
        return "미입력"
    starts = pd.to_datetime(rows["period_start"], errors="coerce")
    ends = pd.to_datetime(rows["period_end"], errors="coerce")
    valid = starts.notna() & ends.notna() & starts.le(ends)
    if not valid.any():
        return "미입력"
    period = f"{starts[valid].min():%Y.%m.%d} ~ {ends[valid].max():%Y.%m.%d}"
    return period + (" · 일부 연차 미확인" if not valid.all() else "")


def business_card(row: pd.Series, yearly: pd.DataFrame) -> str:
    def text(column: str, fallback: str = "미입력") -> str:
        return html.escape(normalize_text(row.get(column)) or fallback)

    title = text("project_name", normalize_text(row.get("business_name")) or "과제명 미입력")
    period = registered_period(yearly, normalize_text(row.get("proposal_id")))
    fields = [
        ("부처", text("ministry")), ("기관", text("agency")),
        ("담당자", text("owner")), ("제품", text("product_code")),
        ("등록 연차 기간", html.escape(period)), ("협력기관", text("partner")),
    ]
    details = ''.join(f'<div><dt>{label}</dt><dd>{value}</dd></div>' for label, value in fields)
    topic = f'<p class="business-topic">{text("topic")}</p>' if normalize_text(row.get("topic")) else ""
    return (
        '<article class="business-result-card">'
        f'<div class="business-result-top"><p class="business-program">{text("business_name", "사업명 미입력")}</p>'
        f'<span class="business-status">{text("status_name", "상태 미입력")}</span></div>'
        f'<h3>{title}</h3>{topic}<dl class="business-fields">{details}</dl>'
        f'<div class="business-id">{text("proposal_id", "")}</div></article>'
    )


def render_search_results(matches: pd.DataFrame, yearly: pd.DataFrame, keyword: str) -> None:
    if not keyword.strip():
        return
    st.markdown(f"### 검색 결과 · {len(matches)}건")
    st.caption("전체 등록 사업에서 검색합니다. 상단 사업비 카드는 수주 과제 기준입니다.")
    if matches.empty:
        st.info("검색어와 일치하는 사업이 없습니다. 사업명, 과제명, 부처 또는 담당자로 검색해 보세요.")
        return
    cards = ''.join(business_card(row, yearly) for _, row in matches.iterrows())
    st.markdown(f'<div class="business-results">{cards}</div>', unsafe_allow_html=True)
