from __future__ import annotations

import pandas as pd


YEARLY_BUDGET_SHEET_HEADERS = [
    "제안ID",
    "연차",
    "연차 시작일",
    "연차 종료일",
    "총사업비(천원)",
    "우리 정부지원금(천원)",
    "우리 민간부담금(현금, 천원)",
    "우리 민간부담금(현물, 천원)",
    "비고",
    "최종수정일시",
]

YEARLY_BUDGET_ALIASES = dict(zip(YEARLY_BUDGET_SHEET_HEADERS, [
    "proposal_id",
    "project_year",
    "period_start",
    "period_end",
    "total_project_cost_kkrw",
    "our_government_funding_kkrw",
    "our_private_cash_kkrw",
    "our_private_in_kind_kkrw",
    "notes",
    "last_updated_at",
]))

AMOUNT_COLUMNS = [
    "total_project_cost_kkrw",
    "our_government_funding_kkrw",
    "our_private_cash_kkrw",
    "our_private_in_kind_kkrw",
]


def normalize_yearly_budget(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.rename(columns=YEARLY_BUDGET_ALIASES).copy()
    for column in YEARLY_BUDGET_ALIASES.values():
        if column not in normalized:
            normalized[column] = pd.NA
    normalized = normalized[list(YEARLY_BUDGET_ALIASES.values())]
    normalized["proposal_id"] = normalized["proposal_id"].fillna("").astype(str).str.strip()
    normalized["project_year"] = pd.to_numeric(normalized["project_year"], errors="coerce").astype("Int64")
    for column in ("period_start", "period_end", "notes"):
        normalized[column] = normalized[column].fillna("").astype(str).str.strip()
    for column in AMOUNT_COLUMNS:
        normalized[column] = pd.to_numeric(normalized[column].astype(str).str.replace(",", "", regex=False), errors="coerce")
    normalized["our_project_cost_kkrw"] = normalized[AMOUNT_COLUMNS[1:]].sum(axis=1, min_count=3)
    return normalized


def validate_yearly_budget_amounts(amounts: dict[str, object]) -> dict[str, int | None]:
    validated: dict[str, int | None] = {}
    for column in AMOUNT_COLUMNS:
        value = amounts.get(column)
        if value is None or str(value).strip() == "":
            validated[column] = None
            continue
        try:
            number = int(str(value).replace(",", ""))
        except ValueError as exc:
            raise ValueError(f"{column}: 천원 단위의 정수를 입력해 주세요.") from exc
        if number < 0:
            raise ValueError(f"{column}: 음수는 입력할 수 없습니다.")
        validated[column] = number
    our_values = [validated[column] for column in AMOUNT_COLUMNS[1:]]
    total = validated[AMOUNT_COLUMNS[0]]
    if total is not None and all(value is not None for value in our_values) and sum(our_values) > total:
        raise ValueError("우리 사업비 합계가 해당 연차의 전체 총사업비보다 클 수 없습니다.")
    return validated


def build_project_yearly_matrix(proposals: pd.DataFrame, yearly: pd.DataFrame) -> pd.DataFrame:
    columns = ["제안ID", "사업명", "과제명"]
    if proposals.empty or yearly.empty:
        return pd.DataFrame(columns=columns)
    visible_ids = set(proposals["proposal_id"].fillna("").astype(str))
    visible = yearly.loc[yearly["proposal_id"].isin(visible_ids) & yearly["project_year"].notna()].copy()
    if visible.empty:
        return pd.DataFrame(columns=columns)

    max_year = max(5, int(visible["project_year"].max()))
    names = proposals.drop_duplicates("proposal_id").set_index("proposal_id")
    rows: list[dict[str, object]] = []
    for proposal_id, project_rows in visible.groupby("proposal_id", sort=False):
        info = names.loc[proposal_id]
        record: dict[str, object] = {
            "제안ID": proposal_id,
            "사업명": info.get("business_name", ""),
            "과제명": info.get("project_name", ""),
        }
        for year in range(1, max_year + 1):
            annual = project_rows.loc[project_rows["project_year"].eq(year)]
            if annual.empty:
                period = ""
            else:
                starts = annual["period_start"].loc[annual["period_start"].ne("")]
                ends = annual["period_end"].loc[annual["period_end"].ne("")]
                period = f"{starts.min() if not starts.empty else '시작일 미상'} ~ {ends.max() if not ends.empty else '종료일 미상'}"
            record[f"{year}차년도 기간"] = period
            record[f"{year}차년도 전체사업비"] = annual["total_project_cost_kkrw"].sum(min_count=1)
            record[f"{year}차년도 우리사업비"] = annual["our_project_cost_kkrw"].sum(min_count=1)
        record["연차별 전체 합계"] = project_rows["total_project_cost_kkrw"].sum(min_count=1)
        record["연차별 우리 합계"] = project_rows["our_project_cost_kkrw"].sum(min_count=1)
        rows.append(record)
    return pd.DataFrame(rows).sort_values("제안ID").reset_index(drop=True)
