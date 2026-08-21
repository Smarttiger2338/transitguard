from transitguard.core.evaluator import evaluate_route, evaluate_transfer
from transitguard.core.models import Arrival, RouteCandidate, RouteSegment, Transfer, TransferStatus


def test_safe_transfer_when_vehicle_arrives_after_required_time_with_margin():
    transfer = Transfer(
        from_station_id="A",
        to_station_id="B",
        arrival_minute=100,
        walking_minutes=5,
        minimum_buffer_minutes=3,
        candidate_arrivals=(Arrival("B", "R2", 112),),
    )

    result = evaluate_transfer(transfer)

    assert result.status == TransferStatus.SAFE
    assert result.required_minute == 108
    assert result.board_minute == 112
    assert result.wait_minutes == 4


def test_tight_transfer_when_margin_is_small():
    transfer = Transfer(
        from_station_id="A",
        to_station_id="B",
        arrival_minute=100,
        walking_minutes=5,
        minimum_buffer_minutes=3,
        candidate_arrivals=(Arrival("B", "R2", 109),),
    )

    result = evaluate_transfer(transfer)

    assert result.status == TransferStatus.TIGHT
    assert result.wait_minutes == 1


def test_missed_transfer_when_no_vehicle_can_be_boarded():
    transfer = Transfer(
        from_station_id="A",
        to_station_id="B",
        arrival_minute=100,
        walking_minutes=5,
        minimum_buffer_minutes=3,
        candidate_arrivals=(Arrival("B", "R2", 107),),
    )

    result = evaluate_transfer(transfer)

    assert result.status == TransferStatus.MISSED
    assert result.board_minute is None


def test_unknown_transfer_without_arrival_data():
    transfer = Transfer(
        from_station_id="A",
        to_station_id="B",
        arrival_minute=100,
        walking_minutes=5,
        minimum_buffer_minutes=3,
        candidate_arrivals=(),
    )

    result = evaluate_transfer(transfer)

    assert result.status == TransferStatus.UNKNOWN


def test_route_evaluation_uses_transfer_status():
    route = RouteCandidate(
        id="route-1",
        segments=(
            RouteSegment("R1", "A", "B", 90, 100),
            RouteSegment("R2", "B", "C", 112, 130),
        ),
        transfers=(
            Transfer(
                from_station_id="B",
                to_station_id="B",
                arrival_minute=100,
                walking_minutes=5,
                minimum_buffer_minutes=3,
                candidate_arrivals=(Arrival("B", "R2", 112),),
            ),
        ),
    )

    result = evaluate_route(route)

    assert result.status == TransferStatus.SAFE
    assert result.total_minutes == 40
    assert result.ranking_score == 50.0


def test_transfer_ignores_arrivals_for_different_station():
    transfer = Transfer(
        from_station_id="A",
        to_station_id="B",
        arrival_minute=100,
        walking_minutes=5,
        minimum_buffer_minutes=3,
        candidate_arrivals=(Arrival("C", "R2", 120),),
    )

    result = evaluate_transfer(transfer)

    assert result.status == TransferStatus.UNKNOWN
    assert result.reason == "no_arrival_data_for_target_station"


def test_safe_transfer_has_full_reliability_for_clear_margin():
    route = RouteCandidate(
        id="route-safe-score",
        segments=(
            RouteSegment("R1", "A", "B", 90, 100),
            RouteSegment("R2", "B", "C", 112, 130),
        ),
        transfers=(
            Transfer(
                from_station_id="B",
                to_station_id="B",
                arrival_minute=100,
                walking_minutes=5,
                minimum_buffer_minutes=3,
                candidate_arrivals=(Arrival("B", "R2", 112),),
            ),
        ),
    )

    result = evaluate_route(route)

    assert result.status == TransferStatus.SAFE
    assert result.reliability_score == 1.0


def test_transfer_filters_by_target_route_id():
    transfer = Transfer(
        from_station_id="A",
        to_station_id="B",
        arrival_minute=100,
        walking_minutes=5,
        minimum_buffer_minutes=3,
        candidate_arrivals=(
            Arrival("B", "WRONG", 108),
            Arrival("B", "R2", 115),
        ),
        target_route_id="R2",
    )

    result = evaluate_transfer(transfer)

    assert result.status == TransferStatus.SAFE
    assert result.board_minute == 115


def test_transfer_reports_unknown_when_target_route_arrival_is_missing():
    transfer = Transfer(
        from_station_id="A",
        to_station_id="B",
        arrival_minute=100,
        walking_minutes=5,
        minimum_buffer_minutes=3,
        candidate_arrivals=(Arrival("B", "WRONG", 115),),
        target_route_id="R2",
    )

    result = evaluate_transfer(transfer)

    assert result.status == TransferStatus.UNKNOWN
    assert result.reason == "no_arrival_data_for_target_route"


def test_negative_tight_threshold_is_rejected():
    transfer = Transfer(
        from_station_id="A",
        to_station_id="B",
        arrival_minute=100,
        walking_minutes=5,
        minimum_buffer_minutes=3,
        candidate_arrivals=(Arrival("B", "R2", 115),),
    )

    try:
        evaluate_transfer(transfer, tight_threshold_minutes=-1)
    except ValueError as exc:
        assert "tight_threshold_minutes" in str(exc)
    else:
        raise AssertionError("negative threshold should be rejected")


def test_route_candidate_rejects_disconnected_segments():
    try:
        RouteCandidate(
            id="disconnected",
            segments=(
                RouteSegment("R1", "A", "B", 100, 110),
                RouteSegment("R2", "X", "Y", 120, 130),
            ),
        )
    except ValueError as exc:
        assert "connect" in str(exc)
    else:
        raise AssertionError("disconnected route segments should be rejected")


def test_route_candidate_rejects_out_of_order_segments():
    try:
        RouteCandidate(
            id="time-travel",
            segments=(
                RouteSegment("R1", "A", "B", 200, 210),
                RouteSegment("R2", "B", "C", 100, 110),
            ),
        )
    except ValueError as exc:
        assert "ordered by time" in str(exc)
    else:
        raise AssertionError("out-of-order route segments should be rejected")


def test_route_evaluation_includes_initial_wait_when_requested_start_is_set():
    route = RouteCandidate(
        id="late-start",
        segments=(RouteSegment("R1", "A", "B", 200, 210),),
        requested_start_minute=100,
    )

    result = evaluate_route(route)

    assert result.initial_wait_minutes == 100
    assert result.total_minutes == 110


def test_route_candidate_allows_walking_transfer_between_different_stations():
    route = RouteCandidate(
        id="walk-transfer",
        segments=(
            RouteSegment("R1", "A", "B1", 100, 110),
            RouteSegment("R2", "B2", "C", 124, 140),
        ),
        transfers=(
            Transfer(
                from_station_id="B1",
                to_station_id="B2",
                arrival_minute=110,
                walking_minutes=5,
                minimum_buffer_minutes=3,
                candidate_arrivals=(Arrival("B2", "R2", 124),),
                target_route_id="R2",
            ),
        ),
    )

    result = evaluate_route(route)

    assert result.status == TransferStatus.SAFE
