from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from core.settings import ROOT_DIR, Settings


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


def fetch_worksheet_records(settings: Settings, worksheet_name: str) -> list[dict[str, object]]:
    if not is_google_sheet_configured(settings):
        return []

    try:
        import gspread
    except ImportError as exc:
        raise RuntimeError("`gspread` is not installed. Run `pip install -r requirements.txt`.") from exc

    if settings.google_service_account_json:
        try:
            service_account_info = json.loads(settings.google_service_account_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("`GOOGLE_SERVICE_ACCOUNT_JSON` is not valid JSON.") from exc
        client = gspread.service_account_from_dict(service_account_info)
    else:
        service_account_path = _service_account_path(settings)
        if not service_account_path.exists():
            raise FileNotFoundError(f"Service account file not found: {service_account_path}")
        client = gspread.service_account(filename=str(service_account_path))

    workbook = client.open_by_key(settings.google_sheet_id)
    worksheet = workbook.worksheet(worksheet_name)
    return worksheet.get_all_records()


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
