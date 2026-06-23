from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


STATUS_DISPLAY_SEQUENCE = [
    "수주",
    "선정대기",
    "발표평가",
    "발표대기",
    "서면평가",
    "제출 완료",
    "제안서 작성 중",
    "입찰 여부 결정",
    "기회 검토",
    "미선정",
    "미수주",
]
STATUS_SORT_ORDER = {status: index for index, status in enumerate(STATUS_DISPLAY_SEQUENCE)}


SUBMITTED_ONLY_STATUS_CODES = {"SUBMITTED"}
SUBMITTED_ONLY_STATUS_NAMES = {"제출 완료"}
AWARDED_STATUS_CODES = {"AWARDED"}
AWARDED_STATUS_NAMES = {"수주"}
NOT_AWARDED_STATUS_CODES = {"NOT_AWARDED"}
NOT_AWARDED_STATUS_NAMES = {"미수주", "미선정"}
SELECTION_WAIT_STATUS_CODES = {"SELECTION_WAIT"}
SELECTION_WAIT_STATUS_NAMES = {"선정대기"}
ANNOUNCEMENT_WAIT_STATUS_CODES = {"ANNOUNCEMENT_WAIT"}
ANNOUNCEMENT_WAIT_STATUS_NAMES = {"발표대기", "발표평가"}
DOCUMENT_EVAL_STATUS_CODES = {"DOCUMENT_EVAL"}
DOCUMENT_EVAL_STATUS_NAMES = {"서면평가"}

SUBMITTED_STATUS_CODES = (
    SUBMITTED_ONLY_STATUS_CODES
    | AWARDED_STATUS_CODES
    | NOT_AWARDED_STATUS_CODES
    | SELECTION_WAIT_STATUS_CODES
    | ANNOUNCEMENT_WAIT_STATUS_CODES
    | DOCUMENT_EVAL_STATUS_CODES
)
SUBMITTED_STATUS_NAMES = (
    SUBMITTED_ONLY_STATUS_NAMES
    | AWARDED_STATUS_NAMES
    | NOT_AWARDED_STATUS_NAMES
    | SELECTION_WAIT_STATUS_NAMES
    | ANNOUNCEMENT_WAIT_STATUS_NAMES
    | DOCUMENT_EVAL_STATUS_NAMES
)


def status_sort_rank(status_name: object) -> int:
    normalized = str(status_name or "").strip()
    return STATUS_SORT_ORDER.get(normalized, len(STATUS_SORT_ORDER))


def sort_status_values(values: list[str]) -> list[str]:
    return sorted(values, key=lambda value: (status_sort_rank(value), str(value).strip()))


def status_stage_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    if df.empty:
        empty_mask = pd.Series(dtype=bool)
        return {
            "submitted_only": empty_mask,
            "awarded": empty_mask,
            "not_awarded": empty_mask,
            "selection_wait": empty_mask,
            "announcement_wait": empty_mask,
            "document_eval": empty_mask,
            "submitted": empty_mask,
            "closed": empty_mask,
            "status_present": empty_mask,
        }

    status_code_series = (
        df["status_code"].fillna("").astype(str).str.upper().str.strip()
        if "status_code" in df.columns
        else pd.Series("", index=df.index, dtype=str)
    )
    status_name_series = (
        df["status_name"].fillna("").astype(str).str.strip()
        if "status_name" in df.columns
        else pd.Series("", index=df.index, dtype=str)
    )
    awarded_flag_series = (
        df["awarded_yn"].fillna("").astype(str).str.upper().str.strip()
        if "awarded_yn" in df.columns
        else pd.Series("", index=df.index, dtype=str)
    )

    awarded_mask = (
        status_code_series.isin(AWARDED_STATUS_CODES)
        | status_name_series.isin(AWARDED_STATUS_NAMES)
        | awarded_flag_series.eq("Y")
    )
    not_awarded_mask = status_code_series.isin(NOT_AWARDED_STATUS_CODES) | status_name_series.isin(NOT_AWARDED_STATUS_NAMES)
    selection_wait_mask = (
        status_code_series.isin(SELECTION_WAIT_STATUS_CODES)
        | status_name_series.str.contains(r"선정\s*대기", regex=True, na=False)
    )
    announcement_wait_mask = (
        status_code_series.isin(ANNOUNCEMENT_WAIT_STATUS_CODES)
        | status_name_series.str.contains(r"발표\s*(대기|평가)", regex=True, na=False)
    )
    document_eval_mask = (
        status_code_series.isin(DOCUMENT_EVAL_STATUS_CODES)
        | status_name_series.str.contains(r"서면\s*평가", regex=True, na=False)
    )
    submitted_only_mask = (
        (status_code_series.isin(SUBMITTED_ONLY_STATUS_CODES) | status_name_series.isin(SUBMITTED_ONLY_STATUS_NAMES))
        & ~awarded_mask
        & ~not_awarded_mask
        & ~selection_wait_mask
        & ~announcement_wait_mask
        & ~document_eval_mask
    )
    submitted_mask = (
        submitted_only_mask
        | awarded_mask
        | not_awarded_mask
        | selection_wait_mask
        | announcement_wait_mask
        | document_eval_mask
    )
    closed_mask = awarded_mask | not_awarded_mask
    status_present_mask = status_code_series.ne("") | status_name_series.ne("")

    return {
        "submitted_only": submitted_only_mask,
        "awarded": awarded_mask,
        "not_awarded": not_awarded_mask,
        "selection_wait": selection_wait_mask,
        "announcement_wait": announcement_wait_mask,
        "document_eval": document_eval_mask,
        "submitted": submitted_mask,
        "closed": closed_mask,
        "status_present": status_present_mask,
    }


def submitted_proposal_mask(df: pd.DataFrame) -> pd.Series:
    return status_stage_masks(df)["submitted"]


def summarize_proposals(df: pd.DataFrame) -> dict[str, int | float]:
    stage_masks = status_stage_masks(df)
    submitted_only_mask = stage_masks["submitted_only"]
    submitted_only_count = int(submitted_only_mask.sum()) if len(submitted_only_mask) else 0
    submitted_mask = stage_masks["submitted"]
    submitted_count = int(submitted_mask.sum()) if len(submitted_mask) else 0
    awarded_mask = stage_masks["awarded"]
    awarded_count = int(awarded_mask.sum()) if len(awarded_mask) else 0
    awarded_total_project_cost = (
        float(df.loc[awarded_mask, "total_project_cost_kkrw"].fillna(0).sum())
        if len(awarded_mask) and "total_project_cost_kkrw" in df.columns
        else 0.0
    )
    awarded_government_funding = (
        float(df.loc[awarded_mask, "government_funding_kkrw"].fillna(0).sum())
        if len(awarded_mask) and "government_funding_kkrw" in df.columns
        else 0.0
    )
    awarded_private_cash = (
        float(df.loc[awarded_mask, "private_cash_kkrw"].fillna(0).sum())
        if len(awarded_mask) and "private_cash_kkrw" in df.columns
        else 0.0
    )
    awarded_private_in_kind = (
        float(df.loc[awarded_mask, "private_in_kind_kkrw"].fillna(0).sum())
        if len(awarded_mask) and "private_in_kind_kkrw" in df.columns
        else 0.0
    )
    status_present_mask = stage_masks["status_present"]
    closed_mask = stage_masks["closed"]
    open_pipeline_count = int((status_present_mask & ~closed_mask).sum()) if len(status_present_mask) else 0
    open_pipeline_count = max(open_pipeline_count, 0)
    win_rate = (awarded_count / submitted_count * 100) if submitted_count else 0.0

    return {
        "total_proposals": int(len(df)),
        "submitted_only_count": submitted_only_count,
        "submitted_count": submitted_count,
        "awarded_count": awarded_count,
        "awarded_total_project_cost_kkrw": awarded_total_project_cost,
        "awarded_government_funding_kkrw": awarded_government_funding,
        "awarded_private_cash_kkrw": awarded_private_cash,
        "awarded_private_in_kind_kkrw": awarded_private_in_kind,
        "open_pipeline_count": open_pipeline_count,
        "win_rate_pct": win_rate,
    }


def proposals_due_within_days(df: pd.DataFrame, days: int, today: datetime | None = None) -> pd.DataFrame:
    if "submission_deadline" not in df.columns or df.empty:
        return pd.DataFrame(columns=df.columns)

    base_date = pd.Timestamp(today or datetime.now()).normalize()
    end_date = base_date + timedelta(days=days)
    due_mask = df["submission_deadline"].notna() & df["submission_deadline"].between(base_date, end_date)
    return df.loc[due_mask].sort_values(by="submission_deadline").copy()


def filter_proposals(
    df: pd.DataFrame,
    *,
    years: list[str] | None = None,
    products: list[str] | None = None,
    statuses: list[str] | None = None,
    ministries: list[str] | None = None,
    keyword: str = "",
) -> pd.DataFrame:
    filtered = df.copy()

    if years and "proposal_year" in filtered.columns:
        filtered = filtered[filtered["proposal_year"].isin(years)]
    if products:
        filtered = filtered[filtered["product_code"].isin(products)]
    if statuses:
        filtered = filtered[filtered["status_name"].isin(statuses)]
    if ministries:
        filtered = filtered[filtered["ministry"].isin(ministries)]
    if keyword.strip():
        pattern = keyword.strip().lower()
        searchable = (
            filtered["proposal_id"].fillna("").astype(str)
            + " "
            + filtered["business_name"].fillna("").astype(str)
            + " "
            + filtered["project_name"].fillna("").astype(str)
            + " "
            + filtered["topic"].fillna("").astype(str)
            + " "
            + filtered["agency"].fillna("").astype(str)
        ).str.lower()
        filtered = filtered[searchable.str.contains(pattern, na=False)]

    return filtered.copy()


def aggregate_counts(df: pd.DataFrame, column: str, *, top_n: int = 10, empty_label: str = "Unspecified") -> pd.DataFrame:
    if column not in df.columns or df.empty:
        return pd.DataFrame(columns=[column, "proposal_count"])

    summary = (
        df.assign(**{column: df[column].fillna("").astype(str).str.strip().replace("", empty_label)})
        .groupby(column, dropna=False)
        .size()
        .reset_index(name="proposal_count")
    )
    if column == "status_name":
        summary["_sort_rank"] = summary[column].map(status_sort_rank)
        summary = summary.sort_values(by=["_sort_rank", "proposal_count", column], ascending=[True, False, True]).drop(
            columns=["_sort_rank"]
        )
    else:
        summary = summary.sort_values(by=["proposal_count", column], ascending=[False, True])
    return summary.head(top_n)


def count_overdue_open_proposals(df: pd.DataFrame, today: datetime | None = None) -> int:
    if "submission_deadline" not in df.columns or df.empty:
        return 0

    base_date = pd.Timestamp(today or datetime.now()).normalize()
    awarded_mask = df["awarded_yn"].fillna("").astype(str).str.upper().eq("Y") if "awarded_yn" in df.columns else False
    submitted_mask = submitted_proposal_mask(df) if len(df) else False
    overdue_mask = df["submission_deadline"].notna() & df["submission_deadline"].lt(base_date) & ~awarded_mask & ~submitted_mask
    return int(overdue_mask.sum())


def add_deadline_health_columns(df: pd.DataFrame, today: datetime | None = None) -> pd.DataFrame:
    if "submission_deadline" not in df.columns or df.empty:
        enriched = df.copy()
        enriched["days_to_deadline"] = pd.Series(dtype="Int64")
        enriched["deadline_bucket"] = pd.Series(dtype=str)
        return enriched

    base_date = pd.Timestamp(today or datetime.now()).normalize()
    enriched = df.copy()
    days_to_deadline = (enriched["submission_deadline"] - base_date).dt.days
    enriched["days_to_deadline"] = days_to_deadline.astype("Int64")

    def bucket(days: object) -> str:
        if pd.isna(days):
            return "No deadline"
        if int(days) < 0:
            return "Overdue"
        if int(days) <= 7:
            return "Due in 7 days"
        if int(days) <= 30:
            return "Due in 30 days"
        return "Later"

    enriched["deadline_bucket"] = enriched["days_to_deadline"].map(bucket)
    return enriched
