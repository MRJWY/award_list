from __future__ import annotations

import pandas as pd

PLACEHOLDER_TEXT_VALUES = {"-", "--", "—", "–", "N/A", "n/a", "NA", "na", "없음"}


PROPOSAL_MASTER_COLUMNS = [
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

PROPOSAL_MASTER_COLUMN_LABELS = {
    "proposal_id": "제안ID",
    "business_name": "사업명",
    "project_name": "과제명",
    "product_code": "제품코드",
    "topic": "주제",
    "ministry": "부처",
    "agency": "기관",
    "status_code": "상태코드",
    "status_name": "상태명",
    "submission_deadline": "제출마감일",
    "awarded_yn": "수주여부",
    "total_project_cost_kkrw": "총사업비(천원)",
    "government_funding_kkrw": "정부지원금(천원)",
    "private_cash_kkrw": "민간부담금(현금, 천원)",
    "private_in_kind_kkrw": "민간부담금(현물, 천원)",
    "owner": "책임자",
    "partner": "협력기관",
    "notes": "비고",
    "last_updated_at": "최종수정일시",
}

PROPOSAL_MASTER_COLUMN_ALIASES = {
    "proposal_id": "proposal_id",
    "제안ID": "proposal_id",
    "business_name": "business_name",
    "사업명": "business_name",
    "project_name": "project_name",
    "과제명": "project_name",
    "product_code": "product_code",
    "제품코드": "product_code",
    "topic": "topic",
    "주제": "topic",
    "ministry": "ministry",
    "부처": "ministry",
    "agency": "agency",
    "기관": "agency",
    "status_code": "status_code",
    "상태코드": "status_code",
    "status_name": "status_name",
    "상태명": "status_name",
    "submission_deadline": "submission_deadline",
    "제출마감일": "submission_deadline",
    "submitted_date": None,
    "제출일": None,
    "awarded_yn": "awarded_yn",
    "수주여부": "awarded_yn",
    "total_project_cost_kkrw": "total_project_cost_kkrw",
    "총사업비(천원)": "total_project_cost_kkrw",
    "government_funding_kkrw": "government_funding_kkrw",
    "정부지원금(천원)": "government_funding_kkrw",
    "private_cash_kkrw": "private_cash_kkrw",
    "민간부담금(현금, 천원)": "private_cash_kkrw",
    "private_in_kind_kkrw": "private_in_kind_kkrw",
    "민간부담금(현물, 천원)": "private_in_kind_kkrw",
    "owner": "owner",
    "책임자": "owner",
    "partner": "partner",
    "협력기관": "partner",
    "notes": "notes",
    "비고": "notes",
    "last_updated_at": "last_updated_at",
    "최종수정일시": "last_updated_at",
}


def proposal_master_label(column: str) -> str:
    return PROPOSAL_MASTER_COLUMN_LABELS.get(column, column)


def normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    normalized = str(value).strip()
    if normalized in PLACEHOLDER_TEXT_VALUES:
        return ""
    return normalized


def normalize_yn_flag(value: object) -> str:
    normalized = normalize_text(value).upper()
    if normalized in {"Y", "YES", "TRUE", "1"}:
        return "Y"
    if normalized in {"N", "NO", "FALSE", "0"}:
        return "N"
    return normalized


def normalize_proposal_master(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy() if not df.empty else pd.DataFrame(columns=PROPOSAL_MASTER_COLUMNS)
    normalized.columns = [str(column).strip() for column in normalized.columns]
    normalized = normalized.rename(
        columns={
            column: alias
            for column, alias in (
                (column, PROPOSAL_MASTER_COLUMN_ALIASES.get(column, column))
                for column in normalized.columns
            )
            if alias is not None
        }
    )
    normalized = normalized.loc[:, [column for column in normalized.columns if column in PROPOSAL_MASTER_COLUMNS]]

    for column in PROPOSAL_MASTER_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA

    text_columns = [
        "proposal_id",
        "business_name",
        "project_name",
        "product_code",
        "topic",
        "ministry",
        "agency",
        "status_code",
        "status_name",
        "owner",
        "partner",
        "notes",
    ]
    for column in text_columns:
        normalized[column] = normalized[column].map(normalize_text)

    normalized["awarded_yn"] = normalized["awarded_yn"].map(normalize_yn_flag)
    normalized["submission_deadline"] = pd.to_datetime(normalized["submission_deadline"], errors="coerce")
    normalized["last_updated_at"] = pd.to_datetime(normalized["last_updated_at"], errors="coerce")
    amount_columns = [
        "total_project_cost_kkrw",
        "government_funding_kkrw",
        "private_cash_kkrw",
        "private_in_kind_kkrw",
    ]
    for column in amount_columns:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    return normalized[PROPOSAL_MASTER_COLUMNS]
