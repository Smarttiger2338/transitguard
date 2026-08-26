# TransitGuard API 안내

TransitGuard의 핵심 API는 **기존 경로 후보의 환승 안정성 평가**에 초점을 맞춥니다. Kakao 지도는 선택적인 브라우저 시각화 기능입니다.

서버 실행 후 Swagger UI에서 전체 요청·응답 모델을 확인할 수 있습니다.

    http://127.0.0.1:8000/docs

## GET /api/setup/check

TransitGuard 버전, 시간대 처리, TAGO 서비스 키와 Kakao 지도 키 설정 상태를 확인합니다. 실제 비밀 키 값은 반환하지 않습니다.

## GET /api/kakao/config

브라우저 데모가 사용할 공개 Kakao 지도 JavaScript 설정을 반환합니다. Kakao JavaScript 키는 Kakao Developers에서 허용 웹 도메인을 제한해야 합니다.

## POST /api/routes/assess/quick

한 번의 환승을 간단한 폼 형태로 평가합니다.

    curl -X POST http://127.0.0.1:8000/api/routes/assess/quick \
      --header "Content-Type: application/json" \
      --data @examples/assess_quick_payload.json

응답에는 한국어 상태, 요약, 추천, 신뢰도, 위험 경고와 점수 내역이 포함됩니다. 첫 시연이나 간단한 테스트에 적합합니다.

## POST /api/routes/assess

기존 경로 후보를 평가하는 핵심 API입니다.

    curl -X POST http://127.0.0.1:8000/api/routes/assess \
      --header "Content-Type: application/json" \
      --data @examples/assess_routes_payload.json

요청에 tago_arrival_sources를 추가하면 실제 TAGO 정류소 도착정보를 내부 환승 정류소와 연결할 수 있습니다.

    {
      "station_id": "B",
      "city_code": "22",
      "node_id": "TAGO_정류소_ID",
      "route_key": "route_no"
    }

route_key가 route_no이면 버스 번호를 비교하고, route_id이면 TAGO 공식 노선 ID를 비교합니다.

## POST /api/routes/rank

요청 본문에 포함된 데이터만 사용해 여러 경로 후보를 평가하고 순위를 정합니다. 외부 API가 필요 없는 단위 테스트와 오프라인 시연에 적합합니다.

## POST /api/routes/plan/tago

출발·도착 좌표를 받아 주변 TAGO 정류소를 조회하고 제한된 경로 후보를 구성한 뒤 안정성을 평가합니다.

    curl -X POST http://127.0.0.1:8000/api/routes/plan/tago \
      --header "Content-Type: application/json" \
      --data @examples/plan_tago_coordinates_payload.json

이 API는 브라우저 데모의 실사용 모드를 위해 제공됩니다. 정류소와 노선 ID를 미리 알지 못해도 첫 탐색을 시작할 수 있지만, 호출 수와 탐색 범위가 제한되므로 모든 경로를 보장하지 않습니다.

기본 탐색은 노선 구조를 먼저 사용합니다. 느린 실시간 도착정보 기반 후보 탐색이 필요할 때만 use_live_arrival_discovery를 true로 설정합니다.

후보가 없으면 HTTP 200과 빈 routes 목록, diagnostics를 반환할 수 있습니다. diagnostics에는 확인한 정류소, 출발 도착정보와 노선, 가능한 원인과 한국어 제안이 포함됩니다.

## TAGO 보조 API

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | /api/tago/diagnostics | TAGO 환경설정과 연결 상태 확인 |
| GET | /api/tago/arrivals | 정류소 도착예정정보 조회 |
| GET | /api/tago/stations/nearby | 좌표 주변 정류소 조회 |
| GET | /api/tago/route-stops | 노선별 정류소 순서 조회 |

이 API들은 실제 공공데이터 입력을 얻기 위한 보조 기능이며 TransitGuard를 완성형 지도 서비스로 만들지는 않습니다.

## 지하철 후보

origin_name과 destination_name이 제공되면 공식 TAGO SubwayInfo 역명 검색을 사용할 수 있습니다. 두 역이 같은 노선에 있으면 직접 지하철 후보를 만들 수 있으며, 대구에서는 반월당 또는 청라언덕을 이용한 제한적인 1회 환승 후보를 지원합니다.

현재 지하철 출발·이동시간과 첫 구간·마지막 구간 접근시간은 추정값입니다. 버스와 지하철의 공식 시간표를 완전히 결합한 기능은 아직 제공하지 않습니다.

## Kakao 지도와 웹 데모

웹 데모는 /api/kakao/config를 호출한 뒤 Kakao Places 검색과 지도 오버레이를 사용합니다. Kakao 지도는 다음 용도로만 사용됩니다.

- 장소 검색
- 좌표 입력과 편집
- 지도 마커와 경로선 표시
- 선택 좌표 주변의 TAGO 정류소 검색 시작

Python 핵심 엔진은 Kakao 지도에 의존하지 않습니다.

## 실험적 후보 생성 API

다음 API는 실험을 위해 유지하지만 프로젝트의 핵심 범위는 아닙니다.

    POST /api/route-candidates/generate-graph
    POST /api/route-candidates/generate-tago
    POST /api/route-candidates/discover-tago

## 결과 해석

- safe: 환승 가능 여유가 충분함
- tight: 환승 가능하지만 여유가 적음
- missed: 제공된 도착정보로는 환승에 실패함
- unknown: 판단할 도착정보가 부족함

실제 도착정보와 노선 구조 기반 추정시간을 구분해야 하며 안정성 점수는 실제 성공 확률을 보장하지 않습니다.

