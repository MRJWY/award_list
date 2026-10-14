"""Session-scoped editor access; viewing the dashboard remains public."""
from __future__ import annotations

import hashlib
import hmac
import os
import time

import streamlit as st

from core.settings import _streamlit_secret

SESSION_SECONDS = 1800


def edit_password() -> str:
    return _streamlit_secret("DASHBOARD_EDIT_PASSWORD") or os.getenv("DASHBOARD_EDIT_PASSWORD", "")


def can_edit() -> bool:
    password = edit_password()
    if len(password) < 12:
        return False
    token = st.session_state.get("editor_access", {})
    return (
        isinstance(token, dict)
        and time.time() < token.get("expires", 0)
        and hmac.compare_digest(str(token.get("fingerprint", "")), hashlib.sha256(password.encode()).hexdigest())
    )


def unlock_editor() -> None:
    password = edit_password()
    supplied = st.session_state.pop("editor_password_input", "")
    if len(password) >= 12 and hmac.compare_digest(str(supplied).encode(), password.encode()):
        st.session_state["editor_access"] = {
            "fingerprint": hashlib.sha256(password.encode()).hexdigest(),
            "expires": time.time() + SESSION_SECONDS,
        }
        st.session_state.pop("editor_password_error", None)
    else:
        st.session_state["editor_password_error"] = "비밀번호가 일치하지 않습니다."


def require_editor_access() -> bool:
    if can_edit():
        return True
    if len(edit_password()) < 12:
        st.info("수정 비밀번호 설정을 준비 중입니다. 지금은 조회만 가능합니다.")
        return False
    st.caption("수정 권한 확인 · 인증 후 30분 동안 이 창에서 수정할 수 있습니다.")
    with st.form("editor_unlock"):
        st.text_input("수정 비밀번호", type="password", key="editor_password_input")
        st.form_submit_button("수정 잠금 해제", on_click=unlock_editor, type="primary")
    if message := st.session_state.get("editor_password_error"):
        st.error(message)
    return False
