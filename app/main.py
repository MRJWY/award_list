from __future__ import annotations

import html
import sys
from decimal import Decimal, ROUND_HALF_UP
from textwrap import dedent
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.business_logic import (
    add_deadline_health_columns,
    aggregate_counts,
    filter_proposals,
    submitted_proposal_mask,
    summarize_proposals,
)
from core.settings import load_settings
from core.transforms import PROPOSAL_MASTER_COLUMN_LABELS, normalize_proposal_master
from integrations.google_sheets import (
    WorkbookLoadResult,
    build_google_sheet_diagnostics,
    load_live_or_cached_workbook_frames,
)


DISPLAY_LABELS = {
    **PROPOSAL_MASTER_COLUMN_LABELS,
    "days_to_deadline": "D-Day",
    "deadline_bucket": "마감 구간",
}

CARD_STYLES = [
    ("#2F80ED", "#EAF2FF"),
    ("#27AE60", "#EAF8F0"),
    ("#8E5CF6", "#F2EBFF"),
    ("#F39C12", "#FFF4E5"),
    ("#F05A5A", "#FFECEC"),
]


@st.cache_data(ttl=300, show_spinner=False)
def load_dashboard_data() -> tuple[pd.DataFrame, str, str, dict[str, object]]:
    settings = load_settings()
    load_result: WorkbookLoadResult = load_live_or_cached_workbook_frames(settings)
    proposal_df = load_result.workbook_frames.get(settings.google_worksheet_proposal_master, pd.DataFrame())
    normalized = add_deadline_health_columns(normalize_proposal_master(proposal_df))
    diagnostics = build_google_sheet_diagnostics(settings)
    return normalized, load_result.source, load_result.message, diagnostics


def render_connection_diagnostics(load_message: str, diagnostics: dict[str, object]) -> None:
    with st.expander("Google Sheet Connection Diagnostics", expanded=True):
        st.code(load_message, language="text")

        client_email = diagnostics.get("service_account_client_email") or "-"
        sheet_id_preview = diagnostics.get("google_sheet_id_preview") or "-"
        json_valid = diagnostics.get("service_account_json_valid")
        json_valid_label = "Y" if json_valid is True else "N" if json_valid is False else "-"

        diagnostic_rows = pd.DataFrame(
            [
                {"Item": "GOOGLE_SHEET_ID present", "Value": "Y" if diagnostics.get("google_sheet_id_present") else "N"},
                {"Item": "GOOGLE_SHEET_ID preview", "Value": sheet_id_preview},
                {"Item": "Service account JSON present", "Value": "Y" if diagnostics.get("service_account_json_present") else "N"},
                {"Item": "Service account JSON valid", "Value": json_valid_label},
                {"Item": "Service account email", "Value": client_email},
                {"Item": "PROPOSAL_MASTER worksheet", "Value": diagnostics.get("proposal_master_sheet") or "-"},
                {"Item": "CODE_MAP_PRODUCT worksheet", "Value": diagnostics.get("product_sheet") or "-"},
                {"Item": "CODE_MAP_STATUS worksheet", "Value": diagnostics.get("status_sheet") or "-"},
                {"Item": "SYNC_LOG worksheet", "Value": diagnostics.get("sync_log_sheet") or "-"},
            ]
        )
        st.dataframe(diagnostic_rows, use_container_width=True, hide_index=True)
        st.caption(
            "If the service account email is shown here, make sure the same email was added to the target Google "
            "Spreadsheet sharing settings. If JSON valid is N, the GOOGLE_SERVICE_ACCOUNT_JSON secret is usually cut off."
        )


def inject_styles() -> None:
    st.markdown(
        dedent(
            """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@700;800&display=swap');

        :root {
            --page-bg: linear-gradient(180deg, #f5f8ff 0%, #f8fafc 100%);
            --panel-bg: rgba(255, 255, 255, 0.92);
            --panel-border: rgba(148, 163, 184, 0.18);
            --text-main: #1f2a44;
            --text-sub: #6b7a99;
            --shadow: 0 16px 40px rgba(31, 42, 68, 0.08);
        }

        .stApp {
            background: var(--page-bg);
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 2.25rem;
            max-width: 1400px;
        }

        .dashboard-shell {
            display: flex;
            flex-direction: column;
            gap: 1.1rem;
        }

        .hero-card, .filter-card, .panel-card, .table-card, .metric-card {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 24px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(10px);
        }

        .hero-card {
            padding: 1.25rem 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
        }

        .hero-title-wrap {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .hero-icon {
            width: 54px;
            height: 54px;
            border-radius: 18px;
            background: linear-gradient(135deg, #2f80ed, #5d9cff);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-size: 1.5rem;
            box-shadow: 0 14px 30px rgba(47, 128, 237, 0.3);
        }

        .hero-title {
            margin: 0;
            color: var(--text-main);
            font-family: "Nunito", "Pretendard Variable", "Noto Sans KR", sans-serif;
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: -0.04em;
        }

        .hero-subtitle {
            margin: 0.35rem 0 0;
            color: var(--text-sub);
            font-size: 0.94rem;
        }

        .hero-meta {
            text-align: right;
            color: var(--text-sub);
            font-size: 0.92rem;
            line-height: 1.55;
            white-space: nowrap;
        }

        .filter-card {
            padding: 0.95rem 1.1rem 0.25rem;
        }

        .metric-card {
            padding: 1.15rem 1.15rem 1rem;
            height: 188px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }

        .metric-top {
            display: flex;
            align-items: center;
            gap: 0.9rem;
        }

        .metric-icon {
            width: 52px;
            height: 52px;
            border-radius: 18px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.45rem;
            font-weight: 700;
        }

        .metric-label {
            color: var(--text-main);
            font-size: 1.02rem;
            font-weight: 700;
        }

        .metric-value {
            margin: 0.8rem 0 0;
            color: var(--text-main);
            font-family: "Nunito", "Pretendard Variable", "Noto Sans KR", sans-serif;
            font-size: 2.1rem;
            font-weight: 800;
            letter-spacing: -0.05em;
        }

        .metric-unit {
            color: var(--text-sub);
            font-size: 1rem;
            font-weight: 700;
            margin-left: 0.35rem;
        }

        .metric-caption {
            color: var(--text-sub);
            font-size: 0.88rem;
            line-height: 1.45;
            min-height: 2.6em;
        }

        .metric-caption-compact {
            font-size: 0.8rem;
            line-height: 1.35;
        }

        .panel-card {
            padding: 1.1rem 1.15rem 0.95rem;
            min-height: 340px;
        }

        .panel-title {
            margin: 0 0 1rem;
            color: var(--text-main);
            font-size: 1.08rem;
            font-weight: 800;
        }

        .bar-list {
            display: flex;
            flex-direction: column;
            gap: 1rem;
            margin-top: 1rem;
        }

        .bar-row {
            display: grid;
            grid-template-columns: 88px 1fr 38px;
            align-items: center;
            gap: 0.75rem;
        }

        .bar-label {
            color: var(--text-main);
            font-size: 0.93rem;
            font-weight: 700;
        }

        .bar-track {
            width: 100%;
            height: 18px;
            border-radius: 999px;
            background: #eef2ff;
            overflow: hidden;
        }

        .bar-fill {
            height: 100%;
            border-radius: 999px;
        }

        .bar-value {
            text-align: right;
            color: var(--text-sub);
            font-size: 0.92rem;
            font-weight: 700;
        }

        .deadline-stat-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.9rem;
            margin-bottom: 1rem;
        }

        .deadline-stat-card {
            border-radius: 18px;
            padding: 1rem;
            text-align: center;
        }

        .deadline-stat-title {
            margin: 0 0 0.35rem;
            font-size: 0.95rem;
            font-weight: 800;
        }

        .deadline-stat-value {
            margin: 0;
            font-family: "Nunito", "Pretendard Variable", "Noto Sans KR", sans-serif;
            font-size: 2rem;
            font-weight: 800;
        }

        .mini-chart {
            display: flex;
            align-items: end;
            justify-content: space-between;
            gap: 0.6rem;
            height: 182px;
            padding-top: 0.75rem;
        }

        .mini-group {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0.45rem;
        }

        .mini-bars {
            height: 126px;
            display: flex;
            align-items: end;
            gap: 0.28rem;
        }

        .mini-bar {
            width: 24px;
            border-radius: 10px 10px 4px 4px;
            position: relative;
        }

        .mini-bar span {
            position: absolute;
            top: -1.35rem;
            left: 50%;
            transform: translateX(-50%);
            color: var(--text-main);
            font-size: 0.82rem;
            font-weight: 800;
        }

        .mini-label {
            color: var(--text-sub);
            font-size: 0.82rem;
            font-weight: 700;
            text-align: center;
            line-height: 1.35;
        }

        .split-panel {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .split-panel-section {
            display: flex;
            flex-direction: column;
        }

        .split-divider {
            height: 1px;
            background: linear-gradient(90deg, rgba(148, 163, 184, 0), rgba(148, 163, 184, 0.35), rgba(148, 163, 184, 0));
        }

        .compact-owner-list {
            display: flex;
            flex-direction: column;
            gap: 0.65rem;
            margin-top: 0.15rem;
        }

        .compact-owner-row {
            background: rgba(247, 249, 253, 0.9);
            border: 1px solid rgba(226, 232, 240, 0.95);
            border-radius: 18px;
            padding: 0.72rem 0.82rem;
        }

        .compact-owner-head {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 0.6rem;
        }

        .compact-owner-name {
            color: var(--text-main);
            font-size: 0.92rem;
            font-weight: 800;
        }

        .compact-owner-total {
            color: var(--text-sub);
            font-size: 0.8rem;
            font-weight: 700;
        }

        .compact-owner-awarded {
            color: #8E5CF6;
            font-size: 0.86rem;
            font-weight: 800;
            white-space: nowrap;
        }

        .compact-owner-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem 0.8rem;
            margin-top: 0.45rem;
            color: var(--text-sub);
            font-size: 0.78rem;
            font-weight: 700;
        }

        .owner-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1rem;
            margin-top: 0.35rem;
        }

        .owner-card {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 22px;
            box-shadow: var(--shadow);
            padding: 1.1rem 1.15rem;
        }

        .owner-card-top {
            display: flex;
            justify-content: space-between;
            align-items: start;
            gap: 0.75rem;
            margin-bottom: 0.9rem;
        }

        .owner-name {
            color: var(--text-main);
            font-size: 1rem;
            font-weight: 800;
        }

        .owner-subtext {
            color: var(--text-sub);
            font-size: 0.86rem;
            margin-top: 0.2rem;
        }

        .owner-awarded {
            display: flex;
            flex-direction: column;
            align-items: end;
            gap: 0.15rem;
        }

        .owner-awarded-label {
            color: var(--text-sub);
            font-size: 0.76rem;
            font-weight: 700;
        }

        .owner-awarded-value {
            color: #8E5CF6;
            font-size: 1rem;
            font-weight: 800;
        }

        .owner-stack {
            display: flex;
            width: 100%;
            height: 14px;
            background: #eef2ff;
            border-radius: 999px;
            overflow: hidden;
        }

        .owner-stack-segment {
            height: 100%;
        }

        .owner-submitted {
            background: #27AE60;
        }

        .owner-awarded-segment {
            background: #8E5CF6;
        }

        .owner-not-awarded {
            background: #2F80ED;
        }

        .owner-other {
            background: #94A3B8;
        }

        .owner-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem 0.9rem;
            margin-top: 0.85rem;
            color: var(--text-sub);
            font-size: 0.82rem;
            font-weight: 700;
        }

        .owner-legend span {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
        }

        .legend-dot {
            width: 9px;
            height: 9px;
            border-radius: 999px;
            display: inline-block;
        }

        .table-card {
            padding: 1.15rem 1.2rem 1.1rem;
        }

        .table-toolbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.9rem;
            gap: 1rem;
        }

        .section-title {
            margin: 0;
            color: var(--text-main);
            font-size: 1.12rem;
            font-weight: 800;
        }

        .table-note {
            color: var(--text-sub);
            font-size: 0.9rem;
        }

        .proposal-feed {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 0.9rem;
            margin-top: 0.9rem;
        }

        .proposal-feed-card {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 22px;
            box-shadow: var(--shadow);
            padding: 1.05rem 1.1rem;
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
        }

        .proposal-feed-top {
            display: flex;
            justify-content: space-between;
            align-items: start;
            gap: 0.8rem;
        }

        .proposal-feed-business {
            color: var(--text-main);
            font-size: 1rem;
            font-weight: 800;
            line-height: 1.35;
        }

        .proposal-feed-project {
            color: var(--text-sub);
            font-size: 0.86rem;
            line-height: 1.5;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .proposal-feed-meta {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.7rem;
        }

        .proposal-feed-meta-item {
            background: #f7f9fd;
            border-radius: 16px;
            padding: 0.7rem 0.8rem;
        }

        .proposal-feed-meta-label {
            color: var(--text-sub);
            font-size: 0.76rem;
            font-weight: 700;
            margin-bottom: 0.22rem;
        }

        .proposal-feed-meta-value {
            color: var(--text-main);
            font-size: 0.88rem;
            font-weight: 800;
            line-height: 1.35;
        }

        .proposal-feed-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.75rem;
            color: var(--text-sub);
            font-size: 0.8rem;
            font-weight: 700;
        }

        .top-panel-row {
            margin-top: 0.55rem;
        }

        .proposal-table {
            width: 100%;
            border-collapse: collapse;
            overflow: hidden;
            border-radius: 18px;
        }

        .proposal-table thead th {
            background: #f7f9fd;
            color: var(--text-main);
            font-size: 0.9rem;
            font-weight: 800;
            padding: 0.9rem 0.8rem;
            text-align: left;
            border-bottom: 1px solid #e5ecf6;
        }

        .proposal-table tbody td {
            padding: 0.88rem 0.8rem;
            font-size: 0.9rem;
            color: #334155;
            border-bottom: 1px solid #eef3fa;
            vertical-align: middle;
        }

        .proposal-table tbody tr:hover td {
            background: #fafcff;
        }

        .filter-button-spacer {
            height: 1.7rem;
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 84px;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 800;
        }

        .status-review { background: #e8f0ff; color: #2f80ed; }
        .status-draft { background: #eef2ff; color: #5061d3; }
        .status-submitted { background: #e9f9ef; color: #27ae60; }
        .status-awarded { background: #f3ebff; color: #8e5cf6; }
        .status-not-awarded { background: #ffeaea; color: #f05a5a; }
        .status-default { background: #eef2f7; color: #64748b; }

        .d-day {
            font-weight: 800;
            white-space: nowrap;
        }

        .d-overdue { color: #f05a5a; }
        .d-upcoming { color: #2f80ed; }
        .d-none { color: #94a3b8; }

        .empty-state {
            color: var(--text-sub);
            padding: 2.8rem 1rem;
            text-align: center;
            font-size: 0.96rem;
        }

        .source-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.4rem 0.7rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 700;
            background: #eef4ff;
            color: #4863a0;
        }
        </style>
        """
        ),
        unsafe_allow_html=True,
    )


def source_badge(source: str) -> str:
    label_map = {
        "google_sheet": "실시간 Google Sheet",
        "cache": "로컬 캐시 데이터",
        "empty": "데이터 없음",
    }
    return f"<span class='source-badge'>데이터 소스 · {html.escape(label_map.get(source, source))}</span>"


def format_count(value: int | float) -> str:
    return f"{int(value):,}"


def format_eok_from_kkrw(value: int | float) -> str:
    amount_eok = (Decimal(str(value)) / Decimal("100000")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount_eok:,.2f}"


def format_timestamp(value: object) -> str:
    if pd.isna(value) or value is None:
        return "-"
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M")


def render_hero(latest_sync: object, data_source: str) -> None:
    st.markdown(
        dedent(
            f"""
        <div class="hero-card">
            <div class="hero-title-wrap">
                <div class="hero-icon">▣</div>
                <div>
                    <h1 class="hero-title">사업 제안 현황 대시보드</h1>
                    <p class="hero-subtitle">Google Sheet 입력 데이터를 기준으로 제안 현황, 수주율, 마감 리스크를 한눈에 확인합니다.</p>
                </div>
            </div>
            <div class="hero-meta">
                <div><strong>최종 업데이트:</strong> {html.escape(format_timestamp(latest_sync))}</div>
                <div>{source_badge(data_source)}</div>
            </div>
        </div>
        """
        ),
        unsafe_allow_html=True,
    )


def render_metric_card(title: str, value: str, unit: str, caption: str, icon: str, accent: str, tint: str) -> str:
    compact_class = " metric-caption-compact" if len(caption) > 20 else ""
    return f"""
    <div class="metric-card">
        <div class="metric-top">
            <div class="metric-icon" style="background:{tint}; color:{accent};">{icon}</div>
            <div class="metric-label">{html.escape(title)}</div>
        </div>
        <div>
            <div class="metric-value" style="color:{accent};">
                {html.escape(value)}<span class="metric-unit">{html.escape(unit)}</span>
            </div>
            <div class="metric-caption{compact_class}">{html.escape(caption)}</div>
        </div>
    </div>
    """


def render_metric_row(summary: dict[str, int | float]) -> None:
    total_project_cost_eok = format_eok_from_kkrw(summary["awarded_total_project_cost_kkrw"])
    government_funding_eok = format_eok_from_kkrw(summary["awarded_government_funding_kkrw"])
    cards = [
        ("총 제안 수", format_count(summary["total_proposals"]), "건", "전체 제안 건수", "□", *CARD_STYLES[0]),
        ("제출 완료 수", format_count(summary["submitted_count"]), "건", "제출 완료 건수", "▶", *CARD_STYLES[1]),
        ("수주 수", format_count(summary["awarded_count"]), "건", "수주 성공 건수", "⌘", *CARD_STYLES[2]),
        ("수주율", f"{summary['win_rate_pct']:.1f}", "%", "수주율 (수주/제출)", "◔", *CARD_STYLES[3]),
        ("총 사업비", total_project_cost_eok, "억원", f"정부지원금 합계 · {government_funding_eok}억원", "₩", *CARD_STYLES[4]),
    ]

    columns = st.columns(5)
    for column, card in zip(columns, cards):
        title, value, unit, caption, icon, accent, tint = card
        column.markdown(render_metric_card(title, value, unit, caption, icon, accent, tint), unsafe_allow_html=True)

def render_filter_bar(proposal_df: pd.DataFrame) -> tuple[list[str], list[str], list[str], str]:
    st.markdown("#### 필터", unsafe_allow_html=False)
    filter_columns = st.columns([1.05, 1.05, 1.05, 1.45, 0.45], vertical_alignment="bottom")
    product_options = sorted([value for value in proposal_df["product_code"].dropna().unique() if str(value).strip()])
    status_options = sorted([value for value in proposal_df["status_name"].dropna().unique() if str(value).strip()])
    ministry_options = sorted([value for value in proposal_df["ministry"].dropna().unique() if str(value).strip()])

    selected_products = filter_columns[0].multiselect("제품코드", product_options, placeholder="전체")
    selected_statuses = filter_columns[1].multiselect("상태", status_options, placeholder="전체")
    selected_ministries = filter_columns[2].multiselect("부처", ministry_options, placeholder="전체")
    keyword = filter_columns[3].text_input("검색어", placeholder="사업명, 과제명, 기관, 주제...")
    filter_columns[4].markdown('<div class="filter-button-spacer"></div>', unsafe_allow_html=True)
    if filter_columns[4].button("새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    return selected_products, selected_statuses, selected_ministries, keyword

def render_rank_panel(title: str, summary_df: pd.DataFrame, label_column: str) -> None:
    if summary_df.empty:
        st.markdown(
            dedent(
                f"""
            <div class="panel-card">
                <h3 class="panel-title">{html.escape(title)}</h3>
                <div class="empty-state">표시할 데이터가 없습니다.</div>
            </div>
            """
            ),
            unsafe_allow_html=True,
        )
        return

    max_count = max(int(summary_df["proposal_count"].max()), 1)
    bar_html: list[str] = [f'<div class="panel-card"><h3 class="panel-title">{html.escape(title)}</h3><div class="bar-list">']
    for index, row in summary_df.iterrows():
        label = str(row[label_column]).strip() or "미입력"
        count = int(row["proposal_count"])
        accent, _ = CARD_STYLES[index % len(CARD_STYLES)]
        width = max(count / max_count * 100, 8)
        bar_html.append(
            dedent(
                f"""
            <div class="bar-row">
                <div class="bar-label">{html.escape(label)}</div>
                <div class="bar-track">
                    <div class="bar-fill" style="width:{width:.1f}%; background:{accent};"></div>
                </div>
                <div class="bar-value">{count}</div>
            </div>
            """
            )
        )
    bar_html.append("</div></div>")
    st.markdown("".join(bar_html), unsafe_allow_html=True)

def build_owner_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "owner" not in df.columns:
        return pd.DataFrame(
            columns=[
                "owner",
                "proposal_count",
                "submitted_only_count",
                "awarded_count",
                "not_awarded_count",
                "other_count",
            ]
        )

    owner_series = df["owner"].fillna("").astype(str).str.strip().replace("", "미입력")
    status_code_series = df["status_code"].fillna("").astype(str).str.upper().str.strip()
    status_name_series = df["status_name"].fillna("").astype(str).str.strip()
    awarded_flag_series = df["awarded_yn"].fillna("").astype(str).str.upper().str.strip()

    awarded_mask = status_code_series.eq("AWARDED") | status_name_series.eq("수주") | awarded_flag_series.eq("Y")
    not_awarded_mask = status_code_series.eq("NOT_AWARDED") | status_name_series.eq("미수주")
    submitted_only_mask = (status_code_series.eq("SUBMITTED") | status_name_series.eq("제출 완료")) & ~awarded_mask & ~not_awarded_mask
    other_mask = ~(submitted_only_mask | awarded_mask | not_awarded_mask)

    summary = (
        pd.DataFrame(
            {
                "owner": owner_series,
                "submitted_only_count": submitted_only_mask.astype(int),
                "awarded_count": awarded_mask.astype(int),
                "not_awarded_count": not_awarded_mask.astype(int),
                "other_count": other_mask.astype(int),
            }
        )
        .groupby("owner", dropna=False)
        .sum()
        .reset_index()
    )
    summary["proposal_count"] = (
        summary["submitted_only_count"] + summary["awarded_count"] + summary["not_awarded_count"] + summary["other_count"]
    )

    raw_total = owner_series.value_counts().rename_axis("owner").reset_index(name="raw_count")
    summary = summary.merge(raw_total, on="owner", how="left")
    summary["proposal_count"] = summary[["proposal_count", "raw_count"]].max(axis=1)
    summary = summary.drop(columns=["raw_count"])

    return summary.sort_values(
        by=["proposal_count", "awarded_count", "owner"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

def render_owner_section(df: pd.DataFrame) -> None:
    owner_summary = build_owner_summary(df).head(12)
    st.markdown("#### 책임자 현황", unsafe_allow_html=False)

    if owner_summary.empty:
        st.markdown(
            """
            <div class="panel-card">
                <h3 class="panel-title">책임자별 제안 현황</h3>
                <div class="empty-state">표시할 책임자 데이터가 없습니다.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    cards_html: list[str] = ['<div class="owner-grid">']
    for _, row in owner_summary.iterrows():
        owner_name = str(row["owner"]).strip() or "미입력"
        proposal_count = int(row["proposal_count"])
        submitted_only_count = int(row["submitted_only_count"])
        awarded_count = int(row["awarded_count"])
        not_awarded_count = int(row["not_awarded_count"])
        other_count = int(row["other_count"])

        stack_total = max(submitted_only_count + awarded_count + not_awarded_count + other_count, 1)
        submitted_width = submitted_only_count / stack_total * 100
        awarded_width = awarded_count / stack_total * 100
        not_awarded_width = not_awarded_count / stack_total * 100
        other_width = other_count / stack_total * 100

        cards_html.append(
            dedent(
                f"""
                <div class="owner-card">
                    <div class="owner-card-top">
                        <div>
                            <div class="owner-name">{html.escape(owner_name)}</div>
                            <div class="owner-subtext">총 {proposal_count}건</div>
                        </div>
                        <div class="owner-awarded">
                            <span class="owner-awarded-label">수주</span>
                            <span class="owner-awarded-value">{awarded_count}건</span>
                        </div>
                    </div>
                    <div class="owner-stack">
                        <div class="owner-stack-segment owner-submitted" style="width:{submitted_width:.1f}%"></div>
                        <div class="owner-stack-segment owner-awarded-segment" style="width:{awarded_width:.1f}%"></div>
                        <div class="owner-stack-segment owner-not-awarded" style="width:{not_awarded_width:.1f}%"></div>
                        <div class="owner-stack-segment owner-other" style="width:{other_width:.1f}%"></div>
                    </div>
                    <div class="owner-legend">
                        <span><i class="legend-dot owner-submitted"></i>제출완료 {submitted_only_count}</span>
                        <span><i class="legend-dot owner-awarded-segment"></i>수주 {awarded_count}</span>
                        <span><i class="legend-dot owner-not-awarded"></i>미수주 {not_awarded_count}</span>
                        <span><i class="legend-dot owner-other"></i>기타 {other_count}</span>
                    </div>
                </div>
                """
            )
        )

    cards_html.append("</div>")
    st.markdown("".join(cards_html), unsafe_allow_html=True)

def prepare_deadline_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "submission_deadline" not in df.columns:
        return df.iloc[0:0].copy()
    submitted_mask = submitted_proposal_mask(df)
    awarded_mask = df["awarded_yn"].fillna("").astype(str).str.upper().eq("Y")
    deadline_df = df.loc[df["submission_deadline"].notna() & ~submitted_mask & ~awarded_mask].copy()
    return deadline_df


def deadline_bucket_counts(df: pd.DataFrame) -> dict[str, int]:
    if df.empty:
        return {"7일 이내": 0, "8~15일": 0, "16~30일": 0, "30일 초과": 0, "마감 지남": 0}

    days = df["days_to_deadline"]
    return {
        "7일 이내": int(days.between(0, 7, inclusive="both").sum()),
        "8~15일": int(days.between(8, 15, inclusive="both").sum()),
        "16~30일": int(days.between(16, 30, inclusive="both").sum()),
        "30일 초과": int(days.gt(30).sum()),
        "마감 지남": int(days.lt(0).sum()),
    }

def render_deadline_panel(df: pd.DataFrame) -> None:
    counts = deadline_bucket_counts(df)
    bucket_items = list(counts.items())
    overdue_total = bucket_items[-1][1] if bucket_items else 0
    upcoming_total = sum(value for _, value in bucket_items[:-1])
    max_bucket = max(max(counts.values()), 1)

    mini_html = [
        dedent(
            f"""
        <div class="panel-card">
            <h3 class="panel-title">마감 예정 / 지난 건</h3>
        <div class="deadline-stat-grid">
            <div class="deadline-stat-card" style="background:#edf4ff; color:#2f80ed;">
                <p class="deadline-stat-title">마감 예정 (30일 기준)</p>
                <p class="deadline-stat-value">{upcoming_total}</p>
            </div>
            <div class="deadline-stat-card" style="background:#ffecec; color:#f05a5a;">
                <p class="deadline-stat-title">마감 지난 건</p>
                <p class="deadline-stat-value">{overdue_total}</p>
            </div>
        </div>
        <div class="mini-chart">
        """
        ),
    ]
    for index, (bucket, value) in enumerate(bucket_items):
        height = max(18, value / max_bucket * 110) if value else 8
        color = "#2F80ED" if index < len(bucket_items) - 1 else "#F05A5A"
        mini_html.append(
            dedent(
                f"""
            <div class="mini-group">
                <div class="mini-bars">
                    <div class="mini-bar" style="height:{height:.1f}px; background:{color};">
                        <span>{value}</span>
                    </div>
                </div>
                <div class="mini-label">{html.escape(bucket)}</div>
            </div>
            """
            )
        )
    mini_html.append("</div></div>")
    st.markdown("".join(mini_html), unsafe_allow_html=True)

def build_compact_owner_panel_html(df: pd.DataFrame) -> str:
    owner_summary = build_owner_summary(df).head(2)

    panel_html = [
        """
        <div class="split-panel-section">
            <h3 class="panel-title">책임자 현황</h3>
        """
    ]

    if owner_summary.empty:
        panel_html.append('<div class="empty-state">표시할 책임자 데이터가 없습니다.</div></div>')
        return "".join(panel_html)

    panel_html.append('<div class="compact-owner-list">')
    for _, row in owner_summary.iterrows():
        owner_name = str(row["owner"]).strip() or "미입력"
        proposal_count = int(row["proposal_count"])
        submitted_only_count = int(row["submitted_only_count"])
        awarded_count = int(row["awarded_count"])
        not_awarded_count = int(row["not_awarded_count"])
        other_count = int(row["other_count"])

        stack_total = max(submitted_only_count + awarded_count + not_awarded_count + other_count, 1)
        submitted_width = submitted_only_count / stack_total * 100
        awarded_width = awarded_count / stack_total * 100
        not_awarded_width = not_awarded_count / stack_total * 100
        other_width = other_count / stack_total * 100

        panel_html.append(
            dedent(
                f"""
                <div class="compact-owner-row">
                    <div class="compact-owner-head">
                        <div>
                            <div class="compact-owner-name">{html.escape(owner_name)}</div>
                            <div class="compact-owner-total">총 {proposal_count}건</div>
                        </div>
                        <div class="compact-owner-awarded">수주 {awarded_count}건</div>
                    </div>
                    <div class="owner-stack">
                        <div class="owner-stack-segment owner-submitted" style="width:{submitted_width:.1f}%"></div>
                        <div class="owner-stack-segment owner-awarded-segment" style="width:{awarded_width:.1f}%"></div>
                        <div class="owner-stack-segment owner-not-awarded" style="width:{not_awarded_width:.1f}%"></div>
                        <div class="owner-stack-segment owner-other" style="width:{other_width:.1f}%"></div>
                    </div>
                    <div class="compact-owner-meta">
                        <span>제출완료 {submitted_only_count}</span>
                        <span>수주 {awarded_count}</span>
                        <span>미수주 {not_awarded_count}</span>
                        <span>기타 {other_count}</span>
                    </div>
                </div>
                """
            )
        )
    panel_html.append("</div></div>")
    return "".join(panel_html)

def render_owner_summary_panel(df: pd.DataFrame) -> None:
    st.markdown(
        '<div class="panel-card">' + build_compact_owner_panel_html(df) + "</div>",
        unsafe_allow_html=True,
    )

def render_deadline_owner_panel(deadline_df: pd.DataFrame, owner_df: pd.DataFrame) -> None:
    counts = deadline_bucket_counts(deadline_df)
    bucket_items = list(counts.items())
    overdue_total = bucket_items[-1][1] if bucket_items else 0
    upcoming_total = sum(value for _, value in bucket_items[:-1])
    max_bucket = max(max(counts.values()), 1)

    mini_html = [
        dedent(
            """
        <div class="panel-card split-panel">
            <div class="split-panel-section">
                <h3 class="panel-title">마감 예정 / 지난 건</h3>
        """
        ),
        dedent(
            f"""
        <div class="deadline-stat-grid">
            <div class="deadline-stat-card" style="background:#edf4ff; color:#2f80ed;">
                <p class="deadline-stat-title">마감 예정 (30일 기준)</p>
                <p class="deadline-stat-value">{upcoming_total}</p>
            </div>
            <div class="deadline-stat-card" style="background:#ffecec; color:#f05a5a;">
                <p class="deadline-stat-title">마감 지난 건</p>
                <p class="deadline-stat-value">{overdue_total}</p>
            </div>
        </div>
        <div class="mini-chart">
        """
        ),
    ]
    for index, (bucket, value) in enumerate(bucket_items):
        height = max(18, value / max_bucket * 110) if value else 8
        color = "#2F80ED" if index < len(bucket_items) - 1 else "#F05A5A"
        mini_html.append(
            dedent(
                f"""
            <div class="mini-group">
                <div class="mini-bars">
                    <div class="mini-bar" style="height:{height:.1f}px; background:{color};">
                        <span>{value}</span>
                    </div>
                </div>
                <div class="mini-label">{html.escape(bucket)}</div>
            </div>
            """
            )
        )

    mini_html.extend(
        [
            "</div></div>",
            '<div class="split-divider"></div>',
            build_compact_owner_panel_html(owner_df),
            "</div>",
        ]
    )
    st.markdown("".join(mini_html), unsafe_allow_html=True)

def status_pill_class(status_name: str) -> str:
    normalized = status_name.strip()
    if normalized == "기회 검토":
        return "status-review"
    if normalized == "제안서 작성 중":
        return "status-draft"
    if normalized == "제출 완료":
        return "status-submitted"
    if normalized == "수주":
        return "status-awarded"
    if normalized == "미수주":
        return "status-not-awarded"
    return "status-default"

def format_deadline(value: object) -> str:
    if pd.isna(value) or value is None:
        return "-"
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def format_d_day(value: object) -> tuple[str, str]:
    if pd.isna(value) or value is None:
        return "-", "d-none"

    days = int(value)
    if days < 0:
        return f"D+{abs(days)}", "d-overdue"
    if days == 0:
        return "D-Day", "d-upcoming"
    return f"D-{days}", "d-upcoming"


def build_detail_table(df: pd.DataFrame) -> str:
    if df.empty:
        return '<div class="empty-state">표시할 제안 데이터가 없습니다.</div>'

    table_df = df.copy()
    if "submission_deadline" in table_df.columns:
        table_df = table_df.sort_values(by=["submission_deadline", "proposal_id"], na_position="last")

    rows_html: list[str] = []
    for _, row in table_df.iterrows():
        status_name = str(row.get("status_name", "")).strip() or "미입력"
        d_day_text, d_day_class = format_d_day(row.get("days_to_deadline"))
        awarded_flag = str(row.get("awarded_yn", "")).strip().upper()
        awarded_text = "Y" if awarded_flag == "Y" else ("N" if awarded_flag == "N" else "-")
        rows_html.append(
            f"""
            <tr>
                <td>{html.escape(str(row.get("business_name", "")).strip() or "-")}</td>
                <td>{html.escape(str(row.get("project_name", "")).strip() or "-")}</td>
                <td><span class="status-pill {status_pill_class(status_name)}">{html.escape(status_name)}</span></td>
                <td>{html.escape(format_deadline(row.get("submission_deadline")))}</td>
                <td><span class="d-day {d_day_class}">{html.escape(d_day_text)}</span></td>
                <td>{html.escape(awarded_text)}</td>
                <td>{html.escape(str(row.get("owner", "")).strip() or "-")}</td>
            </tr>
            """
        )

    return (
        """
        <table class="proposal-table">
            <thead>
                <tr>
                    <th>사업명</th>
                    <th>과제명</th>
                    <th>상태명</th>
                    <th>마감일</th>
                    <th>D-Day</th>
                    <th>수주여부</th>
                    <th>책임자</th>
                </tr>
            </thead>
            <tbody>
        """
        + "".join(rows_html)
        + """
            </tbody>
        </table>
        """
    )

def build_detail_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    table_df = df.copy()
    if "submission_deadline" in table_df.columns:
        table_df = table_df.sort_values(by=["submission_deadline", "proposal_id"], na_position="last")

    display_df = pd.DataFrame(
        {
            "사업명": table_df["business_name"].fillna("").astype(str).str.strip().replace("", "-"),
            "과제명": table_df["project_name"].fillna("").astype(str).str.strip().replace("", "-"),
            "상태명": table_df["status_name"].fillna("").astype(str).str.strip().replace("", "미입력"),
            "마감일": table_df["submission_deadline"].apply(format_deadline),
            "D-Day": table_df["days_to_deadline"].apply(lambda value: format_d_day(value)[0]),
            "수주여부": table_df["awarded_yn"].fillna("").astype(str).str.upper().map({"Y": "Y", "N": "N"}).fillna("-"),
            "책임자": table_df["owner"].fillna("").astype(str).str.strip().replace("", "-"),
        }
    )
    return display_df.reset_index(drop=True)

def build_recent_proposal_feed_html(df: pd.DataFrame, limit: int = 12) -> str:
    if df.empty:
        return '<div class="empty-state">표시할 제안 데이터가 없습니다.</div>'

    feed_df = df.copy()
    sort_columns: list[str] = []
    ascending: list[bool] = []
    for column in ["last_updated_at", "submission_deadline", "proposal_id"]:
        if column in feed_df.columns:
            sort_columns.append(column)
            ascending.append(False)
    if sort_columns:
        feed_df = feed_df.sort_values(by=sort_columns, ascending=ascending, na_position="last")
    feed_df = feed_df.head(limit)

    cards_html: list[str] = ['<div class="proposal-feed">']
    for _, row in feed_df.iterrows():
        business_name = str(row.get("business_name", "")).strip() or "-"
        project_name = str(row.get("project_name", "")).strip() or "-"
        status_name = str(row.get("status_name", "")).strip() or "미입력"
        owner_name = str(row.get("owner", "")).strip() or "-"
        ministry_name = str(row.get("ministry", "")).strip() or "-"
        updated_at = format_timestamp(row.get("last_updated_at"))
        deadline_text = format_deadline(row.get("submission_deadline"))
        d_day_text, d_day_class = format_d_day(row.get("days_to_deadline"))

        cards_html.append(
            dedent(
                f"""
                <div class="proposal-feed-card">
                    <div class="proposal-feed-top">
                        <div>
                            <div class="proposal-feed-business">{html.escape(business_name)}</div>
                            <div class="proposal-feed-project">{html.escape(project_name)}</div>
                        </div>
                        <span class="status-pill {status_pill_class(status_name)}">{html.escape(status_name)}</span>
                    </div>
                    <div class="proposal-feed-meta">
                        <div class="proposal-feed-meta-item">
                            <div class="proposal-feed-meta-label">담당자</div>
                            <div class="proposal-feed-meta-value">{html.escape(owner_name)}</div>
                        </div>
                        <div class="proposal-feed-meta-item">
                            <div class="proposal-feed-meta-label">부처</div>
                            <div class="proposal-feed-meta-value">{html.escape(ministry_name)}</div>
                        </div>
                        <div class="proposal-feed-meta-item">
                            <div class="proposal-feed-meta-label">마감일</div>
                            <div class="proposal-feed-meta-value">{html.escape(deadline_text)}</div>
                        </div>
                        <div class="proposal-feed-meta-item">
                            <div class="proposal-feed-meta-label">D-Day</div>
                            <div class="proposal-feed-meta-value"><span class="d-day {d_day_class}">{html.escape(d_day_text)}</span></div>
                        </div>
                    </div>
                    <div class="proposal-feed-footer">
                        <span>최신 수정 {html.escape(updated_at)}</span>
                    </div>
                </div>
                """
            )
        )
    cards_html.append("</div>")
    return "".join(cards_html)

def build_download_frame(df: pd.DataFrame) -> pd.DataFrame:
    export_columns = [
        "proposal_id",
        "business_name",
        "project_name",
        "product_code",
        "topic",
        "ministry",
        "agency",
        "status_code",
        "status_name",
        "submission_deadline",
        "awarded_yn",
        "total_project_cost_kkrw",
        "government_funding_kkrw",
        "private_cash_kkrw",
        "private_in_kind_kkrw",
        "owner",
        "partner",
        "notes",
        "last_updated_at",
    ]
    available_columns = [column for column in export_columns if column in df.columns]
    export_df = df[available_columns].copy()
    export_df = export_df.rename(columns=DISPLAY_LABELS)
    for column in [DISPLAY_LABELS.get("submission_deadline", "submission_deadline"), DISPLAY_LABELS.get("last_updated_at", "last_updated_at")]:
        if column in export_df.columns:
            export_df[column] = export_df[column].apply(format_deadline if column == DISPLAY_LABELS.get("submission_deadline", "submission_deadline") else format_timestamp)
    return export_df

def render_detail_section(df: pd.DataFrame) -> None:
    toolbar_left, toolbar_right = st.columns([0.8, 0.2])
    toolbar_left.markdown(
        dedent(
            """
        <h3 class="section-title">원본 제안 리스트</h3>
        <div class="table-note">필터가 적용된 제안 중 최신 수정순 12건을 보여줍니다. 상세 수정은 Google Sheet에서 직접 진행합니다.</div>
        """
        ),
        unsafe_allow_html=True,
    )
    toolbar_right.download_button(
        "CSV 다운로드",
        data=build_download_frame(df).to_csv(index=False, encoding="utf-8-sig"),
        file_name="proposal_dashboard_export.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.markdown(build_recent_proposal_feed_html(df), unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="사업 제안 현황 대시보드", layout="wide")
    inject_styles()

    try:
        proposal_df, data_source, load_message, diagnostics = load_dashboard_data()
    except Exception as exc:
        st.error(f"Google Sheet 데이터를 불러오지 못했습니다: {exc}")
        st.info("`.env` 값과 Google 서비스 계정 권한을 확인한 뒤 다시 실행해 주세요.")
        return

    latest_sync = proposal_df["last_updated_at"].max() if "last_updated_at" in proposal_df.columns else pd.NaT
    render_hero(latest_sync, data_source)

    if data_source == "cache":
        st.warning(load_message)
    elif data_source == "empty":
        st.error("Google Sheet connection failed, so no dashboard data is available.")
        render_connection_diagnostics(load_message, diagnostics)

    if proposal_df.empty:
        st.warning("아직 제안 데이터가 없습니다. Google Sheet에 데이터를 입력한 뒤 다시 확인해 주세요.")
        return

    selected_products, selected_statuses, selected_ministries, keyword = render_filter_bar(proposal_df)
    filtered_df = filter_proposals(
        proposal_df,
        products=selected_products,
        statuses=selected_statuses,
        ministries=selected_ministries,
        keyword=keyword,
    )

    if filtered_df.empty:
        st.warning("현재 필터 조건에 맞는 데이터가 없습니다.")
        return

    summary = summarize_proposals(filtered_df)
    render_metric_row(summary)
    st.caption("수주율은 제출 완료, 수주, 미수주 상태를 제출 건으로 간주해 계산합니다. 금액 단위는 입력 기준상 천원이며 KPI 정부지원금은 억원으로 환산해 표시합니다.")

    status_summary = aggregate_counts(filtered_df, "status_name", top_n=8, empty_label="미입력")
    product_summary = aggregate_counts(filtered_df, "product_code", top_n=8, empty_label="미입력")
    top_columns = st.columns(3, gap="small")
    with top_columns[0]:
        render_rank_panel("상태별 건수", status_summary, "status_name")
    with top_columns[1]:
        render_rank_panel("제품코드별 건수", product_summary, "product_code")
    with top_columns[2]:
        render_owner_summary_panel(filtered_df)

    render_detail_section(filtered_df)

if __name__ == "__main__":
    main()






