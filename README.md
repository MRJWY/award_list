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
- `GOOGLE_WORKSHEET_YEARLY_BUDGET` (기본값: `PROJECT_YEAR_BUDGET`)

Google 서비스 계정은 둘 중 하나 방식으로 설정하면 됩니다.

- 로컬: `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`
- Streamlit Cloud: `GOOGLE_SERVICE_ACCOUNT_JSON`

## 연차별 사업비 입력

연결된 Google Sheet의 `PROJECT_YEAR_BUDGET` 탭에 과제별로 1차년도, 2차년도 등의 행을 입력합니다. 한 과제와 한 연차는 한 행이며 `제안ID`는 `PROPOSAL_MASTER`의 제안ID와 같아야 합니다. 금액 단위는 모두 **천원**입니다.

| 열 | 의미 |
| --- | --- |
| 제안ID | 원본 과제와 연결하는 ID |
| 연차 | 1, 2, 3 … (사업 시작 연도를 1차년도로 계산) |
| 연차 시작일·종료일 | 해당 연차의 사업 기간. 원본에 정확한 날짜가 없으면 공란 |
| 총사업비(천원) | 해당 연차의 전체 사업비 |
| 우리 정부지원금(천원) | 해당 연차에 우리 회사에 배정된 정부지원금 |
| 우리 민간부담금(현금, 천원) | 해당 연차의 우리 회사 현금 부담금 |
| 우리 민간부담금(현물, 천원) | 해당 연차의 우리 회사 현물 부담금 |

대시보드의 **우리 사업비 합계**는 우리 회사의 세 금액이 모두 입력된 연차에 한해 계산합니다. 일부만 입력된 연차는 미입력으로 표시합니다. 과제 카드의 상세 화면에서도 연차별 금액을 입력하거나 수정할 수 있습니다. 전체 사업비의 연차 합계와 원본 과제의 총사업비는 나란히 보여주며, 차이가 있어도 입력 도중에는 저장을 막지 않습니다.

Google Sheet의 `연차별 사업비 요약 (자동)` 탭과 대시보드의 **과제별 연차 비교** 표에서는 한 과제를 한 행에 놓고 1~5차년도 기간·전체사업비·우리사업비를 나란히 표시합니다. 연차는 사업 시작일부터 그해 12월 31일까지를 1차년도로, 이후 매년 1월 1일부터 12월 31일까지를 다음 연차로 구분합니다. 마지막 연차는 실제 사업 종료일에 끝납니다. 시작일 또는 종료일이 확인되지 않은 과제의 날짜는 추정하지 않고 비워 둡니다. 금액은 초록색 `PROJECT_YEAR_BUDGET` 탭의 노란색 E:H열 또는 대시보드의 과제 상세 화면에서 입력합니다. 요약 탭은 입력값을 참조하는 보기용 표입니다.

## Streamlit Community Cloud 배포

1. Streamlit Cloud에서 이 저장소를 연결합니다.
2. Main file path를 `streamlit_app.py`로 지정합니다.
3. `.streamlit/secrets.toml.example` 내용을 기준으로 Secrets를 입력합니다.
4. 서비스 계정 이메일을 대상 Google Sheet에 공유합니다.

## 참고

- `.env`, `secrets/`, 실제 캐시 CSV, 로그 파일은 저장소에 올리지 않도록 `.gitignore`에 제외되어 있습니다.
- Google Sheet 연결이 실패하면 `data/cache/`의 CSV를 fallback으로 읽도록 설계되어 있습니다.
