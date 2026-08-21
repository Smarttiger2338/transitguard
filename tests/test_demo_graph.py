from transitguard.core.demo_graph import build_demo_route_candidates, find_demo_station
from transitguard.core.models import Arrival


def test_demo_graph_override_arrival_updates_next_segment_departure():
    origin = find_demo_station("대구역앞")
    destination = find_demo_station("동대구역건너")

    routes = build_demo_route_candidates(
        origin,
        destination,
        520,
        arrival_overrides={"S3": (Arrival("S3", "708", 600),)},
    )

    transfer_route = next(route for route in routes if len(route.segments) == 2)
    assert transfer_route.segments[1].departure_minute == 600
    assert transfer_route.requested_start_minute == 520


def test_current_minute_uses_fixed_kst_when_zoneinfo_data_is_missing(monkeypatch):
    import transitguard.core.demo_graph as demo_graph

    class MissingZoneInfo:
        def __init__(self, key):
            raise demo_graph.ZoneInfoNotFoundError(key)

    monkeypatch.setattr(demo_graph, "ZoneInfo", MissingZoneInfo)

    assert demo_graph.current_minute_of_day() >= 0
