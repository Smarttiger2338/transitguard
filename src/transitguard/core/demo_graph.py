from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from transitguard.core.models import (
    Arrival,
    Coordinate,
    RouteCandidate,
    RouteSegment,
    Station,
    Transfer,
)


@dataclass(frozen=True)
class GraphEdge:
    route_id: str
    from_station_id: str
    to_station_id: str
    travel_minutes: int


_DEMO_STATIONS: tuple[Station, ...] = (
    Station("S1", "대구역앞", Coordinate(35.8761, 128.5961), "S2"),
    Station("S2", "대구역건너", Coordinate(35.8757, 128.5965), "S1"),
    Station("S3", "동대구역", Coordinate(35.8797, 128.6284), "S4"),
    Station("S4", "동대구역건너", Coordinate(35.8792, 128.6288), "S3"),
    Station("S5", "중앙로", Coordinate(35.8708, 128.5931), None),
    Station("S6", "반월당", Coordinate(35.8646, 128.5933), None),
)

_DEMO_EDGES: tuple[GraphEdge, ...] = (
    GraphEdge("101", "S1", "S3", 20),
    GraphEdge("101", "S2", "S3", 22),
    GraphEdge("708", "S3", "S4", 18),
    GraphEdge("708", "S3", "S6", 24),
    GraphEdge("급행1", "S1", "S4", 55),
    GraphEdge("급행1", "S5", "S4", 47),
    GraphEdge("순환2", "S5", "S6", 8),
    GraphEdge("순환2", "S6", "S3", 17),
)


def get_demo_stations() -> tuple[Station, ...]:
    return _DEMO_STATIONS


def get_demo_edges() -> tuple[GraphEdge, ...]:
    return _DEMO_EDGES


def station_to_dict(station: Station) -> dict[str, object]:
    return {
        "id": station.id,
        "name": station.name,
        "lat": station.coordinate.lat,
        "lon": station.coordinate.lon,
        "opposite_id": station.opposite_id,
    }


def edge_to_dict(edge: GraphEdge) -> dict[str, object]:
    return {
        "route_id": edge.route_id,
        "from_station_id": edge.from_station_id,
        "to_station_id": edge.to_station_id,
        "travel_minutes": edge.travel_minutes,
    }


def graph_overview() -> dict[str, object]:
    return {
        "station_count": len(_DEMO_STATIONS),
        "route_count": len({edge.route_id for edge in _DEMO_EDGES}),
        "edge_count": len(_DEMO_EDGES),
        "stations": [station_to_dict(station) for station in _DEMO_STATIONS],
        "edges": [edge_to_dict(edge) for edge in _DEMO_EDGES],
    }


def search_demo_stations(query: str | None = None) -> list[Station]:
    normalized = (query or "").strip().lower()
    if not normalized:
        return list(_DEMO_STATIONS)

    return [
        station
        for station in _DEMO_STATIONS
        if normalized in station.id.lower() or normalized in station.name.lower()
    ]


def find_demo_station(query: str) -> Station:
    normalized = query.strip().lower()
    if not normalized:
        raise ValueError("station query must not be empty")

    exact_matches = [
        station
        for station in _DEMO_STATIONS
        if normalized in {station.id.lower(), station.name.lower()}
    ]
    if exact_matches:
        return exact_matches[0]

    matches = search_demo_stations(query)
    if not matches:
        raise ValueError(f"station not found: {query}")
    return matches[0]


def is_demo_station_id(station_id: str) -> bool:
    return any(station.id == station_id for station in _DEMO_STATIONS)


def seoul_timezone():
    try:
        return ZoneInfo("Asia/Seoul")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=9), name="KST")


def current_minute_of_day(now: datetime | None = None) -> int:
    tz = seoul_timezone()
    if now is None:
        value = datetime.now(tz)
    elif now.tzinfo is None:
        value = now
    else:
        value = now.astimezone(tz)
    return value.hour * 60 + value.minute


def generate_demo_arrivals(
    base_minute: int,
    transfer_station_id: str = "S3",
) -> tuple[Arrival, ...]:
    if base_minute < 0:
        raise ValueError("base_minute must be non-negative")
    if not is_demo_station_id(transfer_station_id):
        raise ValueError(f"station not found: {transfer_station_id}")

    routes = sorted(
        {edge.route_id for edge in _DEMO_EDGES if edge.from_station_id == transfer_station_id}
    )
    if not routes:
        return ()

    arrivals: list[Arrival] = []
    for index, route_id in enumerate(routes):
        offset = 26 + index * 4
        arrivals.extend(
            [
                Arrival(transfer_station_id, route_id, base_minute + offset),
                Arrival(transfer_station_id, route_id, base_minute + offset + 9),
            ]
        )
    return tuple(sorted(arrivals, key=lambda arrival: arrival.arrival_minute))


def build_demo_route_candidates(
    origin: Station,
    destination: Station,
    current_minute: int,
    arrival_overrides: Mapping[str, Sequence[Arrival]] | None = None,
) -> tuple[RouteCandidate, ...]:
    if current_minute < 0:
        raise ValueError("current_minute must be non-negative")
    if origin.id == destination.id:
        raise ValueError("origin and destination must be different")

    paths = _find_demo_paths(origin.id, destination.id, max_segments=3)
    candidates: list[RouteCandidate] = []
    for path in paths:
        candidate = _path_to_candidate(
            path,
            current_minute,
            len(candidates),
            arrival_overrides or {},
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _find_demo_paths(
    origin_id: str,
    destination_id: str,
    max_segments: int,
) -> tuple[tuple[GraphEdge, ...], ...]:
    paths: list[tuple[GraphEdge, ...]] = []

    def visit(current_id: str, path: tuple[GraphEdge, ...], visited: set[str]) -> None:
        if current_id == destination_id and path:
            paths.append(path)
            return
        if len(path) >= max_segments:
            return

        for edge in _DEMO_EDGES:
            if edge.from_station_id != current_id:
                continue
            if edge.to_station_id in visited:
                continue
            visit(edge.to_station_id, (*path, edge), {*visited, edge.to_station_id})

    visit(origin_id, (), {origin_id})
    return tuple(
        sorted(paths, key=lambda path: (len(path), sum(edge.travel_minutes for edge in path)))
    )


def _path_to_candidate(
    path: tuple[GraphEdge, ...],
    current_minute: int,
    index: int,
    arrival_overrides: Mapping[str, Sequence[Arrival]],
) -> RouteCandidate | None:
    departure = current_minute + 2 + index * 2
    segments: list[RouteSegment] = []
    transfers: list[Transfer] = []

    for edge_index, edge in enumerate(path):
        if edge.travel_minutes <= 0:
            raise ValueError("edge travel_minutes must be positive")

        arrival = departure + edge.travel_minutes
        segments.append(
            RouteSegment(
                route_id=edge.route_id,
                from_station_id=edge.from_station_id,
                to_station_id=edge.to_station_id,
                departure_minute=departure,
                arrival_minute=arrival,
            )
        )

        if edge_index < len(path) - 1:
            next_edge = path[edge_index + 1]
            walking_minutes = 4
            minimum_buffer_minutes = 3
            required_minute = arrival + walking_minutes + minimum_buffer_minutes
            override_arrivals = tuple(arrival_overrides.get(next_edge.from_station_id, ()))
            if override_arrivals:
                candidate_arrivals = override_arrivals
                selected_board = _next_board_minute(
                    candidate_arrivals,
                    station_id=next_edge.from_station_id,
                    route_id=next_edge.route_id,
                    required_minute=required_minute,
                )
                if selected_board is None:
                    return None
                board_minute = selected_board
            else:
                board_minute = required_minute + (3 if index % 2 == 0 else 0)
                candidate_arrivals = (
                    Arrival(next_edge.from_station_id, next_edge.route_id, board_minute),
                    Arrival(next_edge.from_station_id, next_edge.route_id, board_minute + 9),
                )
            transfers.append(
                Transfer(
                    from_station_id=edge.to_station_id,
                    to_station_id=next_edge.from_station_id,
                    arrival_minute=arrival,
                    walking_minutes=walking_minutes,
                    minimum_buffer_minutes=minimum_buffer_minutes,
                    candidate_arrivals=candidate_arrivals,
                    target_route_id=next_edge.route_id,
                )
            )
            departure = board_minute

    route_kind = "direct" if len(path) == 1 else "transfer"
    route_ids = "-".join(edge.route_id for edge in path)
    return RouteCandidate(
        id=f"{route_kind}-{index + 1}-{route_ids}",
        segments=tuple(segments),
        transfers=tuple(transfers),
        requested_start_minute=current_minute,
    )


def _next_board_minute(
    arrivals: Sequence[Arrival],
    *,
    station_id: str,
    route_id: str,
    required_minute: int,
) -> int | None:
    candidates = [
        arrival.arrival_minute
        for arrival in arrivals
        if arrival.station_id == station_id
        and arrival.route_id == route_id
        and arrival.arrival_minute >= required_minute
    ]
    return min(candidates) if candidates else None
