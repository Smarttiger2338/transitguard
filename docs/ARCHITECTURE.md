# TransitGuard 아키텍처

TransitGuard는 완성형 길찾기 서비스가 아니라 작은 **환승 안정성 평가 엔진**을 중심으로 구성됩니다.

    기존 경로 후보
          ↓
    핵심 평가 로직
          ↓
    safe / tight / missed / unknown
          ↓
    안정성 점수 및 경로 순위

## 핵심 엔진

src/transitguard/core에는 외부 서비스에 의존하지 않는 Python 로직이 있습니다.

- models.py: 정류소, 도착정보, 경로 구간, 환승과 평가 결과 모델
- evaluator.py: 환승 준비 시각, 탑승 가능 차량, 위험도와 안정성 계산
- ranking.py: 전체 이동시간, 대기시간과 환승 위험을 반영한 후보 순위화
- station_matcher.py: 정류소 좌표와 대응 정류소를 이용한 후보 매칭
- demo_graph.py: 예제 및 실험용 경로 그래프 구성

핵심 계층은 TAGO 데이터를 직접 조회하지 않고, Kakao 지도를 불러오지 않으며 FastAPI에도 의존하지 않습니다. 따라서 직접 만든 데이터와 오프라인 테스트에서도 사용할 수 있습니다.

## 데이터 어댑터

src/transitguard/adapters는 외부 데이터를 핵심 모델로 변환합니다.

- tago.py: 환경설정 로드, TAGO 정류소·도착·노선·노선별 정류소 조회와 응답 변환
- timetable_csv.py: 로컬 정류소 및 도착정보 CSV 로더

어댑터는 데이터를 제공하는 계층이며 프로젝트의 중심 경로 탐색 엔진은 아닙니다. 다른 데이터베이스를 연결할 때도 이 계층에서 Station과 Arrival 같은 공통 모델로 변환하는 방식을 권장합니다.

## API 계층

src/transitguard/api/app.py는 FastAPI를 통해 평가 기능을 제공합니다.

핵심 API:

    POST /api/routes/assess

기존 경로 후보와 선택적인 TAGO 도착정보 출처를 받아 평가합니다.

간편 및 실사용 API:

    POST /api/routes/assess/quick
    POST /api/routes/plan/tago
    POST /api/routes/rank

/api/routes/plan/tago는 좌표를 주변 TAGO 정류소로 변환하고 제한된 후보 탐색을 실행하는 실사용 래퍼입니다. 외부 API 호출 수를 제어하기 위해 정류소, 노선, 후보와 호출 예산을 제한합니다.

보조 API:

    GET /api/setup/check
    GET /api/kakao/config
    GET /api/tago/diagnostics
    GET /api/tago/arrivals
    GET /api/tago/stations/nearby
    GET /api/tago/route-stops

/api/kakao/config는 정적 웹 데모가 설정된 Kakao JavaScript 키를 읽도록 돕습니다. TAGO 서비스 키는 브라우저에 반환하지 않습니다.

## 웹 데모

web-demo는 다음 기능을 제공하는 정적 브라우저 UI입니다.

- 간편 환승 평가와 예제 프리셋
- 기존 경로 JSON 평가
- 출발·도착 좌표를 사용하는 실제 TAGO 모드
- 후보가 없을 때의 정류소·노선·원인 진단
- Kakao 장소 검색, 마커와 경로선 표시

Kakao 지도는 시각화 및 좌표 선택 계층입니다. TransitGuard 평가 엔진을 대체하지 않으며 자동으로 전국 대중교통 경로를 생성하지 않습니다.

## 실사용 데이터 흐름

    장소 검색 또는 좌표 입력
            ↓
    출발·도착 지역 정책 결정
            ↓
    주변 정류소 조회
            ↓
    정류소별 노선 및 노선별 정류소 조회
            ↓
    직행·환승 후보 구성
            ↓
    도착정보와 시간 출처 결합
            ↓
    환승 평가 및 경로 순위화
            ↓
    경로 카드 또는 실패 진단 반환

## 설계 원칙

1. 실제 도착정보와 추정시간을 구분합니다.
2. 하나의 외부 API 실패가 전체 탐색을 중단하지 않도록 격리합니다.
3. 외부 API 호출은 캐시와 요청 예산으로 제한합니다.
4. 후보 0건을 프로그램 오류가 아니라 설명 가능한 결과 상태로 처리합니다.
5. 핵심 평가 엔진은 외부 서비스 없이도 테스트할 수 있도록 유지합니다.

