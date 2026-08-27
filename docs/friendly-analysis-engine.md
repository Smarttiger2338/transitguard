# 쉬운 분석 엔진 사용법

TransitGuard의 기본 모델은 `RouteCandidate`, `RouteSegment`, `Transfer`, `Arrival`로 구성됩니다. 이 구조는 개발자에게는 명확하지만, 처음 사용하는 사람에게는 입력이 어렵게 느껴질 수 있습니다.

그래서 `transitguard.easy` 모듈은 사람이 이해하기 쉬운 형태의 환승 정보를 받아 내부 모델로 변환하고, 한국어 설명을 함께 반환합니다.

## 가장 쉬운 예제

```python
from transitguard.easy import assess_simple_transfer

assessment = assess_simple_transfer(
    requested_start="08:35",
    origin_station="대구역앞",
    transfer_station="중앙로역",
    destination_station="동대구역건너",
    first_route="101",
    second_route="708",
    first_departure="08:40",
    transfer_arrival="08:55",
    second_departure="09:06",
    final_arrival="09:22",
    next_vehicle_arrivals=["09:06", "09:12"],
    walking_minutes=4,
    minimum_buffer_minutes=3,
)

print(assessment.summary)
print(assessment.suggestions)
print(assessment.to_dict())
```

예상 출력은 다음과 같은 형태입니다.

```text
안전: 최소 환승 가능 시각은 09:02이고 다음 차량은 09:06에 도착합니다. 환승 여유는 4분이며 전체 예상 시간은 47분입니다.
```

## 입력값 의미

| 입력값 | 의미 |
|---|---|
| requested_start | 사용자가 이동을 시작하려는 시각 |
| origin_station | 첫 번째 탑승 정류소 이름 또는 ID |
| transfer_station | 환승 정류소 이름 또는 ID |
| destination_station | 최종 도착 정류소 이름 또는 ID |
| first_route | 첫 번째 노선 번호 또는 ID |
| second_route | 환승 후 탈 노선 번호 또는 ID |
| first_departure | 첫 번째 차량 출발 시각 |
| transfer_arrival | 첫 번째 차량이 환승 정류소에 도착하는 시각 |
| second_departure | 두 번째 차량 출발 시각 |
| final_arrival | 최종 도착 시각 |
| next_vehicle_arrivals | 환승 정류소에서 확인된 두 번째 노선 도착 후보들 |
| walking_minutes | 환승 이동에 걸리는 도보 시간 |
| minimum_buffer_minutes | 최소 환승 여유 시간 |

시간은 `08:40` 같은 `HH:MM` 문자열이나 정수 분 단위로 입력할 수 있습니다. `24:10`처럼 자정을 넘긴 시각도 사용할 수 있습니다.

## 결과 읽기

`assessment.summary`는 사람이 바로 읽을 수 있는 한국어 요약입니다.

`assessment.suggestions`는 다음에 확인하면 좋은 사항입니다.

`assessment.to_dict()`는 웹 API나 외부 프로그램에 넘기기 쉬운 딕셔너리 형태입니다.

상태는 다음 네 가지입니다.

| 상태 | 의미 |
|---|---|
| 안전 | 환승 가능성이 높음 |
| 촉박 | 가능은 하지만 여유가 적음 |
| 환승 실패 | 제공된 도착정보 기준으로 환승 불가 |
| 정보 부족 | 판단에 필요한 도착정보가 부족함 |

## 기존 코어 모델과의 관계

`assess_simple_transfer()`는 내부적으로 다음 순서로 동작합니다.

1. 사람이 입력한 시각과 노선 정보를 분 단위 값으로 변환합니다.
2. `RouteSegment`, `Transfer`, `Arrival` 객체를 만듭니다.
3. `RouteCandidate`를 생성합니다.
4. 기존 `evaluate_route()` 로직으로 평가합니다.
5. 결과를 한국어 요약과 제안으로 감싸서 반환합니다.

따라서 기존 엔진을 대체하는 기능이 아니라, 기존 엔진을 더 쉽게 쓰기 위한 얇은 사용성 레이어입니다.

## 언제 이 방식을 쓰면 좋은가

- 수업 발표나 시연에서 JSON을 직접 보여주기 부담스러울 때
- 경로 후보 1개를 빠르게 평가하고 싶을 때
- 사용자가 노선번호와 시각만 알고 있을 때
- 외부 데이터셋을 TransitGuard 내부 모델로 바꾸기 전, 흐름을 먼저 검증하고 싶을 때

복잡한 다중 환승, 여러 경로 비교, TAGO 실시간 데이터 결합은 기존 API와 코어 모델을 사용하는 편이 더 적합합니다.
