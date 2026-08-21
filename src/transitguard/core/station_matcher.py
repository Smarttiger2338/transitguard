from dataclasses import dataclass

from transitguard.core.models import Coordinate, Station


@dataclass(frozen=True)
class StationMatch:
    station: Station
    distance_m: float
    is_opposite: bool = False


def find_nearby_stations(
    point: Coordinate,
    stations: list[Station],
    radius_m: float = 500,
    include_opposite: bool = True,
) -> list[StationMatch]:
    if radius_m < 0:
        raise ValueError("radius_m must be non-negative")

    by_id = {station.id: station for station in stations}
    matches: dict[str, StationMatch] = {}

    for station in stations:
        distance = point.distance_to(station.coordinate)
        if distance > radius_m:
            continue

        matches[station.id] = StationMatch(station=station, distance_m=distance)

        if include_opposite and station.opposite_id and station.opposite_id in by_id:
            opposite = by_id[station.opposite_id]
            opposite_distance = point.distance_to(opposite.coordinate)
            if opposite_distance <= radius_m:
                matches.setdefault(
                    opposite.id,
                    StationMatch(
                        station=opposite,
                        distance_m=opposite_distance,
                        is_opposite=True,
                    ),
                )

    return sorted(matches.values(), key=lambda match: (match.distance_m, match.station.name))


def match_route_endpoints(
    origin: Coordinate,
    destination: Coordinate,
    stations: list[Station],
    radius_m: float = 700,
) -> dict[str, list[StationMatch]]:
    return {
        "origin_candidates": find_nearby_stations(origin, stations, radius_m),
        "destination_candidates": find_nearby_stations(destination, stations, radius_m),
    }
