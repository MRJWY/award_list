from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(slots=True)
class Settings:
    app_env: str
    app_timezone: str
    log_level: str
    google_service_account_json_path: str
    google_service_account_json: str
    google_sheet_id: str
    google_worksheet_proposal_master: str
    google_worksheet_code_map_product: str
    google_worksheet_code_map_status: str
    google_worksheet_sync_log: str
    streamlit_server_port: int
    streamlit_server_headless: bool
    slack_bot_token: str
    slack_app_token: str
    slack_signing_secret: str
    slack_default_channel: str


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _streamlit_secret(name: str, default: str = "") -> str:
    try:
        import streamlit as st

        if not hasattr(st, "secrets"):
            return default
        value = _find_streamlit_secret_value(st.secrets, name, default)
        if value is None:
            return default
        return str(value).strip()
    except Exception:
        return default


def _find_streamlit_secret_value(container: object, name: str, default: object = "") -> object:
    if isinstance(container, Mapping):
        if name in container:
            return container.get(name, default)

        lowered_name = name.lower()
        upper_name = name.upper()
        for key in (lowered_name, upper_name):
            if key in container:
                return container.get(key, default)

        for value in container.values():
            nested = _find_streamlit_secret_value(value, name, default=None)
            if nested is not None:
                return nested

    return default


def _config_value(name: str, default: str = "") -> str:
    return _env(name) or _streamlit_secret(name, default) or default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name) or _streamlit_secret(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_settings() -> Settings:
    _load_env_file(ROOT_DIR / ".env")
    google_service_account_json_path = _config_value("GOOGLE_SERVICE_ACCOUNT_JSON_PATH") or _config_value("GOOGLE_SERVICE_ACCOUNT_FILE")
    google_service_account_json = _config_value("GOOGLE_SERVICE_ACCOUNT_JSON")

    return Settings(
        app_env=_config_value("APP_ENV", "local"),
        app_timezone=_config_value("APP_TIMEZONE", "Asia/Seoul"),
        log_level=_config_value("LOG_LEVEL", "INFO"),
        google_service_account_json_path=google_service_account_json_path,
        google_service_account_json=google_service_account_json,
        google_sheet_id=_config_value("GOOGLE_SHEET_ID"),
        google_worksheet_proposal_master=_config_value("GOOGLE_WORKSHEET_PROPOSAL_MASTER", "PROPOSAL_MASTER"),
        google_worksheet_code_map_product=_config_value("GOOGLE_WORKSHEET_CODE_MAP_PRODUCT", "CODE_MAP_PRODUCT"),
        google_worksheet_code_map_status=_config_value("GOOGLE_WORKSHEET_CODE_MAP_STATUS", "CODE_MAP_STATUS"),
        google_worksheet_sync_log=_config_value("GOOGLE_WORKSHEET_SYNC_LOG", "SYNC_LOG"),
        streamlit_server_port=int(_config_value("STREAMLIT_SERVER_PORT", "8501")),
        streamlit_server_headless=_env_bool("STREAMLIT_SERVER_HEADLESS", True),
        slack_bot_token=_config_value("SLACK_BOT_TOKEN"),
        slack_app_token=_config_value("SLACK_APP_TOKEN"),
        slack_signing_secret=_config_value("SLACK_SIGNING_SECRET"),
        slack_default_channel=_config_value("SLACK_DEFAULT_CHANNEL", "#proposal-alerts"),
    )
