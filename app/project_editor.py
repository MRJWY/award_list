"""Project-scoped forms backed by the existing Google Sheet writers."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from app.edit_access import can_edit, require_editor_access

from core.settings import load_settings
from core.transforms import normalize_text
from core.yearly_budget import AMOUNT_COLUMNS, validate_yearly_budget_amounts
from integrations.google_sheets import (
    DEFAULT_STATUS_CODE_MAP, update_proposal_master_record,
    upsert_yearly_budget_record, validate_edit_date,
)


def close_editor() -> None:
    for name in ("edit_project", "q", "ministry"):
        st.query_params.pop(name, None)


def finish_save(message: str) -> None:
    st.cache_data.clear()
    st.session_state["portfolio_save_message"] = message
    close_editor()
    st.rerun()


def render_info_form(row: pd.Series, product_options: list[dict]) -> None:
    proposal_id = normalize_text(row.proposal_id)
    before = row.to_dict()
    deadline = pd.to_datetime(row.get("submission_deadline"), errors="coerce")
    before["submission_deadline"] = "" if pd.isna(deadline) else deadline.strftime("%Y-%m-%d")
    fields = [
        ("business_name", "사업명"), ("project_name", "과제명"),
        ("ministry", "부처"), ("agency", "기관"), ("owner", "담당자"),
        ("partner", "협력기관"), ("topic", "주제"), ("submission_deadline", "제출 마감일"),
    ]
    with st.form(f"project_info_{proposal_id}"):
        values = {}
        cols = st.columns(2)
        for i, (key, label) in enumerate(fields):
            values[key] = cols[i % 2].text_input(label, value=normalize_text(before.get(key)),
                                               key=f"info_{proposal_id}_{key}")
        codes = list(dict.fromkeys(["", *[option["code"] for option in product_options], normalize_text(row.product_code)]))
        values["product_code"] = cols[0].selectbox("제품", codes, index=codes.index(normalize_text(row.product_code)),
                                                  format_func=lambda value: value or "미입력")
        statuses = list(dict.fromkeys([*DEFAULT_STATUS_CODE_MAP, normalize_text(row.status_name)]))
        values["status_name"] = cols[1].selectbox("상태", statuses, index=statuses.index(normalize_text(row.status_name)))
        values["notes"] = st.text_area("비고", value=normalize_text(row.get("notes")))
        st.caption("제출 마감일은 YYYY-MM-DD 형식입니다. 수행기간과 금액은 ‘연차별 예산’에서 수정합니다.")
        submitted = st.form_submit_button("기본 정보 저장", type="primary")
    if not submitted:
        return
    if not can_edit():
        st.error("수정 인증이 만료되었습니다. 창을 닫고 다시 인증해 주세요.")
        return
    try:
        values["submission_deadline"] = validate_edit_date(values["submission_deadline"])
        changed = {key: value for key, value in values.items() if normalize_text(value) != normalize_text(before.get(key))}
        if not changed:
            st.info("변경된 내용이 없습니다.")
            return
        if "status_name" in changed:
            changed["awarded_yn"] = "Y" if changed["status_name"] == "수주" else "N" if changed["status_name"] in ("미수주", "미선정") else ""
        expected = {key: before.get(key) for key in changed}
        with st.spinner("Google Sheet에 저장하고 확인하는 중…"):
            update_proposal_master_record(load_settings(), proposal_id, changed, expected=expected)
    except Exception as exc:
        st.error(f"저장하지 못했습니다: {exc}")
        return
    finish_save("기본 정보를 Google Sheet에 저장했습니다.")


def render_budget_form(row: pd.Series, yearly: pd.DataFrame) -> None:
    proposal_id = normalize_text(row.proposal_id)
    st.caption("단위: 천원 · 빈칸은 미입력, 0은 0원입니다. 선택한 연차만 저장합니다.")
    selected_year = st.selectbox("수정할 연차", range(1, 31), format_func=lambda value: f"{value}차년도",
                                 key=f"editor_year_{proposal_id}")
    matches = yearly.loc[yearly.proposal_id.eq(proposal_id) & yearly.project_year.eq(selected_year)]
    if len(matches) > 1:
        st.error("같은 연차가 중복되어 있습니다. 시트에서 중복을 정리해 주세요.")
        return
    current = matches.iloc[0] if len(matches) else pd.Series(dtype=object)
    if matches.empty:
        st.info("등록되지 않은 연차입니다. 저장하면 새 연차로 추가합니다.")
    with st.form(f"project_budget_{proposal_id}_{selected_year}"):
        dates = st.columns(2)
        start = dates[0].text_input("연차 시작일", value=normalize_text(current.get("period_start")), placeholder="YYYY-MM-DD")
        end = dates[1].text_input("연차 종료일", value=normalize_text(current.get("period_end")), placeholder="YYYY-MM-DD")
        inputs = {}
        cols = st.columns(3)
        labels = ["우리 정부지원금", "우리 민간부담금(현금)", "우리 민간부담금(현물)"]
        for holder, column, label in zip(cols, AMOUNT_COLUMNS[1:], labels):
            value = current.get(column)
            inputs[column] = holder.text_input(label, value="" if value is None or pd.isna(value) else f"{value:,.0f}")
        with st.expander("컨소시엄 전체 사업비 · 선택 입력"):
            value = current.get(AMOUNT_COLUMNS[0])
            inputs[AMOUNT_COLUMNS[0]] = st.text_input("전체 총사업비", value="" if value is None or pd.isna(value) else f"{value:,.0f}")
        notes = st.text_input("연차별 비고", value=normalize_text(current.get("notes")))
        st.caption("우리 사업비는 정부지원금·현금·현물 합계로 계산합니다. 2026년 카드는 별도로 확정한 Excel 기준값을 유지합니다.")
        submitted = st.form_submit_button("연차별 예산 저장", type="primary")
    if not submitted:
        return
    if not can_edit():
        st.error("수정 인증이 만료되었습니다. 창을 닫고 다시 인증해 주세요.")
        return
    try:
        amounts = validate_yearly_budget_amounts(inputs)
        start, end = validate_edit_date(start), validate_edit_date(end)
        if start and end and start > end:
            raise ValueError("종료일은 시작일보다 빠를 수 없습니다.")
        if matches.empty and not any(value is not None for value in amounts.values()) and not (start or end or notes.strip()):
            raise ValueError("기간 또는 예산을 입력해 주세요.")
        expected = {key: current.get(key) for key in [*AMOUNT_COLUMNS, "period_start", "period_end", "notes"]} if len(matches) else {}
        with st.spinner("Google Sheet에 저장하고 확인하는 중…"):
            upsert_yearly_budget_record(load_settings(), proposal_id, selected_year, amounts, notes,
                                       period_start=start, period_end=end, expected=expected)
    except Exception as exc:
        st.error(f"저장하지 못했습니다: {exc}")
        return
    finish_save(f"{selected_year}차년도 예산을 Google Sheet에 저장했습니다.")


@st.dialog("과제 수정", width="large", on_dismiss=close_editor)
def project_editor(row: pd.Series, yearly: pd.DataFrame, product_options: list[dict]) -> None:
    st.write(normalize_text(row.business_name) or normalize_text(row.project_name))
    if require_editor_access():
        st.caption("저장을 누르면 연결된 Google Sheet 원본에 반영됩니다.")
        info_tab, budget_tab = st.tabs(["기본 정보", "연차별 예산"])
        with info_tab:
            render_info_form(row, product_options)
        with budget_tab:
            render_budget_form(row, yearly)
        if st.button("수정 잠그기"):
            st.session_state.pop("editor_access", None)
            st.rerun(scope="fragment")
    if st.button("닫기 · 저장하지 않음"):
        close_editor()
        st.rerun()


def render_requested_editor(proposals: pd.DataFrame, yearly: pd.DataFrame, product_options: list[dict], data_source: str) -> None:
    proposal_id = st.query_params.get("edit_project", "")
    if not proposal_id:
        return
    if data_source != "google_sheet":
        st.warning("실시간 시트 연결이 복구되면 수정할 수 있습니다.")
        return
    matching = proposals.loc[proposals.proposal_id.eq(proposal_id)]
    if len(matching) != 1:
        st.error("수정할 과제를 찾을 수 없거나 제안ID가 중복되었습니다.")
        return
    project_editor(matching.iloc[0].copy(), yearly.copy(), product_options)
