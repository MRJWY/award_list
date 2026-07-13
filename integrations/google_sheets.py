from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from uuid import uuid4

import pandas as pd

from core.settings import ROOT_DIR, Settings
from core.transforms import PROPOSAL_MASTER_COLUMN_ALIASES, PROPOSAL_MASTER_COLUMNS, normalize_text, normalize_yn_flag


def is_google_sheet_configured(settings: Settings) -> bool:
    return bool(
        (settings.google_service_account_json_path or settings.google_service_account_json)
        and settings.google_sheet_id
        and "your_google_sheet_id_here" not in settings.google_sheet_id
    )


def build_google_sheet_diagnostics(settings: Settings) -> dict[str, object]:
    diagnostics: dict[str, object] = {
        "google_sheet_id_present": bool(settings.google_sheet_id),
        "google_sheet_id_preview": (
            f"{settings.google_sheet_id[:6]}...{settings.google_sheet_id[-6:]}"
            if len(settings.google_sheet_id) >= 12
            else settings.google_sheet_id
        ),
        "proposal_master_sheet": settings.google_worksheet_proposal_master,
        "product_sheet": settings.google_worksheet_code_map_product,
        "status_sheet": settings.google_worksheet_code_map_status,
        "sync_log_sheet": settings.google_worksheet_sync_log,
        "service_account_json_present": bool(settings.google_service_account_json),
        "service_account_json_path_present": bool(settings.google_service_account_json_path),
        "service_account_json_valid": None,
        "service_account_client_email": "",
    }

    if settings.google_service_account_json:
        try:
            service_account_info = json.loads(settings.google_service_account_json)
        except json.JSONDecodeError as exc:
            diagnostics["service_account_json_valid"] = False
            diagnostics["service_account_json_error"] = str(exc)
        else:
            diagnostics["service_account_json_valid"] = True
            diagnostics["service_account_client_email"] = service_account_info.get("client_email", "")
    elif settings.google_service_account_json_path:
        diagnostics["service_account_json_path_exists"] = _service_account_path(settings).exists()

    return diagnostics


def _service_account_path(settings: Settings) -> Path:
    raw_path = Path(settings.google_service_account_json_path)
    if raw_path.is_absolute():
        return raw_path
    return ROOT_DIR / raw_path


def _build_gspread_client(settings: Settings):
    try:
        import gspread
    except ImportError as exc:
        raise RuntimeError("`gspread` is not installed. Run `pip install -r requirements.txt`.") from exc

    if settings.google_service_account_json:
        try:
            service_account_info = json.loads(settings.google_service_account_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("`GOOGLE_SERVICE_ACCOUNT_JSON` is not valid JSON.") from exc
        return gspread.service_account_from_dict(service_account_info)

    service_account_path = _service_account_path(settings)
    if not service_account_path.exists():
        raise FileNotFoundError(f"Service account file not found: {service_account_path}")
    return gspread.service_account(filename=str(service_account_path))


def _proposal_master_header_index_map(headers: list[object]) -> dict[str, int]:
    header_map: dict[str, int] = {}
    for index, raw_header in enumerate(headers, start=1):
        header = str(raw_header).strip()
        canonical = PROPOSAL_MASTER_COLUMN_ALIASES.get(header, header)
        if canonical:
            header_map[str(canonical)] = index
    return header_map


def _serialize_update_value(column: str, value: object) -> str:
    if column in {
        "total_project_cost_kkrw",
        "government_funding_kkrw",
        "private_cash_kkrw",
        "private_in_kind_kkrw",
    }:
        normalized = normalize_text(value)
        if not normalized:
            return ""
        numeric = pd.to_numeric(pd.Series([normalized]), errors="coerce").iloc[0]
        if pd.isna(numeric):
            raise ValueError(f"`{column}` must be numeric.")
        if float(numeric).is_integer():
            return str(int(numeric))
        return str(float(numeric))

    if column == "awarded_yn":
        return normalize_yn_flag(value)

    if column == "last_updated_at":
        return normalize_text(value) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return normalize_text(value)


def _status_name_to_code_map(settings: Settings) -> dict[str, str]:
    status_records = fetch_worksheet_records(settings, settings.google_worksheet_code_map_status)
    status_df = pd.DataFrame(status_records)
    if status_df.empty or "status_name" not in status_df.columns or "status_code" not in status_df.columns:
        return {}

    return {
        normalize_text(row.get("status_name")): normalize_text(row.get("status_code")).upper()
        for _, row in status_df.iterrows()
        if normalize_text(row.get("status_name"))
    }


def validate_proposal_master_edit_payload(
    settings: Settings,
    worksheet,
    proposal_id: str,
    updates: dict[str, object],
) -> tuple[dict[str, int], dict[str, object]]:
    normalized_proposal_id = normalize_text(proposal_id)
    if not normalized_proposal_id:
        raise ValueError("`proposal_id` is required.")

    headers = worksheet.row_values(1)
    header_map = _proposal_master_header_index_map(headers)
    required_columns = {
        "proposal_id",
        "status_code",
        "status_name",
        "awarded_yn",
        "ministry",
        "owner",
        "notes",
        "total_project_cost_kkrw",
        "government_funding_kkrw",
        "private_cash_kkrw",
        "private_in_kind_kkrw",
        "last_updated_at",
    }
    missing_columns = sorted(column for column in required_columns if column not in header_map)
    if missing_columns:
        raise RuntimeError(f"PROPOSAL_MASTER에 필요한 컬럼이 없습니다: {', '.join(missing_columns)}")

    validated_updates = dict(updates)
    if "status_name" in validated_updates:
        status_name = normalize_text(validated_updates["status_name"])
        if status_name:
            status_map = _status_name_to_code_map(settings)
            if status_name not in status_map:
                raise ValueError(f"상태값 `{status_name}` 이 CODE_MAP_STATUS에 없습니다.")
            validated_updates["status_name"] = status_name
            validated_updates["status_code"] = status_map[status_name]

    awarded_flag = normalize_yn_flag(validated_updates.get("awarded_yn"))
    if awarded_flag not in {"", "Y", "N"}:
        raise ValueError("수주여부는 Y, N 또는 빈값만 입력할 수 있습니다.")
    if "awarded_yn" in validated_updates:
        validated_updates["awarded_yn"] = awarded_flag

    return header_map, validated_updates


def append_sync_log_entry(
    settings: Settings,
    action: str,
    source_sheet: str,
    message: str,
    row_count: int = 1,
) -> None:
    client = _build_gspread_client(settings)
    workbook = client.open_by_key(settings.google_sheet_id)
    worksheet = workbook.worksheet(settings.google_worksheet_sync_log)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "run_id": f"manual-edit-{uuid4().hex[:12]}",
        "run_type": action,
        "source_sheet": source_sheet,
        "started_at": timestamp,
        "finished_at": timestamp,
        "rows_read": str(row_count),
        "rows_valid": str(row_count),
        "rows_error": "0",
        "message": message,
    }
    headers = [str(header).strip() for header in worksheet.row_values(1)]
    row_values = [payload.get(header, "") for header in headers]
    worksheet.append_row(row_values, value_input_option="USER_ENTERED")
    refreshed_records = worksheet.get_all_records()
    pd.DataFrame(refreshed_records).to_csv(
        cache_path_for_worksheet(settings.google_worksheet_sync_log),
        index=False,
        encoding="utf-8-sig",
    )


def generate_next_proposal_id(worksheet) -> str:
    headers = worksheet.row_values(1)
    header_map = _proposal_master_header_index_map(headers)
    proposal_id_col = header_map.get("proposal_id")
    if proposal_id_col is None:
        raise RuntimeError("`proposal_id` column was not found in PROPOSAL_MASTER.")

    current_year = datetime.now().year
    proposal_ids = worksheet.col_values(proposal_id_col)[1:]
    pattern = re.compile(r"^PROP-(\d{4})-(\d+)$", re.IGNORECASE)
    max_sequence = 0
    for raw_value in proposal_ids:
        match = pattern.match(normalize_text(raw_value))
        if not match:
            continue
        proposal_year = int(match.group(1))
        proposal_sequence = int(match.group(2))
        if proposal_year == current_year:
            max_sequence = max(max_sequence, proposal_sequence)
    return f"PROP-{current_year}-{max_sequence + 1:03d}"


def create_proposal_master_record(
    settings: Settings,
    payload: dict[str, object],
) -> dict[str, str]:
    if not is_google_sheet_configured(settings):
        raise RuntimeError("Google Sheet is not configured.")

    client = _build_gspread_client(settings)
    workbook = client.open_by_key(settings.google_sheet_id)
    worksheet = workbook.worksheet(settings.google_worksheet_proposal_master)
    headers = [str(header).strip() for header in worksheet.row_values(1)]
    header_map = _proposal_master_header_index_map(headers)

    required_columns = {
        "proposal_id",
        "business_name",
        "project_name",
        "status_code",
        "status_name",
        "submission_deadline",
        "awarded_yn",
        "owner",
        "last_updated_at",
    }
    missing_columns = sorted(column for column in required_columns if column not in header_map)
    if missing_columns:
        raise RuntimeError(f"PROPOSAL_MASTER에 필요한 컬럼이 없습니다: {', '.join(missing_columns)}")

    status_map = _status_name_to_code_map(settings)
    status_name = normalize_text(payload.get("status_name"))
    if not status_name:
        raise ValueError("상태는 필수입니다.")
    if status_name not in status_map:
        raise ValueError(f"상태값 `{status_name}` 이 CODE_MAP_STATUS에 없습니다.")

    business_name = normalize_text(payload.get("business_name"))
    project_name = normalize_text(payload.get("project_name"))
    if not business_name:
        raise ValueError("사업명은 필수입니다.")
    if not project_name:
        raise ValueError("과제명은 필수입니다.")

    submission_deadline = normalize_text(payload.get("submission_deadline"))
    if not submission_deadline:
        raise ValueError("마감일은 필수입니다.")
    parsed_deadline = pd.to_datetime(submission_deadline, errors="coerce")
    if pd.isna(parsed_deadline):
        raise ValueError("마감일은 YYYY-MM-DD 형식으로 입력해 주세요.")

    awarded_flag = normalize_yn_flag(payload.get("awarded_yn"))
    if awarded_flag not in {"", "Y", "N"}:
        raise ValueError("수주여부는 Y, N 또는 빈값만 입력할 수 있습니다.")

    proposal_id = generate_next_proposal_id(worksheet)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized_payload: dict[str, object] = {column: "" for column in PROPOSAL_MASTER_COLUMNS}
    normalized_payload.update(
        {
            "proposal_id": proposal_id,
            "business_name": business_name,
            "project_name": project_name,
            "product_code": normalize_text(payload.get("product_code")),
            "topic": normalize_text(payload.get("topic")),
            "ministry": normalize_text(payload.get("ministry")),
            "agency": normalize_text(payload.get("agency")),
            "status_code": status_map[status_name],
            "status_name": status_name,
            "submission_deadline": parsed_deadline.strftime("%Y-%m-%d"),
            "awarded_yn": awarded_flag,
            "owner": normalize_text(payload.get("owner")),
            "partner": normalize_text(payload.get("partner")),
            "notes": normalize_text(payload.get("notes")),
            "last_updated_at": timestamp,
        }
    )
    for amount_column in [
        "total_project_cost_kkrw",
        "government_funding_kkrw",
        "private_cash_kkrw",
        "private_in_kind_kkrw",
    ]:
        normalized_payload[amount_column] = payload.get(amount_column)

    row_values: list[str] = []
    applied_values: dict[str, str] = {}
    for header in headers:
        canonical = PROPOSAL_MASTER_COLUMN_ALIASES.get(header, header)
        raw_value = normalized_payload.get(str(canonical), "")
        serialized_value = _serialize_update_value(str(canonical), raw_value)
        row_values.append(serialized_value)
        if str(canonical) in PROPOSAL_MASTER_COLUMNS and serialized_value:
            applied_values[str(canonical)] = serialized_value

    worksheet.append_row(row_values, value_input_option="USER_ENTERED")
    refreshed_records = worksheet.get_all_records()
    pd.DataFrame(refreshed_records).to_csv(
        cache_path_for_worksheet(settings.google_worksheet_proposal_master),
        index=False,
        encoding="utf-8-sig",
    )
    append_sync_log_entry(
        settings=settings,
        action="MANUAL_CREATE",
        source_sheet=settings.google_worksheet_proposal_master,
        message=f"{proposal_id} created: {project_name}",
        row_count=1,
    )
    return applied_values


def fetch_worksheet_records(settings: Settings, worksheet_name: str) -> list[dict[str, object]]:
    if not is_google_sheet_configured(settings):
        return []

    client = _build_gspread_client(settings)
    workbook = client.open_by_key(settings.google_sheet_id)
    worksheet = workbook.worksheet(worksheet_name)
    return worksheet.get_all_records()


def update_proposal_master_record(
    settings: Settings,
    proposal_id: str,
    updates: dict[str, object],
) -> dict[str, str]:
    normalized_proposal_id = normalize_text(proposal_id)
    if not normalized_proposal_id:
        raise ValueError("`proposal_id` is required.")
    if not is_google_sheet_configured(settings):
        raise RuntimeError("Google Sheet is not configured.")

    allowed_columns = {
        "status_code",
        "status_name",
        "awarded_yn",
        "ministry",
        "owner",
        "notes",
        "total_project_cost_kkrw",
        "government_funding_kkrw",
        "private_cash_kkrw",
        "private_in_kind_kkrw",
        "last_updated_at",
    }
    sanitized_updates = {column: value for column, value in updates.items() if column in allowed_columns}
    if not sanitized_updates:
        raise ValueError("No editable fields were provided.")

    if "status_name" in sanitized_updates and "status_code" not in sanitized_updates:
        status_code = _status_name_to_code_map(settings).get(normalize_text(sanitized_updates["status_name"]), "")
        sanitized_updates["status_code"] = status_code
    sanitized_updates["last_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    client = _build_gspread_client(settings)
    workbook = client.open_by_key(settings.google_sheet_id)
    worksheet = workbook.worksheet(settings.google_worksheet_proposal_master)
    header_map, sanitized_updates = validate_proposal_master_edit_payload(
        settings=settings,
        worksheet=worksheet,
        proposal_id=normalized_proposal_id,
        updates=sanitized_updates,
    )
    proposal_id_col = header_map.get("proposal_id")
    if proposal_id_col is None:
        raise RuntimeError("`proposal_id` column was not found in PROPOSAL_MASTER.")

    proposal_ids = worksheet.col_values(proposal_id_col)
    target_row_index: int | None = None
    for row_index, cell_value in enumerate(proposal_ids[1:], start=2):
        if normalize_text(cell_value) == normalized_proposal_id:
            target_row_index = row_index
            break
    if target_row_index is None:
        raise KeyError(f"Proposal not found: {normalized_proposal_id}")

    try:
        import gspread
    except ImportError as exc:
        raise RuntimeError("`gspread` is not installed. Run `pip install -r requirements.txt`.") from exc

    cells: list[object] = []
    applied_updates: dict[str, str] = {}
    for column, raw_value in sanitized_updates.items():
        column_index = header_map.get(column)
        if column_index is None:
            continue
        serialized_value = _serialize_update_value(column, raw_value)
        cells.append(gspread.Cell(target_row_index, column_index, serialized_value))
        applied_updates[column] = serialized_value

    if not cells:
        raise RuntimeError("Editable columns were not found in PROPOSAL_MASTER.")

    worksheet.update_cells(cells, value_input_option="USER_ENTERED")
    refreshed_records = worksheet.get_all_records()
    pd.DataFrame(refreshed_records).to_csv(
        cache_path_for_worksheet(settings.google_worksheet_proposal_master),
        index=False,
        encoding="utf-8-sig",
    )
    append_sync_log_entry(
        settings=settings,
        action="MANUAL_EDIT",
        source_sheet=settings.google_worksheet_proposal_master,
        message=f"{normalized_proposal_id} updated: {', '.join(sorted(applied_updates))}",
        row_count=1,
    )
    return applied_updates


def worksheet_names(settings: Settings) -> list[str]:
    return [
        settings.google_worksheet_proposal_master,
        settings.google_worksheet_code_map_product,
        settings.google_worksheet_code_map_status,
        settings.google_worksheet_sync_log,
    ]


def cache_dir() -> Path:
    return ROOT_DIR / "data" / "cache"


def cache_path_for_worksheet(worksheet_name: str) -> Path:
    return cache_dir() / f"{worksheet_name}.csv"


def _format_exception(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__


def load_cached_workbook_frames(settings: Settings) -> dict[str, pd.DataFrame]:
    workbook_frames: dict[str, pd.DataFrame] = {}
    for worksheet_name in worksheet_names(settings):
        csv_path = cache_path_for_worksheet(worksheet_name)
        workbook_frames[worksheet_name] = pd.read_csv(csv_path) if csv_path.exists() else pd.DataFrame()
    return workbook_frames


@dataclass(slots=True)
class WorkbookLoadResult:
    workbook_frames: dict[str, pd.DataFrame]
    source: str
    message: str


def load_workbook_frames(settings: Settings, allow_empty: bool = False) -> dict[str, pd.DataFrame]:
    if not is_google_sheet_configured(settings):
        if allow_empty:
            return {name: pd.DataFrame() for name in worksheet_names(settings)}
        raise RuntimeError("Google Sheet is not configured. Update `.env` before loading data.")

    workbook_frames: dict[str, pd.DataFrame] = {}
    for sheet_name in worksheet_names(settings):
        records = fetch_worksheet_records(settings, sheet_name)
        workbook_frames[sheet_name] = pd.DataFrame(records)
    return workbook_frames


def load_live_or_cached_workbook_frames(settings: Settings) -> WorkbookLoadResult:
    if is_google_sheet_configured(settings):
        try:
            return WorkbookLoadResult(
                workbook_frames=load_workbook_frames(settings),
                source="google_sheet",
                message="Loaded live data from Google Sheet.",
            )
        except Exception as exc:
            cached_frames = load_cached_workbook_frames(settings)
            if any(not frame.empty for frame in cached_frames.values()):
                return WorkbookLoadResult(
                    workbook_frames=cached_frames,
                    source="cache",
                    message=f"Google Sheet load failed, using cached CSV data instead: {_format_exception(exc)}",
                )
            return WorkbookLoadResult(
                workbook_frames={name: pd.DataFrame() for name in worksheet_names(settings)},
                source="empty",
                message=f"Google Sheet load failed and no cached CSV data was found: {_format_exception(exc)}",
            )

    cached_frames = load_cached_workbook_frames(settings)
    if any(not frame.empty for frame in cached_frames.values()):
        return WorkbookLoadResult(
            workbook_frames=cached_frames,
            source="cache",
            message="Google Sheet is not configured, using cached CSV data.",
        )

    return WorkbookLoadResult(
        workbook_frames={name: pd.DataFrame() for name in worksheet_names(settings)},
        source="empty",
        message="Google Sheet is not configured and no cached CSV data was found.",
    )


def resolve_workbook_update_timestamp(
    workbook_frames: dict[str, pd.DataFrame],
    settings: Settings,
    source: str,
) -> pd.Timestamp | None:
    sync_log_name = settings.google_worksheet_sync_log
    sync_log_df = workbook_frames.get(sync_log_name, pd.DataFrame())

    if not sync_log_df.empty:
        candidate_columns = [
            "last_updated_at",
            "updated_at",
            "timestamp",
            "synced_at",
            "created_at",
        ]
        for column in candidate_columns:
            if column in sync_log_df.columns:
                timestamps = pd.to_datetime(sync_log_df[column], errors="coerce").dropna()
                if not timestamps.empty:
                    return pd.Timestamp(timestamps.max())

    if source == "cache":
        cache_timestamps: list[pd.Timestamp] = []
        for worksheet_name in worksheet_names(settings):
            csv_path = cache_path_for_worksheet(worksheet_name)
            if csv_path.exists():
                cache_timestamps.append(pd.Timestamp(csv_path.stat().st_mtime, unit="s"))
        if cache_timestamps:
            return max(cache_timestamps)

    return None
