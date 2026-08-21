from transitguard.core.models import Coordinate, Station
from transitguard.core.station_matcher import find_nearby_stations, match_route_endpoints


def test_find_nearby_stations_includes_opposite_stop():
    stations = [
        Station("S1", "대구역앞", Coordinate(35.8761, 128.5961), "S2"),
        Station("S2", "대구역건너", Coordinate(35.8757, 128.5965), "S1"),
        Station("S3", "먼정류장", Coordinate(35.9000, 128.6500), None),
    ]

    matches = find_nearby_stations(Coordinate(35.8761, 128.5961), stations, radius_m=80)
    ids = {match.station.id for match in matches}

    assert "S1" in ids
    assert "S2" in ids
    assert "S3" not in ids


def test_match_route_endpoints_returns_origin_and_destination_candidates():
    stations = [
        Station("S1", "출발정류장", Coordinate(35.8761, 128.5961)),
        Station("S2", "도착정류장", Coordinate(35.8797, 128.6284)),
    ]

    result = match_route_endpoints(
        Coordinate(35.8761, 128.5961),
        Coordinate(35.8797, 128.6284),
        stations,
        radius_m=100,
    )

    assert result["origin_candidates"][0].station.id == "S1"
    assert result["destination_candidates"][0].station.id == "S2"


def test_negative_radius_is_rejected():
    stations = [Station("S1", "정류장", Coordinate(35.8761, 128.5961))]

    try:
        find_nearby_stations(Coordinate(35.8761, 128.5961), stations, radius_m=-1)
    except ValueError as exc:
        assert "radius_m" in str(exc)
    else:
        raise AssertionError("negative radius should be rejected")
