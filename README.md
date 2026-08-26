# TransitGuard

TransitGuard는 기존 경로 후보에 TAGO 공공데이터 API의 버스 도착예정정보와 정류소 정보를 결합해 **환승 안정성**을 분석하는 오픈소스 프로젝트입니다.

사용자가 입력한 출발 정류소, 도착 정류소와 후보 노선 정보를 바탕으로 첫차 대기시간, 환승 가능 시각, 도보 환승시간과 다음 차량 도착 시각을 계산하고 경로별 안정성 점수를 제공합니다. 완성형 길찾기 서비스를 대체하기보다는 기존 대중교통 경로가 실제로 이용 가능한지를 현실적으로 평가하는 보조 분석 엔진에 가깝습니다.

- 현재 개발 버전: `v0.1.0-alpha.29` (`0.1.0a29`)
- 지원 Python: 3.10 이상
- 라이선스: MIT

> [!IMPORTANT]
> 공개 저장소에는 실제 API 키, `.env`, 개인 PC 경로와 대회 접수정보를 포함하지 않습니다. 실행 전 `.env.example`을 `.env`로 복사하고 본인의 키를 입력하세요.

## 목차

- [프로젝트가 해결하려는 문제](#프로젝트가-해결하려는-문제)
- [주요 기능](#주요-기능)
- [평가 결과](#평가-결과)
- [동작 구조](#동작-구조)
- [빠른 시작](#빠른-시작)
- [환경변수 설정](#환경변수-설정)
- [웹 데모 사용법](#웹-데모-사용법)
- [API 사용법](#api-사용법)
- [보유 대중교통 DB 연동](#보유-대중교통-db-연동)
- [대구·경산 처리 정책](#대구경산-처리-정책)
- [테스트](#테스트)
- [현재 한계](#현재-한계)
- [보안 및 개인정보](#보안-및-개인정보)

## 프로젝트가 해결하려는 문제

일반적인 대중교통 길찾기는 이동시간과 환승 횟수를 중심으로 결과를 보여줍니다. 그러나 실제 이동에서는 다음과 같은 이유로 안내된 환승에 실패할 수 있습니다.

- 첫 번째 차량이 늦게 도착함
- 하차 정류소와 다음 승차 정류소 사이에 도보 이동이 필요함
- 환승에 필요한 최소 여유시간이 부족함
- 다음 차량의 도착정보가 없거나 너무 촉박함
- 지역별 정류소 ID와 도시코드가 달라 실제 노선이 누락됨
- 공공데이터 API의 일부 요청이 지연되거나 실패함

TransitGuard는 이러한 조건을 계산해 단순히 빠른 경로가 아니라 **실제로 환승에 성공할 가능성이 높은 경로를 판단할 수 있도록 돕는 것**을 목표로 합니다.

```text
경로 후보 입력 또는 제한적 후보 탐색
              ↓
정류소·노선·도착정보 결합
              ↓
대기시간·도보시간·최소 환승 여유 계산
              ↓
환승 상태 및 안정성 점수 산출
              ↓
경로 순위·경고·한국어 안내 제공
```

## 주요 기능

### 환승 가능성 평가

- 첫 번째 차량을 기다리는 시간을 계산합니다.
- 이전 차량의 도착 시각에 도보 이동시간과 최소 환승 여유시간을 더해 환승 준비 완료 시각을 구합니다.
- 다음 차량의 도착 후보 중 실제로 탑승 가능한 차량을 선택합니다.
- 환승 결과를 `안전`, `촉박`, `환승 실패`, `정보 부족`으로 구분합니다.
- 전체 이동시간, 첫차 대기시간, 환승 위험과 정보 신뢰도를 반영해 경로별 점수를 계산합니다.

### 기존 경로 후보 평가

TransitGuard의 핵심 기능은 이미 존재하는 경로 후보를 평가하는 것입니다. 사용자가 직접 만든 경로, 다른 길찾기 서비스에서 얻은 후보 또는 자체 데이터베이스에서 생성한 후보를 API나 Python 모델로 전달할 수 있습니다.

```text
기존 경로 후보 → 시간과 환승 조건 검증 → 안정성 평가 → 후보 순위화
```

### 실제 TAGO 데이터 연동

`TAGO_SERVICE_KEY`가 설정되어 있으면 다음 공공데이터를 조회할 수 있습니다.

- 주변 버스정류소
- 정류소별 도착예정정보
- 정류소별 경유 노선
- 노선별 정류소 순서
- 도시코드 및 지하철 역 정보

실사용 모드는 출발지와 도착지 좌표를 받아 주변 정류소를 찾고, 제한된 호출 예산 안에서 직행 또는 환승 후보를 구성합니다.

### 후보가 없을 때의 진단

후보가 0건인 경우에도 단순 오류로 처리하지 않습니다. 응답의 `diagnostics`와 웹 화면에서 다음 정보를 확인할 수 있습니다.

- 실제로 확인한 출발·도착 정류소
- 출발 정류소에서 확인된 도착정보와 노선
- 적용한 도시코드와 정류소 ID 정책
- 후보를 만들지 못한 가능한 원인
- 정류소 수, 검색 범위 또는 탐색 옵션 조정 방법

### 버스·지하철 및 지역 경계 처리

버스 직행과 1회 환승 후보를 평가할 수 있으며, 대구 지역에서는 주변 지하철역과 제한적인 지하철 직접·환승 후보도 구성할 수 있습니다. 대구 DGB 정류소와 경산 GYB 정류소가 중복되거나 서로 다른 API 결과를 제공하는 문제를 줄이기 위해 지역별 도시코드와 정류소 ID 정책을 적용합니다.

### 오류 격리와 호출 제한

- 요청 단위 캐시로 동일한 TAGO 조회를 반복하지 않습니다.
- API 호출 예산을 적용해 무제한 탐색을 방지합니다.
- 하나의 정류소나 노선 조회가 실패해도 가능한 다른 후보 탐색을 계속합니다.
- 공공데이터포털 오류 응답과 시간 초과를 사용자가 이해할 수 있는 메시지로 변환합니다.

## 평가 결과

| 내부 상태 | 한국어 의미 | 설명 |
|---|---|---|
| `safe` | 안전 | 도보 이동과 최소 환승 여유를 고려해 다음 차량에 탑승할 수 있음 |
| `tight` | 촉박 | 탑승 가능성이 있지만 남는 시간이 적어 지연 시 실패 위험이 있음 |
| `missed` | 환승 실패 | 제공된 도착정보로는 필요한 시각 이후에 다음 차량을 탈 수 없음 |
| `unknown` | 정보 부족 | 도착정보가 없거나 부족해 성공 여부를 판단하기 어려움 |

경로 평가에는 다음 정보가 포함됩니다.

- `reliability_score`: 경로 안정성 점수
- `total_minutes`: 전체 이동시간
- `initial_wait_minutes`: 첫 번째 차량 대기시간
- `transfer_results`: 환승별 상태, 탑승 가능 시각, 대기시간과 판단 이유
- `ranking_score`: 여러 경로를 비교하기 위한 순위 점수
- 한국어 요약, 추천, 위험 경고와 다음 행동 안내(API 응답 유형에 따라 제공)

> [!NOTE]
> 높은 점수는 입력된 데이터와 평가 규칙 안에서 상대적으로 안정적이라는 의미입니다. 실제 교통상황과 운행 취소까지 보장하는 확률값은 아닙니다.

## 동작 구조

```text
웹 브라우저
  ├─ 간편 환승 평가
  ├─ 실제 TAGO 경로 탐색
  └─ Kakao 장소 검색 및 지도 표시(선택)
          ↓
FastAPI 서버
  ├─ 입력값 검증
  ├─ 경로 후보 구성
  ├─ TAGO 데이터 조회
  └─ 진단 응답 생성
          ↓
TransitGuard 핵심 엔진
  ├─ 정류소 매칭
  ├─ 환승 평가
  └─ 경로 순위화
```

```text
Kakao 지도    : 장소 검색, 좌표 선택, 마커와 경로 표시
TAGO          : 정류소, 노선과 버스 도착예정정보 제공
TransitGuard  : 경로 후보의 환승 가능성 평가 및 진단
```

## 빠른 시작

### Windows 권장 방법

```text
1. setup_windows.bat 실행
2. start_all_windows.bat 실행
3. http://127.0.0.1:8080 접속
```

`setup_windows.bat`은 `.venv` 가상환경 생성, 의존성 설치, `.env` 예시 복사와 자동화 테스트를 수행합니다. `start_all_windows.bat`은 API 서버와 웹 데모를 각각 실행합니다.

PowerShell에서 `Activate.ps1` 실행이 차단되어도 가상환경을 직접 활성화할 필요는 없습니다. 배치 파일 또는 `.venv\Scripts\python.exe`를 사용하면 됩니다.

### 수동 설치 및 실행

Linux/macOS 계열 셸:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,api]"
python -m pytest -q
python -m uvicorn transitguard.api.app:app --reload
```

Windows:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,api]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn transitguard.api.app:app --reload
```

| 용도 | 주소 |
|---|---|
| 웹 데모 | `http://127.0.0.1:8080` |
| API 문서 | `http://127.0.0.1:8000/docs` |
| 환경 설정 점검 | `http://127.0.0.1:8000/api/setup/check` |

## 환경변수 설정

`.env.example`을 `.env`로 복사한 뒤 필요한 값만 입력합니다.

```env
TAGO_SERVICE_KEY=
TAGO_CITY_CODE=
TAGO_NODE_ID=
TAGO_ORIGIN_NODE_ID=
TAGO_DESTINATION_NODE_ID=
TAGO_ROUTE_IDS=
TRANSITGUARD_CORS_ORIGINS=*
# TRANSITGUARD_ENV_FILE=/absolute/path/to/.env
KAKAO_MAP_JAVASCRIPT_KEY=
```

### TAGO 서비스 키

공공데이터포털에서 관련 TAGO API 사용 신청을 완료한 뒤 발급받은 키를 `TAGO_SERVICE_KEY`에 입력합니다. 키가 없더라도 예제 데이터, 간편 평가 기능과 일반 자동화 테스트는 사용할 수 있습니다.

### Kakao 지도 키

1. Kakao Developers 애플리케이션을 만듭니다.
2. JavaScript 키를 확인합니다.
3. 웹 플랫폼 도메인에 `http://127.0.0.1:8080`을 등록합니다.
4. `.env`의 `KAKAO_MAP_JAVASCRIPT_KEY`에 키를 입력합니다.
5. API 서버를 다시 시작합니다.

> [!WARNING]
> `.env`와 실제 서비스 키를 GitHub에 올리지 마세요. Kakao JavaScript 키도 허용 도메인을 반드시 제한해야 합니다.

## 웹 데모 사용법

### 간편 환승 평가

간단한 시간과 노선 정보를 입력해 한 번의 환승을 평가할 수 있습니다. 안전·촉박·실패 예제 버튼을 사용하면 API 키 없이도 점수와 상태 변화를 확인할 수 있습니다.

### 실제 TAGO 경로 탐색

1. 출발지와 도착지를 검색하거나 위도·경도를 입력합니다.
2. 지역 선택값이 대구 또는 경산에 맞는지 확인합니다.
3. 필요한 경우 탐색 기준 시각과 후보 제한값을 조정합니다.
4. **실제 TAGO 데이터로 후보 찾기**를 실행합니다.
5. 경로 카드에서 노선, 승차·하차 정류소, 경유 정류소, 환승 지점과 시간 출처를 확인합니다.

같은 출발지와 도착지라도 입력한 기준 시각에 따라 대기시간과 환승 평가가 달라질 수 있습니다. 자정을 넘는 시간은 다음 날 시각으로 구분해 표시합니다.

실시간 도착정보와 노선 구조 기반 추정시간은 화면에서 구분합니다. 추정 하차 시각을 공식 시간표로 해석해서는 안 됩니다.

## API 사용법

### 한 번의 환승을 간편하게 평가

```bash
curl -X POST http://127.0.0.1:8000/api/routes/assess/quick \
  --header "Content-Type: application/json" \
  --data @examples/assess_quick_payload.json
```

### 기존 경로 후보 평가

```bash
curl -X POST http://127.0.0.1:8000/api/routes/assess \
  --header "Content-Type: application/json" \
  --data @examples/assess_routes_payload.json
```

TAGO 도착정보를 함께 결합하는 예제는 `examples/assess_routes_tago_payload.json`을 사용합니다. 버스 번호로 비교하려면 `route_key`를 `route_no`로, TAGO 공식 노선 ID로 비교하려면 `route_id`로 설정합니다.

### 출발·도착 좌표로 제한적 후보 탐색

```bash
curl -X POST http://127.0.0.1:8000/api/routes/plan/tago \
  --header "Content-Type: application/json" \
  --data @examples/plan_tago_coordinates_payload.json
```

이 API는 호출 예산 안에서 후보를 구성하며 전국의 모든 가능한 경로를 완전 탐색하지는 않습니다.

### 주요 API 목록

| 메서드 | 경로 | 용도 |
|---|---|---|
| `GET` | `/api/setup/check` | 버전, 시간대와 API 키 설정 확인 |
| `GET` | `/api/demo/quick-presets` | 간편 평가 예제 조회 |
| `POST` | `/api/routes/assess/quick` | 한 번의 환승 간편 평가 |
| `POST` | `/api/routes/assess` | 기존 경로 후보 평가 |
| `POST` | `/api/routes/rank` | 입력 데이터만 사용한 순위화 |
| `POST` | `/api/routes/plan/tago` | 좌표 기반 제한적 TAGO 후보 탐색 |
| `GET` | `/api/tago/diagnostics` | TAGO 설정 및 연결 진단 |
| `GET` | `/api/tago/arrivals` | 정류소 도착예정정보 조회 |
| `GET` | `/api/tago/stations/nearby` | 좌표 주변 정류소 조회 |
| `GET` | `/api/tago/route-stops` | 노선별 정류소 순서 조회 |

상세 요청·응답 형식은 [API 문서](docs/API.md)와 실행 후 제공되는 Swagger UI를 참고하세요.

## 최소 Python 사용 예제

```python
from transitguard import evaluate_route
from transitguard.core.models import Arrival, RouteCandidate, RouteSegment, Transfer

route = RouteCandidate(
    id="candidate-a",
    requested_start_minute=520,
    segments=(
        RouteSegment("101", "A", "B", 524, 540),
        RouteSegment("708", "B", "C", 552, 570),
    ),
    transfers=(
        Transfer(
            from_station_id="B",
            to_station_id="B",
            arrival_minute=540,
            walking_minutes=4,
            minimum_buffer_minutes=3,
            candidate_arrivals=(Arrival("B", "708", 552),),
            target_route_id="708",
        ),
    ),
)

result = evaluate_route(route)
print(result.status, result.reliability_score, result.total_minutes)
```

시간값은 당일 자정부터 지난 분으로 표현합니다. 예를 들어 `08:40`은 `520`, `09:12`는 `552`입니다.

## 보유 대중교통 DB 연동

TransitGuard는 특정 데이터베이스 제품에 종속되지 않습니다. 보유한 정류소·노선·도착정보를 공통 모델로 변환하면 기존 평가 기능을 사용할 수 있습니다.

### CSV로 연결

정류소 CSV:

```csv
id,name,lat,lon,opposite_id
S1,대구역앞,35.8761,128.5961,S2
S2,대구역건너,35.8757,128.5965,S1
```

도착정보 CSV:

```csv
station_id,route_id,arrival_minute
S3,708,548
S3,708,552
```

```python
from transitguard.adapters.timetable_csv import load_arrivals, load_stations

stations = load_stations("stations.csv")
arrivals = load_arrivals("arrivals.csv")
```

- `id`/`station_id`: 내부 정류소 식별자
- `name`: 표시할 정류소 이름
- `lat`, `lon`: 위도와 경도
- `opposite_id`: 길 건너편 또는 대응 정류소 ID, 없으면 빈 값
- `route_id`: 내부 노선 식별자
- `arrival_minute`: 당일 자정부터 계산한 도착 예정 분

실제 예제는 `examples/minimal_stations.csv`와 `examples/minimal_arrivals.csv`에 있습니다.

### 데이터베이스를 직접 연결

1. 데이터베이스에서 정류소, 노선과 도착정보를 조회합니다.
2. 정류소를 `Station`, 도착정보를 `Arrival` 모델로 변환합니다.
3. 경로 구간은 `RouteSegment`, 환승 조건은 `Transfer`, 전체 후보는 `RouteCandidate`로 구성합니다.
4. `evaluate_route` 또는 `rank_routes`에 전달합니다.

정류소 ID 체계가 다른 데이터끼리 결합한다면 이름만 비교하지 말고 좌표, 방향, 대응 정류소와 지역코드도 함께 확인해야 합니다. 새로운 외부 API나 DB를 지속적으로 사용하려면 `src/transitguard/adapters`에 TAGO 어댑터와 같은 변환 계층을 추가하는 방식을 권장합니다.

## 대구·경산 처리 정책

| 이동 구간 | TAGO 도시코드 | 우선 사용하는 정류소 ID |
|---|---:|---|
| 경산 ↔ 경산 | `37100` | `GYB` |
| 대구가 포함된 구간 | `22` | `DGB` |

주변 정류소 제한은 물리 정류소를 기준으로 적용하며, 이름과 좌표가 유사한 DGB/GYB 미러 정류소를 함께 고려할 수 있습니다. 이 규칙은 대구·경산 사례를 안정화하기 위한 명시적 정책이며 전국의 모든 지역 조합을 자동 해결하는 일반 정책은 아닙니다.

## 프로젝트 구조

```text
transitguard/
├─ src/transitguard/
│  ├─ core/                 # 평가 모델, 환승 판정, 순위화, 정류소 매칭
│  ├─ adapters/             # TAGO 및 CSV 데이터 변환
│  └─ api/                  # FastAPI 서버와 요청·응답 모델
├─ web-demo/                # 브라우저 데모
├─ examples/                # API 요청과 CSV 예제
├─ tests/                   # 자동화 테스트
├─ docs/                    # API, 아키텍처와 Windows 안내
├─ setup_windows.bat        # Windows 최초 설정
├─ start_all_windows.bat    # API와 웹 데모 동시 실행
└─ .env.example             # 공개 가능한 환경변수 예시
```

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

실제 TAGO API를 사용하는 선택적 테스트:

```powershell
.\.venv\Scripts\python.exe -m pytest -m live_tago -q
```

실데이터 테스트는 서비스 키와 외부 서버 상태에 영향을 받습니다. 기본 테스트와 분리하면 외부 API 지연을 코드 회귀 오류로 잘못 판단하는 일을 줄일 수 있습니다.

## 현재 한계

- 완성형 전국 대중교통 길찾기 서비스가 아닙니다.
- 좌표 기반 탐색은 시간 초과를 방지하기 위해 정류소·노선·API 호출 수를 제한합니다.
- 제한 밖에 있는 실제 경로가 결과에서 누락될 수 있습니다.
- TAGO 도착예정정보가 없거나 지연되면 `정보 부족`으로 평가될 수 있습니다.
- 노선 구조를 바탕으로 계산한 하차·이동시간은 공식 시간표가 아닌 추정값입니다.
- 지하철 시간과 첫 구간·마지막 구간 이동시간은 제한적으로 추정합니다.
- 교통상황, 운행 취소, 임시 우회와 현장 보행 조건을 완전히 반영하지 못합니다.

실제 이동 전에는 지역 교통기관이나 지도 서비스의 최신 운행정보도 함께 확인해야 합니다.

## 보안 및 개인정보

- 실제 `.env`와 API 키를 커밋하지 않습니다.
- 로그, 화면 녹화와 오류 보고에 키가 표시되지 않았는지 확인합니다.
- 배포 환경에서는 `TRANSITGUARD_CORS_ORIGINS=*` 대신 허용할 출처만 지정합니다.
- Kakao JavaScript 키는 허용 웹 도메인을 제한합니다.
- 노출된 키는 파일만 삭제하지 말고 발급기관에서 폐기·재발급합니다.

보안 문제 제보 절차는 [SECURITY.md](SECURITY.md)를 참고하세요.

## 추가 문서

- [API 설명](docs/API.md)
- [아키텍처](docs/ARCHITECTURE.md)
- [Windows 실행 안내](docs/WINDOWS.md)
- [변경 이력](CHANGELOG.md)
- [기여 방법](CONTRIBUTING.md)

## 라이선스

TransitGuard는 [MIT License](LICENSE)로 배포됩니다.

