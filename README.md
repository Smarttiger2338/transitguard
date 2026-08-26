# TransitGuard

TransitGuard는 대중교통 경로의 **환승 가능성과 안정성**을 확인할 수 있는 오픈소스 분석 도구입니다.

이미 알고 있는 경로 후보나 직접 보유한 대중교통 데이터를 입력하면 첫 차량 대기시간, 환승 준비 시각, 도보 이동시간과 다음 차량 도착 시각을 계산합니다. 결과는 안전, 촉박, 환승 실패 또는 정보 부족 상태와 경로별 점수로 제공됩니다.

> TransitGuard는 전국의 모든 경로를 찾아주는 완성형 지도 서비스가 아닙니다. 기존 경로 후보가 실제로 환승 가능한지 평가하거나, 제한된 TAGO 데이터를 이용해 탐색 결과를 보조하는 용도로 사용하세요.

- 현재 버전: v0.1.0-alpha.29
- Python: 3.10 이상
- 라이선스: MIT

## 이런 경우에 사용할 수 있습니다

- 여러 대중교통 경로 중 환승 여유가 더 충분한 경로를 비교하고 싶을 때
- 버스 도착예정정보를 반영해 환승 실패 가능성을 확인하고 싶을 때
- 직접 보유한 정류소·노선·도착 DB에 환승 평가 기능을 추가하고 싶을 때
- TAGO 공공데이터의 정류소, 노선과 도착정보를 테스트하고 싶을 때
- 수업이나 연구에서 대중교통 데이터 처리, API 오류 대응과 자동화 테스트 사례가 필요할 때

## 먼저 선택할 사용 방법

| 사용 목적 | 권장 방법 | API 키 |
|---|---|---|
| 기능을 빠르게 체험 | 웹 데모의 간편 환승 평가 | 필요 없음 |
| 보유한 경로 후보 평가 | POST /api/routes/assess | 필요 없음 |
| Python 코드에서 평가 | evaluate_route, rank_routes | 필요 없음 |
| 보유 CSV·DB 연동 | CSV 어댑터 또는 사용자 어댑터 | 필요 없음 |
| 실제 주변 정류소 탐색 | 웹 데모 실사용 모드 또는 POST /api/routes/plan/tago | TAGO 키 필요 |
| 장소 검색과 지도 표시 | Kakao 지도 연동 | Kakao JavaScript 키 필요 |

처음 사용하는 경우에는 API 키 없이 실행한 뒤 웹 데모의 예제 버튼으로 평가 결과를 확인하는 방법을 권장합니다.

## 빠른 시작

### Windows

1. 저장소를 내려받거나 ZIP 파일을 압축 해제합니다.
2. 프로젝트 폴더에서 setup_windows.bat을 실행합니다.
3. 설치가 완료되면 start_all_windows.bat을 실행합니다.
4. 브라우저에서 http://127.0.0.1:8080을 엽니다.

setup_windows.bat은 가상환경 생성, 패키지 설치, .env 예시 복사와 기본 테스트를 수행합니다.

실행 후 사용할 주소:

| 용도 | 주소 |
|---|---|
| 웹 데모 | http://127.0.0.1:8080 |
| API 문서 | http://127.0.0.1:8000/docs |
| 설정 상태 점검 | http://127.0.0.1:8000/api/setup/check |

### 수동 설치

Linux 또는 macOS:

    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -e ".[dev,api]"
    python -m pytest -q
    python -m uvicorn transitguard.api.app:app --reload

Windows:

    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -e ".[dev,api]"
    .\.venv\Scripts\python.exe -m pytest -q
    .\.venv\Scripts\python.exe -m uvicorn transitguard.api.app:app --reload

PowerShell에서 Activate.ps1이 차단되더라도 가상환경을 활성화할 필요는 없습니다. 위 예제처럼 .venv의 Python을 직접 실행하세요.

## API 키 없이 체험하기

웹 데모의 **간편 환승 평가**에서 안전, 촉박, 실패 예제를 선택할 수 있습니다. 시간이나 노선을 바꾸면 환승 상태와 점수가 어떻게 달라지는지 바로 확인할 수 있습니다.

다음 API를 직접 호출할 수도 있습니다.

    curl -X POST http://127.0.0.1:8000/api/routes/assess/quick \
      --header "Content-Type: application/json" \
      --data @examples/assess_quick_payload.json

이 방식은 외부 서버 상태와 관계없이 TransitGuard의 핵심 평가 흐름을 확인하는 데 적합합니다.

## 평가 결과 읽는 방법

| 상태 | 의미 | 확인할 내용 |
|---|---|---|
| 안전 | 도보 이동과 최소 환승 여유를 고려해 다음 차량에 탑승 가능 | 남은 환승 여유와 전체 이동시간 |
| 촉박 | 현재 정보로는 탑승 가능하지만 여유가 적음 | 지연 시 실패 위험과 대체 차량 |
| 환승 실패 | 제공된 다음 차량 도착정보로는 환승 불가능 | 더 늦은 차량 또는 다른 경로 |
| 정보 부족 | 판단에 필요한 도착정보가 없음 | 누락된 정류소·노선·도착 데이터 |

주요 결과 필드:

- reliability_score: 경로 안정성 점수
- total_minutes: 전체 이동시간
- initial_wait_minutes: 첫 번째 차량 대기시간
- transfer_results: 환승별 상태, 탑승 시각, 대기시간과 판단 이유
- ranking_score: 여러 경로를 비교할 때 사용하는 순위 점수

점수는 입력된 데이터와 평가 규칙을 기준으로 한 상대적 결과입니다. 실제 성공 확률이나 운행을 보장하지 않습니다.

## 기존 경로 후보 평가하기

TransitGuard의 기본 사용 방식은 경로 후보를 입력해 평가하는 것입니다.

    curl -X POST http://127.0.0.1:8000/api/routes/assess \
      --header "Content-Type: application/json" \
      --data @examples/assess_routes_payload.json

예제 요청은 경로 구간, 출발·도착 시각, 환승 정류소, 도보시간, 최소 여유시간과 다음 차량 도착 후보를 포함합니다.

실제 TAGO 도착정보를 기존 후보와 결합하려면 다음 예제를 사용하세요.

    examples/assess_routes_tago_payload.json

경로에서 버스 번호를 사용한다면 route_key를 route_no로 설정하고, TAGO 공식 노선 ID를 사용한다면 route_id로 설정합니다.

전체 요청·응답 모델은 서버 실행 후 Swagger UI에서 확인할 수 있습니다.

    http://127.0.0.1:8000/docs

## Python에서 사용하기

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
    print(result.status)
    print(result.reliability_score)
    print(result.total_minutes)

시간값은 당일 자정부터 지난 분으로 입력합니다.

| 시각 | 분 단위 값 |
|---|---:|
| 08:40 | 520 |
| 09:00 | 540 |
| 09:12 | 552 |

## 보유 대중교통 CSV 사용하기

정류소 CSV:

    id,name,lat,lon,opposite_id
    S1,대구역앞,35.8761,128.5961,S2
    S2,대구역건너,35.8757,128.5965,S1

도착정보 CSV:

    station_id,route_id,arrival_minute
    S3,708,548
    S3,708,552

불러오기:

    from transitguard.adapters.timetable_csv import load_arrivals, load_stations

    stations = load_stations("stations.csv")
    arrivals = load_arrivals("arrivals.csv")

필드 설명:

| 필드 | 설명 |
|---|---|
| id, station_id | 내부 정류소 식별자 |
| name | 화면에 표시할 정류소 이름 |
| lat, lon | 위도와 경도 |
| opposite_id | 길 건너편 또는 대응 정류소 ID. 없으면 빈 값 |
| route_id | 내부 노선 식별자 |
| arrival_minute | 당일 자정부터 계산한 도착예정 분 |

전체 예제는 examples/minimal_stations.csv와 examples/minimal_arrivals.csv에 있습니다.

## 보유 데이터베이스 연결하기

특정 데이터베이스 제품에 맞춘 기본 커넥터는 포함되어 있지 않습니다. 다음 순서로 연결할 수 있습니다.

1. 데이터베이스에서 정류소, 노선과 도착정보를 조회합니다.
2. 정류소를 Station, 도착정보를 Arrival 모델로 변환합니다.
3. 경로 구간을 RouteSegment, 환승 조건을 Transfer로 구성합니다.
4. 전체 경로를 RouteCandidate로 만든 뒤 evaluate_route 또는 rank_routes에 전달합니다.

정류소 ID 체계가 다르면 이름만 비교하지 말고 좌표, 이동 방향, 대응 정류소와 지역코드를 함께 사용하세요. 지속적으로 사용하는 외부 데이터는 src/transitguard/adapters에 별도 어댑터를 추가하는 방식을 권장합니다.

## 실제 TAGO 데이터 사용하기

### 환경변수 설정

.env.example을 .env로 복사한 뒤 발급받은 키를 입력합니다.

    TAGO_SERVICE_KEY=

선택 설정:

    TAGO_CITY_CODE=
    TAGO_NODE_ID=
    TAGO_ORIGIN_NODE_ID=
    TAGO_DESTINATION_NODE_ID=
    TAGO_ROUTE_IDS=
    TRANSITGUARD_CORS_ORIGINS=*
    KAKAO_MAP_JAVASCRIPT_KEY=

실제 키는 Git에 커밋하지 마세요. 키를 입력한 뒤 API 서버를 다시 시작하고 다음 주소에서 설정 상태를 확인하세요.

    http://127.0.0.1:8000/api/setup/check

### 좌표로 경로 후보 찾기

웹 데모에서 출발·도착 장소를 검색하거나 좌표를 입력한 뒤 **실제 TAGO 데이터로 후보 찾기**를 실행합니다.

API를 직접 호출할 수도 있습니다.

    curl -X POST http://127.0.0.1:8000/api/routes/plan/tago \
      --header "Content-Type: application/json" \
      --data @examples/plan_tago_coordinates_payload.json

이 기능은 다음 과정을 제한적으로 수행합니다.

1. 좌표 주변의 정류소 조회
2. 정류소 경유 노선 조회
3. 노선별 정류소 순서 확인
4. 직행 또는 환승 후보 구성
5. 도착정보 결합 및 안정성 평가

시간 초과를 방지하기 위해 확인하는 정류소, 노선, 조합과 API 호출 수가 제한됩니다. 실제 존재하는 모든 경로가 반환된다고 가정하지 마세요.

### 후보가 없을 때

후보 0건은 항상 프로그램 오류를 의미하지 않습니다. 웹 화면이나 diagnostics에서 다음 항목을 확인하세요.

- 적용된 지역과 도시코드
- 확인한 출발·도착 정류소
- 출발 정류소에서 확인된 노선
- 실시간 도착정보 존재 여부
- 가능한 원인과 다음 검색 제안

TAGO 요청 시간 초과가 반복되면 잠시 뒤 다시 시도하거나 정류소·조합 수를 줄이고, 느린 실시간 후보 탐색 옵션은 필요한 경우에만 사용하세요.

## Kakao 지도 사용하기

Kakao 지도는 장소 검색과 결과 시각화를 위한 선택 기능입니다. TransitGuard 핵심 평가와 API 키 없는 예제에는 필요하지 않습니다.

1. Kakao Developers에서 애플리케이션을 만듭니다.
2. JavaScript 키를 확인합니다.
3. 웹 플랫폼 도메인에 http://127.0.0.1:8080을 등록합니다.
4. .env에 KAKAO_MAP_JAVASCRIPT_KEY를 입력합니다.
5. API 서버를 다시 시작합니다.

Kakao 지도는 장소와 좌표를 찾고 마커·경로선을 표시합니다. 대중교통 노선과 도착정보는 TAGO 또는 사용자가 제공한 데이터에서 가져옵니다.

## 대구·경산에서 사용할 때

현재 실사용 탐색에는 다음 지역 정책이 적용됩니다.

| 이동 구간 | TAGO 도시코드 | 정류소 ID |
|---|---:|---|
| 경산 내부 | 37100 | GYB |
| 대구가 포함된 구간 | 22 | DGB |

이 규칙은 대구·경산의 중복 정류소와 지역별 API 차이를 처리하기 위한 정책입니다. 다른 지역에서 사용하려면 해당 지역의 도시코드, 정류소 ID 체계와 API 응답을 검증해야 합니다.

## 현재 지원하지 않거나 제한적인 기능

- 전국의 모든 대중교통 경로 완전 탐색
- 공식 시간표를 이용한 모든 구간의 정확한 하차 시각
- 모든 지역의 도시코드와 정류소 ID 자동 판별
- 버스와 지하철의 완전한 공식 시간표 결합
- 교통상황, 운행 취소, 임시 우회와 현장 보행 조건의 완전한 반영

노선 구조로 계산한 이동·하차시간과 지하철 일부 시간은 추정값입니다. 실제 이동 전에는 지역 교통기관이나 지도 서비스의 최신 운행정보도 확인하세요.

## 문제 해결

### API 서버가 시작되지 않음

- Python 3.10 이상인지 확인합니다.
- setup_windows.bat을 다시 실행합니다.
- 8000 포트를 사용 중인 다른 프로그램이 있는지 확인합니다.

### 웹 데모가 열리지 않음

- start_web_demo.bat 창이 실행 중인지 확인합니다.
- 8080 포트를 사용 중인 다른 프로그램이 있는지 확인합니다.

### TAGO request timed out

- 공공데이터 서버가 느릴 수 있으므로 잠시 뒤 다시 시도합니다.
- 탐색할 주변 정류소와 정류소 조합 수를 줄입니다.
- /api/tago/diagnostics에서 설정 상태를 확인합니다.

### 경산 경로가 검색되지 않음

- 출발지와 도착지가 경산으로 판별되었는지 확인합니다.
- 진단에 cityCode 37100과 GYB 정책이 표시되는지 확인합니다.
- 출발 정류소에서 확인된 경유 노선을 확인합니다.

더 자세한 Windows 문제 해결은 docs/WINDOWS.md를 참고하세요.

## 주요 API

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | /api/setup/check | 설정 상태 확인 |
| POST | /api/routes/assess/quick | 간편 환승 평가 |
| POST | /api/routes/assess | 기존 경로 후보 평가 |
| POST | /api/routes/rank | 오프라인 경로 순위화 |
| POST | /api/routes/plan/tago | 좌표 기반 제한적 TAGO 탐색 |
| GET | /api/tago/diagnostics | TAGO 설정 진단 |
| GET | /api/tago/arrivals | 정류소 도착정보 조회 |
| GET | /api/tago/stations/nearby | 주변 정류소 조회 |
| GET | /api/tago/route-stops | 노선별 정류소 조회 |

자세한 설명은 docs/API.md를 참고하세요.

## 프로젝트 구조

    transitguard/
    ├─ src/transitguard/
    │  ├─ core/                 평가, 순위화와 정류소 매칭
    │  ├─ adapters/             TAGO 및 CSV 데이터 변환
    │  └─ api/                  FastAPI 서버
    ├─ web-demo/                브라우저 데모
    ├─ examples/                API 요청과 CSV 예제
    ├─ tests/                   자동화 테스트
    └─ docs/                    사용 및 개발 문서

## 테스트

기본 테스트:

    .\.venv\Scripts\python.exe -m pytest -q

정적 검사:

    .\.venv\Scripts\python.exe -m ruff check .

실제 TAGO API를 사용하는 선택적 테스트:

    .\.venv\Scripts\python.exe -m pytest -m live_tago -q

실데이터 테스트는 서비스 키, 실행 시각과 외부 API 상태에 영향을 받습니다.

## 보안

- 실제 .env, API 키, 토큰과 비공개 데이터를 커밋하지 마세요.
- 시연영상과 오류 화면에 키가 표시되지 않도록 확인하세요.
- 배포 시 TRANSITGUARD_CORS_ORIGINS에 허용할 출처만 지정하세요.
- 노출된 키는 발급기관에서 폐기하고 새로 발급받으세요.

자세한 내용은 SECURITY.md를 참고하세요.

## 문서

- API 안내: docs/API.md
- Windows 안내: docs/WINDOWS.md
- 아키텍처: docs/ARCHITECTURE.md
- 변경 이력: CHANGELOG.md
- 기여 방법: CONTRIBUTING.md
- 보안 정책: SECURITY.md

## 라이선스

TransitGuard는 MIT License로 배포됩니다. 자세한 내용은 LICENSE를 확인하세요.

