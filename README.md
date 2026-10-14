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

### 간단한 사업비 대시보드

- 기본 화면은 통합 검색창과 **우리 총 사업비 · 정부지원 사업비 · 2026년 사업비** 세 카드입니다. 검색은 과제명, 사업명, 제품, 부처, 기관, 담당자 등을 지원합니다.
- 검색어를 입력하면 예산 카드 아래에 전체 등록 사업의 검색 결과를 표시합니다. 각 결과에서 사업명·과제명, 상태, 부처·기관, 담당자, 제품, 협력기관과 등록 연차 기간을 확인할 수 있습니다. 검색어를 지우면 결과도 숨깁니다. 상단 예산 집계는 계속 수주 과제 기준입니다.
- 수주 과제에 연결된 `PROJECT_YEAR_BUDGET`의 우리 회사 배정 금액을 합산합니다. 우리 총 사업비는 전체 연차의 정부지원금·현금·현물 합계이며, 정부지원 사업비는 전체 연차의 우리 정부지원금입니다. 컨소시엄 전체 금액을 우리 사업비로 사용하지 않습니다.
- 2026년 사업비는 사용자 확인을 거친 Excel `예산 총괄표 `의 `K3` 정부지원금 합계입니다. 검색과 관계없이 Excel 전체 과제 기준으로 표시하며, 현금·현물 부담금은 포함하지 않습니다.
- Excel 확정 합계와 기준일은 Streamlit Cloud의 **Secrets**에 `ANNUAL_BUDGET_2026_GOVERNMENT_KKRW`(천원), `ANNUAL_BUDGET_2026_AS_OF`(`YYYY-MM-DD`)로 설정합니다. 로컬에서는 Git에서 제외된 `.streamlit/secrets.toml` 또는 `.env`를 사용합니다. 실제 금액과 원본 Excel은 공개 저장소에 포함하지 않습니다.
- Excel 변경 시 `K3`를 구성하는 과제별 정부지원금 합계와 대조한 뒤 비공개 설정의 금액과 기준일을 함께 갱신합니다. Excel 자동 동기화는 하지 않으며, 설정이 없거나 잘못되면 2026년 카드는 `미입력`으로 표시합니다. Secrets는 저장 위치를 보호하며, 카드의 공개 여부는 앱 접근 권한에 따릅니다.
- 미입력은 0원과 구분하고, 카드 하단에 입력 연차 수·미등록 과제 수를 표시합니다. 우리 사업비는 정부지원금·현금·현물 세 항목이 모두 입력된 연차만 포함합니다.
- 과제 및 예산 수정은 연결된 Google Sheet에서 합니다. 앱에서 관리 탭·분포 차트·기존 건수 KPI는 표시하지 않습니다.

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

대시보드의 **우리 총 사업비**는 우리 회사의 세 금액이 모두 입력된 연차에 한해 계산합니다. 일부만 입력된 연차는 합계에서 제외하며 입력 연차 수를 카드에 표시합니다. 금액 수정은 Google Sheet에서 합니다.

Google Sheet의 `연차별 사업비 요약 (자동)` 탭에서는 한 과제를 한 행에 놓고 1~5차년도 기간·전체사업비·우리사업비를 나란히 표시합니다. 연차는 사업 시작일부터 그해 12월 31일까지를 1차년도로, 이후 매년 1월 1일부터 12월 31일까지를 다음 연차로 구분합니다. 마지막 연차는 실제 사업 종료일에 끝납니다. 시작일 또는 종료일이 확인되지 않은 과제의 날짜는 추정하지 않고 비워 둡니다. 금액은 초록색 `PROJECT_YEAR_BUDGET` 탭의 노란색 E:H열에서 입력합니다. 요약 탭은 입력값을 참조하는 보기용 표입니다.

## Streamlit Community Cloud 배포

1. Streamlit Cloud에서 이 저장소를 연결합니다.
2. Main file path를 `streamlit_app.py`로 지정합니다.
3. `.streamlit/secrets.toml.example` 내용을 기준으로 Secrets를 입력합니다.
4. 서비스 계정 이메일을 대상 Google Sheet에 공유합니다.

## 참고

- `.env`, `secrets/`, 실제 캐시 CSV, 로그 파일은 저장소에 올리지 않도록 `.gitignore`에 제외되어 있습니다.
- Google Sheet 연결이 실패하면 `data/cache/`의 CSV를 fallback으로 읽도록 설계되어 있습니다.
