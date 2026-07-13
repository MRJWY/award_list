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
    sort_status_values,
    status_sort_rank,
    status_stage_masks,
    submitted_proposal_mask,
    summarize_proposals,
)
from core.settings import load_settings
from core.transforms import PROPOSAL_MASTER_COLUMN_LABELS, normalize_proposal_master
from integrations.google_sheets import (
    WorkbookLoadResult,
    build_google_sheet_diagnostics,
    create_proposal_master_record,
    load_live_or_cached_workbook_frames,
    resolve_workbook_update_timestamp,
    update_proposal_master_record,
)


DISPLAY_LABELS = {
    **PROPOSAL_MASTER_COLUMN_LABELS,
    "days_to_deadline": "D-Day",
    "deadline_bucket": "마감 구간",
}

CARD_STYLES = [
    ("var(--accent)", "var(--accent-muted)"),
    ("var(--success)", "rgba(22, 163, 74, 0.10)"),
    ("var(--warning)", "rgba(217, 119, 6, 0.10)"),
    ("var(--info)", "rgba(37, 99, 235, 0.10)"),
    ("var(--error)", "rgba(220, 38, 38, 0.10)"),
]

METRIC_CARD_STYLE = ("var(--accent)", "var(--accent-muted)")

OWNER_STAGE_SPECS = [
    ("submitted_only_count", "제출완료", "owner-submitted"),
    ("awarded_count", "수주", "owner-awarded-segment"),
    ("not_awarded_count", "미수주", "owner-not-awarded"),
    ("selection_wait_count", "선정대기", "owner-selection-wait"),
    ("announcement_wait_count", "발표대기", "owner-announcement-wait"),
    ("document_eval_count", "서면평가", "owner-document-eval"),
    ("other_count", "기타", "owner-other"),
]

TOP_SUMMARY_PANEL_HEIGHT = 420

EDITABLE_STATUS_OPTIONS = sort_status_values(
    [
        "기회 검토",
        "입찰 여부 결정",
        "제안서 작성 중",
        "제출 완료",
        "서면평가",
        "선정대기",
        "발표대기",
        "발표평가",
        "수주",
        "미수주",
        "미선정",
    ]
)


def build_product_code_options(
    workbook_frames: dict[str, pd.DataFrame],
    settings,
) -> list[dict[str, str]]:
    product_df = workbook_frames.get(settings.google_worksheet_code_map_product, pd.DataFrame()).copy()
    if product_df.empty:
        return []

    product_df.columns = [str(column).strip() for column in product_df.columns]
    if "product_code" not in product_df.columns:
        return []

    if "is_active" in product_df.columns:
        active_values = product_df["is_active"].fillna("").astype(str).str.upper().str.strip()
        product_df = product_df[active_values.isin({"", "Y", "YES", "TRUE", "1"})]

    if "display_order" in product_df.columns:
        product_df["display_order"] = pd.to_numeric(product_df["display_order"], errors="coerce")
        product_df = product_df.sort_values(by=["display_order", "product_code"], ascending=[True, True], na_position="last")
    else:
        product_df = product_df.sort_values(by=["product_code"], ascending=[True])

    options: list[dict[str, str]] = []
    for _, row in product_df.iterrows():
        code = str(row.get("product_code", "")).strip()
        name = str(row.get("product_name", "")).strip()
        if code:
            options.append({"code": code, "name": name})
    return options


@st.cache_data(ttl=300, show_spinner=False)
def load_dashboard_data() -> tuple[pd.DataFrame, object, str, str, dict[str, object], list[dict[str, str]]]:
    settings = load_settings()
    load_result: WorkbookLoadResult = load_live_or_cached_workbook_frames(settings)
    proposal_df = load_result.workbook_frames.get(settings.google_worksheet_proposal_master, pd.DataFrame())
    normalized = add_deadline_health_columns(normalize_proposal_master(proposal_df))
    latest_update = resolve_workbook_update_timestamp(load_result.workbook_frames, settings, load_result.source)
    diagnostics = build_google_sheet_diagnostics(settings)
    product_options = build_product_code_options(load_result.workbook_frames, settings)
    return normalized, latest_update, load_result.source, load_result.message, diagnostics, product_options


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
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --radius-full: 9999px;

            --accent: #5b5bd6;
            --accent-hover: #4f4fc8;
            --accent-muted: hsl(240 55% 96%);

            --grey-50: hsl(240 20% 98%);
            --grey-100: hsl(240 18% 96%);
            --grey-200: hsl(240 14% 90%);
            --grey-300: hsl(240 12% 82%);
            --grey-500: hsl(240 8% 55%);
            --grey-700: hsl(240 10% 32%);
            --grey-900: hsl(240 12% 14%);

            --success: #16a34a;
            --warning: #d97706;
            --error: #dc2626;
            --info: #2563eb;

            --space-1: 4px;
            --space-2: 8px;
            --space-3: 12px;
            --space-4: 16px;
            --space-6: 24px;
            --space-8: 32px;
            --space-12: 48px;
            --space-16: 64px;

            --text-xs: 12px;
            --text-sm: 14px;
            --text-md: 16px;
            --text-lg: 18px;
            --text-xl: 24px;
            --text-2xl: 32px;

            --line-tight: 1.25;
            --line-normal: 1.5;
            --line-loose: 1.7;

            --control-sm: 32px;
            --control-md: 40px;
            --control-lg: 48px;

            --motion-fast: 120ms;
            --motion-normal: 180ms;
            --motion-slow: 240ms;
            --ease-standard: cubic-bezier(0.2, 0, 0, 1);
            --ease-emphasized: cubic-bezier(0.2, 0, 0, 1.2);

            --shadow-sm: 0 1px 2px hsl(220 40% 20% / 0.06);
            --shadow-md:
                0 1px 2px hsl(220 40% 20% / 0.08),
                0 2px 4px hsl(220 40% 20% / 0.08),
                0 4px 8px hsl(220 40% 20% / 0.08);
            --shadow-lg:
                0 2px 4px hsl(220 40% 20% / 0.07),
                0 6px 12px hsl(220 40% 20% / 0.07),
                0 12px 24px hsl(220 40% 20% / 0.07);
            --shadow-xl:
                0 2px 4px hsl(220 40% 20% / 0.06),
                0 8px 16px hsl(220 40% 20% / 0.06),
                0 16px 32px hsl(220 40% 20% / 0.06),
                0 32px 64px hsl(220 40% 20% / 0.06);

            --font-sans: "Pretendard Variable", "Noto Sans KR", sans-serif;
            --font-display: "Nunito", "Pretendard Variable", "Noto Sans KR", sans-serif;

            --page-bg: linear-gradient(180deg, var(--grey-50) 0%, #ffffff 58%, var(--grey-100) 100%);
            --panel-bg: rgba(255, 255, 255, 0.94);
            --panel-border: var(--grey-200);
            --text-main: var(--grey-900);
            --text-sub: var(--grey-700);
            --summary-panel-height: 420px;
        }

        .stApp {
            background: var(--page-bg);
            color: var(--text-main);
            font-family: var(--font-sans);
        }

        .block-container {
            padding-top: var(--space-8);
            padding-bottom: var(--space-8);
            max-width: 1400px;
        }

        .dashboard-shell {
            display: flex;
            flex-direction: column;
            gap: var(--space-4);
        }

        .hero-card, .filter-card, .panel-card, .table-card, .metric-card {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-md);
        }

        .hero-card {
            padding: var(--space-6);
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: var(--space-4);
        }

        .hero-title-wrap {
            display: flex;
            align-items: center;
            gap: var(--space-4);
        }

        .hero-icon {
            width: 56px;
            height: 56px;
            border-radius: var(--radius-md);
            background: linear-gradient(135deg, var(--accent), var(--accent-hover));
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            box-shadow: var(--shadow-lg);
        }

        .hero-icon svg,
        .metric-icon svg {
            width: 20px;
            height: 20px;
            stroke: currentColor;
            fill: none;
            stroke-width: 1.9;
            stroke-linecap: round;
            stroke-linejoin: round;
            vector-effect: non-scaling-stroke;
        }

        .hero-title {
            margin: 0;
            color: var(--text-main);
            font-family: var(--font-display);
            font-size: var(--text-2xl);
            font-weight: 800;
            letter-spacing: -0.04em;
            line-height: var(--line-tight);
        }

        .hero-subtitle {
            margin: var(--space-2) 0 0;
            color: var(--text-sub);
            font-size: var(--text-sm);
            line-height: var(--line-normal);
        }

        .hero-meta {
            text-align: right;
            color: var(--text-sub);
            font-size: var(--text-sm);
            line-height: var(--line-normal);
            white-space: nowrap;
        }

        .filter-card {
            padding: var(--space-4) var(--space-4) var(--space-1);
        }

        .stMultiSelect [data-baseweb="select"] {
            min-height: var(--control-md);
            border-radius: var(--radius-sm);
            border: 1px solid var(--grey-200);
            box-shadow: none;
            background: #fff;
            transition: border-color var(--motion-fast) var(--ease-standard), box-shadow var(--motion-fast) var(--ease-standard);
        }

        .stTextInput input {
            min-height: var(--control-md);
            border-radius: var(--radius-sm);
            border: 1px solid var(--grey-200);
            box-shadow: none;
            background: #fff;
            color: var(--text-main);
            font-size: var(--text-sm);
            transition: border-color var(--motion-fast) var(--ease-standard), box-shadow var(--motion-fast) var(--ease-standard);
        }

        .stTextInput input::placeholder {
            color: var(--grey-500);
        }

        .stMultiSelect [data-baseweb="select"]:focus-within,
        .stTextInput input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(91, 91, 214, 0.12);
        }

        .stButton > button,
        .stDownloadButton > button {
            height: var(--control-md);
            border-radius: var(--radius-sm);
            border: 1px solid var(--grey-200);
            background: #fff;
            color: var(--text-main);
            box-shadow: var(--shadow-sm);
            padding: 0 var(--space-4);
            font-size: var(--text-sm);
            font-weight: 700;
            transition:
                background var(--motion-fast) var(--ease-standard),
                border-color var(--motion-fast) var(--ease-standard),
                color var(--motion-fast) var(--ease-standard),
                transform var(--motion-fast) var(--ease-standard);
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: var(--accent);
            background: var(--accent-muted);
            color: var(--accent-hover);
        }

        .metric-card {
            padding: var(--space-4);
            height: 188px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }

        .metric-top {
            display: flex;
            align-items: center;
            gap: var(--space-3);
        }

        .metric-icon {
            width: 52px;
            height: 52px;
            border-radius: var(--radius-sm);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
        }

        .metric-label {
            color: var(--text-main);
            font-size: var(--text-md);
            font-weight: 700;
        }

        .metric-value {
            margin: var(--space-3) 0 0;
            color: var(--text-main);
            font-family: var(--font-display);
            font-size: var(--text-2xl);
            font-weight: 800;
            letter-spacing: -0.05em;
            line-height: var(--line-tight);
        }

        .metric-unit {
            color: var(--text-sub);
            font-size: var(--text-md);
            font-weight: 700;
            margin-left: var(--space-1);
        }

        .metric-caption {
            color: var(--text-sub);
            font-size: var(--text-sm);
            line-height: var(--line-normal);
            min-height: 2.6em;
        }

        .metric-caption-compact {
            font-size: var(--text-xs);
            line-height: var(--line-normal);
        }

        .panel-card {
            padding: var(--space-4);
            min-height: 340px;
            height: 100%;
            display: flex;
            flex-direction: column;
        }

        .summary-panel-card {
            height: var(--summary-panel-height);
            min-height: var(--summary-panel-height);
            box-sizing: border-box;
            overflow: hidden;
        }

        .panel-title {
            margin: 0 0 var(--space-4);
            color: var(--text-main);
            font-size: var(--text-lg);
            font-weight: 800;
            line-height: var(--line-tight);
        }

        .summary-panel-scroll {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            padding-right: 0.2rem;
        }

        .bar-list {
            display: flex;
            flex-direction: column;
            gap: 1rem;
            margin-top: 1rem;
            flex: 1;
            min-height: 0;
            justify-content: flex-start;
        }

        .bar-row {
            display: grid;
            grid-template-columns: 88px 1fr 38px;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 1rem;
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
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            padding-right: 0.2rem;
        }

        .compact-owner-row {
            background: rgba(247, 249, 253, 0.9);
            border: 1px solid rgba(226, 232, 240, 0.95);
            border-radius: var(--radius-sm);
            padding: var(--space-3);
            display: flex;
            flex-direction: column;
            min-height: 122px;
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
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-md);
            padding: var(--space-4);
            height: 100%;
            display: flex;
            flex-direction: column;
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
            background: var(--accent);
        }

        .owner-awarded-segment {
            background: var(--success);
        }

        .owner-not-awarded {
            background: var(--error);
        }

        .owner-selection-wait {
            background: var(--warning);
        }

        .owner-announcement-wait {
            background: var(--info);
        }

        .owner-document-eval {
            background: var(--accent-hover);
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
            margin-top: auto;
            padding-top: 0.85rem;
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
            padding: var(--space-4);
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
            font-size: var(--text-lg);
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
            align-items: stretch;
        }

        .proposal-feed-card {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-md);
            padding: var(--space-4);
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
            height: 100%;
        }

        .proposal-feed-top {
            display: flex;
            justify-content: space-between;
            align-items: start;
            gap: 0.8rem;
            min-height: 4.8rem;
        }

        .proposal-feed-top > div {
            flex: 1;
            min-width: 0;
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
            min-height: 2.6em;
        }

        .proposal-feed-meta {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.7rem;
        }

        .proposal-feed-meta-item {
            background: var(--grey-50);
            border-radius: var(--radius-sm);
            padding: var(--space-3);
            min-height: 4.6rem;
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
            margin-top: auto;
        }

        .proposal-detail-card {
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-md);
            padding: var(--space-4);
            margin-top: 1rem;
        }

        .proposal-detail-header {
            display: flex;
            justify-content: space-between;
            align-items: start;
            gap: 1rem;
            margin-bottom: 1rem;
        }

        .proposal-detail-header > div {
            min-width: 0;
            flex: 1;
        }

        .proposal-detail-business {
            color: var(--text-sub);
            font-size: 0.85rem;
            font-weight: 800;
            margin-bottom: 0.2rem;
        }

        .proposal-detail-project {
            color: var(--text-main);
            font-size: 1.1rem;
            font-weight: 800;
            line-height: 1.4;
        }

        .proposal-detail-grid,
        .proposal-amount-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 0.75rem;
        }

        .proposal-detail-grid {
            margin-bottom: 1rem;
        }

        .proposal-detail-item,
        .proposal-amount-card,
        .proposal-note-card {
            background: var(--grey-50);
            border: 1px solid var(--grey-200);
            border-radius: var(--radius-sm);
            padding: var(--space-3);
        }

        .proposal-detail-label,
        .proposal-amount-label,
        .proposal-note-label {
            color: var(--text-sub);
            font-size: 0.76rem;
            font-weight: 700;
            margin-bottom: 0.28rem;
        }

        .proposal-detail-value,
        .proposal-amount-value,
        .proposal-note-value {
            color: var(--text-main);
            font-size: 0.92rem;
            font-weight: 800;
            line-height: 1.45;
            word-break: break-word;
        }

        .proposal-amount-value {
            font-size: 1rem;
        }

        .proposal-note-card {
            margin-top: 0.75rem;
        }

        .proposal-square-business {
            color: var(--text-sub);
            font-size: 0.84rem;
            font-weight: 700;
            line-height: 1.45;
            margin-bottom: 0.45rem;
        }

        .proposal-square-project {
            color: var(--text-main);
            font-size: 0.98rem;
            font-weight: 800;
            line-height: 1.45;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
            min-height: 4.35em;
            margin-bottom: 0.85rem;
        }

        .proposal-square-topic {
            color: var(--text-main);
            font-size: 0.9rem;
            line-height: 1.5;
            display: -webkit-box;
            -webkit-line-clamp: 4;
            -webkit-box-orient: vertical;
            overflow: hidden;
            min-height: 6em;
        }

        .top-panel-row {
            margin-top: 0.55rem;
        }

        .proposal-table {
            width: 100%;
            border-collapse: collapse;
            overflow: hidden;
            border-radius: var(--radius-md);
        }

        .proposal-table thead th {
            background: var(--grey-50);
            color: var(--text-main);
            font-size: var(--text-sm);
            font-weight: 800;
            padding: var(--space-3);
            text-align: left;
            border-bottom: 1px solid var(--grey-200);
        }

        .proposal-table tbody td {
            padding: var(--space-3);
            font-size: var(--text-sm);
            color: var(--text-main);
            border-bottom: 1px solid var(--grey-100);
            vertical-align: middle;
        }

        .proposal-table tbody tr:hover td {
            background: var(--grey-50);
        }

        .filter-button-spacer {
            height: 1.7rem;
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: var(--control-sm);
            min-width: 84px;
            padding: 0 var(--space-3);
            border-radius: var(--radius-full);
            font-size: var(--text-xs);
            font-weight: 800;
        }

        .status-review { background: var(--grey-100); color: var(--grey-700); }
        .status-draft { background: var(--accent-muted); color: var(--accent-hover); }
        .status-submitted { background: rgba(37, 99, 235, 0.10); color: var(--info); }
        .status-awarded { background: rgba(22, 163, 74, 0.10); color: var(--success); }
        .status-selection-wait { background: rgba(217, 119, 6, 0.10); color: var(--warning); }
        .status-announcement-wait { background: rgba(91, 91, 214, 0.10); color: var(--accent); }
        .status-document-eval { background: rgba(37, 99, 235, 0.10); color: var(--info); }
        .status-not-awarded { background: rgba(220, 38, 38, 0.10); color: var(--error); }
        .status-default { background: var(--grey-100); color: var(--grey-700); }

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
            gap: var(--space-1);
            padding: 0 var(--space-3);
            min-height: var(--control-sm);
            border-radius: var(--radius-full);
            font-size: var(--text-xs);
            font-weight: 700;
            background: var(--accent-muted);
            color: var(--accent-hover);
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


def dashboard_icon_svg() -> str:
    return """
    <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="4.5" y="4.5" width="15" height="15" rx="2.5"></rect>
        <path d="M9 8.5v7"></path>
        <path d="M12 8.5v7"></path>
        <path d="M15 8.5v7"></path>
    </svg>
    """


def metric_icon_svg(name: str) -> str:
    icons = {
        "total": """
        <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="6.5" y="6.5" width="11" height="11" rx="1.5"></rect>
        </svg>
        """,
        "submitted": """
        <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M7 6.5v11"></path>
            <path d="M7 12h10"></path>
            <path d="M13 8l4 4-4 4"></path>
        </svg>
        """,
        "awarded": """
        <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M8.5 7.5h7"></path>
            <path d="M12 7.5v9"></path>
            <path d="M7.5 11.5h9"></path>
            <path d="M8 16.5l-1.5 2"></path>
            <path d="M16 16.5l1.5 2"></path>
        </svg>
        """,
        "win_rate": """
        <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="7"></circle>
            <path d="M12 12V5"></path>
            <path d="M12 12h5"></path>
        </svg>
        """,
        "budget": """
        <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M9 7.5h5"></path>
            <path d="M8.5 11.5h6"></path>
            <path d="M9 16.5h5"></path>
            <path d="M12 6v12"></path>
        </svg>
        """,
    }
    return icons.get(name, icons["total"])


def format_count(value: int | float) -> str:
    return f"{int(value):,}"


def format_eok_from_kkrw(value: int | float) -> str:
    amount_eok = (Decimal(str(value)) / Decimal("100000")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount_eok:,.2f}"


def format_kkrw_amount(value: object) -> str:
    if pd.isna(value) or value is None:
        return "-"
    amount = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(amount):,}천원"


def format_kkrw_amount_with_eok(value: object) -> str:
    if pd.isna(value) or value is None:
        return "-"
    return f"{format_kkrw_amount(value)} ({format_eok_from_kkrw(float(value))}억원)"


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
                <div class="hero-icon">{dashboard_icon_svg()}</div>
                <div>
                    <h1 class="hero-title">사업 제안 현황 대시보드</h1>
                    <p class="hero-subtitle">Google Sheet 입력 데이터를 기준으로 제안 현황, 수주율, 마감 리스크를 한눈에 확인합니다.</p>
                </div>
            </div>
            <div class="hero-meta">
                <div><strong>최종 동기화:</strong> {html.escape(format_timestamp(latest_sync))}</div>
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
            <div class="metric-icon" style="background:{tint}; color:{accent};">{metric_icon_svg(icon)}</div>
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
        ("총 제안 수", format_count(summary["total_proposals"]), "건", "전체 제안 건수", "total", *METRIC_CARD_STYLE),
        ("제출 완료 수", format_count(summary["submitted_only_count"]), "건", "상태가 제출 완료인 건수", "submitted", *METRIC_CARD_STYLE),
        ("제출 후 단계 수", format_count(summary["submitted_count"]), "건", "제출 완료 포함 후속 단계 건수", "submitted", *METRIC_CARD_STYLE),
        ("수주 수", format_count(summary["awarded_count"]), "건", "수주 성공 건수", "awarded", *METRIC_CARD_STYLE),
        ("수주율", f"{summary['win_rate_pct']:.1f}", "%", "수주율 (수주/제출 후 단계)", "win_rate", *METRIC_CARD_STYLE),
        ("총 사업비", total_project_cost_eok, "억원", f"정부지원금 합계 · {government_funding_eok}억원", "budget", *METRIC_CARD_STYLE),
    ]

    columns = st.columns(len(cards))
    for column, card in zip(columns, cards):
        title, value, unit, caption, icon, accent, tint = card
        column.markdown(render_metric_card(title, value, unit, caption, icon, accent, tint), unsafe_allow_html=True)

def render_filter_bar(proposal_df: pd.DataFrame) -> tuple[list[str], list[str], list[str], str]:
    st.markdown("#### 필터", unsafe_allow_html=False)
    filter_columns = st.columns([1.05, 1.05, 1.05, 1.45, 0.45], vertical_alignment="bottom")
    product_options = sorted([value for value in proposal_df["product_code"].dropna().unique() if str(value).strip()])
    status_options = sort_status_values([value for value in proposal_df["status_name"].dropna().unique() if str(value).strip()])
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
    panel_container = st.container(height=TOP_SUMMARY_PANEL_HEIGHT, border=True)
    with panel_container:
        st.markdown(f"<h3 class='panel-title'>{html.escape(title)}</h3>", unsafe_allow_html=True)
        if summary_df.empty:
            st.markdown('<div class="empty-state">표시할 데이터가 없습니다.</div>', unsafe_allow_html=True)
            return

        max_count = max(int(summary_df["proposal_count"].max()), 1)
        rows_html: list[str] = ['<div class="summary-panel-scroll"><div class="bar-list">']
        for index, row in summary_df.iterrows():
            label = str(row[label_column]).strip() or "미입력"
            count = int(row["proposal_count"])
            accent, _ = CARD_STYLES[index % len(CARD_STYLES)]
            width = max(count / max_count * 100, 8)
            rows_html.append(
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
        rows_html.append("</div></div>")
        st.markdown("".join(rows_html), unsafe_allow_html=True)

def build_owner_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "owner" not in df.columns:
        return pd.DataFrame(
            columns=[
                "owner",
                "proposal_count",
                "submitted_only_count",
                "awarded_count",
                "not_awarded_count",
                "selection_wait_count",
                "announcement_wait_count",
                "document_eval_count",
                "other_count",
            ]
        )

    owner_series = df["owner"].fillna("").astype(str).str.strip().replace("", "미입력")
    stage_masks = status_stage_masks(df)
    submitted_only_mask = stage_masks["submitted_only"]
    awarded_mask = stage_masks["awarded"]
    not_awarded_mask = stage_masks["not_awarded"]
    selection_wait_mask = stage_masks["selection_wait"]
    announcement_wait_mask = stage_masks["announcement_wait"]
    document_eval_mask = stage_masks["document_eval"]
    other_mask = ~(
        submitted_only_mask
        | awarded_mask
        | not_awarded_mask
        | selection_wait_mask
        | announcement_wait_mask
        | document_eval_mask
    )

    summary = (
        pd.DataFrame(
            {
                "owner": owner_series,
                "submitted_only_count": submitted_only_mask.astype(int),
                "awarded_count": awarded_mask.astype(int),
                "not_awarded_count": not_awarded_mask.astype(int),
                "selection_wait_count": selection_wait_mask.astype(int),
                "announcement_wait_count": announcement_wait_mask.astype(int),
                "document_eval_count": document_eval_mask.astype(int),
                "other_count": other_mask.astype(int),
            }
        )
        .groupby("owner", dropna=False)
        .sum()
        .reset_index()
    )
    summary["proposal_count"] = (
        summary["submitted_only_count"]
        + summary["awarded_count"]
        + summary["not_awarded_count"]
        + summary["selection_wait_count"]
        + summary["announcement_wait_count"]
        + summary["document_eval_count"]
        + summary["other_count"]
    )

    raw_total = owner_series.value_counts().rename_axis("owner").reset_index(name="raw_count")
    summary = summary.merge(raw_total, on="owner", how="left")
    summary["proposal_count"] = summary[["proposal_count", "raw_count"]].max(axis=1)
    summary = summary.drop(columns=["raw_count"])

    return summary.sort_values(
        by=["proposal_count", "awarded_count", "owner"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def owner_stage_items(row: pd.Series) -> list[tuple[str, str, int]]:
    return [
        (label, css_class, int(row.get(count_key, 0) or 0))
        for count_key, label, css_class in OWNER_STAGE_SPECS
    ]

def render_owner_section(df: pd.DataFrame) -> None:
    owner_summary = build_owner_summary(df)
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
        awarded_count = int(row["awarded_count"])
        stage_items = owner_stage_items(row)
        stack_total = max(sum(value for _, _, value in stage_items), 1)
        stack_html = "".join(
            f'<div class="owner-stack-segment {css_class}" style="width:{value / stack_total * 100:.1f}%"></div>'
            for _, css_class, value in stage_items
        )
        legend_html = "".join(
            f'<span><i class="legend-dot {css_class}"></i>{label} {value}</span>'
            for label, css_class, value in stage_items
        )

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
                        {stack_html}
                    </div>
                    <div class="owner-legend">
                        {legend_html}
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
    owner_summary = build_owner_summary(df)

    panel_html = ['<div class="split-panel-section">']

    if owner_summary.empty:
        panel_html.append('<div class="empty-state">표시할 책임자 데이터가 없습니다.</div></div>')
        return "".join(panel_html)

    panel_html.append('<div class="summary-panel-scroll compact-owner-list">')
    for _, row in owner_summary.iterrows():
        owner_name = str(row["owner"]).strip() or "미입력"
        proposal_count = int(row["proposal_count"])
        awarded_count = int(row["awarded_count"])
        stage_items = owner_stage_items(row)
        stack_total = max(sum(value for _, _, value in stage_items), 1)
        stack_html = "".join(
            f'<div class="owner-stack-segment {css_class}" style="width:{value / stack_total * 100:.1f}%"></div>'
            for _, css_class, value in stage_items
        )
        meta_html = "".join(
            f"<span>{label} {value}</span>"
            for label, _, value in stage_items
        )

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
                        {stack_html}
                    </div>
                    <div class="compact-owner-meta">
                        {meta_html}
                    </div>
                </div>
                """
            )
        )
    panel_html.append("</div></div>")
    return "".join(panel_html)

def render_owner_summary_panel(df: pd.DataFrame) -> None:
    owner_container = st.container(height=TOP_SUMMARY_PANEL_HEIGHT, border=True)
    with owner_container:
        st.markdown('<h3 class="panel-title">책임자 현황</h3>', unsafe_allow_html=True)
        if build_owner_summary(df).empty:
            st.markdown('<div class="empty-state">표시할 책임자 데이터가 없습니다.</div>', unsafe_allow_html=True)
            return
        st.markdown(build_compact_owner_panel_html(df), unsafe_allow_html=True)

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
    if normalized == "입찰 여부 결정":
        return "status-review"
    if normalized == "제안서 작성 중":
        return "status-draft"
    if normalized == "제출 완료":
        return "status-submitted"
    if normalized == "서면평가":
        return "status-document-eval"
    if normalized == "선정대기":
        return "status-selection-wait"
    if normalized in {"발표대기", "발표평가"}:
        return "status-announcement-wait"
    if normalized == "수주":
        return "status-awarded"
    if normalized in {"미수주", "미선정"}:
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
        table_df = table_df.assign(
            _status_rank=table_df["status_name"].fillna("").astype(str).map(status_sort_rank)
        ).sort_values(by=["_status_rank", "submission_deadline", "proposal_id"], ascending=[True, True, True], na_position="last")
        table_df = table_df.drop(columns=["_status_rank"])

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

def prepare_detail_display_rows(df: pd.DataFrame) -> pd.DataFrame:
    table_df = df.copy()
    if "submission_deadline" in table_df.columns:
        table_df = table_df.assign(
            _status_rank=table_df["status_name"].fillna("").astype(str).map(status_sort_rank)
        ).sort_values(by=["_status_rank", "submission_deadline", "proposal_id"], ascending=[True, True, True], na_position="last")
        table_df = table_df.drop(columns=["_status_rank"])
    return table_df.reset_index(drop=True)

def build_detail_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    table_df = prepare_detail_display_rows(df)
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

def render_detail_field(label: str, value: str) -> None:
    st.markdown(f"**{label}**")
    st.write(value)


def format_amount_input_value(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return ""
    if float(numeric).is_integer():
        return str(int(numeric))
    return str(float(numeric))


def editable_status_options(current_status: str) -> list[str]:
    current = current_status.strip()
    if current and current not in EDITABLE_STATUS_OPTIONS:
        return sort_status_values([*EDITABLE_STATUS_OPTIONS, current])
    return EDITABLE_STATUS_OPTIONS


def parse_editable_amount(value: str, label: str) -> float | None:
    normalized = str(value).strip()
    if not normalized:
        return None
    numeric = pd.to_numeric(pd.Series([normalized]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        raise ValueError(f"`{label}`은 숫자로 입력해 주세요.")
    return float(numeric)


def editing_proposal_keys() -> set[str]:
    keys = st.session_state.get("editing_proposal_keys")
    if not isinstance(keys, list):
        return set()
    return {str(key) for key in keys}


def set_editing_proposal_keys(keys: set[str]) -> None:
    st.session_state["editing_proposal_keys"] = sorted(keys)


def new_proposal_form_open() -> bool:
    return bool(st.session_state.get("show_new_proposal_form"))


def set_new_proposal_form_open(is_open: bool) -> None:
    st.session_state["show_new_proposal_form"] = bool(is_open)


def render_proposal_edit_form(row: pd.Series, row_key: str) -> None:
    proposal_id = str(row.get("proposal_id", "")).strip()
    if not proposal_id:
        st.info("제안ID가 없는 항목은 여기서 수정할 수 없습니다.")
        return

    save_message = st.session_state.get("proposal_save_message")
    if isinstance(save_message, dict) and save_message.get("proposal_id") == proposal_id:
        st.success(str(save_message.get("message", "저장되었습니다.")))

    current_status = str(row.get("status_name", "")).strip() or "미입력"
    current_awarded = str(row.get("awarded_yn", "")).strip().upper()
    awarded_options = ["", "Y", "N"]
    awarded_index = awarded_options.index(current_awarded) if current_awarded in awarded_options else 0
    status_options = editable_status_options(current_status)
    status_index = status_options.index(current_status) if current_status in status_options else 0

    with st.form(f"proposal_edit_form_{row_key}", clear_on_submit=False):
        st.markdown("**수정 폼**")
        st.caption("상태, 책임자, 수주여부, 부처, 비고, 금액만 수정할 수 있습니다. 금액은 천원 단위입니다.")

        top_cols = st.columns(4)
        edited_status = top_cols[0].selectbox("상태", status_options, index=status_index)
        edited_owner = top_cols[1].text_input("책임자", value=str(row.get("owner", "")).strip())
        edited_awarded = top_cols[2].selectbox(
            "수주여부",
            awarded_options,
            index=awarded_index,
            format_func=lambda value: {"": "미입력", "Y": "Y", "N": "N"}.get(value, value),
        )
        edited_ministry = top_cols[3].text_input("부처", value=str(row.get("ministry", "")).strip())

        amount_cols = st.columns(4)
        edited_total_cost = amount_cols[0].text_input("총사업비(천원)", value=format_amount_input_value(row.get("total_project_cost_kkrw")))
        edited_government = amount_cols[1].text_input("정부지원금(천원)", value=format_amount_input_value(row.get("government_funding_kkrw")))
        edited_private_cash = amount_cols[2].text_input("민간부담금(현금, 천원)", value=format_amount_input_value(row.get("private_cash_kkrw")))
        edited_private_kind = amount_cols[3].text_input("민간부담금(현물, 천원)", value=format_amount_input_value(row.get("private_in_kind_kkrw")))

        edited_notes = st.text_area("비고", value=str(row.get("notes", "")).strip(), height=120)
        submitted = st.form_submit_button("저장", use_container_width=False)

    if not submitted:
        return

    try:
        payload = {
            "status_name": edited_status,
            "owner": edited_owner,
            "awarded_yn": edited_awarded,
            "ministry": edited_ministry,
            "notes": edited_notes,
            "total_project_cost_kkrw": parse_editable_amount(edited_total_cost, "총사업비"),
            "government_funding_kkrw": parse_editable_amount(edited_government, "정부지원금"),
            "private_cash_kkrw": parse_editable_amount(edited_private_cash, "민간부담금(현금)"),
            "private_in_kind_kkrw": parse_editable_amount(edited_private_kind, "민간부담금(현물)"),
        }
        settings = load_settings()
        update_proposal_master_record(settings, proposal_id, payload)
    except Exception as exc:
        st.error(f"저장 중 오류가 발생했습니다: {exc}")
        return

    st.cache_data.clear()
    st.session_state["proposal_save_message"] = {
        "proposal_id": proposal_id,
        "message": f"{proposal_id} 항목을 Google Sheet에 저장했습니다.",
    }
    editing_keys = editing_proposal_keys()
    editing_keys.discard(row_key)
    set_editing_proposal_keys(editing_keys)
    st.rerun()


def render_new_proposal_form(product_options: list[dict[str, str]]) -> None:
    save_message = st.session_state.get("proposal_create_message")
    if isinstance(save_message, str) and save_message.strip():
        st.success(save_message)

    product_codes = [option["code"] for option in product_options]
    product_labels = {
        option["code"]: f'{option["code"]} | {option["name"]}' if option["name"] else option["code"]
        for option in product_options
    }

    with st.form("new_proposal_form", clear_on_submit=False):
        st.markdown("**신규 과제 추가**")
        st.caption("기본 정보와 핵심 관리 항목을 입력하면 Google Sheet에 신규 과제가 추가됩니다.")

        identity_cols = st.columns(4)
        business_name = identity_cols[0].text_input("사업명")
        project_name = identity_cols[1].text_input("과제명")
        product_code = identity_cols[2].selectbox(
            "제품코드",
            options=product_codes if product_codes else [""],
            index=0,
            format_func=lambda value: product_labels.get(value, value or "선택 가능한 제품코드 없음"),
        )
        owner = identity_cols[3].text_input("책임자")

        core_cols = st.columns(4)
        status_name = core_cols[0].selectbox("상태", EDITABLE_STATUS_OPTIONS, index=0)
        submission_deadline = core_cols[1].text_input("마감일", placeholder="2026-07-31")
        awarded_yn = core_cols[2].selectbox(
            "수주여부",
            ["", "Y", "N"],
            index=0,
            format_func=lambda value: {"": "미입력", "Y": "Y", "N": "N"}.get(value, value),
        )
        ministry = core_cols[3].text_input("부처")

        detail_cols = st.columns(4)
        agency = detail_cols[0].text_input("기관")
        partner = detail_cols[1].text_input("협력기관")
        topic = detail_cols[2].text_input("주제")
        _ = detail_cols[3].empty()

        amount_cols = st.columns(4)
        total_cost = amount_cols[0].text_input("총사업비(천원)")
        government_funding = amount_cols[1].text_input("정부지원금(천원)")
        private_cash = amount_cols[2].text_input("민간부담금(현금, 천원)")
        private_in_kind = amount_cols[3].text_input("민간부담금(현물, 천원)")

        notes = st.text_area("비고", height=120)
        submitted = st.form_submit_button("신규 과제 저장", use_container_width=False)

    if not submitted:
        return

    try:
        payload = {
            "business_name": business_name,
            "project_name": project_name,
            "product_code": product_code,
            "topic": topic,
            "ministry": ministry,
            "agency": agency,
            "status_name": status_name,
            "submission_deadline": submission_deadline,
            "awarded_yn": awarded_yn,
            "total_project_cost_kkrw": parse_editable_amount(total_cost, "총사업비"),
            "government_funding_kkrw": parse_editable_amount(government_funding, "정부지원금"),
            "private_cash_kkrw": parse_editable_amount(private_cash, "민간부담금(현금)"),
            "private_in_kind_kkrw": parse_editable_amount(private_in_kind, "민간부담금(현물)"),
            "owner": owner,
            "partner": partner,
            "notes": notes,
        }
        settings = load_settings()
        created_record = create_proposal_master_record(settings, payload)
    except Exception as exc:
        st.error(f"신규 과제 저장 중 오류가 발생했습니다: {exc}")
        return

    created_proposal_id = str(created_record.get("proposal_id", "")).strip()
    st.cache_data.clear()
    st.session_state["proposal_create_message"] = (
        f"{created_proposal_id or '신규 과제'}가 Google Sheet에 추가되었습니다."
    )
    set_new_proposal_form_open(False)
    if created_proposal_id:
        open_keys = expanded_proposal_keys()
        open_keys.add(created_proposal_id)
        set_expanded_proposal_keys(open_keys)
    st.rerun()


def render_selected_proposal_detail(row: pd.Series, row_key: str) -> None:
    status_name = str(row.get("status_name", "")).strip() or "미입력"
    awarded_flag = str(row.get("awarded_yn", "")).strip().upper()
    awarded_text = "Y" if awarded_flag == "Y" else ("N" if awarded_flag == "N" else "-")
    d_day_text, _ = format_d_day(row.get("days_to_deadline"))

    header_cols = st.columns([0.82, 0.18], vertical_alignment="center")
    with header_cols[0]:
        st.caption(str(row.get("business_name", "")).strip() or "-")
        st.markdown(f"**{str(row.get('project_name', '')).strip() or '-'}**")
    with header_cols[1]:
        st.markdown(
            f"<div style='text-align:right;'><span class='status-pill {status_pill_class(status_name)}'>{html.escape(status_name)}</span></div>",
            unsafe_allow_html=True,
        )
    editing_keys = editing_proposal_keys()
    is_editing = row_key in editing_keys
    notes_value = str(row.get("notes", "")).strip()

    info_tab, schedule_tab, budget_tab, notes_tab = st.tabs(["기본 정보", "일정 / 상태", "금액", "비고 / 수정"])

    with info_tab:
        info_cols = st.columns(5)
        info_items = [
            ("제안ID", str(row.get("proposal_id", "")).strip() or "-"),
            ("주제", str(row.get("topic", "")).strip() or "-"),
            ("부처", str(row.get("ministry", "")).strip() or "-"),
            ("기관", str(row.get("agency", "")).strip() or "-"),
            ("담당자", str(row.get("owner", "")).strip() or "-"),
        ]
        for column, (label, value) in zip(info_cols, info_items):
            with column:
                render_detail_field(label, value)

    with schedule_tab:
        extra_cols = st.columns(5)
        extra_items = [
            ("협력기관", str(row.get("partner", "")).strip() or "-"),
            ("마감일", format_deadline(row.get("submission_deadline"))),
            ("D-Day", d_day_text),
            ("수주여부", awarded_text),
            ("최종수정", format_timestamp(row.get("last_updated_at"))),
        ]
        for column, (label, value) in zip(extra_cols, extra_items):
            with column:
                render_detail_field(label, value)

    with budget_tab:
        amount_cols = st.columns(4)
        amount_items = [
            ("총사업비", format_kkrw_amount_with_eok(row.get("total_project_cost_kkrw"))),
            ("정부지원금", format_kkrw_amount_with_eok(row.get("government_funding_kkrw"))),
            ("민간부담금(현금)", format_kkrw_amount_with_eok(row.get("private_cash_kkrw"))),
            ("민간부담금(현물)", format_kkrw_amount_with_eok(row.get("private_in_kind_kkrw"))),
        ]
        for column, (label, value) in zip(amount_cols, amount_items):
            with column:
                render_detail_field(label, value)

    with notes_tab:
        st.markdown("**비고**")
        if notes_value:
            st.markdown(
                f"<div style='white-space:pre-wrap; word-break:break-word; overflow-wrap:anywhere;'>{html.escape(notes_value)}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("입력된 비고가 없습니다.")

        st.divider()
        action_cols = st.columns([0.16, 0.84], vertical_alignment="center")
        edit_label = "수정 닫기" if is_editing else "수정"
        if action_cols[0].button(edit_label, key=f"edit_toggle_{row_key}", use_container_width=True):
            if is_editing:
                editing_keys.discard(row_key)
            else:
                editing_keys.add(row_key)
            set_editing_proposal_keys(editing_keys)
            st.rerun()

        if is_editing:
            render_proposal_edit_form(row, row_key)

def build_proposal_expander_label(row: pd.Series) -> str:
    business_name = str(row.get("business_name", "")).strip() or "-"
    project_name = str(row.get("project_name", "")).strip() or "-"
    status_name = str(row.get("status_name", "")).strip() or "미입력"
    deadline_text = format_deadline(row.get("submission_deadline"))
    d_day_text, _ = format_d_day(row.get("days_to_deadline"))
    owner_name = str(row.get("owner", "")).strip() or "-"
    return f"{business_name} | {project_name} | {status_name} | {deadline_text} | {d_day_text} | {owner_name}"


def proposal_row_key(row: pd.Series, fallback_index: int) -> str:
    proposal_id = str(row.get("proposal_id", "")).strip()
    return proposal_id or f"row-{fallback_index}"


def expanded_proposal_keys() -> set[str]:
    keys = st.session_state.get("expanded_proposal_keys")
    if not isinstance(keys, list):
        return set()
    return {str(key) for key in keys}


def set_expanded_proposal_keys(keys: set[str]) -> None:
    st.session_state["expanded_proposal_keys"] = sorted(keys)


def render_proposal_summary_card(row: pd.Series, row_key: str) -> None:
    status_name = str(row.get("status_name", "")).strip() or "미입력"
    d_day_text, d_day_class = format_d_day(row.get("days_to_deadline"))
    business_name = str(row.get("business_name", "")).strip() or "-"
    project_name = str(row.get("project_name", "")).strip() or "-"
    owner_name = str(row.get("owner", "")).strip() or "-"
    ministry_name = str(row.get("ministry", "")).strip() or "-"
    deadline_text = format_deadline(row.get("submission_deadline"))

    header_cols = st.columns([0.62, 0.14, 0.14, 0.10], vertical_alignment="center")
    with header_cols[0]:
        st.caption(business_name)
        st.markdown(f"**{project_name}**")
    with header_cols[1]:
        st.caption("담당자")
        st.write(owner_name)
    with header_cols[2]:
        st.caption("마감일")
        st.write(deadline_text)
    with header_cols[3]:
        is_open = st.session_state.get("expanded_proposal_key") == row_key
        button_label = "접기" if is_open else "상세"
        if st.button(button_label, key=f"toggle_{row_key}", use_container_width=True):
            st.session_state["expanded_proposal_key"] = None if is_open else row_key
            st.rerun()

    meta_cols = st.columns([0.34, 0.24, 0.20, 0.22], vertical_alignment="center")
    with meta_cols[0]:
        st.caption("부처")
        st.write(ministry_name)
    with meta_cols[1]:
        st.caption("상태")
        st.markdown(
            f"<span class='status-pill {status_pill_class(status_name)}'>{html.escape(status_name)}</span>",
            unsafe_allow_html=True,
        )
    with meta_cols[2]:
        st.caption("D-Day")
        st.markdown(
            f"<span class='d-day {d_day_class}'>{html.escape(d_day_text)}</span>",
            unsafe_allow_html=True,
        )
    with meta_cols[3]:
        st.caption("주제")
        st.write(str(row.get("topic", "")).strip() or "-")


def render_proposal_square_card(row: pd.Series, row_key: str) -> None:
    status_name = str(row.get("status_name", "")).strip() or "미입력"
    d_day_text, d_day_class = format_d_day(row.get("days_to_deadline"))
    business_name = str(row.get("business_name", "")).strip() or "-"
    project_name = str(row.get("project_name", "")).strip() or "-"
    owner_name = str(row.get("owner", "")).strip() or "-"
    ministry_name = str(row.get("ministry", "")).strip() or "-"
    deadline_text = format_deadline(row.get("submission_deadline"))
    topic_name = str(row.get("topic", "")).strip() or "-"

    with st.container(height=320, border=True):
        st.markdown(f"<div class='proposal-square-business'>{html.escape(business_name)}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='proposal-square-project'>{html.escape(project_name)}</div>", unsafe_allow_html=True)

        top_cols = st.columns([0.58, 0.42], vertical_alignment="top")
        with top_cols[0]:
            st.caption("담당자")
            st.write(owner_name)
        with top_cols[1]:
            st.caption("상태")
            st.markdown(
                f"<span class='status-pill {status_pill_class(status_name)}'>{html.escape(status_name)}</span>",
                unsafe_allow_html=True,
            )

        mid_cols = st.columns(2, vertical_alignment="top")
        with mid_cols[0]:
            st.caption("마감일")
            st.write(deadline_text)
        with mid_cols[1]:
            st.caption("D-Day")
            st.markdown(
                f"<span class='d-day {d_day_class}'>{html.escape(d_day_text)}</span>",
                unsafe_allow_html=True,
            )

        bottom_cols = st.columns(2, vertical_alignment="top")
        with bottom_cols[0]:
            st.caption("부처")
            st.write(ministry_name)
        with bottom_cols[1]:
            st.caption("주제")
            st.markdown(f"<div class='proposal-square-topic'>{html.escape(topic_name)}</div>", unsafe_allow_html=True)

        is_open = st.session_state.get("expanded_proposal_key") == row_key
        button_label = "접기" if is_open else "상세 보기"
        if st.button(button_label, key=f"card_toggle_{row_key}", use_container_width=True):
            st.session_state["expanded_proposal_key"] = None if is_open else row_key
            st.rerun()


def render_proposal_list_card(row: pd.Series, row_key: str) -> None:
    status_name = str(row.get("status_name", "")).strip() or "미입력"
    d_day_text, d_day_class = format_d_day(row.get("days_to_deadline"))
    business_name = str(row.get("business_name", "")).strip() or "-"
    project_name = str(row.get("project_name", "")).strip() or "-"
    owner_name = str(row.get("owner", "")).strip() or "-"
    ministry_name = str(row.get("ministry", "")).strip() or "-"
    deadline_text = format_deadline(row.get("submission_deadline"))
    topic_name = str(row.get("topic", "")).strip() or "-"
    open_keys = expanded_proposal_keys()
    is_open = row_key in open_keys
    button_label = "접기" if is_open else "상세 보기"

    with st.container(border=True):
        top_cols = st.columns([0.46, 0.14, 0.14, 0.12, 0.14], vertical_alignment="center")
        with top_cols[0]:
            st.caption(business_name)
            st.markdown(f"**{project_name}**")
        with top_cols[1]:
            st.caption("담당자")
            st.write(owner_name)
        with top_cols[2]:
            st.caption("부처")
            st.write(ministry_name)
        with top_cols[3]:
            st.caption("마감 / D-Day")
            st.write(deadline_text)
            st.markdown(
                f"<span class='d-day {d_day_class}'>{html.escape(d_day_text)}</span>",
                unsafe_allow_html=True,
            )
        with top_cols[4]:
            st.caption("상태")
            st.markdown(
                f"<div style='margin-bottom:0.5rem;'><span class='status-pill {status_pill_class(status_name)}'>{html.escape(status_name)}</span></div>",
                unsafe_allow_html=True,
            )
            if st.button(button_label, key=f"list_toggle_{row_key}", use_container_width=True):
                if is_open:
                    open_keys.discard(row_key)
                else:
                    open_keys.add(row_key)
                set_expanded_proposal_keys(open_keys)
                st.rerun()

        topic_cols = st.columns([0.12, 0.88], vertical_alignment="top")
        with topic_cols[0]:
            st.caption("주제")
        with topic_cols[1]:
            st.write(topic_name)

        if is_open:
            st.divider()
            render_selected_proposal_detail(row, row_key)

def build_recent_proposal_feed_html(df: pd.DataFrame, limit: int = 12) -> str:
    if df.empty:
        return '<div class="empty-state">표시할 제안 데이터가 없습니다.</div>'

    feed_df = df.copy()
    feed_df = feed_df.assign(
        _status_rank=feed_df["status_name"].fillna("").astype(str).map(status_sort_rank)
    )
    sort_columns: list[str] = ["_status_rank"]
    ascending: list[bool] = [True]
    if "last_updated_at" in feed_df.columns:
        sort_columns.append("last_updated_at")
        ascending.append(False)
    if "submission_deadline" in feed_df.columns:
        sort_columns.append("submission_deadline")
        ascending.append(True)
    if "proposal_id" in feed_df.columns:
        sort_columns.append("proposal_id")
        ascending.append(True)
    feed_df = feed_df.sort_values(by=sort_columns, ascending=ascending, na_position="last").drop(columns=["_status_rank"])
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

def render_detail_section(df: pd.DataFrame, product_options: list[dict[str, str]]) -> None:
    toolbar_left, toolbar_right = st.columns([0.8, 0.2])
    toolbar_left.markdown(
        dedent(
            """
        <h3 class="section-title">원본 제안 리스트</h3>
        <div class="table-note">카드형 리스트에서 상세 버튼을 누르면 같은 카드 아래로 주제와 개별 금액 상세가 펼쳐집니다. 상세 수정은 Google Sheet에서 직접 진행합니다.</div>
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
    detail_df = prepare_detail_display_rows(df)
    if "expanded_proposal_keys" not in st.session_state:
        st.session_state["expanded_proposal_keys"] = []
    if "editing_proposal_keys" not in st.session_state:
        st.session_state["editing_proposal_keys"] = []
    if "show_new_proposal_form" not in st.session_state:
        st.session_state["show_new_proposal_form"] = False

    st.markdown("#### 과제 카드")
    action_cols = st.columns([0.12, 0.12, 0.16, 0.60], vertical_alignment="center")
    if action_cols[0].button("전체 펼치기", use_container_width=True):
        set_expanded_proposal_keys({proposal_row_key(row, idx) for idx, (_, row) in enumerate(detail_df.iterrows())})
        st.rerun()
    if action_cols[1].button("전체 접기", use_container_width=True):
        set_expanded_proposal_keys(set())
        st.rerun()
    if action_cols[2].button("신규 과제 추가", use_container_width=True):
        set_new_proposal_form_open(not new_proposal_form_open())
        st.rerun()
    if new_proposal_form_open():
        render_new_proposal_form(product_options)
    detail_container = st.container(border=False)
    with detail_container:
        for row_index, (_, row) in enumerate(detail_df.iterrows()):
            row_key = proposal_row_key(row, row_index)
            render_proposal_list_card(row, row_key)


def main() -> None:
    st.set_page_config(page_title="사업 제안 현황 대시보드", layout="wide")
    inject_styles()

    try:
        proposal_df, latest_sync, data_source, load_message, diagnostics, product_options = load_dashboard_data()
    except Exception as exc:
        st.error(f"Google Sheet 데이터를 불러오지 못했습니다: {exc}")
        st.info("`.env` 값과 Google 서비스 계정 권한을 확인한 뒤 다시 실행해 주세요.")
        return

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
    st.caption("제출 완료 수는 상태가 제출 완료인 건수입니다. 제출 후 단계 수와 수주율은 제출 완료, 서면평가, 선정대기, 발표대기, 수주, 미수주 상태를 기준으로 계산합니다. 금액 단위는 입력 기준상 천원이며 KPI 정부지원금은 억원으로 환산해 표시합니다.")

    status_summary = aggregate_counts(filtered_df, "status_name", top_n=12, empty_label="미입력")
    product_summary = aggregate_counts(filtered_df, "product_code", top_n=8, empty_label="미입력")
    top_columns = st.columns(3, gap="small")
    with top_columns[0]:
        render_rank_panel("상태별 건수", status_summary, "status_name")
    with top_columns[1]:
        render_rank_panel("제품코드별 건수", product_summary, "product_code")
    with top_columns[2]:
        render_owner_summary_panel(filtered_df)

    render_detail_section(filtered_df, product_options)

if __name__ == "__main__":
    main()






