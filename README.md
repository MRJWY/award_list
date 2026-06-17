# Award List Dashboard

Google Sheet 기반 사업 제안/수주 현황을 Streamlit 대시보드로 확인하는 앱입니다.

## 포함된 내용

- `app/main.py`: 메인 Streamlit 대시보드
- `streamlit_app.py`: Streamlit Cloud용 엔트리포인트
- `core/`: 대시보드 집계, 설정, 데이터 정규화 로직
- `integrations/google_sheets.py`: Google Sheets 로드 및 캐시 fallback 처리
- `scripts/run_dashboard.py`: 로컬 실행 스크립트
- `.streamlit/`: Streamlit 설정 및 secrets 예시

## 로컬 실행

```powershell
pip install -r requirements.txt
copy .env.example .env
python scripts\run_dashboard.py
```

또는

```powershell
streamlit run streamlit_app.py
```

## 필수 환경변수

- `GOOGLE_SHEET_ID`
- `GOOGLE_WORKSHEET_PROPOSAL_MASTER`
- `GOOGLE_WORKSHEET_CODE_MAP_PRODUCT`
- `GOOGLE_WORKSHEET_CODE_MAP_STATUS`
- `GOOGLE_WORKSHEET_SYNC_LOG`

Google 서비스 계정은 둘 중 하나 방식으로 설정하면 됩니다.

- 로컬: `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`
- Streamlit Cloud: `GOOGLE_SERVICE_ACCOUNT_JSON`

## Streamlit Community Cloud 배포

1. Streamlit Cloud에서 이 저장소를 연결합니다.
2. Main file path를 `streamlit_app.py`로 지정합니다.
3. `.streamlit/secrets.toml.example` 내용을 기준으로 Secrets를 입력합니다.
4. 서비스 계정 이메일을 대상 Google Sheet에 공유합니다.

## 참고

- `.env`, `secrets/`, 실제 캐시 CSV, 로그 파일은 저장소에 올리지 않도록 `.gitignore`에 제외되어 있습니다.
- Google Sheet 연결이 실패하면 `data/cache/`의 CSV를 fallback으로 읽도록 설계되어 있습니다.
