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
            padding: 1.2rem 1.25rem 1rem;
            min-height: 410px;
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
                <div class="hero-icon">▥</div>
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
    total_cost_eok = format_eok_from_kkrw(summary["awarded_government_funding_kkrw"])
    total_cost_kkrw = format_count(summary["awarded_government_funding_kkrw"])
    cards = [
        ("총 제안 수", format_count(summary["total_proposals"]), "건", "전체 제안 건수", "▣", *CARD_STYLES[0]),
        ("제출 완료 수", format_count(summary["submitted_count"]), "건", "제출 완료 건수", "➤", *CARD_STYLES[1]),
        ("수주 수", format_count(summary["awarded_count"]), "건", "수주 성공 건수", "⌘", *CARD_STYLES[2]),
        ("수주율", f"{summary['win_rate_pct']:.1f}", "%", "수주율 (수주/제출)", "◔", *CARD_STYLES[3]),
        ("정부지원금 합계", total_cost_eok, "억원", f"수주 건 정부지원금 합계 · {total_cost_kkrw}천원", "₩", *CARD_STYLES[4]),
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


def render_owner_section(df: pd.DataFrame) -> None:
    owner_summary = aggregate_counts(df, "owner", top_n=12, empty_label="미입력")
    st.markdown("#### 책임자 현황", unsafe_allow_html=False)
    render_rank_panel("책임자별 제안 건수", owner_summary, "owner")


def prepare_deadline_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "submission_deadline" not in df.columns:
        return df.iloc[0:0].copy()
    submitted_mask = submitted_proposal_mask(df)
    awarded_mask = df["awarded_yn"].fillna("").astype(str).str.upper().eq("Y")
    deadline_df = df.loc[df["submission_deadline"].notna() & ~submitted_mask & ~awarded_mask].copy()
    return deadline_df


def deadline_bucket_counts(df: pd.DataFrame) -> dict[str, int]:
    if df.empty:
        return {"7일 이내": 0, "8~15일": 0, "16~30일": 0, "30일 초과": 0, "마감 지난": 0}

    days = df["days_to_deadline"]
    return {
        "7일 이내": int(days.between(0, 7, inclusive="both").sum()),
        "8~15일": int(days.between(8, 15, inclusive="both").sum()),
        "16~30일": int(days.between(16, 30, inclusive="both").sum()),
        "30일 초과": int(days.gt(30).sum()),
        "마감 지난": int(days.lt(0).sum()),
    }


def render_deadline_panel(df: pd.DataFrame) -> None:
    counts = deadline_bucket_counts(df)
    upcoming_total = counts["7일 이내"] + counts["8~15일"] + counts["16~30일"] + counts["30일 초과"]
    overdue_total = counts["마감 지난"]
    max_bucket = max(max(counts.values()), 1)

    bucket_order = ["7일 이내", "8~15일", "16~30일", "30일 초과", "마감 지난"]
    mini_html = [
        dedent(
            """
        <div class="panel-card">
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
    for bucket in bucket_order:
        value = counts[bucket]
        height = max(18, value / max_bucket * 110) if value else 8
        color = "#2F80ED" if bucket != "마감 지난" else "#F05A5A"
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
        return '<div class="empty-state">표시할 제안이 없습니다.</div>'

    table_df = df.copy()
    if "submission_deadline" in table_df.columns:
        table_df = table_df.sort_values(by=["submission_deadline", "proposal_id"], na_position="last")

    rows_html: list[str] = []
    for _, row in table_df.iterrows():
        status_name = str(row.get("status_name", "")).strip() or "미입력"
        d_day_text, d_day_class = format_d_day(row.get("days_to_deadline"))
        awarded_flag = str(row.get("awarded_yn", "")).strip().upper()
        awarded_text = "○" if awarded_flag == "Y" else ("×" if awarded_flag == "N" else "-")
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
                    <th>제출마감일</th>
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
            "제출마감일": table_df["submission_deadline"].apply(format_deadline),
            "D-Day": table_df["days_to_deadline"].apply(lambda value: format_d_day(value)[0]),
            "수주여부": table_df["awarded_yn"].fillna("").astype(str).str.upper().map({"Y": "○", "N": "×"}).fillna("-"),
            "책임자": table_df["owner"].fillna("").astype(str).str.strip().replace("", "-"),
        }
    )
    return display_df.reset_index(drop=True)


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
    for column in ["제출마감일", "최종수정일시"]:
        if column in export_df.columns:
            export_df[column] = export_df[column].apply(format_deadline if column == "제출마감일" else format_timestamp)
    return export_df


def render_detail_section(df: pd.DataFrame) -> None:
    toolbar_left, toolbar_right = st.columns([0.8, 0.2])
    toolbar_left.markdown(
        dedent(
            """
        <h3 class="section-title">원본 제안 리스트</h3>
        <div class="table-note">필터가 적용된 제안 목록입니다. 상세 값 수정은 Google Sheet에서 직접 진행합니다.</div>
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
    st.dataframe(
        build_detail_display_frame(df),
        use_container_width=True,
        hide_index=True,
        column_config={
            "사업명": st.column_config.TextColumn(width="medium"),
            "과제명": st.column_config.TextColumn(width="large"),
            "상태명": st.column_config.TextColumn(width="small"),
            "제출마감일": st.column_config.TextColumn(width="small"),
            "D-Day": st.column_config.TextColumn(width="small"),
            "수주여부": st.column_config.TextColumn(width="small"),
            "책임자": st.column_config.TextColumn(width="small"),
        },
    )


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
    deadline_df = prepare_deadline_frame(filtered_df)

    panel_columns = st.columns([1.1, 1.1, 1.3])
    with panel_columns[0]:
        render_rank_panel("상태별 건수", status_summary, "status_name")
    with panel_columns[1]:
        render_rank_panel("제품코드별 건수", product_summary, "product_code")
    with panel_columns[2]:
        render_deadline_panel(deadline_df)

    render_owner_section(filtered_df)
    render_detail_section(filtered_df)


if __name__ == "__main__":
    main()
