from transitguard.core.models import (
    RouteCandidate,
    RouteEvaluation,
    Transfer,
    TransferEvaluation,
    TransferStatus,
)


def evaluate_transfer(transfer: Transfer, tight_threshold_minutes: int = 3) -> TransferEvaluation:
    if tight_threshold_minutes < 0:
        raise ValueError("tight_threshold_minutes must be non-negative")

    required_minute = (
        transfer.arrival_minute + transfer.walking_minutes + transfer.minimum_buffer_minutes
    )
    relevant_arrivals = tuple(
        arrival
        for arrival in transfer.candidate_arrivals
        if arrival.station_id == transfer.to_station_id
        and (transfer.target_route_id is None or arrival.route_id == transfer.target_route_id)
    )

    if not relevant_arrivals:
        reason = (
            "no_arrival_data_for_target_route"
            if transfer.target_route_id
            else "no_arrival_data_for_target_station"
        )
        return TransferEvaluation(
            status=TransferStatus.UNKNOWN,
            board_minute=None,
            required_minute=required_minute,
            wait_minutes=None,
            risk_score=0.5,
            reason=reason,
        )

    boardable_arrivals = sorted(
        (arrival for arrival in relevant_arrivals if arrival.arrival_minute >= required_minute),
        key=lambda arrival: arrival.arrival_minute,
    )

    if not boardable_arrivals:
        return TransferEvaluation(
            status=TransferStatus.MISSED,
            board_minute=None,
            required_minute=required_minute,
            wait_minutes=None,
            risk_score=1.0,
            reason="no_boardable_vehicle",
        )

    selected = boardable_arrivals[0]
    wait_minutes = selected.arrival_minute - required_minute
    status = (
        TransferStatus.SAFE
        if wait_minutes >= tight_threshold_minutes
        else TransferStatus.TIGHT
    )
    risk_score = _risk_from_wait(wait_minutes, tight_threshold_minutes)

    return TransferEvaluation(
        status=status,
        board_minute=selected.arrival_minute,
        required_minute=required_minute,
        wait_minutes=wait_minutes,
        risk_score=risk_score,
        reason="boardable_vehicle_found",
    )


def evaluate_route(route: RouteCandidate) -> RouteEvaluation:
    transfer_results = tuple(evaluate_transfer(transfer) for transfer in route.transfers)
    start_minute = route.requested_start_minute
    if start_minute is None:
        start_minute = route.segments[0].departure_minute
    initial_wait_minutes = route.segments[0].departure_minute - start_minute
    total_minutes = route.segments[-1].arrival_minute - start_minute
    status = _route_status(transfer_results)
    reliability_score = _route_reliability(transfer_results)

    ranking_score = _route_ranking_score(
        status,
        reliability_score,
        total_minutes,
        transfer_count=len(route.transfers),
    )

    return RouteEvaluation(
        route_id=route.id,
        status=status,
        reliability_score=reliability_score,
        total_minutes=total_minutes,
        transfer_results=transfer_results,
        initial_wait_minutes=initial_wait_minutes,
        ranking_score=ranking_score,
    )


def _risk_from_wait(wait_minutes: int, tight_threshold_minutes: int) -> float:
    if wait_minutes >= tight_threshold_minutes or tight_threshold_minutes == 0:
        return 0.0
    return round((tight_threshold_minutes - wait_minutes) / tight_threshold_minutes, 3)


def _route_status(transfer_results: tuple[TransferEvaluation, ...]) -> TransferStatus:
    if any(result.status == TransferStatus.MISSED for result in transfer_results):
        return TransferStatus.MISSED
    if any(result.status == TransferStatus.UNKNOWN for result in transfer_results):
        return TransferStatus.UNKNOWN
    if any(result.status == TransferStatus.TIGHT for result in transfer_results):
        return TransferStatus.TIGHT
    return TransferStatus.SAFE


def _route_reliability(transfer_results: tuple[TransferEvaluation, ...]) -> float:
    if not transfer_results:
        return 1.0
    average_risk = sum(result.risk_score for result in transfer_results) / len(transfer_results)
    return round(max(0.0, min(1.0, 1 - average_risk)), 3)


def _route_ranking_score(
    status: TransferStatus,
    reliability_score: float,
    total_minutes: int,
    transfer_count: int = 0,
) -> float:
    status_penalty = {
        TransferStatus.SAFE: 0.0,
        TransferStatus.TIGHT: 8.0,
        TransferStatus.UNKNOWN: 20.0,
        TransferStatus.MISSED: 10_000.0,
    }[status]
    reliability_penalty = (1.0 - reliability_score) * 10.0
    return round(
        total_minutes
        + transfer_count * 10.0
        + status_penalty
        + reliability_penalty,
        3,
    )
