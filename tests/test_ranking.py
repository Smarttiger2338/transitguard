from transitguard.core.models import Arrival, RouteCandidate, RouteSegment, Transfer
from transitguard.core.ranking import rank_routes


def make_route(route_id: str, candidate_minute: int) -> RouteCandidate:
    return RouteCandidate(
        id=route_id,
        segments=(
            RouteSegment("R1", "A", "B", 100, 110),
            RouteSegment("R2", "B", "C", candidate_minute, 140),
        ),
        transfers=(
            Transfer(
                from_station_id="B",
                to_station_id="B",
                arrival_minute=110,
                walking_minutes=4,
                minimum_buffer_minutes=3,
                candidate_arrivals=(Arrival("B", "R2", candidate_minute),),
            ),
        ),
    )


def test_rank_routes_prefers_safer_route_over_shorter_missed_route():
    ranked = rank_routes([make_route("missed", 116), make_route("safe", 121)])

    assert ranked[0].route_id == "safe"


def test_rank_routes_does_not_overprefer_very_late_direct_route():
    direct = RouteCandidate(
        id="late-direct",
        segments=(RouteSegment("D", "A", "C", 600, 620),),
        requested_start_minute=500,
    )
    tight_transfer = RouteCandidate(
        id="soon-tight",
        segments=(
            RouteSegment("R1", "A", "B", 501, 510),
            RouteSegment("R2", "B", "C", 518, 535),
        ),
        transfers=(
            Transfer(
                from_station_id="B",
                to_station_id="B",
                arrival_minute=510,
                walking_minutes=5,
                minimum_buffer_minutes=2,
                candidate_arrivals=(Arrival("B", "R2", 518),),
                target_route_id="R2",
            ),
        ),
        requested_start_minute=500,
    )

    ranked = rank_routes([direct, tight_transfer])

    assert ranked[0].route_id == "soon-tight"
