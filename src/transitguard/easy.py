from __future__ import annotations

from dataclasses import dataclass

from transitguard.core.evaluator import evaluate_route
from transitguard.core.models import Arrival, RouteCandidate, RouteEvaluation, RouteSegment, Transfer, TransferStatus


@dataclass(frozen=True)
class FriendlyAssessment:
    """Human-readable wrapper around a TransitGuard route evaluation."""

    route: RouteCandidate
    evaluation: RouteEvaluation
    summary: str
    suggestions: tuple[str, ...]
    details: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "route_id": self.evaluation.route_id,
            "status": self.evaluation.status.value,
            "status_label": status_label_ko(self.evaluation.status),
            "summary": self.summary,
            "suggestions": list(self.suggestions),
            "reliability_score": self.evaluation.reliability_score,
            "ranking_score": self.evaluation.ranking_score,
            "total_minutes": self.evaluation.total_minutes,
            "initial_wait_minutes": self.evaluation.initial_wait_minutes,
            "details": self.details,
        }


def minute_from_hhmm(value: str | int) -> int:
    """Convert an integer minute or a HH:MM string into minutes after midnight.

    ``24:10`` is accepted and means the next day at 00:10. This keeps examples
    simple when a route crosses midnight while still using the core minute model.
    """

    if isinstance(value, int):
        if value < 0:
            raise ValueError("minute value must be non-negative")
        return value

    raw = value.strip()
    if not raw:
        raise ValueError("time value must not be empty")
    if ":" not in raw:
        raise ValueError("time value must use HH:MM format")

    hour_text, minute_text = raw.split(":", 1)
    if not hour_text.isdigit() or not minute_text.isdigit():
        raise ValueError("time value must use numeric HH:MM format")

    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or not 0 <= minute <= 59:
        raise ValueError("time value must use a valid minute between 00 and 59")
    return hour * 60 + minute


def hhmm_from_minute(value: int) -> str:
    if value < 0:
        raise ValueError("minute value must be non-negative")
    day_offset, minute_of_day = divmod(value, 24 * 60)
    hour, minute = divmod(minute_of_day, 60)
    suffix = f"(+{day_offset}일)" if day_offset else ""
    return f"{hour:02d}:{minute:02d}{suffix}"


def build_simple_transfer_route(
    *,
    id: str = "simple-transfer",
    requested_start: str | int,
    origin_station: str,
    transfer_station: str,
    destination_station: str,
    first_route: str,
    second_route: str,
    first_departure: str | int,
    transfer_arrival: str | int,
    second_departure: str | int,
    final_arrival: str | int,
    next_vehicle_arrivals: tuple[str | int, ...] | list[str | int] | None = None,
    walking_minutes: int = 4,
    minimum_buffer_minutes: int = 3,
) -> RouteCandidate:
    """Build a RouteCandidate from common, human-friendly transfer fields.

    This is intended for users who know the visible route plan but do not want to
    manually assemble ``RouteSegment``, ``Transfer`` and ``Arrival`` objects.
    """

    requested_start_minute = minute_from_hhmm(requested_start)
    first_departure_minute = minute_from_hhmm(first_departure)
    transfer_arrival_minute = minute_from_hhmm(transfer_arrival)
    second_departure_minute = minute_from_hhmm(second_departure)
    final_arrival_minute = minute_from_hhmm(final_arrival)

    if walking_minutes < 0:
        raise ValueError("walking_minutes must be non-negative")
    if minimum_buffer_minutes < 0:
        raise ValueError("minimum_buffer_minutes must be non-negative")

    candidate_times = next_vehicle_arrivals or (second_departure,)
    candidate_arrivals = tuple(
        Arrival(transfer_station, second_route, minute_from_hhmm(arrival_time))
        for arrival_time in candidate_times
    )

    return RouteCandidate(
        id=id,
        requested_start_minute=requested_start_minute,
        segments=(
            RouteSegment(
                route_id=first_route,
                from_station_id=origin_station,
                to_station_id=transfer_station,
                departure_minute=first_departure_minute,
                arrival_minute=transfer_arrival_minute,
            ),
            RouteSegment(
                route_id=second_route,
                from_station_id=transfer_station,
                to_station_id=destination_station,
                departure_minute=second_departure_minute,
                arrival_minute=final_arrival_minute,
            ),
        ),
        transfers=(
            Transfer(
                from_station_id=transfer_station,
                to_station_id=transfer_station,
                arrival_minute=transfer_arrival_minute,
                walking_minutes=walking_minutes,
                minimum_buffer_minutes=minimum_buffer_minutes,
                candidate_arrivals=candidate_arrivals,
                target_route_id=second_route,
            ),
        ),
    )


def assess_simple_transfer(**kwargs: object) -> FriendlyAssessment:
    """Evaluate a simple two-leg transfer and return Korean explanations."""

    route = build_simple_transfer_route(**kwargs)  # type: ignore[arg-type]
    evaluation = evaluate_route(route)
    return explain_route(route, evaluation)


def explain_route(route: RouteCandidate, evaluation: RouteEvaluation) -> FriendlyAssessment:
    transfer_result = evaluation.transfer_results[0] if evaluation.transfer_results else None
    summary = _summary_for(route, evaluation)
    suggestions = _suggestions_for(evaluation)

    details: dict[str, object] = {
        "requested_start": hhmm_from_minute(route.requested_start_minute or route.segments[0].departure_minute),
        "first_departure": hhmm_from_minute(route.segments[0].departure_minute),
        "first_arrival_at_transfer": hhmm_from_minute(route.segments[0].arrival_minute),
        "second_departure": hhmm_from_minute(route.segments[1].departure_minute)
        if len(route.segments) > 1
        else None,
        "final_arrival": hhmm_from_minute(route.segments[-1].arrival_minute),
        "total_minutes": evaluation.total_minutes,
        "initial_wait_minutes": evaluation.initial_wait_minutes,
    }
    if transfer_result is not None:
        details.update(
            {
                "required_transfer_ready_time": hhmm_from_minute(transfer_result.required_minute),
                "board_time": hhmm_from_minute(transfer_result.board_minute)
                if transfer_result.board_minute is not None
                else None,
                "transfer_wait_minutes": transfer_result.wait_minutes,
                "reason": transfer_result.reason,
            }
        )

    return FriendlyAssessment(
        route=route,
        evaluation=evaluation,
        summary=summary,
        suggestions=suggestions,
        details=details,
    )


def status_label_ko(status: TransferStatus) -> str:
    return {
        TransferStatus.SAFE: "안전",
        TransferStatus.TIGHT: "촉박",
        TransferStatus.MISSED: "환승 실패",
        TransferStatus.UNKNOWN: "정보 부족",
    }[status]


def _summary_for(route: RouteCandidate, evaluation: RouteEvaluation) -> str:
    transfer_result = evaluation.transfer_results[0] if evaluation.transfer_results else None
    label = status_label_ko(evaluation.status)
    total = evaluation.total_minutes

    if transfer_result is None:
        return f"{label}: 환승이 없는 경로입니다. 전체 예상 시간은 {total}분입니다."

    required = hhmm_from_minute(transfer_result.required_minute)
    if evaluation.status == TransferStatus.SAFE:
        board = hhmm_from_minute(transfer_result.board_minute or transfer_result.required_minute)
        return (
            f"{label}: 최소 환승 가능 시각은 {required}이고 다음 차량은 {board}에 도착합니다. "
            f"환승 여유는 {transfer_result.wait_minutes}분이며 전체 예상 시간은 {total}분입니다."
        )
    if evaluation.status == TransferStatus.TIGHT:
        board = hhmm_from_minute(transfer_result.board_minute or transfer_result.required_minute)
        return (
            f"{label}: 환승은 가능하지만 여유가 {transfer_result.wait_minutes}분뿐입니다. "
            f"최소 환승 가능 시각은 {required}, 다음 차량 도착은 {board}입니다."
        )
    if evaluation.status == TransferStatus.MISSED:
        return (
            f"{label}: 도보 이동과 최소 여유시간을 고려하면 {required} 이후 차량이 필요하지만, "
            "제공된 도착정보에서는 탈 수 있는 차량이 없습니다."
        )
    return (
        f"{label}: 환승 판단에 필요한 다음 차량 도착정보가 부족합니다. "
        f"최소 환승 가능 시각은 {required}입니다."
    )


def _suggestions_for(evaluation: RouteEvaluation) -> tuple[str, ...]:
    if evaluation.status == TransferStatus.SAFE:
        return (
            "현재 입력값 기준으로는 환승 가능성이 높습니다.",
            "실제 서비스에서는 지연 가능성을 고려해 대체 차량도 함께 확인하세요.",
        )
    if evaluation.status == TransferStatus.TIGHT:
        return (
            "도보 이동시간이나 최소 환승 여유시간을 조금 더 보수적으로 잡아보세요.",
            "다음 차량 도착 후보를 1개가 아니라 여러 개 입력하면 판단이 더 안정적입니다.",
        )
    if evaluation.status == TransferStatus.MISSED:
        return (
            "더 늦은 두 번째 차량 도착시각을 추가해 다시 평가해보세요.",
            "환승 정류장을 바꾸거나 도보 환승 반경을 넓히는 대안을 확인하세요.",
        )
    return (
        "두 번째 노선의 도착예정정보가 입력되었는지 확인하세요.",
        "route_id나 정류소 ID가 실제 도착정보의 값과 같은지 확인하세요.",
    )
