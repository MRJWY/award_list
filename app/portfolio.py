"""A compact project board with ministry filters and a shared calendar axis."""
from __future__ import annotations

import html
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from app.search_results import business_card
from core.business_logic import filter_proposals, status_stage_masks
from core.transforms import normalize_text


def ministry_name(value: object) -> str:
    name = normalize_text(value)
    return {"중소기업벤처부": "중소벤처기업부"}.get(name, name) or "부처 미확인"


def money(value: object) -> str:
    if pd.isna(value):
        return "미입력"
    amount = (Decimal(str(value)) / Decimal("100000")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:,.2f}억"


def project_period(yearly: pd.DataFrame, proposal_id: str) -> tuple[object, object, bool]:
    rows = yearly.loc[yearly.proposal_id.eq(proposal_id) & yearly.project_year.gt(0)]
    starts = pd.to_datetime(rows.period_start, errors="coerce")
    ends = pd.to_datetime(rows.period_end, errors="coerce")
    valid = starts.notna() & ends.notna() & starts.le(ends)
    if not valid.any():
        return None, None, False
    return starts[valid].min(), ends[valid].max(), bool(valid.all())


def ministry_summary(proposals: pd.DataFrame, yearly: pd.DataFrame) -> list[dict]:
    result = []
    grouped = proposals.assign(ministry_group=proposals.ministry.map(ministry_name))
    for name, projects in grouped.groupby("ministry_group", sort=True):
        rows = yearly.loc[yearly.proposal_id.isin(projects.proposal_id) & yearly.project_year.gt(0)]
        known = rows.loc[rows.our_government_funding_kkrw.notna(), "proposal_id"].nunique()
        result.append({"name": name, "count": len(projects), "funding": rows.our_government_funding_kkrw.sum(min_count=1), "known": known})
    return sorted(result, key=lambda x: (x["name"] == "부처 미확인", -x["count"], x["name"]))


def visible_projects(proposals: pd.DataFrame, keyword: str, ministry: str) -> pd.DataFrame:
    base = proposals if keyword.strip() else proposals.loc[status_stage_masks(proposals)["awarded"]]
    visible = filter_proposals(base, keyword=keyword)
    if ministry != "전체":
        visible = visible.loc[visible.ministry.map(ministry_name).eq(ministry)]
    return visible


def timeline_axis(proposals: pd.DataFrame, yearly: pd.DataFrame, today: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    periods = [project_period(yearly, str(pid)) for pid in proposals.proposal_id]
    years = [today.year] + [int(t.year) for start, end, _ in periods for t in (start, end) if t is not None]
    return pd.Timestamp(min(years), 1, 1), pd.Timestamp(max(years) + 1, 1, 1)


def timeline_html(period: tuple, axis: tuple, today: date) -> str:
    start, end, complete = period
    if start is None:
        return '<span class="period-unknown">기간 미확인</span>'
    axis_start, axis_end = axis
    days = (axis_end - axis_start).days
    left = max(0, (start - axis_start).days / days * 100)
    width = max(.3, min(100 - left, ((end - start).days + 1) / days * 100))
    marker = (pd.Timestamp(today) - axis_start).days / days * 100
    today_line = f'<i class="today-line" style="left:{marker:.3f}%" title="오늘 {today.isoformat()}"></i>' if 0 <= marker <= 100 else ""
    label = f"{start:%Y.%m} – {end:%Y.%m}" + (" · 일부 확인" if not complete else "")
    return f'<div class="period-track"><span class="period-fill {"partial" if not complete else ""}" style="left:{left:.3f}%;width:{width:.3f}%"></span>{today_line}</div><small>{label}</small>'


def year_table(yearly: pd.DataFrame, proposal_id: str) -> str:
    rows = yearly.loc[yearly.proposal_id.eq(proposal_id) & yearly.project_year.gt(0)].sort_values("project_year")
    if rows.empty:
        return '<p class="year-empty">등록된 연차별 예산이 없습니다.</p>'
    body = []
    for _, row in rows.iterrows():
        values = [f'{int(row.project_year)}차년도', normalize_text(row.period_start) or "미확인", normalize_text(row.period_end) or "미확인"]
        values += ["미입력" if pd.isna(row[col]) else f'{Decimal(str(row[col])):,.0f}' for col in ["our_government_funding_kkrw", "our_private_cash_kkrw", "our_private_in_kind_kkrw", "our_project_cost_kkrw"]]
        body.append('<tr>' + ''.join(f'<td>{html.escape(value)}</td>' for value in values) + '</tr>')
    headings = ["연차", "시작일", "종료일", "정부지원금", "현금", "현물", "우리 사업비"]
    return '<div class="year-budget"><p>연차별 우리 예산 · 단위: 천원</p><table><thead><tr>' + ''.join(f'<th>{h}</th>' for h in headings) + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div>'


def project_row(row: pd.Series, yearly: pd.DataFrame, axis: tuple, today: date) -> str:
    esc = lambda value, fallback="미입력": html.escape(normalize_text(value) or fallback)
    name = normalize_text(row.business_name) or normalize_text(row.project_name) or "과제명 미입력"
    name = re.sub(r"^20\d{2}(?:년도|년)?\s*", "", name).replace("\n", " ")
    period = project_period(yearly, str(row.proposal_id))
    start, end, complete = period
    phase = "기간 미확인"
    if start is not None and complete:
        phase = "시작 예정" if pd.Timestamp(today) < start else "기간 종료" if pd.Timestamp(today) > end else "진행 중"
    elif start is not None:
        phase = "기간 일부 확인"
    detail = business_card(row, yearly) + year_table(yearly, str(row.proposal_id))
    return (
        '<details class="project-row"><summary class="project-grid">'
        f'<div class="project-title"><strong>{html.escape(name)}</strong><small>{esc(row.project_name, "정식 과제명 미확인")}</small></div>'
        f'<div class="project-product">{esc(row.product_code)}</div><div class="project-owner">{esc(row.owner)}</div>'
        f'<div class="project-period">{timeline_html(period, axis, today)}</div>'
        f'<div class="project-state"><span>{esc(row.status_name)}</span><small>{phase}</small></div>'
        f'<span class="project-chevron" aria-hidden="true">⌄</span></summary><div class="project-expanded">{detail}</div></details>'
    )


def render_portfolio(proposals: pd.DataFrame, yearly: pd.DataFrame, keyword: str) -> None:
    awarded = proposals.loc[status_stage_masks(proposals)["awarded"]]
    groups = ministry_summary(awarded, yearly)
    st.markdown('<div class="portfolio-heading"><h2>과제 현황</h2><span>수주 과제의 부처별 분포 · 정부지원금 기준</span></div>', unsafe_allow_html=True)
    labels = {"전체": f"전체 · {len(awarded)}건"}
    short = {"중소벤처기업부": "중기부", "과학기술정보통신부": "과기정통부", "산업통상자원부": "산업부", "서울특별시": "서울시", "국토교통부": "국토부"}
    colors = ["#7866d8", "#559ba3", "#7997c4", "#bd9e69", "#a5acbb", "#897daa"]
    segments = []
    for i, group in enumerate(groups):
        label = f'{short.get(group["name"], group["name"])} · {group["count"]}건 · {money(group["funding"])}'
        if group["known"] < group["count"] and group["known"]:
            label += " (일부)"
        labels[group["name"]] = label
        tooltip = html.escape(label, quote=True)
        segments.append(f'<span style="width:{group["count"] / max(len(awarded), 1) * 100:.2f}%;background:{colors[i % len(colors)]}" title="{tooltip}"></span>')
    st.markdown('<div class="ministry-strip" aria-label="부처별 과제 수 비율">' + ''.join(segments) + '</div>', unsafe_allow_html=True)
    options = list(labels)
    if st.session_state.get("portfolio_ministry") not in options:
        st.session_state["portfolio_ministry"] = "전체"
    ministry = st.pills("부처 선택", options, format_func=labels.get, key="portfolio_ministry", label_visibility="collapsed") or "전체"
    visible = visible_projects(proposals, keyword, ministry)
    st.caption(f'{"검색 결과" if keyword.strip() else "수주 과제"} {len(visible)}건 · 행을 누르면 상세정보와 연차별 예산이 펼쳐집니다. 검색은 전체 등록 사업에서 찾습니다.')
    if visible.empty:
        st.info("조건에 맞는 과제가 없습니다. 검색어 또는 부처 선택을 바꿔 보세요.")
        return
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    axis = timeline_axis(proposals, yearly, today)
    header = f'<div class="project-grid project-header"><span>과제명</span><span>제품</span><span>담당자</span><span>등록 수행기간 <small>{axis[0].year} — {axis[1].year-1} · 세로선: 오늘</small></span><span>상태</span><span></span></div>'
    rows = ''.join(project_row(row, yearly, axis, today) for _, row in visible.iterrows())
    st.markdown('<div class="portfolio-board">' + header + rows + '</div>', unsafe_allow_html=True)
