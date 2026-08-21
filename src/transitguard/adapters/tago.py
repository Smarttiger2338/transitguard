from __future__ import annotations

import json
import os
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from math import asin, ceil, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any, TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import urlopen
from xml.etree import ElementTree

from transitguard.core.models import Arrival, RouteCandidate, RouteSegment, Transfer

TAGO_ARRIVAL_ENDPOINT = (
    "https://apis.data.go.kr/1613000/ArvlInfoInqireService/"
    "getSttnAcctoArvlPrearngeInfoList"
)
TAGO_STATION_NEARBY_ENDPOINT = (
    "https://apis.data.go.kr/1613000/BusSttnInfoInqireService/getCrdntPrxmtSttnList"
)
TAGO_STATION_ROUTES_ENDPOINT = (
    "https://apis.data.go.kr/1613000/BusSttnInfoInqireService/getSttnThrghRouteList"
)
TAGO_ROUTE_STOPS_ENDPOINT = (
    "https://apis.data.go.kr/1613000/BusRouteInfoInqireService/getRouteAcctoThrghSttnList"
)
TAGO_SUBWAY_STATION_ENDPOINT = (
    "https://apis.data.go.kr/1613000/SubwayInfo/GetKwrdFndSubwaySttnList"
)


@dataclass(frozen=True)
class TagoConfig:
    service_key: str | None
    source: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.service_key)


@dataclass(frozen=True)
class TagoArrival:
    node_id: str
    node_name: str | None
    route_id: str
    route_no: str | None
    route_type: str | None
    arrival_seconds: int
    arrival_minute: int
    previous_station_count: int | None = None
    vehicle_type: str | None = None

    def to_core_arrival(
        self,
        station_id: str | None = None,
        prefer_route_no: bool = True,
    ) -> Arrival:
        route_value = self.route_no if prefer_route_no and self.route_no else self.route_id
        return Arrival(
            station_id=station_id or self.node_id,
            route_id=route_value,
            arrival_minute=self.arrival_minute,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "route_id": self.route_id,
            "route_no": self.route_no,
            "route_type": self.route_type,
            "arrival_seconds": self.arrival_seconds,
            "arrival_minute": self.arrival_minute,
            "previous_station_count": self.previous_station_count,
            "vehicle_type": self.vehicle_type,
        }


@dataclass(frozen=True)
class TagoStation:
    city_code: str
    node_id: str
    node_name: str
    lat: float
    lon: float

    def to_dict(self) -> dict[str, object]:
        return {
            "city_code": self.city_code,
            "node_id": self.node_id,
            "node_name": self.node_name,
            "lat": self.lat,
            "lon": self.lon,
        }


@dataclass(frozen=True)
class TagoStationRoute:
    route_id: str
    route_no: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"route_id": self.route_id, "route_no": self.route_no}


@dataclass(frozen=True)
class TagoSubwayStation:
    station_id: str
    station_name: str
    route_id: str
    route_name: str

    def to_dict(self) -> dict[str, str]:
        return {
            "station_id": self.station_id,
            "station_name": self.station_name,
            "route_id": self.route_id,
            "route_name": self.route_name,
        }


@dataclass(frozen=True)
class TagoRouteStop:
    city_code: str
    route_id: str
    route_no: str | None
    node_id: str
    node_name: str
    order: int
    lat: float | None = None
    lon: float | None = None
    updown_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "city_code": self.city_code,
            "route_id": self.route_id,
            "route_no": self.route_no,
            "node_id": self.node_id,
            "node_name": self.node_name,
            "order": self.order,
            "lat": self.lat,
            "lon": self.lon,
            "updown_code": self.updown_code,
        }


class TagoApiError(RuntimeError):
    pass


class TagoRouteBuildError(ValueError):
    pass


@dataclass
class TagoCallBudget:
    """Per-planning-request guard against exhausting TAGO request quotas."""

    limit: int = 60
    used: int = 0

    def consume(self) -> None:
        if self.used >= self.limit:
            raise TagoApiError(
                f"TAGO call budget exhausted ({self.used}/{self.limit})"
            )
        self.used += 1

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


_ACTIVE_CALL_BUDGET: ContextVar[TagoCallBudget | None] = ContextVar(
    "transitguard_tago_call_budget", default=None
)


@contextmanager
def use_tago_call_budget(limit: int):
    if limit < 1:
        raise ValueError("TAGO call budget must be greater than zero")
    budget = TagoCallBudget(limit=limit)
    token = _ACTIVE_CALL_BUDGET.set(budget)
    try:
        yield budget
    finally:
        _ACTIVE_CALL_BUDGET.reset(token)


@dataclass(frozen=True)
class _ForwardPair:
    origin: TagoRouteStop
    destination: TagoRouteStop

    @property
    def gap(self) -> int:
        return self.destination.order - self.origin.order


@dataclass(frozen=True)
class _TransferSpec:
    first_route_id: str
    second_route_id: str
    first_transfer_node_id: str
    second_transfer_node_id: str
    first_gap: int
    second_gap: int
    walking_minutes: int
    walking_distance_m: float | None = None

    @property
    def total_gap(self) -> int:
        return self.first_gap + self.second_gap


@dataclass(frozen=True)
class _BoardingOption:
    node_id: str
    walking_minutes: int
    walking_distance_m: float | None = None


def read_config_value(key: str) -> tuple[str | None, str | None]:
    environment_value = os.getenv(key)
    if environment_value and environment_value.strip():
        return environment_value.strip(), "environment"

    dotenv_value = _read_dotenv_value(key)
    if dotenv_value:
        return dotenv_value, ".env"

    return None, None


def load_tago_config() -> TagoConfig:
    value, source = read_config_value("TAGO_SERVICE_KEY")
    return TagoConfig(service_key=value, source=source)


def require_tago_config() -> TagoConfig:
    config = load_tago_config()
    if not config.available:
        raise RuntimeError("TAGO_SERVICE_KEY is not configured")
    return config


def fetch_station_arrivals(
    city_code: str,
    node_id: str,
    *,
    current_minute: int,
    page_no: int = 1,
    num_of_rows: int = 10,
    timeout_seconds: float = 5.0,
    service_key: str | None = None,
    endpoint: str = TAGO_ARRIVAL_ENDPOINT,
    fetch_all_pages: bool = True,
    strict_items: bool = True,
) -> tuple[TagoArrival, ...]:
    _require_text(city_code, "city_code")
    _require_text(node_id, "node_id")
    if current_minute < 0:
        raise ValueError("current_minute must be non-negative")

    items = _fetch_tago_items(
        endpoint=endpoint,
        service_key=service_key,
        timeout_seconds=timeout_seconds,
        params={
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            "_type": "json",
            "cityCode": city_code.strip(),
            "nodeId": node_id.strip(),
        },
        fetch_all_pages=fetch_all_pages,
    )
    return _convert_tago_items(
        items,
        lambda item: _item_to_tago_arrival(
            item,
            fallback_node_id=node_id.strip(),
            current_minute=current_minute,
        ),
        strict_items=strict_items,
    )


def fetch_station_arrivals_as_core(
    city_code: str,
    node_id: str,
    *,
    current_minute: int,
    station_id: str | None = None,
    prefer_route_no: bool = True,
    page_no: int = 1,
    num_of_rows: int = 10,
    timeout_seconds: float = 5.0,
    fetch_all_pages: bool = True,
    strict_items: bool = True,
) -> tuple[Arrival, ...]:
    return tuple(
        arrival.to_core_arrival(station_id=station_id, prefer_route_no=prefer_route_no)
        for arrival in fetch_station_arrivals(
            city_code,
            node_id,
            current_minute=current_minute,
            page_no=page_no,
            num_of_rows=num_of_rows,
            timeout_seconds=timeout_seconds,
            fetch_all_pages=fetch_all_pages,
            strict_items=strict_items,
        )
    )


def fetch_nearby_stations(
    *,
    lat: float,
    lon: float,
    page_no: int = 1,
    num_of_rows: int = 20,
    timeout_seconds: float = 5.0,
    service_key: str | None = None,
    endpoint: str = TAGO_STATION_NEARBY_ENDPOINT,
    fetch_all_pages: bool = False,
    strict_items: bool = True,
) -> tuple[TagoStation, ...]:
    if not -90 <= lat <= 90:
        raise ValueError("lat must be between -90 and 90")
    if not -180 <= lon <= 180:
        raise ValueError("lon must be between -180 and 180")
    items = _fetch_tago_items(
        endpoint=endpoint,
        service_key=service_key,
        timeout_seconds=timeout_seconds,
        params={
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            "_type": "json",
            "gpsLati": lat,
            "gpsLong": lon,
        },
        fetch_all_pages=fetch_all_pages,
    )
    return _convert_tago_items(items, _item_to_tago_station, strict_items=strict_items)


def fetch_station_routes(
    city_code: str,
    node_id: str,
    *,
    num_of_rows: int = 100,
    timeout_seconds: float = 5.0,
    service_key: str | None = None,
    endpoint: str = TAGO_STATION_ROUTES_ENDPOINT,
) -> tuple[TagoStationRoute, ...]:
    """Return routes that pass a stop, independent of live arrival availability."""
    _require_text(city_code, "city_code")
    _require_text(node_id, "node_id")
    params = {
        "pageNo": 1,
        "numOfRows": num_of_rows,
        "_type": "json",
        "cityCode": city_code.strip(),
        # Unlike the arrival API (nodeId), this operation documents and
        # accepts the stop identifier as lowercase ``nodeid``.
        "nodeid": node_id.strip(),
    }
    last_error: TagoApiError | None = None
    for attempt in range(2):
        try:
            items = _fetch_tago_items(
                endpoint=endpoint,
                service_key=service_key,
                timeout_seconds=timeout_seconds,
                params=params,
                fetch_all_pages=False,
            )
            break
        except TagoApiError as exc:
            last_error = exc
            transient = "response object" in str(exc) or "timed out" in str(exc).lower()
            if attempt or not transient:
                raise
    else:  # pragma: no cover - the loop either succeeds or raises
        assert last_error is not None
        raise last_error
    converted = _convert_tago_items(items, _item_to_station_route, strict_items=False)
    routes: list[TagoStationRoute] = []
    seen_route_ids: set[str] = set()
    for route in converted:
        if route.route_id in seen_route_ids:
            continue
        seen_route_ids.add(route.route_id)
        routes.append(route)

    # Daegu returning a city-sized catalogue means its stop filter was ignored.
    # Gyeongsan is different: one physical stop can legitimately expose many
    # branch/direction route IDs (Jain stops currently return about 96), even
    # though the public route numbers repeat.  Rejecting those valid GYB rows
    # made every Jain search appear to have no routes.
    is_gyeongsan_stop = city_code.strip() == "37100" and node_id.strip().startswith(
        "GYB"
    )
    if len(routes) > 60 and not is_gyeongsan_stop:
        raise TagoApiError(
            "TAGO returned an unfiltered city-wide route list for one stop"
        )
    return tuple(routes)


def fetch_subway_stations(
    station_name: str,
    *,
    num_of_rows: int = 30,
    timeout_seconds: float = 12.0,
    service_key: str | None = None,
    endpoint: str = TAGO_SUBWAY_STATION_ENDPOINT,
) -> tuple[TagoSubwayStation, ...]:
    """Find subway stations by name through the official TAGO SubwayInfo API."""
    _require_text(station_name, "station_name")
    items = _fetch_tago_items(
        endpoint=endpoint,
        service_key=service_key,
        timeout_seconds=timeout_seconds,
        params={
            "pageNo": 1,
            "numOfRows": num_of_rows,
            "_type": "json",
            "subwayStationName": station_name.strip(),
        },
        fetch_all_pages=False,
    )
    return _convert_tago_items(items, _item_to_subway_station, strict_items=False)


def discover_subway_candidates(
    *,
    origin_name: str,
    destination_name: str,
    current_minute: int,
) -> tuple[RouteCandidate, ...]:
    """Build direct or one-transfer subway candidates from TAGO station results."""
    origin_stations = fetch_subway_stations(_normalize_subway_keyword(origin_name))
    destination_stations = fetch_subway_stations(
        _normalize_subway_keyword(destination_name)
    )
    candidates: list[RouteCandidate] = []
    for origin in origin_stations:
        for destination in destination_stations:
            if origin.route_id != destination.route_id:
                continue
            departure = current_minute + 5
            candidates.append(
                RouteCandidate(
                    id=(
                        f"tago-subway-direct-{origin.route_id}-"
                        f"{origin.station_id}-{destination.station_id}"
                    ),
                    requested_start_minute=current_minute,
                    segments=(
                        RouteSegment(
                            route_id=origin.route_name or origin.route_id,
                            from_station_id=origin.station_id,
                            to_station_id=destination.station_id,
                            departure_minute=departure,
                            arrival_minute=departure + 20,
                        ),
                    ),
                )
            )
    if candidates:
        return tuple(candidates)

    transfer_names = ("반월당", "청라언덕")
    for origin in origin_stations:
        for destination in destination_stations:
            if origin.route_id == destination.route_id:
                continue
            for transfer_name in transfer_names:
                transfer_stations = fetch_subway_stations(transfer_name)
                first_transfer = next(
                    (
                        station
                        for station in transfer_stations
                        if station.route_id == origin.route_id
                    ),
                    None,
                )
                second_transfer = next(
                    (
                        station
                        for station in transfer_stations
                        if station.route_id == destination.route_id
                    ),
                    None,
                )
                if first_transfer is None or second_transfer is None:
                    continue
                first_departure = current_minute + 5
                transfer_arrival = first_departure + 20
                second_departure = transfer_arrival + 5
                candidates.append(
                    RouteCandidate(
                        id=(
                            f"tago-subway-transfer-{origin.route_id}-"
                            f"{destination.route_id}-{transfer_name}"
                        ),
                        requested_start_minute=current_minute,
                        segments=(
                            RouteSegment(
                                route_id=origin.route_name,
                                from_station_id=origin.station_id,
                                to_station_id=first_transfer.station_id,
                                departure_minute=first_departure,
                                arrival_minute=transfer_arrival,
                            ),
                            RouteSegment(
                                route_id=destination.route_name,
                                from_station_id=second_transfer.station_id,
                                to_station_id=destination.station_id,
                                departure_minute=second_departure,
                                arrival_minute=second_departure + 20,
                            ),
                        ),
                        transfers=(
                            Transfer(
                                from_station_id=first_transfer.station_id,
                                to_station_id=second_transfer.station_id,
                                arrival_minute=transfer_arrival,
                                walking_minutes=5,
                                minimum_buffer_minutes=0,
                                candidate_arrivals=(
                                    Arrival(
                                        station_id=second_transfer.station_id,
                                        route_id=destination.route_name,
                                        arrival_minute=second_departure,
                                    ),
                                ),
                                target_route_id=destination.route_name,
                            ),
                        ),
                    )
                )
                break
    return tuple(candidates)


def discover_direct_subway_candidates(
    *, origin_name: str, destination_name: str, current_minute: int
) -> tuple[RouteCandidate, ...]:
    """Backward-compatible alias for subway candidate discovery."""
    return discover_subway_candidates(
        origin_name=origin_name,
        destination_name=destination_name,
        current_minute=current_minute,
    )


def discover_tago_topology_candidates(
    *,
    city_code: str,
    origin_node_id: str,
    destination_node_id: str,
    current_minute: int,
    max_routes_per_stop: int = 8,
    average_minutes_per_stop: float = 2.0,
    assumed_initial_wait_minutes: int = 10,
    assumed_transfer_wait_minutes: int = 5,
    minimum_transfer_buffer_minutes: int = 3,
    max_direct_candidates: int = 2,
    max_walking_transfer_m: float = 400.0,
    walking_meters_per_minute: float = 80.0,
    timeout_seconds: float = 5.0,
    station_route_cache: dict[str, tuple[TagoStationRoute, ...]] | None = None,
    route_stop_cache: dict[str, tuple[TagoRouteStop, ...]] | None = None,
) -> tuple[RouteCandidate, ...]:
    """Find direct or one-transfer topology candidates when live arrivals are sparse."""
    station_routes = station_route_cache if station_route_cache is not None else {}
    route_cache = route_stop_cache if route_stop_cache is not None else {}

    def routes(node_id: str) -> tuple[TagoStationRoute, ...]:
        if node_id not in station_routes:
            station_routes[node_id] = fetch_station_routes(
                city_code, node_id, timeout_seconds=timeout_seconds
            )
        return station_routes[node_id][:max_routes_per_stop]

    origin_routes = routes(origin_node_id)
    destination_routes: tuple[TagoStationRoute, ...] | None = None

    def stops(route_id: str) -> tuple[TagoRouteStop, ...]:
        try:
            return _cached_route_stops(
                route_cache,
                city_code=city_code,
                route_id=route_id,
                timeout_seconds=timeout_seconds,
            )
        except (RuntimeError, TagoApiError, ValueError):
            # Regional TAGO backends occasionally fail for one branch route.
            # That branch must not abort discovery of every other route serving
            # the same stop (Jain can expose around 96 branch/direction IDs).
            route_cache[route_id] = ()
            return ()

    candidates: list[RouteCandidate] = []
    direct_count = 0
    for first in origin_routes:
        direct_pair = _find_best_forward_pair(
            stops(first.route_id), origin_node_id, destination_node_id
        )
        if direct_pair is not None:
            departure = current_minute + assumed_initial_wait_minutes
            candidates.append(
                RouteCandidate(
                    id=f"tago-topology-direct-{first.route_id}",
                    requested_start_minute=current_minute,
                    segments=(
                        RouteSegment(
                            route_id=first.route_no or first.route_id,
                            from_station_id=origin_node_id,
                            to_station_id=destination_node_id,
                            departure_minute=departure,
                            arrival_minute=departure
                            + _estimate_travel_minutes(
                                direct_pair.gap, average_minutes_per_stop
                            ),
                        ),
                    ),
                )
            )
            direct_count += 1
            if direct_count >= max_direct_candidates:
                return tuple(candidates)
            continue

        first_pairs = _transfer_pairs_after_origin(
            stops(first.route_id),
            origin_node_id=origin_node_id,
            destination_node_id=destination_node_id,
        )
        if destination_routes is None:
            destination_routes = routes(destination_node_id)
        found_transfer = False
        for second in destination_routes:
            if second.route_id == first.route_id:
                continue
            second_stops = stops(second.route_id)
            second_pairs = _transfer_pairs_to_destination(
                second_stops,
                origin_node_id=origin_node_id,
                destination_node_id=destination_node_id,
            )
            for first_pair in first_pairs:
                matches: list[tuple[_ForwardPair, int, float | None]] = []
                for second_pair in second_pairs:
                    walk = _walking_transfer(
                        first_pair.destination,
                        second_pair.origin,
                        base_walking_minutes=assumed_transfer_wait_minutes,
                        max_walking_transfer_m=max_walking_transfer_m,
                        walking_meters_per_minute=walking_meters_per_minute,
                    )
                    if walk is not None:
                        matches.append((second_pair, *walk))
                if not matches:
                    continue
                second_pair, transfer_wait, walking_distance_m = min(
                    matches,
                    key=lambda match: (
                        match[2] if match[2] is not None else 0.0,
                        match[0].gap,
                    ),
                )
                first_departure = current_minute + assumed_initial_wait_minutes
                transfer_arrival = first_departure + _estimate_travel_minutes(
                    first_pair.gap, average_minutes_per_stop
                )
                second_departure = (
                    transfer_arrival
                    + transfer_wait
                    + minimum_transfer_buffer_minutes
                )
                candidates.append(
                    RouteCandidate(
                        id=f"tago-topology-transfer-{first.route_id}-{second.route_id}",
                        requested_start_minute=current_minute,
                        segments=(
                            RouteSegment(
                                route_id=first.route_no or first.route_id,
                                from_station_id=origin_node_id,
                                to_station_id=first_pair.destination.node_id,
                                departure_minute=first_departure,
                                arrival_minute=transfer_arrival,
                            ),
                            RouteSegment(
                                route_id=second.route_no or second.route_id,
                                from_station_id=second_pair.origin.node_id,
                                to_station_id=destination_node_id,
                                departure_minute=second_departure,
                                arrival_minute=second_departure
                                + _estimate_travel_minutes(
                                    second_pair.gap, average_minutes_per_stop
                                ),
                            ),
                        ),
                        transfers=(
                            Transfer(
                                from_station_id=first_pair.destination.node_id,
                                to_station_id=second_pair.origin.node_id,
                                arrival_minute=transfer_arrival,
                                walking_minutes=transfer_wait,
                                minimum_buffer_minutes=minimum_transfer_buffer_minutes,
                                candidate_arrivals=(
                                    Arrival(
                                        station_id=second_pair.origin.node_id,
                                        route_id=second.route_no or second.route_id,
                                        arrival_minute=second_departure,
                                    ),
                                ),
                                target_route_id=second.route_no or second.route_id,
                            ),
                        ),
                    )
                )
                found_transfer = True
                break
            if found_transfer:
                break
    return tuple(candidates)


def fetch_route_stops(
    city_code: str,
    route_id: str,
    *,
    page_no: int = 1,
    num_of_rows: int = 300,
    timeout_seconds: float = 5.0,
    service_key: str | None = None,
    endpoint: str = TAGO_ROUTE_STOPS_ENDPOINT,
    fetch_all_pages: bool = True,
    strict_items: bool = True,
) -> tuple[TagoRouteStop, ...]:
    _require_text(city_code, "city_code")
    _require_text(route_id, "route_id")
    items = _fetch_tago_items(
        endpoint=endpoint,
        service_key=service_key,
        timeout_seconds=timeout_seconds,
        params={
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            "_type": "json",
            "cityCode": city_code.strip(),
            "routeId": route_id.strip(),
        },
        fetch_all_pages=fetch_all_pages,
    )
    stops = _convert_tago_items(
        items,
        lambda item: _item_to_tago_route_stop(item, city_code=city_code.strip()),
        strict_items=strict_items,
    )
    if _should_preserve_route_stop_order(stops):
        return stops
    return tuple(sorted(stops, key=lambda stop: (stop.updown_code or "", stop.order)))


def _should_preserve_route_stop_order(stops: tuple[TagoRouteStop, ...]) -> bool:
    if not stops or any(stop.updown_code for stop in stops):
        return False
    orders = [stop.order for stop in stops]
    order_pairs = zip(orders, orders[1:], strict=False)
    has_reset = any(current <= previous for previous, current in order_pairs)
    has_duplicate_order = len(set(orders)) < len(orders)
    return has_duplicate_order or (has_reset and orders[0] <= orders[-1])


def build_tago_route_candidates(
    *,
    city_code: str,
    origin_node_id: str,
    destination_node_id: str,
    route_ids: tuple[str, ...],
    current_minute: int,
    average_minutes_per_stop: float = 2.0,
    walking_minutes: int = 4,
    minimum_buffer_minutes: int = 3,
    max_transfer_candidates: int = 5,
    max_walking_transfer_m: float = 300.0,
    walking_meters_per_minute: float = 80.0,
    timeout_seconds: float = 5.0,
) -> tuple[RouteCandidate, ...]:
    _require_text(city_code, "city_code")
    _require_text(origin_node_id, "origin_node_id")
    _require_text(destination_node_id, "destination_node_id")
    if origin_node_id == destination_node_id:
        raise TagoRouteBuildError("origin_node_id and destination_node_id must be different")
    if not route_ids:
        raise TagoRouteBuildError("at least one route_id is required")
    if current_minute < 0:
        raise ValueError("current_minute must be non-negative")
    if average_minutes_per_stop <= 0:
        raise ValueError("average_minutes_per_stop must be positive")
    if walking_minutes < 0 or minimum_buffer_minutes < 0:
        raise ValueError("walking and buffer minutes must be non-negative")
    if max_walking_transfer_m < 0:
        raise ValueError("max_walking_transfer_m must be non-negative")
    if walking_meters_per_minute <= 0:
        raise ValueError("walking_meters_per_minute must be positive")

    unique_route_ids = tuple(
        dict.fromkeys(route_id.strip() for route_id in route_ids if route_id.strip())
    )
    if not unique_route_ids:
        raise TagoRouteBuildError("at least one non-empty route_id is required")

    stop_map = {
        route_id: fetch_route_stops(
            city_code,
            route_id,
            timeout_seconds=timeout_seconds,
        )
        for route_id in unique_route_ids
    }
    origin_arrivals = fetch_station_arrivals(
        city_code,
        origin_node_id,
        current_minute=current_minute,
        num_of_rows=100,
        timeout_seconds=timeout_seconds,
    )
    transfer_arrival_cache: dict[str, tuple[TagoArrival, ...]] = {}
    candidates: list[RouteCandidate] = []

    for route_id, stops in stop_map.items():
        direct = _direct_candidate_from_real_data(
            route_id=route_id,
            stops=stops,
            origin_node_id=origin_node_id,
            destination_node_id=destination_node_id,
            origin_arrivals=origin_arrivals,
            average_minutes_per_stop=average_minutes_per_stop,
            current_minute=current_minute,
            index=len(candidates),
        )
        if direct is not None:
            candidates.append(direct)

    transfer_specs = _find_transfer_specs(
        stop_map=stop_map,
        origin_node_id=origin_node_id,
        destination_node_id=destination_node_id,
        limit=max_transfer_candidates,
        base_walking_minutes=walking_minutes,
        max_walking_transfer_m=max_walking_transfer_m,
        walking_meters_per_minute=walking_meters_per_minute,
    )
    for spec in transfer_specs:
        first_board = _select_relevant_arrival(origin_arrivals, spec.first_route_id)
        if first_board is None:
            continue
        first_arrival_minute = first_board.arrival_minute + _estimate_travel_minutes(
            spec.first_gap, average_minutes_per_stop
        )
        required_minute = (
            first_arrival_minute + spec.walking_minutes + minimum_buffer_minutes
        )
        transfer_arrivals = transfer_arrival_cache.get(spec.second_transfer_node_id)
        if transfer_arrivals is None:
            transfer_arrivals = fetch_station_arrivals(
                city_code,
                spec.second_transfer_node_id,
                current_minute=current_minute,
                num_of_rows=100,
                timeout_seconds=timeout_seconds,
            )
            transfer_arrival_cache[spec.second_transfer_node_id] = transfer_arrivals
        second_board = _select_relevant_arrival(
            transfer_arrivals,
            spec.second_route_id,
            earliest_minute=required_minute,
        )
        if second_board is None:
            continue
        candidates.append(
            _transfer_candidate_from_real_data(
                first_route_id=spec.first_route_id,
                second_route_id=spec.second_route_id,
                origin_node_id=origin_node_id,
                first_transfer_node_id=spec.first_transfer_node_id,
                second_transfer_node_id=spec.second_transfer_node_id,
                destination_node_id=destination_node_id,
                first_board_minute=first_board.arrival_minute,
                first_arrival_minute=first_arrival_minute,
                second_board_minute=second_board.arrival_minute,
                second_gap=spec.second_gap,
                transfer_arrivals=transfer_arrivals,
                average_minutes_per_stop=average_minutes_per_stop,
                walking_minutes=spec.walking_minutes,
                minimum_buffer_minutes=minimum_buffer_minutes,
                current_minute=current_minute,
                index=len(candidates),
            )
        )


    return tuple(candidates)


def discover_tago_route_candidates(
    *,
    city_code: str,
    origin_node_id: str,
    destination_node_id: str,
    current_minute: int,
    average_minutes_per_stop: float = 2.0,
    walking_minutes: int = 4,
    minimum_buffer_minutes: int = 3,
    max_origin_routes: int = 8,
    max_transfer_stops_per_route: int = 8,
    max_transfer_routes_per_stop: int = 6,
    max_walking_transfer_m: float = 300.0,
    walking_meters_per_minute: float = 80.0,
    max_walking_transfer_stations: int = 6,
    timeout_seconds: float = 5.0,
    diagnostics: dict[str, object] | None = None,
) -> tuple[RouteCandidate, ...]:
    """Discover bounded TAGO route candidates without pre-supplied route IDs.

    The search starts from routes in the live arrivals at the origin stop. It then
    checks direct paths and one-transfer paths. Transfer boarding can happen at
    the same stop or at a nearby stop when TAGO coordinates are available.
    """
    _require_text(city_code, "city_code")
    _require_text(origin_node_id, "origin_node_id")
    _require_text(destination_node_id, "destination_node_id")
    if origin_node_id == destination_node_id:
        raise TagoRouteBuildError("origin_node_id and destination_node_id must be different")
    if current_minute < 0:
        raise ValueError("current_minute must be non-negative")
    if average_minutes_per_stop <= 0:
        raise ValueError("average_minutes_per_stop must be positive")
    if walking_minutes < 0 or minimum_buffer_minutes < 0:
        raise ValueError("walking and buffer minutes must be non-negative")
    if min(max_origin_routes, max_transfer_stops_per_route, max_transfer_routes_per_stop) < 1:
        raise ValueError("discovery limits must be greater than zero")
    if max_walking_transfer_m < 0:
        raise ValueError("max_walking_transfer_m must be non-negative")
    if walking_meters_per_minute <= 0:
        raise ValueError("walking_meters_per_minute must be positive")
    if max_walking_transfer_stations < 1:
        raise ValueError("max_walking_transfer_stations must be greater than zero")

    origin_arrivals = fetch_station_arrivals(
        city_code,
        origin_node_id,
        current_minute=current_minute,
        num_of_rows=100,
        timeout_seconds=timeout_seconds,
    )
    origin_route_ids = _arrival_route_ids(origin_arrivals)[:max_origin_routes]
    if diagnostics is not None:
        diagnostics["origin_arrivals"] = [arrival.to_dict() for arrival in origin_arrivals]
        diagnostics["origin_routes"] = [
            {
                "route_id": route_id,
                "route_no": next(
                    (
                        arrival.route_no
                        for arrival in origin_arrivals
                        if arrival.route_id == route_id and arrival.route_no
                    ),
                    None,
                ),
            }
            for route_id in origin_route_ids
        ]
    route_stop_cache: dict[str, tuple[TagoRouteStop, ...]] = {}
    arrival_cache: dict[str, tuple[TagoArrival, ...]] = {origin_node_id: origin_arrivals}
    candidates: list[RouteCandidate] = []

    for route_id in origin_route_ids:
        stops = _cached_route_stops(
            route_stop_cache,
            city_code=city_code,
            route_id=route_id,
            timeout_seconds=timeout_seconds,
        )
        direct = _direct_candidate_from_real_data(
            route_id=route_id,
            stops=stops,
            origin_node_id=origin_node_id,
            destination_node_id=destination_node_id,
            origin_arrivals=origin_arrivals,
            average_minutes_per_stop=average_minutes_per_stop,
            current_minute=current_minute,
            index=len(candidates),
        )
        if direct is not None:
            candidates.append(direct)

        transfer_pairs = _transfer_pairs_after_origin(
            stops,
            origin_node_id=origin_node_id,
            destination_node_id=destination_node_id,
        )[:max_transfer_stops_per_route]
        for transfer_pair in transfer_pairs:
            boarding_options = _discovery_boarding_options(
                transfer_pair.destination,
                base_walking_minutes=walking_minutes,
                max_walking_transfer_m=max_walking_transfer_m,
                walking_meters_per_minute=walking_meters_per_minute,
                max_walking_transfer_stations=max_walking_transfer_stations,
                timeout_seconds=timeout_seconds,
            )
            for option in boarding_options:
                transfer_arrivals = _cached_station_arrivals(
                    arrival_cache,
                    city_code=city_code,
                    node_id=option.node_id,
                    current_minute=current_minute,
                    timeout_seconds=timeout_seconds,
                )
                second_route_ids = _arrival_route_ids(transfer_arrivals)[
                    :max_transfer_routes_per_stop
                ]
                for second_route_id in second_route_ids:
                    if second_route_id == route_id:
                        continue
                    second_stops = _cached_route_stops(
                        route_stop_cache,
                        city_code=city_code,
                        route_id=second_route_id,
                        timeout_seconds=timeout_seconds,
                    )
                    second_pair = _find_best_forward_pair(
                        second_stops,
                        option.node_id,
                        destination_node_id,
                    )
                    if second_pair is None:
                        continue
                    first_board = _select_relevant_arrival(origin_arrivals, route_id)
                    if first_board is None:
                        continue
                    first_arrival_minute = (
                        first_board.arrival_minute
                        + _estimate_travel_minutes(
                            transfer_pair.gap,
                            average_minutes_per_stop,
                        )
                    )
                    required_minute = (
                        first_arrival_minute
                        + option.walking_minutes
                        + minimum_buffer_minutes
                    )
                    second_board = _select_relevant_arrival(
                        transfer_arrivals,
                        second_route_id,
                        earliest_minute=required_minute,
                    )
                    if second_board is None:
                        continue
                    candidates.append(
                        _transfer_candidate_from_real_data(
                            first_route_id=route_id,
                            second_route_id=second_route_id,
                            origin_node_id=origin_node_id,
                            first_transfer_node_id=transfer_pair.destination.node_id,
                            second_transfer_node_id=option.node_id,
                            destination_node_id=destination_node_id,
                            first_board_minute=first_board.arrival_minute,
                            first_arrival_minute=first_arrival_minute,
                            second_board_minute=second_board.arrival_minute,
                            second_gap=second_pair.gap,
                            transfer_arrivals=transfer_arrivals,
                            average_minutes_per_stop=average_minutes_per_stop,
                            walking_minutes=option.walking_minutes,
                            minimum_buffer_minutes=minimum_buffer_minutes,
                            current_minute=current_minute,
                            index=len(candidates),
                        )
                    )

    return _dedupe_candidates(candidates)


def _discovery_boarding_options(
    alighting_stop: TagoRouteStop,
    *,
    base_walking_minutes: int,
    max_walking_transfer_m: float,
    walking_meters_per_minute: float,
    max_walking_transfer_stations: int,
    timeout_seconds: float,
) -> tuple[_BoardingOption, ...]:
    options = [_BoardingOption(alighting_stop.node_id, base_walking_minutes, 0.0)]
    if alighting_stop.lat is None or alighting_stop.lon is None:
        return tuple(options)

    try:
        nearby = fetch_nearby_stations(
            lat=alighting_stop.lat,
            lon=alighting_stop.lon,
            num_of_rows=max(max_walking_transfer_stations * 2, 10),
            timeout_seconds=timeout_seconds,
        )
    except TagoApiError:
        return tuple(options)
    except RuntimeError:
        return tuple(options)

    reference_stop = TagoRouteStop(
        city_code=alighting_stop.city_code,
        route_id=alighting_stop.route_id,
        route_no=alighting_stop.route_no,
        node_id=alighting_stop.node_id,
        node_name=alighting_stop.node_name,
        order=alighting_stop.order,
        lat=alighting_stop.lat,
        lon=alighting_stop.lon,
    )
    for station in nearby:
        if station.node_id == alighting_stop.node_id:
            continue
        candidate_stop = TagoRouteStop(
            city_code=station.city_code,
            route_id="",
            route_no=None,
            node_id=station.node_id,
            node_name=station.node_name,
            order=0,
            lat=station.lat,
            lon=station.lon,
        )
        walk = _walking_transfer(
            reference_stop,
            candidate_stop,
            base_walking_minutes=base_walking_minutes,
            max_walking_transfer_m=max_walking_transfer_m,
            walking_meters_per_minute=walking_meters_per_minute,
        )
        if walk is None:
            continue
        minutes, distance_m = walk
        options.append(_BoardingOption(station.node_id, minutes, distance_m))
        if len(options) >= max_walking_transfer_stations:
            break
    return tuple(
        sorted(
            dict.fromkeys(options),
            key=lambda option: (option.walking_minutes, option.walking_distance_m or 0.0),
        )
    )

def _cached_route_stops(
    cache: dict[str, tuple[TagoRouteStop, ...]],
    *,
    city_code: str,
    route_id: str,
    timeout_seconds: float,
) -> tuple[TagoRouteStop, ...]:
    if route_id not in cache:
        cache[route_id] = fetch_route_stops(
            city_code,
            route_id,
            timeout_seconds=timeout_seconds,
        )
    return cache[route_id]


def _cached_station_arrivals(
    cache: dict[str, tuple[TagoArrival, ...]],
    *,
    city_code: str,
    node_id: str,
    current_minute: int,
    timeout_seconds: float,
) -> tuple[TagoArrival, ...]:
    if node_id not in cache:
        cache[node_id] = fetch_station_arrivals(
            city_code,
            node_id,
            current_minute=current_minute,
            num_of_rows=100,
            timeout_seconds=timeout_seconds,
        )
    return cache[node_id]


def _arrival_route_ids(arrivals: tuple[TagoArrival, ...]) -> tuple[str, ...]:
    route_ids = []
    for arrival in sorted(arrivals, key=lambda item: item.arrival_minute):
        if arrival.route_id not in route_ids:
            route_ids.append(arrival.route_id)
    return tuple(route_ids)


def _dedupe_candidates(candidates: list[RouteCandidate]) -> tuple[RouteCandidate, ...]:
    seen: set[tuple[tuple[str, str, str], ...]] = set()
    result: list[RouteCandidate] = []
    for candidate in candidates:
        key = tuple(
            (segment.route_id, segment.from_station_id, segment.to_station_id)
            for segment in candidate.segments
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return tuple(result)


def _direct_candidate_from_real_data(
    *,
    route_id: str,
    stops: tuple[TagoRouteStop, ...],
    origin_node_id: str,
    destination_node_id: str,
    origin_arrivals: tuple[TagoArrival, ...],
    average_minutes_per_stop: float,
    current_minute: int,
    index: int,
) -> RouteCandidate | None:
    pair = _find_best_forward_pair(stops, origin_node_id, destination_node_id)
    if pair is None:
        return None
    board = _select_relevant_arrival(origin_arrivals, route_id)
    if board is None:
        return None
    arrival_minute = board.arrival_minute + _estimate_travel_minutes(
        pair.gap,
        average_minutes_per_stop,
    )
    return RouteCandidate(
        id=f"tago-direct-{index + 1}-{route_id}",
        segments=(
            RouteSegment(
                route_id=route_id,
                from_station_id=origin_node_id,
                to_station_id=destination_node_id,
                departure_minute=board.arrival_minute,
                arrival_minute=arrival_minute,
            ),
        ),
        transfers=(),
        requested_start_minute=current_minute,
    )


def _transfer_candidate_from_real_data(
    *,
    first_route_id: str,
    second_route_id: str,
    origin_node_id: str,
    first_transfer_node_id: str,
    second_transfer_node_id: str,
    destination_node_id: str,
    first_board_minute: int,
    first_arrival_minute: int,
    second_board_minute: int,
    second_gap: int,
    transfer_arrivals: tuple[TagoArrival, ...],
    average_minutes_per_stop: float,
    walking_minutes: int,
    minimum_buffer_minutes: int,
    current_minute: int,
    index: int,
) -> RouteCandidate:
    second_arrival_minute = second_board_minute + _estimate_travel_minutes(
        second_gap, average_minutes_per_stop
    )
    core_transfer_arrivals = tuple(
        arrival.to_core_arrival(
            station_id=second_transfer_node_id,
            prefer_route_no=False,
        )
        for arrival in transfer_arrivals
    )
    return RouteCandidate(
        id=f"tago-transfer-{index + 1}-{first_route_id}-{second_route_id}",
        segments=(
            RouteSegment(
                route_id=first_route_id,
                from_station_id=origin_node_id,
                to_station_id=first_transfer_node_id,
                departure_minute=first_board_minute,
                arrival_minute=first_arrival_minute,
            ),
            RouteSegment(
                route_id=second_route_id,
                from_station_id=second_transfer_node_id,
                to_station_id=destination_node_id,
                departure_minute=second_board_minute,
                arrival_minute=second_arrival_minute,
            ),
        ),
        transfers=(
            Transfer(
                from_station_id=first_transfer_node_id,
                to_station_id=second_transfer_node_id,
                arrival_minute=first_arrival_minute,
                walking_minutes=walking_minutes,
                minimum_buffer_minutes=minimum_buffer_minutes,
                candidate_arrivals=core_transfer_arrivals,
                target_route_id=second_route_id,
            ),
        ),
        requested_start_minute=current_minute,
    )


def _find_transfer_specs(
    *,
    stop_map: dict[str, tuple[TagoRouteStop, ...]],
    origin_node_id: str,
    destination_node_id: str,
    limit: int,
    base_walking_minutes: int,
    max_walking_transfer_m: float,
    walking_meters_per_minute: float,
) -> tuple[_TransferSpec, ...]:
    if limit == 0:
        return ()

    specs: list[_TransferSpec] = []
    for first_route_id, first_stops in stop_map.items():
        for second_route_id, second_stops in stop_map.items():
            if first_route_id == second_route_id:
                continue
            specs.extend(
                _transfer_specs_for_pair(
                    first_route_id=first_route_id,
                    first_stops=first_stops,
                    second_route_id=second_route_id,
                    second_stops=second_stops,
                    origin_node_id=origin_node_id,
                    destination_node_id=destination_node_id,
                    base_walking_minutes=base_walking_minutes,
                    max_walking_transfer_m=max_walking_transfer_m,
                    walking_meters_per_minute=walking_meters_per_minute,
                )
            )

    unique_specs = tuple(dict.fromkeys(specs))
    return tuple(
        sorted(
            unique_specs,
            key=lambda spec: (
                spec.total_gap,
                spec.walking_minutes,
                spec.first_transfer_node_id,
                spec.second_transfer_node_id,
                spec.first_route_id,
            ),
        )[:limit]
    )


def _transfer_specs_for_pair(
    *,
    first_route_id: str,
    first_stops: tuple[TagoRouteStop, ...],
    second_route_id: str,
    second_stops: tuple[TagoRouteStop, ...],
    origin_node_id: str,
    destination_node_id: str,
    base_walking_minutes: int,
    max_walking_transfer_m: float,
    walking_meters_per_minute: float,
) -> tuple[_TransferSpec, ...]:
    first_pairs = _transfer_pairs_after_origin(
        first_stops,
        origin_node_id=origin_node_id,
        destination_node_id=destination_node_id,
    )
    second_pairs = _transfer_pairs_to_destination(
        second_stops,
        origin_node_id=origin_node_id,
        destination_node_id=destination_node_id,
    )
    specs: list[_TransferSpec] = []
    for first_pair in first_pairs:
        for second_pair in second_pairs:
            walk = _walking_transfer(
                first_pair.destination,
                second_pair.origin,
                base_walking_minutes=base_walking_minutes,
                max_walking_transfer_m=max_walking_transfer_m,
                walking_meters_per_minute=walking_meters_per_minute,
            )
            if walk is None:
                continue
            walking_minutes, walking_distance_m = walk
            specs.append(
                _TransferSpec(
                    first_route_id=first_route_id,
                    second_route_id=second_route_id,
                    first_transfer_node_id=first_pair.destination.node_id,
                    second_transfer_node_id=second_pair.origin.node_id,
                    first_gap=first_pair.gap,
                    second_gap=second_pair.gap,
                    walking_minutes=walking_minutes,
                    walking_distance_m=walking_distance_m,
                )
            )
    return tuple(specs)


def _find_best_forward_pair(
    stops: tuple[TagoRouteStop, ...],
    origin_node_id: str,
    destination_node_id: str,
) -> _ForwardPair | None:
    pairs = _find_forward_pairs(stops, origin_node_id, destination_node_id)
    if not pairs:
        return None
    return min(pairs, key=lambda pair: pair.gap)


def _find_forward_pairs(
    stops: tuple[TagoRouteStop, ...],
    origin_node_id: str,
    destination_node_id: str,
) -> tuple[_ForwardPair, ...]:
    pairs: list[_ForwardPair] = []
    for direction_stops in _split_by_direction(stops):
        origin_stops = [stop for stop in direction_stops if stop.node_id == origin_node_id]
        destination_stops = [
            stop for stop in direction_stops if stop.node_id == destination_node_id
        ]
        for origin_stop in origin_stops:
            for destination_stop in destination_stops:
                if origin_stop.order < destination_stop.order:
                    pairs.append(_ForwardPair(origin_stop, destination_stop))
    return tuple(pairs)


def _transfer_pairs_after_origin(
    stops: tuple[TagoRouteStop, ...],
    *,
    origin_node_id: str,
    destination_node_id: str,
) -> tuple[_ForwardPair, ...]:
    pairs: list[_ForwardPair] = []
    excluded = {origin_node_id, destination_node_id}
    for direction_stops in _split_by_direction(stops):
        origin_stops = [stop for stop in direction_stops if stop.node_id == origin_node_id]
        for origin_stop in origin_stops:
            for stop in direction_stops:
                if stop.node_id in excluded:
                    continue
                if origin_stop.order < stop.order:
                    pairs.append(_ForwardPair(origin_stop, stop))
    return tuple(sorted(pairs, key=lambda pair: pair.gap))


def _transfer_pairs_to_destination(
    stops: tuple[TagoRouteStop, ...],
    *,
    origin_node_id: str,
    destination_node_id: str,
) -> tuple[_ForwardPair, ...]:
    pairs: list[_ForwardPair] = []
    excluded = {origin_node_id, destination_node_id}
    for direction_stops in _split_by_direction(stops):
        destination_stops = [
            stop for stop in direction_stops if stop.node_id == destination_node_id
        ]
        for destination_stop in destination_stops:
            for stop in direction_stops:
                if stop.node_id in excluded:
                    continue
                if stop.order < destination_stop.order:
                    pairs.append(_ForwardPair(stop, destination_stop))
    return tuple(sorted(pairs, key=lambda pair: pair.gap))


def _walking_transfer(
    first_stop: TagoRouteStop,
    second_stop: TagoRouteStop,
    *,
    base_walking_minutes: int,
    max_walking_transfer_m: float,
    walking_meters_per_minute: float,
) -> tuple[int, float | None] | None:
    if first_stop.node_id == second_stop.node_id:
        return base_walking_minutes, 0.0
    distance_m = _stop_distance_m(first_stop, second_stop)
    if distance_m is None or distance_m > max_walking_transfer_m:
        return None
    walking_minutes = max(base_walking_minutes, ceil(distance_m / walking_meters_per_minute))
    return walking_minutes, round(distance_m, 1)


def _stop_distance_m(first_stop: TagoRouteStop, second_stop: TagoRouteStop) -> float | None:
    if first_stop.lat is None or first_stop.lon is None:
        return None
    if second_stop.lat is None or second_stop.lon is None:
        return None
    return _haversine_m(first_stop.lat, first_stop.lon, second_stop.lat, second_stop.lon)


def _haversine_m(first_lat: float, first_lon: float, second_lat: float, second_lon: float) -> float:
    earth_radius_m = 6_371_000
    dlat = radians(second_lat - first_lat)
    dlon = radians(second_lon - first_lon)
    lat1 = radians(first_lat)
    lat2 = radians(second_lat)
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * earth_radius_m * asin(sqrt(a))


def _split_by_direction(
    stops: tuple[TagoRouteStop, ...],
) -> tuple[tuple[TagoRouteStop, ...], ...]:
    coded_groups: dict[str, list[TagoRouteStop]] = {}
    uncoded: list[TagoRouteStop] = []
    for stop in stops:
        if stop.updown_code:
            coded_groups.setdefault(stop.updown_code, []).append(stop)
        else:
            uncoded.append(stop)

    groups = [
        tuple(sorted(group, key=lambda stop: stop.order))
        for group in coded_groups.values()
        if group
    ]
    groups.extend(_split_uncoded_direction_runs(uncoded))
    return tuple(group for group in groups if group)


def _split_uncoded_direction_runs(
    stops: list[TagoRouteStop],
) -> tuple[tuple[TagoRouteStop, ...], ...]:
    if not stops:
        return ()
    ordered = stops
    groups: list[list[TagoRouteStop]] = []
    current: list[TagoRouteStop] = []
    last_order: int | None = None
    for stop in ordered:
        if last_order is not None and stop.order <= last_order:
            groups.append(current)
            current = []
        current.append(stop)
        last_order = stop.order
    if current:
        groups.append(current)
    return tuple(tuple(group) for group in groups if group)


def _select_relevant_arrival(
    arrivals: tuple[TagoArrival, ...],
    route_id: str,
    earliest_minute: int | None = None,
) -> TagoArrival | None:
    minimum = earliest_minute if earliest_minute is not None else 0
    matches = [
        arrival
        for arrival in arrivals
        if arrival.arrival_minute >= minimum
        and (arrival.route_id == route_id or arrival.route_no == route_id)
    ]
    return min(matches, key=lambda arrival: arrival.arrival_minute) if matches else None


def _estimate_travel_minutes(stop_gap: int, average_minutes_per_stop: float) -> int:
    return max(1, ceil(stop_gap * average_minutes_per_stop))


def _fetch_tago_items(
    *,
    endpoint: str,
    params: dict[str, object],
    timeout_seconds: float,
    service_key: str | None = None,
    fetch_all_pages: bool = True,
) -> tuple[dict[str, Any], ...]:
    page_no = int(params.get("pageNo", 1))
    num_of_rows = int(params.get("numOfRows", 10))
    if page_no < 1:
        raise ValueError("page_no must be greater than or equal to 1")
    if num_of_rows < 1:
        raise ValueError("num_of_rows must be greater than or equal to 1")

    key = service_key or require_tago_config().service_key
    assert key is not None

    all_items: list[dict[str, Any]] = []
    current_page = page_no
    max_pages = 50
    for _ in range(max_pages):
        budget = _ACTIVE_CALL_BUDGET.get()
        if budget is not None:
            budget.consume()
        page_params = {**params, "pageNo": current_page, "numOfRows": num_of_rows}
        url = _build_tago_url(endpoint=endpoint, service_key=key, params=page_params)
        raw_body = _http_get_text(url, timeout_seconds=timeout_seconds)
        payload = _decode_tago_response(raw_body)
        _raise_for_tago_error(payload)
        all_items.extend(_extract_items(payload))
        if not fetch_all_pages:
            break

        paging = _extract_paging(payload)
        if paging is None:
            break
        total_count, rows, returned_page = paging
        fetched_rows = returned_page * rows
        if total_count <= fetched_rows or rows <= 0:
            break
        current_page = returned_page + 1
    else:
        raise TagoApiError("TAGO pagination exceeded safety limit")

    return tuple(all_items)



T = TypeVar("T")


def _convert_tago_items(
    items: tuple[dict[str, Any], ...],
    converter: Callable[[dict[str, Any]], T],
    *,
    strict_items: bool,
) -> tuple[T, ...]:
    converted: list[T] = []
    for item in items:
        try:
            converted.append(converter(item))
        except TagoApiError:
            if strict_items:
                raise
            continue
    return tuple(converted)

def _extract_paging(payload: dict[str, Any]) -> tuple[int, int, int] | None:
    body = _response_body(payload)
    total_count = _coerce_int(body.get("totalCount"))
    rows = _coerce_int(body.get("numOfRows"))
    page_no = _coerce_int(body.get("pageNo"))
    if total_count is None or rows is None or page_no is None:
        return None
    return total_count, rows, page_no


def _response_body(payload: dict[str, Any]) -> dict[str, Any]:
    response = payload.get("response", {}) if isinstance(payload, dict) else {}
    body = response.get("body", {}) if isinstance(response, dict) else {}
    return body if isinstance(body, dict) else {}


def _coerce_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_arrival_url(
    *,
    endpoint: str,
    service_key: str,
    city_code: str,
    node_id: str,
    page_no: int,
    num_of_rows: int,
) -> str:
    return _build_tago_url(
        endpoint=endpoint,
        service_key=service_key,
        params={
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            "_type": "json",
            "cityCode": city_code,
            "nodeId": node_id,
        },
    )


def _build_tago_url(*, endpoint: str, service_key: str, params: dict[str, object]) -> str:
    # Public Data Portal keys are sometimes already URL-encoded. Keep '%' unescaped
    # so both encoded and decoded keys can be used without accidental double encoding.
    service_key_part = "serviceKey=" + quote(service_key, safe="%")
    query = urlencode(params)
    return f"{endpoint}?{service_key_part}&{query}"


def _http_get_text(url: str, *, timeout_seconds: float) -> str:
    try:
        with urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        raise TagoApiError(f"TAGO HTTP error: {exc.code}") from exc
    except URLError as exc:
        raise TagoApiError(f"TAGO network error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise TagoApiError("TAGO request timed out") from exc


def _decode_tago_response(raw_body: str) -> dict[str, Any]:
    stripped = raw_body.strip()
    if not stripped:
        raise TagoApiError("TAGO returned an empty response")
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise TagoApiError("TAGO returned invalid JSON") from exc
    return _xml_to_response_dict(stripped)


def _xml_to_response_dict(raw_xml: str) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError as exc:
        raise TagoApiError("TAGO returned neither valid JSON nor valid XML") from exc

    common_error = root.find(".//cmmMsgHeader")
    if common_error is not None:
        error = _children_to_dict(common_error)
        return {
            "response": {
                "header": {
                    "resultCode": error.get("returnReasonCode", "GATEWAY"),
                    "resultMsg": (
                        error.get("returnAuthMsg")
                        or error.get("errMsg")
                        or "TAGO gateway error"
                    ),
                },
                "body": {},
            }
        }

    header = root.find("header")
    body = root.find("body")
    items_node = body.find("items") if body is not None else None
    items = []
    if items_node is not None:
        for item_node in items_node.findall("item"):
            items.append({child.tag: child.text for child in list(item_node)})

    return {
        "response": {
            "header": _children_to_dict(header),
            "body": {
                **_children_to_dict(body, exclude={"items"}),
                "items": {"item": items},
            },
        }
    }


def _children_to_dict(
    node: ElementTree.Element | None,
    exclude: set[str] | None = None,
) -> dict[str, Any]:
    if node is None:
        return {}
    skipped = exclude or set()
    return {child.tag: child.text for child in list(node) if child.tag not in skipped}


def _raise_for_tago_error(payload: dict[str, Any]) -> None:
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, dict):
        raise TagoApiError("TAGO response does not contain a response object")
    header = response.get("header")
    if not isinstance(header, dict):
        raise TagoApiError("TAGO response does not contain a header")
    result_code = str(header.get("resultCode", "")).strip()
    result_message = str(header.get("resultMsg", "")).strip()
    if result_code and result_code != "00":
        raise TagoApiError(f"TAGO API error {result_code}: {result_message or 'unknown error'}")


def _extract_items(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    response = payload.get("response", {})
    body = response.get("body", {}) if isinstance(response, dict) else {}
    items = body.get("items", {}) if isinstance(body, dict) else {}
    if items in (None, ""):
        return ()
    item = items.get("item") if isinstance(items, dict) else items
    if item in (None, ""):
        return ()
    if isinstance(item, list):
        return tuple(row for row in item if isinstance(row, dict))
    if isinstance(item, dict):
        return (item,)
    return ()


def _item_to_tago_arrival(
    item: dict[str, Any],
    *,
    fallback_node_id: str,
    current_minute: int,
) -> TagoArrival:
    arrival_seconds = _read_int(item, "arrtime")
    if arrival_seconds is None:
        raise TagoApiError("TAGO arrival item is missing arrtime")
    if arrival_seconds < 0:
        raise TagoApiError("TAGO arrival item has negative arrtime")
    arrival_minute = current_minute + ceil(arrival_seconds / 60)
    route_id = _read_text(item, "routeid") or _read_text(item, "routeno")
    if not route_id:
        raise TagoApiError("TAGO arrival item is missing routeid/routeno")

    return TagoArrival(
        node_id=_read_text(item, "nodeid") or fallback_node_id,
        node_name=_read_text(item, "nodenm"),
        route_id=route_id,
        route_no=_read_text(item, "routeno"),
        route_type=_read_text(item, "routetp"),
        arrival_seconds=arrival_seconds,
        arrival_minute=arrival_minute,
        previous_station_count=_read_int(item, "arrprevstationcnt"),
        vehicle_type=_read_text(item, "vehicletp"),
    )


def _item_to_tago_station(item: dict[str, Any]) -> TagoStation:
    node_id = _read_text(item, "nodeid")
    node_name = _read_text(item, "nodenm")
    city_code = _read_text(item, "citycode")
    if not node_id or not node_name or not city_code:
        raise TagoApiError("TAGO station item is missing citycode/nodeid/nodenm")
    lat = _read_required_float(item, "gpslati")
    lon = _read_required_float(item, "gpslong")
    if not -90 <= lat <= 90:
        raise TagoApiError("TAGO station item has invalid gpslati")
    if not -180 <= lon <= 180:
        raise TagoApiError("TAGO station item has invalid gpslong")
    return TagoStation(
        city_code=city_code,
        node_id=node_id,
        node_name=node_name,
        lat=lat,
        lon=lon,
    )


def _item_to_station_route(item: dict[str, Any]) -> TagoStationRoute:
    route_id = _read_text(item, "routeid") or _read_text(item, "routeId")
    if not route_id:
        raise TagoApiError("TAGO station-route item is missing route ID")
    return TagoStationRoute(
        route_id=route_id,
        route_no=_read_text(item, "routeno") or _read_text(item, "routeNo"),
    )


def _item_to_subway_station(item: dict[str, Any]) -> TagoSubwayStation:
    station_id = (
        _read_text(item, "subwaystationid")
        or _read_text(item, "subwayStationId")
        or _read_text(item, "stationid")
    )
    station_name = (
        _read_text(item, "subwaystationnm")
        or _read_text(item, "subwayStationName")
        or _read_text(item, "stationnm")
    )
    route_name = (
        _read_text(item, "subwayroutename")
        or _read_text(item, "subwayRouteName")
        or _read_text(item, "routename")
        or _read_text(item, "routeno")
    )
    route_id = (
        _read_text(item, "subwayrouteid")
        or _read_text(item, "subwayRouteId")
        or _read_text(item, "routeid")
        # The current TAGO response omits a separate route ID and exposes
        # only subwayRouteName (for example, "2호선").  It is stable enough
        # to serve as the graph key when no opaque ID is provided.
        or route_name
    )
    if not station_id or not station_name or not route_id:
        raise TagoApiError("TAGO subway-station item is missing station or route data")
    return TagoSubwayStation(
        station_id=station_id,
        station_name=station_name,
        route_id=route_id,
        route_name=route_name or route_id,
    )


def _normalize_subway_keyword(value: str) -> str:
    keyword = value.strip().split("(", 1)[0].strip()
    station_tokens = [token for token in keyword.split() if token.endswith("역")]
    if station_tokens:
        keyword = station_tokens[-1]
    for suffix in (" 지하철역", " 도시철도역", "역"):
        if keyword.endswith(suffix):
            keyword = keyword[: -len(suffix)].strip()
            break
    return keyword


def _item_to_tago_route_stop(item: dict[str, Any], *, city_code: str) -> TagoRouteStop:
    route_id = _read_text(item, "routeid")
    node_id = _read_text(item, "nodeid")
    node_name = _read_text(item, "nodenm")
    order = _read_int(item, "nodeord") or _read_int(item, "ord") or _read_int(item, "seq")
    if not route_id or not node_id or not node_name or order is None:
        raise TagoApiError("TAGO route stop item is missing routeid/nodeid/nodenm/nodeord")
    lat = _read_float(item, "gpslati", default=None)
    lon = _read_float(item, "gpslong", default=None)
    if lat is not None and not -90 <= lat <= 90:
        raise TagoApiError("TAGO route stop item has invalid gpslati")
    if lon is not None and not -180 <= lon <= 180:
        raise TagoApiError("TAGO route stop item has invalid gpslong")
    return TagoRouteStop(
        city_code=_read_text(item, "citycode") or city_code,
        route_id=route_id,
        route_no=_read_text(item, "routeno"),
        node_id=node_id,
        node_name=node_name,
        order=order,
        lat=lat,
        lon=lon,
        updown_code=_read_text(item, "updowncd"),
    )


def _read_text(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_int(item: dict[str, Any], key: str, default: int | None = None) -> int | None:
    value = item.get(key)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TagoApiError(f"TAGO item has invalid integer field: {key}") from exc


def _read_float(item: dict[str, Any], key: str, default: float | None = 0.0) -> float | None:
    value = item.get(key)
    if value in (None, ""):
        if default is None:
            return default
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TagoApiError(f"TAGO item has invalid float field: {key}") from exc


def _read_required_float(item: dict[str, Any], key: str) -> float:
    value = _read_float(item, key, default=None)
    if value is None:
        raise TagoApiError(f"TAGO item is missing required float field: {key}")
    return value


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _read_dotenv_value(key: str) -> str | None:
    for path in _candidate_dotenv_paths():
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() != key:
                continue
            return value.strip().strip('"').strip("'") or None
    return None


def _candidate_dotenv_paths() -> tuple[Path, ...]:
    explicit_path = os.getenv("TRANSITGUARD_ENV_FILE")
    if explicit_path:
        return (Path(explicit_path).expanduser().resolve(),)

    current = Path.cwd().resolve()
    project_root = Path(__file__).resolve().parents[3]
    return tuple(dict.fromkeys((current / ".env", project_root / ".env")))
