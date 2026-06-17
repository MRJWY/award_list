from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


SUBMITTED_STATUS_CODES = {"SUBMITTED", "AWARDED", "NOT_AWARDED"}
SUBMITTED_STATUS_NAMES = {"제출 완료", "수주", "미수주"}


def submitted_proposal_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)

    mask = pd.Series(False, index=df.index)
    if "status_code" in df.columns:
        mask = mask | df["status_code"].fillna("").astype(str).str.upper().isin(SUBMITTED_STATUS_CODES)
    if "status_name" in df.columns:
        mask = mask | df["status_name"].fillna("").astype(str).str.strip().isin(SUBMITTED_STATUS_NAMES)
    return mask


def summarize_proposals(df: pd.DataFrame) -> dict[str, int | float]:
    submitted_mask = submitted_proposal_mask(df)
    submitted_count = int(submitted_mask.sum()) if len(submitted_mask) else 0
    awarded_mask = (
        df["awarded_yn"].astype(str).str.upper().eq("Y") if "awarded_yn" in df.columns else pd.Series(dtype=bool)
    )
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
    open_pipeline_count = int(
        df["status_name"].fillna("").astype(str).str.strip().str.len().gt(0).sum() - awarded_count
    ) if "status_name" in df.columns else max(int(len(df)) - awarded_count, 0)
    open_pipeline_count = max(open_pipeline_count, 0)
    win_rate = (awarded_count / submitted_count * 100) if submitted_count else 0.0

    return {
        "total_proposals": int(len(df)),
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
    products: list[str] | None = None,
    statuses: list[str] | None = None,
    ministries: list[str] | None = None,
    keyword: str = "",
) -> pd.DataFrame:
    filtered = df.copy()

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
        .sort_values(by=["proposal_count", column], ascending=[False, True])
    )
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
