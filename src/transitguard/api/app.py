from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, StringConstraints

from transitguard import __version__
from transitguard.adapters.tago import (
    TagoApiError,
    TagoRouteBuildError,
    build_tago_route_candidates,
    discover_subway_candidates,
    discover_tago_route_candidates,
    discover_tago_topology_candidates,
    fetch_nearby_stations,
    fetch_route_stops,
    fetch_station_arrivals,
    fetch_station_routes,
    load_tago_config,
    read_config_value,
    use_tago_call_budget,
)
from transitguard.core.demo_graph import (
    build_demo_route_candidates,
    current_minute_of_day,
    edge_to_dict,
    find_demo_station,
    generate_demo_arrivals,
    get_demo_edges,
    get_demo_stations,
    graph_overview,
    search_demo_stations,
    seoul_timezone,
    station_to_dict,
)
from transitguard.core.models import (
    Arrival,
    Coordinate,
    RouteCandidate,
    RouteEvaluation,
    RouteSegment,
    Station,
    Transfer,
    TransferStatus,
)
from transitguard.core.ranking import rank_routes
from transitguard.core.station_matcher import find_nearby_stations, match_route_endpoints

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Minute = Annotated[int, Field(ge=0)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Radius = Annotated[float, Field(ge=0)]


def _allowed_cors_origins() -> list[str]:
    raw_value, _ = read_config_value("TRANSITGUARD_CORS_ORIGINS")
    raw_value = raw_value or "*"
    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    return origins or ["*"]


app = FastAPI(title="TransitGuard", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class CoordinatePayload(BaseModel):
    lat: Latitude
    lon: Longitude


class StationPayload(BaseModel):
    id: NonEmptyText
    name: NonEmptyText
    lat: Latitude
    lon: Longitude
    opposite_id: str | None = None


class EndpointMatchPayload(BaseModel):
    origin: CoordinatePayload
    destination: CoordinatePayload
    stations: list[StationPayload] = Field(min_length=1)
    radius_m: Radius = 700


class ArrivalPayload(BaseModel):
    station_id: NonEmptyText
    route_id: NonEmptyText
    arrival_minute: Minute


class TransferPayload(BaseModel):
    from_station_id: NonEmptyText
    to_station_id: NonEmptyText
    arrival_minute: Minute
    walking_minutes: Minute
    minimum_buffer_minutes: Minute
    candidate_arrivals: list[ArrivalPayload] = Field(default_factory=list)
    target_route_id: str | None = None


class SegmentPayload(BaseModel):
    route_id: NonEmptyText
    from_station_id: NonEmptyText
    to_station_id: NonEmptyText
    departure_minute: Minute
    arrival_minute: Minute


class RoutePayload(BaseModel):
    id: NonEmptyText
    segments: list[SegmentPayload] = Field(min_length=1)
    transfers: list[TransferPayload] = Field(default_factory=list)
    requested_start_minute: Minute | None = None


class RankPayload(BaseModel):
    routes: list[RoutePayload] = Field(min_length=1)


class TagoArrivalSourcePayload(BaseModel):
    station_id: NonEmptyText
    city_code: NonEmptyText
    node_id: NonEmptyText
    route_key: Literal["route_no", "route_id"] = "route_no"
    page_no: Annotated[int, Field(ge=1)] = 1
    num_of_rows: Annotated[int, Field(ge=1, le=100)] = 50
    fetch_all_pages: bool = False


class AssessRoutesPayload(BaseModel):
    routes: list[RoutePayload] = Field(min_length=1)
    current_minute: Minute | None = None
    tago_arrival_sources: list[TagoArrivalSourcePayload] = Field(default_factory=list)


class QuickAssessPayload(BaseModel):
    id: NonEmptyText = "quick-candidate"
    requested_start_minute: Minute
    origin_station_id: NonEmptyText = "A"
    transfer_station_id: NonEmptyText = "B"
    destination_station_id: NonEmptyText = "C"
    first_route_id: NonEmptyText
    second_route_id: NonEmptyText
    first_departure_minute: Minute
    transfer_arrival_minute: Minute
    second_departure_minute: Minute
    final_arrival_minute: Minute
    walking_minutes: Minute = 4
    minimum_buffer_minutes: Minute = 3
    next_vehicle_arrival_minutes: list[Minute] = Field(min_length=1)


class GenerateGraphPayload(BaseModel):
    origin: NonEmptyText = "대구역"
    destination: NonEmptyText = "동대구역건너"
    current_minute: Minute | None = None
    include_graph: bool = True
    arrival_source: Literal["demo", "tago"] = "demo"
    tago_city_code: str | None = None
    tago_node_id: str | None = None
    tago_transfer_station_id: str = "S3"


class GenerateTagoRoutePayload(BaseModel):
    city_code: NonEmptyText
    origin_node_id: NonEmptyText
    destination_node_id: NonEmptyText
    route_ids: list[NonEmptyText] = Field(min_length=1)
    current_minute: Minute | None = None
    average_minutes_per_stop: Annotated[float, Field(gt=0)] = 2.0
    walking_minutes: Minute = 4
    minimum_buffer_minutes: Minute = 3
    max_transfer_candidates: Annotated[int, Field(ge=0, le=20)] = 5
    max_walking_transfer_m: Annotated[float, Field(ge=0, le=1000)] = 300.0
    walking_meters_per_minute: Annotated[float, Field(gt=0, le=200)] = 80.0


class DiscoverTagoRoutePayload(BaseModel):
    city_code: NonEmptyText
    origin_node_id: NonEmptyText
    destination_node_id: NonEmptyText
    current_minute: Minute | None = None
    average_minutes_per_stop: Annotated[float, Field(gt=0)] = 2.0
    walking_minutes: Minute = 4
    minimum_buffer_minutes: Minute = 3
    max_origin_routes: Annotated[int, Field(ge=1, le=20)] = 16
    max_transfer_stops_per_route: Annotated[int, Field(ge=1, le=30)] = 8
    max_transfer_routes_per_stop: Annotated[int, Field(ge=1, le=20)] = 6
    max_walking_transfer_m: Annotated[float, Field(ge=0, le=1000)] = 300.0
    walking_meters_per_minute: Annotated[float, Field(gt=0, le=200)] = 80.0
    max_walking_transfer_stations: Annotated[int, Field(ge=1, le=20)] = 6


class PlanTagoRoutePayload(BaseModel):
    origin: CoordinatePayload
    destination: CoordinatePayload
    origin_name: str | None = None
    destination_name: str | None = None
    origin_subway_name: str | None = None
    destination_subway_name: str | None = None
    origin_region: Literal["auto", "daegu", "gyeongsan"] = "auto"
    destination_region: Literal["auto", "daegu", "gyeongsan"] = "auto"
    city_code: NonEmptyText | None = None
    city_codes: list[NonEmptyText] = Field(default_factory=list, max_length=4)
    current_minute: Minute | None = None
    nearby_num_of_rows: Annotated[int, Field(ge=1, le=100)] = 20
    max_origin_stations: Annotated[int, Field(ge=1, le=5)] = 5
    max_destination_stations: Annotated[int, Field(ge=1, le=5)] = 5
    max_station_pairs: Annotated[int, Field(ge=1, le=12)] = 8
    average_minutes_per_stop: Annotated[float, Field(gt=0)] = 2.0
    walking_minutes: Minute = 4
    minimum_buffer_minutes: Minute = 3
    max_origin_routes: Annotated[int, Field(ge=1, le=20)] = 16
    max_transfer_stops_per_route: Annotated[int, Field(ge=1, le=20)] = 4
    max_transfer_routes_per_stop: Annotated[int, Field(ge=1, le=12)] = 3
    max_walking_transfer_m: Annotated[float, Field(ge=0, le=1000)] = 300.0
    walking_meters_per_minute: Annotated[float, Field(gt=0, le=200)] = 80.0
    max_walking_transfer_stations: Annotated[int, Field(ge=1, le=12)] = 3
    max_candidates: Annotated[int, Field(ge=1, le=10)] = 3
    api_call_budget: Annotated[int, Field(ge=10, le=70)] = 60
    use_live_arrival_discovery: bool = True


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/setup/check")
def setup_check() -> dict[str, object]:
    config = load_tago_config()
    tz = seoul_timezone()
    tago_hint = (
        "TAGO_SERVICE_KEY is configured. Live TAGO endpoints can be used."
        if config.available
        else "TAGO_SERVICE_KEY is empty. Demo endpoints work, but live TAGO data needs .env setup."
    )
    return {
        "status": "ok",
        "version": __version__,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "timezone": {
            "name": getattr(tz, "key", str(tz)),
            "current_minute_seoul": current_minute_of_day(),
            "windows_safe": True,
        },
        "tago": {
            "configured": config.available,
            "service_key_source": config.source,
            "hint": tago_hint,
        },
        "kakao_map": _kakao_map_status(),
        "links": {
            "api_docs": "http://127.0.0.1:8000/docs",
            "web_demo": "http://127.0.0.1:8080",
        },
        "windows_commands": [
            "setup_windows.bat",
            "start_all_windows.bat",
            "run_tests.bat",
        ],
    }


@app.get("/api/kakao/config")
def kakao_config() -> dict[str, object]:
    key, source = read_config_value("KAKAO_MAP_JAVASCRIPT_KEY")
    configured = bool(key and key.strip())
    if not configured:
        return {
            "configured": False,
            "app_key": None,
            "source": source,
            "message": (
                "KAKAO_MAP_JAVASCRIPT_KEY is empty. The web demo still works, "
                "but Kakao Map visualization is disabled until the JavaScript key is set."
            ),
        }
    return {
        "configured": True,
        "app_key": key.strip(),
        "source": source,
        "sdk_url": "https://dapi.kakao.com/v2/maps/sdk.js",
        "libraries": ["services"],
        "message": (
            "Kakao Map JavaScript key is configured. Make sure the web demo origin "
            "http://127.0.0.1:8080 is registered in Kakao Developers."
        ),
    }

@app.get("/api/tago/status")
def tago_status() -> dict[str, bool]:
    config = load_tago_config()
    return {"configured": config.available}


@app.get("/api/tago/diagnostics")
def tago_diagnostics() -> dict[str, object]:
    config = load_tago_config()
    return {
        "configured": config.available,
        "service_key_source": config.source,
        "network_probe": "available_via_/api/tago/arrivals",
        "arrival_endpoint": "ArvlInfoInqireService/getSttnAcctoArvlPrearngeInfoList",
        "message": (
            "TAGO_SERVICE_KEY is configured. Use /api/tago/arrivals with city_code and node_id "
            "to fetch live station arrivals."
            if config.available
            else (
                "TAGO_SERVICE_KEY is not configured. Demo mode still works. "
                "To use live TAGO data, copy .env.example to .env and paste "
                "your public-data service key."
            )
        ),
        "checked_at": _utc_now(),
    }


@app.get("/api/tago/arrivals")
def tago_arrivals(
    city_code: Annotated[str, Query(min_length=1)],
    node_id: Annotated[str, Query(min_length=1)],
    current_minute: Annotated[int | None, Query(ge=0)] = None,
    page_no: Annotated[int, Query(ge=1)] = 1,
    num_of_rows: Annotated[int, Query(ge=1, le=100)] = 10,
    fetch_all_pages: bool = False,
) -> dict[str, object]:
    base_minute = current_minute if current_minute is not None else current_minute_of_day()
    arrivals = _fetch_tago_or_http_error(
        city_code=city_code,
        node_id=node_id,
        current_minute=base_minute,
        page_no=page_no,
        num_of_rows=num_of_rows,
        fetch_all_pages=fetch_all_pages,
    )
    return {
        "source": "tago",
        "city_code": city_code,
        "node_id": node_id,
        "current_minute": base_minute,
        "fetched_at": _utc_now(),
        "fetch_all_pages": fetch_all_pages,
        "arrivals": [arrival.to_dict() for arrival in arrivals],
    }


@app.get("/api/tago/stations/nearby")
def tago_nearby_stations(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    page_no: Annotated[int, Query(ge=1)] = 1,
    num_of_rows: Annotated[int, Query(ge=1, le=100)] = 20,
    fetch_all_pages: bool = False,
) -> dict[str, object]:
    try:
        stations = fetch_nearby_stations(
            lat=lat,
            lon=lon,
            page_no=page_no,
            num_of_rows=num_of_rows,
            fetch_all_pages=fetch_all_pages,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TagoApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "source": "tago",
        "lat": lat,
        "lon": lon,
        "fetched_at": _utc_now(),
        "fetch_all_pages": fetch_all_pages,
        "stations": [station.to_dict() for station in stations],
    }


@app.get("/api/tago/route-stops")
def tago_route_stops(
    city_code: Annotated[str, Query(min_length=1)],
    route_id: Annotated[str, Query(min_length=1)],
    page_no: Annotated[int, Query(ge=1)] = 1,
    num_of_rows: Annotated[int, Query(ge=1, le=500)] = 300,
    fetch_all_pages: bool = True,
) -> dict[str, object]:
    try:
        stops = fetch_route_stops(
            city_code,
            route_id,
            page_no=page_no,
            num_of_rows=num_of_rows,
            fetch_all_pages=fetch_all_pages,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TagoApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "source": "tago",
        "city_code": city_code,
        "route_id": route_id,
        "fetched_at": _utc_now(),
        "fetch_all_pages": fetch_all_pages,
        "stops": [stop.to_dict() for stop in stops],
    }


@app.get("/api/graph/overview")
def api_graph_overview() -> dict[str, object]:
    overview = graph_overview()
    overview["generated_at"] = _utc_now()
    return overview


@app.get("/api/graph/stations/search")
def api_station_search(
    q: str = "",
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_m: Annotated[float, Query(ge=0)] = 700,
) -> dict[str, object]:
    stations = list(get_demo_stations())
    if (lat is None) != (lon is None):
        raise HTTPException(status_code=422, detail="lat and lon must be provided together")

    if lat is not None and lon is not None:
        matches = find_nearby_stations(Coordinate(lat, lon), stations, radius_m=radius_m)
        if q.strip():
            normalized = q.strip().lower()
            matches = [
                match
                for match in matches
                if (
                    normalized in match.station.id.lower()
                    or normalized in match.station.name.lower()
                )
            ]
        return {
            "stations": [
                {
                    **station_to_dict(match.station),
                    "distance_m": round(match.distance_m, 1),
                    "is_opposite": match.is_opposite,
                }
                for match in matches
            ]
        }

    return {"stations": [station_to_dict(station) for station in search_demo_stations(q)]}


@app.get("/api/arrivals/refresh")
def refresh_arrivals(
    station_id: str | None = None,
    current_minute: Annotated[int | None, Query(ge=0)] = None,
    source: Literal["demo", "tago"] = "demo",
    city_code: str | None = None,
    node_id: str | None = None,
    page_no: Annotated[int, Query(ge=1)] = 1,
    num_of_rows: Annotated[int, Query(ge=1, le=100)] = 10,
    fetch_all_pages: bool = False,
) -> dict[str, object]:
    base_minute = current_minute if current_minute is not None else current_minute_of_day()
    if source == "tago":
        if not city_code or not node_id:
            raise HTTPException(
                status_code=422,
                detail="city_code and node_id are required when source=tago",
            )
        tago_items = _fetch_tago_or_http_error(
            city_code=city_code,
            node_id=node_id,
            current_minute=base_minute,
            page_no=page_no,
            num_of_rows=num_of_rows,
            fetch_all_pages=fetch_all_pages,
        )
        core_station_id = station_id or node_id
        return {
            "station_id": core_station_id,
            "source": "tago",
            "city_code": city_code,
            "node_id": node_id,
            "refreshed_at": _utc_now(),
            "fetch_all_pages": fetch_all_pages,
            "arrivals": [arrival.to_dict() for arrival in tago_items],
            "core_arrivals": [
                _arrival_to_dict(arrival.to_core_arrival(station_id=core_station_id))
                for arrival in tago_items
            ],
        }

    try:
        demo_station_id = station_id or "S3"
        arrivals = generate_demo_arrivals(base_minute, demo_station_id)
    except ValueError as exc:
        status_code = 404 if "station not found" in str(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return {
        "station_id": demo_station_id,
        "source": "demo",
        "refreshed_at": _utc_now(),
        "arrivals": [_arrival_to_dict(arrival) for arrival in arrivals],
    }


@app.post("/api/stations/match")
def match_stations(payload: EndpointMatchPayload) -> dict[str, list[dict[str, object]]]:
    try:
        stations = [
            Station(
                id=station.id,
                name=station.name,
                coordinate=Coordinate(station.lat, station.lon),
                opposite_id=station.opposite_id,
            )
            for station in payload.stations
        ]
        result = match_route_endpoints(
            origin=Coordinate(payload.origin.lat, payload.origin.lon),
            destination=Coordinate(payload.destination.lat, payload.destination.lon),
            stations=stations,
            radius_m=payload.radius_m,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        key: [
            {
                "id": match.station.id,
                "name": match.station.name,
                "distance_m": round(match.distance_m, 1),
                "is_opposite": match.is_opposite,
            }
            for match in matches
        ]
        for key, matches in result.items()
    }


@app.post("/api/routes/rank")
def rank_route_payload(payload: RankPayload) -> dict[str, list[dict[str, object]]]:
    try:
        routes = [_to_route_candidate(route) for route in payload.routes]
        ranked = rank_routes(routes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"routes": [_route_evaluation_to_dict(result) for result in ranked]}


@app.post("/api/routes/assess")
def assess_existing_routes(payload: AssessRoutesPayload) -> dict[str, object]:
    base_minute = payload.current_minute
    if base_minute is None:
        base_minute = current_minute_of_day()

    try:
        live_arrivals, live_sources = _load_live_arrival_sources(
            payload.tago_arrival_sources,
            base_minute,
        )
        routes = [
            _to_route_candidate(route, arrival_overrides=live_arrivals)
            for route in payload.routes
        ]
        ranked = rank_routes(routes)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=_friendly_runtime_error(exc)) from exc
    except TagoApiError as exc:
        raise HTTPException(status_code=502, detail=_friendly_tago_error(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    route_lookup = {route.id: route for route in routes}
    return {
        "source": "existing_route_assessment",
        "scope": (
            "TransitGuard assesses route candidates supplied by the user or another "
            "routing service. It does not claim to replace a full map router."
        ),
        "current_minute": base_minute,
        "generated_at": _utc_now(),
        "live_arrival_sources": live_sources,
        "routes": [
            {
                **_route_evaluation_to_dict(result),
                "segments": [
                    _segment_to_dict(segment)
                    for segment in route_lookup[result.route_id].segments
                ],
            }
            for result in ranked
        ],
    }




@app.get("/api/demo/quick-presets")
def quick_demo_presets() -> dict[str, object]:
    return {
        "message": (
            "These presets are classroom-friendly examples. They use fixed times and "
            "do not require TAGO or Kakao keys."
        ),
        "presets": _quick_demo_presets(),
        "station_locations": _demo_station_locations(),
    }

@app.post("/api/routes/assess/quick")
def assess_quick_transfer_route(payload: QuickAssessPayload) -> dict[str, object]:
    try:
        route = _quick_payload_to_route_candidate(payload)
        result = rank_routes([route])[0]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "source": "quick_transfer_assessment",
        "mode": "friendly_form",
        "message": (
            "This endpoint builds one two-leg transfer candidate from form-like inputs "
            "and evaluates transfer reliability."
        ),
        "route": {
            **_route_evaluation_to_dict(result),
            "segments": [_segment_to_dict(segment) for segment in route.segments],
        },
    }



@app.post("/api/routes/plan/tago")
def plan_tago_route_from_coordinates(payload: PlanTagoRoutePayload) -> dict[str, object]:
    base_minute = payload.current_minute
    if base_minute is None:
        base_minute = current_minute_of_day()

    budget_manager = use_tago_call_budget(payload.api_call_budget)
    call_budget = budget_manager.__enter__()
    try:
        origin_stations = _fetch_plan_nearby_stations(
            lat=payload.origin.lat,
            lon=payload.origin.lon,
            num_of_rows=payload.nearby_num_of_rows,
        )
        destination_stations = _fetch_plan_nearby_stations(
            lat=payload.destination.lat,
            lon=payload.destination.lon,
            num_of_rows=payload.nearby_num_of_rows,
        )
        selected_city_codes = _select_plan_city_codes(
            requested_city_code=payload.city_code,
            requested_city_codes=payload.city_codes,
            origin_stations=origin_stations,
            destination_stations=destination_stations,
            origin_region=payload.origin_region,
            destination_region=payload.destination_region,
        )
        selected_city_code = selected_city_codes[0]
        origin_candidates = _station_candidates_for_cities(
            origin_stations,
            selected_city_codes,
            payload.max_origin_stations,
        )
        destination_candidates = _station_candidates_for_cities(
            destination_stations,
            selected_city_codes,
            payload.max_destination_stations,
        )
        if not origin_candidates:
            raise TagoRouteBuildError("No nearby origin TAGO stations were found")
        if not destination_candidates:
            raise TagoRouteBuildError("No nearby destination TAGO stations were found")

        candidates: list[RouteCandidate] = []
        attempts: list[dict[str, object]] = []
        subway_origin_name = payload.origin_subway_name or payload.origin_name
        subway_destination_name = (
            payload.destination_subway_name or payload.destination_name
        )
        if subway_origin_name and subway_destination_name:
            subway_attempt: dict[str, object] = {
                "mode": "subway",
                "origin_name": subway_origin_name,
                "destination_name": subway_destination_name,
            }
            try:
                subway_candidates = discover_subway_candidates(
                    origin_name=subway_origin_name,
                    destination_name=subway_destination_name,
                    current_minute=base_minute,
                )
                subway_attempt["route_count"] = len(subway_candidates)
                if subway_candidates:
                    subway_attempt["discovery_source"] = "tago_subway_same_line"
                    subway_attempt["notice"] = (
                        "TAGO 지하철역 노선 정보로 직행 또는 1회 환승 후보를 찾았습니다. "
                        "시간은 아직 추정값입니다."
                    )
                    candidates.extend(subway_candidates)
            except (RuntimeError, TagoApiError, TagoRouteBuildError, ValueError) as exc:
                subway_attempt["route_count"] = 0
                subway_attempt["error"] = _short_error_message(exc)
            attempts.append(subway_attempt)
        topology_station_route_caches: dict[
            str, dict[str, tuple[object, ...]]
        ] = {}
        topology_route_stop_caches: dict[str, dict[str, tuple[object, ...]]] = {}
        routable_origins = []
        unroutable_origins = []
        for station in origin_candidates:
            cache = topology_station_route_caches.setdefault(station.city_code, {})
            try:
                cache[station.node_id] = fetch_station_routes(
                    station.city_code,
                    station.node_id,
                    timeout_seconds=5.0,
                )
            except (RuntimeError, TagoApiError, ValueError):
                unroutable_origins.append(station)
                continue
            if cache[station.node_id]:
                routable_origins.append(station)
            else:
                unroutable_origins.append(station)
        origin_candidates = tuple((*routable_origins, *unroutable_origins))
        attempted_pairs = 0
        for origin_station in origin_candidates:
            ordered_destinations = sorted(
                destination_candidates,
                key=lambda station: station.city_code != origin_station.city_code,
            )
            for destination_station in ordered_destinations:
                if attempted_pairs >= payload.max_station_pairs:
                    break
                if len(candidates) >= payload.max_candidates:
                    break
                if origin_station.node_id == destination_station.node_id:
                    continue
                attempted_pairs += 1
                attempt = {
                    "origin_node_id": origin_station.node_id,
                    "origin_name": origin_station.node_name,
                    "destination_node_id": destination_station.node_id,
                    "destination_name": destination_station.node_name,
                    "city_code": origin_station.city_code,
                    "destination_city_code": destination_station.city_code,
                }
                attempt_diagnostics: dict[str, object] = {}
                discovered: tuple[RouteCandidate, ...] = ()
                pair_city_code = origin_station.city_code
                station_route_cache = topology_station_route_caches.setdefault(
                    pair_city_code, {}
                )
                route_stop_cache = topology_route_stop_caches.setdefault(
                    pair_city_code, {}
                )
                try:
                    discovered = discover_tago_topology_candidates(
                        city_code=origin_station.city_code,
                        origin_node_id=origin_station.node_id,
                        destination_node_id=destination_station.node_id,
                        current_minute=base_minute,
                        max_routes_per_stop=payload.max_origin_routes,
                        average_minutes_per_stop=payload.average_minutes_per_stop,
                        max_walking_transfer_m=payload.max_walking_transfer_m,
                        walking_meters_per_minute=payload.walking_meters_per_minute,
                        station_route_cache=station_route_cache,
                        route_stop_cache=route_stop_cache,
                    )
                    cached_routes = station_route_cache.get(origin_station.node_id, ())
                    attempt_diagnostics["origin_routes"] = [
                        route.to_dict() for route in cached_routes
                    ]
                    attempt_diagnostics["origin_arrivals"] = []
                    if discovered:
                        attempt["discovery_source"] = "route_topology_primary"
                        attempt["notice"] = (
                            "정류소 경유 노선 구조로 후보를 찾았습니다. "
                            "표시 시간은 추정값입니다."
                        )
                except (RuntimeError, TagoApiError, TagoRouteBuildError, ValueError) as exc:
                    attempt["topology_error"] = _short_error_message(exc)

                if payload.use_live_arrival_discovery:
                    try:
                        live_discovered = discover_tago_route_candidates(
                            city_code=origin_station.city_code,
                            origin_node_id=origin_station.node_id,
                            destination_node_id=destination_station.node_id,
                            current_minute=base_minute,
                            average_minutes_per_stop=payload.average_minutes_per_stop,
                            walking_minutes=payload.walking_minutes,
                            minimum_buffer_minutes=payload.minimum_buffer_minutes,
                            max_origin_routes=payload.max_origin_routes,
                            max_transfer_stops_per_route=payload.max_transfer_stops_per_route,
                            max_transfer_routes_per_stop=payload.max_transfer_routes_per_stop,
                            max_walking_transfer_m=payload.max_walking_transfer_m,
                            walking_meters_per_minute=payload.walking_meters_per_minute,
                            max_walking_transfer_stations=(
                                payload.max_walking_transfer_stations
                            ),
                            diagnostics=attempt_diagnostics,
                        )
                        if live_discovered:
                            discovered = (*live_discovered, *discovered)
                            attempt["discovery_source"] = "live_arrival_primary"
                            attempt["notice"] = (
                                "실시간 도착 차량을 우선하고 노선 구조 후보를 보조로 사용합니다."
                            )
                    except (RuntimeError, TagoApiError, TagoRouteBuildError, ValueError) as exc:
                        attempt["live_error"] = _short_error_message(exc)

                if not discovered:
                    errors = [
                        str(attempt[key])
                        for key in ("live_error", "topology_error")
                        if key in attempt
                    ]
                    if errors:
                        attempt["error"] = " / ".join(errors)
                candidates.extend(discovered)
                attempt.update(attempt_diagnostics)
                # Live diagnostics also contain an origin-stop route count. Keep
                # the attempt field unambiguously equal to built candidates.
                attempt["route_count"] = len(discovered)
                attempts.append(attempt)
            if attempted_pairs >= payload.max_station_pairs:
                break
            if len(candidates) >= payload.max_candidates:
                break

        unique_candidates = _dedupe_route_candidates(candidates)
        ranked = rank_routes(unique_candidates)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=_friendly_runtime_error(exc)) from exc
    except TagoApiError as exc:
        raise HTTPException(status_code=502, detail=_friendly_tago_error(exc)) from exc
    except TagoRouteBuildError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        budget_manager.__exit__(*sys.exc_info())

    route_lookup = {route.id: route for route in unique_candidates}
    station_locations = _tago_station_locations(
        (*origin_candidates, *destination_candidates)
    )
    for city_cache in topology_route_stop_caches.values():
        for stops in city_cache.values():
            for stop in stops:
                station_locations.setdefault(
                    stop.node_id,
                    {
                        "name": stop.node_name,
                        "lat": stop.lat,
                        "lon": stop.lon,
                    },
                )
    for route in unique_candidates:
        if not route.id.startswith("tago-subway-"):
            continue
        first_segment = route.segments[0]
        last_segment = route.segments[-1]
        station_locations[first_segment.from_station_id] = {
            "name": payload.origin_name or first_segment.from_station_id,
            "lat": payload.origin.lat,
            "lon": payload.origin.lon,
        }
        station_locations[last_segment.to_station_id] = {
            "name": payload.destination_name or last_segment.to_station_id,
            "lat": payload.destination.lat,
            "lon": payload.destination.lon,
        }
        if len(route.segments) > 1:
            hub = (
                ("반월당역", 35.86535, 128.59355)
                if "반월당" in route.id
                else ("청라언덕역", 35.8642, 128.5822)
            )
            station_locations[first_segment.to_station_id] = {
                "name": hub[0],
                "lat": hub[1],
                "lon": hub[2],
            }
            station_locations[last_segment.from_station_id] = {
                "name": hub[0],
                "lat": hub[1],
                "lon": hub[2],
            }
    diagnostics = _live_plan_diagnostics(
        ranked_count=len(ranked),
        origin_candidates=origin_candidates,
        destination_candidates=destination_candidates,
        attempts=attempts,
    )
    return {
        "source": "tago",
        "mode": "coordinate_to_nearby_station_plan",
        "message": (
            "Origin and destination coordinates were converted to nearby TAGO stops. "
            "TransitGuard then searched bounded live-arrival candidates and ranked "
            "their transfer reliability."
        ),
        "city_code": selected_city_code,
        "city_codes": list(selected_city_codes),
        "region_policy": _region_policy_label(
            selected_city_codes=selected_city_codes,
            origin_region=payload.origin_region,
            destination_region=payload.destination_region,
        ),
        "current_minute": base_minute,
        "current_time": _format_clock_minute(base_minute),
        "generated_at": _utc_now(),
        "api_budget": {
            "limit": call_budget.limit,
            "used": call_budget.used,
            "remaining": call_budget.remaining,
        },
        "limitations": [
            "This is a bounded practical planner, not a full nationwide map router.",
            "Travel time is estimated from TAGO route stop order.",
            "Subway travel times are estimates until full station schedules are linked.",
            "Cross-city two-transfer paths can still be omitted by the request budget.",
        ],
        "origin_stations": [station.to_dict() for station in origin_candidates],
        "destination_stations": [station.to_dict() for station in destination_candidates],
        "station_locations": station_locations,
        "attempts": attempts,
        "diagnostics": diagnostics,
        "routes": [
            {
                **_route_evaluation_to_dict(result),
                "segments": [
                    _segment_to_named_dict(segment, station_locations)
                    for segment in route_lookup[result.route_id].segments
                ],
                "itinerary": _route_itinerary(
                    route_lookup[result.route_id],
                    route_stop_caches=topology_route_stop_caches,
                    station_locations=station_locations,
                ),
            }
            for result in ranked
        ],
    }


def _fetch_plan_nearby_stations(*, lat: float, lon: float, num_of_rows: int):
    """Retry only the two essential coordinate lookups with a longer timeout."""
    last_error: TagoApiError | None = None
    for _ in range(2):
        try:
            return fetch_nearby_stations(
                lat=lat,
                lon=lon,
                num_of_rows=num_of_rows,
                timeout_seconds=12.0,
            )
        except TagoApiError as exc:
            last_error = exc
            if "timed out" not in str(exc).lower():
                raise
    assert last_error is not None
    raise TagoApiError(
        "TAGO nearby-stop request timed out twice. The public-data server is delayed."
    ) from last_error


def _live_plan_diagnostics(
    *,
    ranked_count: int,
    origin_candidates: tuple[object, ...],
    destination_candidates: tuple[object, ...],
    attempts: list[dict[str, object]],
) -> dict[str, object]:
    checked_origins = [
        {"node_id": station.node_id, "name": station.node_name}
        for station in origin_candidates
    ]
    checked_destinations = [
        {"node_id": station.node_id, "name": station.node_name}
        for station in destination_candidates
    ]
    origin_details: dict[str, dict[str, object]] = {}
    for attempt in attempts:
        node_id = str(attempt.get("origin_node_id", "")).strip()
        if not node_id:
            continue
        detail = origin_details.setdefault(
            node_id,
            {
                "node_id": node_id,
                "name": attempt.get("origin_name"),
                "arrivals": [],
                "routes": [],
            },
        )
        for key, identity in (
            ("origin_arrivals", "route_id"),
            ("origin_routes", "route_id"),
        ):
            target_key = "arrivals" if key == "origin_arrivals" else "routes"
            existing = detail[target_key]
            assert isinstance(existing, list)
            seen = {
                str(item.get(identity, ""))
                for item in existing
                if isinstance(item, dict)
            }
            for item in attempt.get(key, []):
                if not isinstance(item, dict):
                    continue
                value = str(item.get(identity, ""))
                if value and value not in seen:
                    existing.append(item)
                    seen.add(value)

    arrivals = []
    for detail in origin_details.values():
        all_routes = detail["routes"]
        assert isinstance(all_routes, list)
        arrivals.append(
            {
                **detail,
                "routes": all_routes[:20],
                "route_count": len(all_routes),
                "routes_truncated": len(all_routes) > 20,
            }
        )
    if ranked_count:
        used_topology_fallback = any(
            str(attempt.get("discovery_source", "")).startswith("route_topology")
            or attempt.get("discovery_source") == "tago_subway_same_line"
            for attempt in attempts
        )
        return {
            "status": "routes_found",
            "title": f"후보 경로 {ranked_count}개를 찾았습니다.",
            "message": (
                "노선 구조로 찾은 버스 또는 지하철 예상 경로가 포함되어 있습니다. "
                "출발·도착 시간은 추정값입니다."
                if used_topology_fallback
                else "실시간 도착정보를 바탕으로 후보를 찾았습니다."
            ),
            "estimated": used_topology_fallback,
            "checked_origin_stops": checked_origins,
            "checked_destination_stops": checked_destinations,
            "origin_arrivals": arrivals,
            "possible_causes": [],
            "suggestions": [],
        }

    has_arrivals = any(item["arrivals"] for item in arrivals)
    has_station_routes = any(item["route_count"] for item in arrivals)
    possible_causes = []
    if has_station_routes:
        possible_causes.append("확인된 노선이 목적지까지 직행하지 않습니다.")
        possible_causes.append("현재 탐색 범위에서 1회 환승 연결점을 찾지 못했습니다.")
    elif not has_arrivals:
        possible_causes.append("출발 정류소의 경유 노선과 현재 도착예정정보가 없거나 부족합니다.")
    else:
        possible_causes.append("실시간 도착 노선의 전체 정류소 순서를 확인하지 못했습니다.")
    if any(attempt.get("error") for attempt in attempts):
        possible_causes.append("일부 TAGO 조회가 실패했거나 사용할 수 있는 노선 정보가 없었습니다.")
    return {
        "status": "no_routes",
        "title": "경로 후보를 찾지 못했습니다.",
        "message": "탐색은 정상 완료되었지만 현재 정보와 범위에서 연결 가능한 경로가 없었습니다.",
        "checked_origin_stops": checked_origins,
        "checked_destination_stops": checked_destinations,
        "origin_arrivals": arrivals,
        "possible_causes": possible_causes,
        "suggestions": [
            "정류소별 경유 노선이 비정상적으로 많다면 새 버전으로 다시 실행하세요.",
            "경계 지역에서는 출발·도착 주변 정류소를 각각 5개까지 확인해보세요.",
            "도보 환승 반경은 400m부터 단계적으로 넓혀보세요.",
            "도착정보가 없는 시간대에도 경유 노선 구조 탐색은 계속 사용할 수 있습니다.",
        ],
    }


@app.post("/api/route-candidates/discover-tago")
def discover_tago_route_candidate_payload(
    payload: DiscoverTagoRoutePayload,
) -> dict[str, object]:
    base_minute = payload.current_minute
    if base_minute is None:
        base_minute = current_minute_of_day()

    try:
        candidates = discover_tago_route_candidates(
            city_code=payload.city_code,
            origin_node_id=payload.origin_node_id,
            destination_node_id=payload.destination_node_id,
            current_minute=base_minute,
            average_minutes_per_stop=payload.average_minutes_per_stop,
            walking_minutes=payload.walking_minutes,
            minimum_buffer_minutes=payload.minimum_buffer_minutes,
            max_origin_routes=payload.max_origin_routes,
            max_transfer_stops_per_route=payload.max_transfer_stops_per_route,
            max_transfer_routes_per_stop=payload.max_transfer_routes_per_stop,
            max_walking_transfer_m=payload.max_walking_transfer_m,
            walking_meters_per_minute=payload.walking_meters_per_minute,
            max_walking_transfer_stations=payload.max_walking_transfer_stations,
        )
        ranked = rank_routes(list(candidates))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TagoApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except TagoRouteBuildError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    route_lookup = {route.id: route for route in candidates}
    return {
        "source": "tago",
        "mode": "discovered_from_live_origin_arrivals",
        "city_code": payload.city_code,
        "origin_node_id": payload.origin_node_id,
        "destination_node_id": payload.destination_node_id,
        "current_minute": base_minute,
        "generated_at": _utc_now(),
        "travel_time_source": "estimated_from_tago_route_stop_order",
        "arrival_source": "tago_live_arrivals",
        "transfer_search_scope": "same_node_or_walking_radius_bounded_discovery",
        "max_walking_transfer_m": payload.max_walking_transfer_m,
        "routes": [
            {
                **_route_evaluation_to_dict(result),
                "segments": [
                    _segment_to_dict(segment)
                    for segment in route_lookup[result.route_id].segments
                ],
            }
            for result in ranked
        ],
    }


@app.post("/api/route-candidates/generate-tago")
def generate_tago_route_candidates(payload: GenerateTagoRoutePayload) -> dict[str, object]:
    base_minute = payload.current_minute
    if base_minute is None:
        base_minute = current_minute_of_day()

    try:
        candidates = build_tago_route_candidates(
            city_code=payload.city_code,
            origin_node_id=payload.origin_node_id,
            destination_node_id=payload.destination_node_id,
            route_ids=tuple(payload.route_ids),
            current_minute=base_minute,
            average_minutes_per_stop=payload.average_minutes_per_stop,
            walking_minutes=payload.walking_minutes,
            minimum_buffer_minutes=payload.minimum_buffer_minutes,
            max_transfer_candidates=payload.max_transfer_candidates,
            max_walking_transfer_m=payload.max_walking_transfer_m,
            walking_meters_per_minute=payload.walking_meters_per_minute,
        )
        ranked = rank_routes(list(candidates))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TagoApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except TagoRouteBuildError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    route_lookup = {route.id: route for route in candidates}
    return {
        "source": "tago",
        "city_code": payload.city_code,
        "origin_node_id": payload.origin_node_id,
        "destination_node_id": payload.destination_node_id,
        "route_ids": payload.route_ids,
        "current_minute": base_minute,
        "generated_at": _utc_now(),
        "travel_time_source": "estimated_from_tago_route_stop_order",
        "arrival_source": "tago_live_arrivals",
        "transfer_search_scope": "same_node_or_walking_radius",
        "routes": [
            {
                **_route_evaluation_to_dict(result),
                "segments": [
                    _segment_to_dict(segment)
                    for segment in route_lookup[result.route_id].segments
                ],
            }
            for result in ranked
        ],
    }


@app.post("/api/route-candidates/generate-graph")
def generate_route_candidates(payload: GenerateGraphPayload) -> dict[str, object]:
    base_minute = payload.current_minute
    if base_minute is None:
        base_minute = current_minute_of_day()

    try:
        origin = find_demo_station(payload.origin)
        destination = find_demo_station(payload.destination)
        arrival_overrides: dict[str, tuple[Arrival, ...]] = {}
        tago_arrival_info: list[dict[str, object]] | None = None
        if payload.arrival_source == "tago":
            if not payload.tago_city_code or not payload.tago_node_id:
                raise ValueError(
                    "tago_city_code and tago_node_id are required when arrival_source=tago"
                )
            tago_items = _fetch_tago_or_http_error(
                city_code=payload.tago_city_code,
                node_id=payload.tago_node_id,
                current_minute=base_minute,
            )
            arrival_overrides[payload.tago_transfer_station_id] = tuple(
                item.to_core_arrival(station_id=payload.tago_transfer_station_id)
                for item in tago_items
            )
            tago_arrival_info = [item.to_dict() for item in tago_items]
        candidates = build_demo_route_candidates(
            origin,
            destination,
            base_minute,
            arrival_overrides=arrival_overrides,
        )
        ranked = rank_routes(list(candidates))
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "station not found" in message else 422
        raise HTTPException(status_code=status_code, detail=message) from exc

    route_lookup = {route.id: route for route in candidates}
    response: dict[str, object] = {
        "origin": station_to_dict(origin),
        "destination": station_to_dict(destination),
        "current_minute": base_minute,
        "generated_at": _utc_now(),
        "arrival_source": payload.arrival_source,
        "arrival_info": (
            tago_arrival_info
            if tago_arrival_info is not None
            else [_arrival_to_dict(arrival) for arrival in generate_demo_arrivals(base_minute)]
        ),
        "routes": [
            {
                **_route_evaluation_to_dict(result),
                "segments": [
                    _segment_to_dict(segment)
                    for segment in route_lookup[result.route_id].segments
                ],
            }
            for result in ranked
        ],
    }
    if payload.include_graph:
        response["graph"] = {
            "stations": [station_to_dict(station) for station in get_demo_stations()],
            "edges": [edge_to_dict(edge) for edge in get_demo_edges()],
        }
    return response




def _tago_station_locations(stations) -> dict[str, dict[str, object]]:
    return {
        station.node_id: {
            "name": station.node_name,
            "lat": station.lat,
            "lon": station.lon,
        }
        for station in stations
    }


def _select_plan_city_code(
    requested_city_code: str | None,
    origin_stations,
    destination_stations,
) -> str:
    if requested_city_code and requested_city_code.strip():
        return requested_city_code.strip()
    origin_codes = [station.city_code for station in origin_stations if station.city_code]
    destination_codes = {station.city_code for station in destination_stations if station.city_code}
    for code in origin_codes:
        if code in destination_codes:
            return code
    if origin_codes:
        return origin_codes[0]
    raise TagoRouteBuildError("Could not infer TAGO city_code from nearby stations")


def _station_candidates_for_city(stations, city_code: str, limit: int):
    return tuple(station for station in stations if station.city_code == city_code)[:limit]


def _select_plan_city_codes(
    *,
    requested_city_code: str | None,
    requested_city_codes: list[str],
    origin_stations,
    destination_stations,
    origin_region: str = "auto",
    destination_region: str = "auto",
) -> tuple[str, ...]:
    explicit_regions = {origin_region, destination_region} - {"auto"}
    if origin_region != "auto" and destination_region != "auto":
        if explicit_regions == {"gyeongsan"}:
            return ("37100",)
        return ("22",)
    explicit = [
        value.strip()
        for value in ([requested_city_code] if requested_city_code else [])
        + requested_city_codes
        if value and value.strip()
    ]
    if explicit:
        return tuple(dict.fromkeys(explicit))
    origin_primary = next(
        (station.city_code for station in origin_stations if station.city_code), None
    )
    destination_primary = next(
        (station.city_code for station in destination_stations if station.city_code), None
    )
    if not origin_primary and not destination_primary:
        raise TagoRouteBuildError("Could not infer TAGO city_code from nearby stations")
    if origin_primary == destination_primary:
        return (origin_primary,)
    if {origin_primary, destination_primary} == {"22", "37100"}:
        return ("22",)
    return tuple(
        dict.fromkeys(
            code for code in (origin_primary, destination_primary) if code
        )
    )


def _region_policy_label(
    *, selected_city_codes: tuple[str, ...], origin_region: str, destination_region: str
) -> str:
    if origin_region == destination_region == "gyeongsan":
        return "경산↔경산: cityCode 37100 / GYB 정류소만 사용"
    if {origin_region, destination_region} == {"daegu", "gyeongsan"}:
        return "대구↔경산: cityCode 22 / DGB 정류소만 사용"
    if origin_region == destination_region == "daegu":
        return "대구↔대구: cityCode 22 / DGB 정류소만 사용"
    return f"자동 판별: TAGO cityCode {', '.join(selected_city_codes)}"


def _station_candidates_for_cities(stations, city_codes: tuple[str, ...], limit: int):
    allowed = set(city_codes)
    candidates = [station for station in stations if station.city_code in allowed]
    selected = []
    consumed: set[str] = set()
    physical_stop_count = 0
    city_order = {code: index for index, code in enumerate(city_codes)}
    for station in candidates:
        if station.node_id in consumed:
            continue
        if physical_stop_count >= limit:
            break
        mirror_group = [
            candidate
            for candidate in candidates
            if candidate.node_id not in consumed
            and _is_mirrored_station(station, candidate)
        ]
        mirror_group.sort(
            key=lambda candidate: (
                0 if candidate.node_id == station.node_id else 1,
                city_order.get(candidate.city_code, len(city_order)),
            )
        )
        selected.extend(mirror_group)
        consumed.update(candidate.node_id for candidate in mirror_group)
        physical_stop_count += 1
    return tuple(selected)


def _is_mirrored_station(first, second) -> bool:
    if _normalized_station_name(first.node_name) != _normalized_station_name(
        second.node_name
    ):
        return False
    first_point = Coordinate(lat=first.lat, lon=first.lon)
    second_point = Coordinate(lat=second.lat, lon=second.lon)
    return first_point.distance_to(second_point) <= 120.0


def _normalized_station_name(value: str) -> str:
    base = value.split("(", 1)[0]
    return "".join(base.split()).casefold()


def _route_itinerary(
    route: RouteCandidate,
    *,
    route_stop_caches: dict[str, dict[str, tuple[object, ...]]],
    station_locations: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    all_route_stops = [
        stops
        for city_cache in route_stop_caches.values()
        for stops in city_cache.values()
    ]
    result = []
    for index, segment in enumerate(route.segments):
        matching_stops = _matching_segment_stops(segment, all_route_stops)
        stop_details = [
            {
                "node_id": stop.node_id,
                "name": stop.node_name,
                "order": stop.order,
            }
            for stop in matching_stops
        ]
        board_name = (
            matching_stops[0].node_name
            if matching_stops
            else station_locations.get(segment.from_station_id, {}).get(
                "name", segment.from_station_id
            )
        )
        alight_name = (
            matching_stops[-1].node_name
            if matching_stops
            else station_locations.get(segment.to_station_id, {}).get(
                "name", segment.to_station_id
            )
        )
        result.append(
            {
                "leg": index + 1,
                "route_id": segment.route_id,
                "board_stop_id": segment.from_station_id,
                "board_stop_name": board_name,
                "board_time": _format_clock_minute(segment.departure_minute),
                "alight_stop_id": segment.to_station_id,
                "alight_stop_name": alight_name,
                "alight_time": _format_clock_minute(segment.arrival_minute),
                "time_source": _candidate_time_source(route),
                "departure_realtime": route.id.startswith(
                    ("tago-direct-", "tago-transfer-")
                ),
                "arrival_estimated": True,
                "accuracy_notice": _candidate_accuracy_notice(route),
                "stops": stop_details,
                "via_stop_names": [stop.node_name for stop in matching_stops[1:-1]],
            }
        )
    return result


def _matching_segment_stops(segment, route_stop_groups):
    best = ()
    for stops in route_stop_groups:
        if not stops:
            continue
        first = stops[0]
        if segment.route_id not in {first.route_id, first.route_no}:
            continue
        for origin_index, stop in enumerate(stops):
            if stop.node_id != segment.from_station_id:
                continue
            for destination_index in range(origin_index + 1, len(stops)):
                if stops[destination_index].node_id != segment.to_station_id:
                    continue
                candidate = stops[origin_index : destination_index + 1]
                if not best or len(candidate) < len(best):
                    best = candidate
    return tuple(best)


def _candidate_time_source(route: RouteCandidate) -> str:
    if route.id.startswith(("tago-direct-", "tago-transfer-")):
        return "TAGO 실시간 탑승 ETA + 경유 정류소 기반 도착 예상"
    if route.id.startswith("tago-subway-"):
        return "TAGO 지하철 노선 기반 예상"
    return "TAGO 노선 구조 기반 예상"


def _candidate_accuracy_notice(route: RouteCandidate) -> str:
    if route.id.startswith(("tago-direct-", "tago-transfer-")):
        return (
            "탑승 시각은 TAGO 실시간 도착정보이며, 하차 시각은 정류소 수를 "
            "기준으로 계산한 예상입니다. 정확한 정류소별 운행 시간표가 아닙니다."
        )
    return (
        "표시 시각 전체가 노선 구조와 평균 이동시간으로 계산된 예상입니다. "
        "정확한 정류소별 운행 시간표가 아닙니다."
    )


def _dedupe_route_candidates(candidates: list[RouteCandidate]) -> list[RouteCandidate]:
    seen: set[tuple[tuple[str, str, str], ...]] = set()
    unique: list[RouteCandidate] = []
    for candidate in candidates:
        key = tuple(
            (segment.route_id, segment.from_station_id, segment.to_station_id)
            for segment in candidate.segments
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _short_error_message(exc: BaseException) -> str:
    message = str(exc).strip()
    if not message:
        return exc.__class__.__name__
    return message[:180]


def _kakao_map_status() -> dict[str, object]:
    key, source = read_config_value("KAKAO_MAP_JAVASCRIPT_KEY")
    configured = bool(key and key.strip())
    return {
        "configured": configured,
        "source": source,
        "hint": (
            "Kakao Map JavaScript key is configured. Web demo map can be enabled."
            if configured
            else (
                "Set KAKAO_MAP_JAVASCRIPT_KEY in .env to enable Kakao Map search, "
                "markers, and route visualization in the web demo."
            )
        ),
    }


def _fetch_tago_or_http_error(
    *,
    city_code: str,
    node_id: str,
    current_minute: int,
    page_no: int = 1,
    num_of_rows: int = 10,
    fetch_all_pages: bool = False,
):
    try:
        return fetch_station_arrivals(
            city_code=city_code,
            node_id=node_id,
            current_minute=current_minute,
            page_no=page_no,
            num_of_rows=num_of_rows,
            fetch_all_pages=fetch_all_pages,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=_friendly_runtime_error(exc)) from exc
    except TagoApiError as exc:
        raise HTTPException(status_code=502, detail=_friendly_tago_error(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _friendly_runtime_error(exc: RuntimeError) -> str:
    message = str(exc)
    if "TAGO_SERVICE_KEY" in message or "service key" in message.lower():
        return (
            "TAGO service key is not configured. Demo mode works without it. "
            "For live data, copy .env.example to .env and fill TAGO_SERVICE_KEY."
        )
    return message


def _friendly_tago_error(exc: TagoApiError) -> str:
    message = str(exc)
    lower = message.lower()
    if "servicekey" in lower or "service key" in lower or "service_key" in lower:
        return (
            "TAGO rejected the service key or the key is missing. Check TAGO_SERVICE_KEY "
            "in .env, and try both the decoded and encoded key from data.go.kr if needed."
        )
    if "url" in lower or "timed out" in lower or "temporary" in lower:
        return "TAGO network request failed. Check your internet connection and try again."
    if "no items" in lower or "not found" in lower:
        return "TAGO returned no data. Check city_code, node_id, and route_id values."
    return message


def _load_live_arrival_sources(
    sources: list[TagoArrivalSourcePayload],
    current_minute: int,
) -> tuple[dict[str, tuple[Arrival, ...]], list[dict[str, object]]]:
    live_arrivals: dict[str, tuple[Arrival, ...]] = {}
    source_summaries: list[dict[str, object]] = []

    for source in sources:
        tago_items = _fetch_tago_or_http_error(
            city_code=source.city_code,
            node_id=source.node_id,
            current_minute=current_minute,
            page_no=source.page_no,
            num_of_rows=source.num_of_rows,
            fetch_all_pages=source.fetch_all_pages,
        )
        prefer_route_no = source.route_key == "route_no"
        converted = tuple(
            item.to_core_arrival(
                station_id=source.station_id,
                prefer_route_no=prefer_route_no,
            )
            for item in tago_items
        )
        existing = live_arrivals.get(source.station_id, ())
        live_arrivals[source.station_id] = _dedupe_arrivals((*existing, *converted))
        source_summaries.append(
            {
                "station_id": source.station_id,
                "city_code": source.city_code,
                "node_id": source.node_id,
                "route_key": source.route_key,
                "arrival_count": len(converted),
                "fetch_all_pages": source.fetch_all_pages,
            }
        )

    return live_arrivals, source_summaries


def _to_route_candidate(
    payload: RoutePayload,
    arrival_overrides: dict[str, tuple[Arrival, ...]] | None = None,
) -> RouteCandidate:
    overrides = arrival_overrides or {}
    return RouteCandidate(
        id=payload.id,
        segments=tuple(
            RouteSegment(
                route_id=segment.route_id,
                from_station_id=segment.from_station_id,
                to_station_id=segment.to_station_id,
                departure_minute=segment.departure_minute,
                arrival_minute=segment.arrival_minute,
            )
            for segment in payload.segments
        ),
        requested_start_minute=payload.requested_start_minute,
        transfers=tuple(
            Transfer(
                from_station_id=transfer.from_station_id,
                to_station_id=transfer.to_station_id,
                arrival_minute=transfer.arrival_minute,
                walking_minutes=transfer.walking_minutes,
                minimum_buffer_minutes=transfer.minimum_buffer_minutes,
                candidate_arrivals=_dedupe_arrivals(
                    (
                        *(
                            Arrival(
                                station_id=arrival.station_id,
                                route_id=arrival.route_id,
                                arrival_minute=arrival.arrival_minute,
                            )
                            for arrival in transfer.candidate_arrivals
                        ),
                        *overrides.get(transfer.to_station_id, ()),
                    )
                ),
                target_route_id=transfer.target_route_id,
            )
            for transfer in payload.transfers
        ),
    )


def _quick_payload_to_route_candidate(payload: QuickAssessPayload) -> RouteCandidate:
    return RouteCandidate(
        id=payload.id,
        requested_start_minute=payload.requested_start_minute,
        segments=(
            RouteSegment(
                route_id=payload.first_route_id,
                from_station_id=payload.origin_station_id,
                to_station_id=payload.transfer_station_id,
                departure_minute=payload.first_departure_minute,
                arrival_minute=payload.transfer_arrival_minute,
            ),
            RouteSegment(
                route_id=payload.second_route_id,
                from_station_id=payload.transfer_station_id,
                to_station_id=payload.destination_station_id,
                departure_minute=payload.second_departure_minute,
                arrival_minute=payload.final_arrival_minute,
            ),
        ),
        transfers=(
            Transfer(
                from_station_id=payload.transfer_station_id,
                to_station_id=payload.transfer_station_id,
                arrival_minute=payload.transfer_arrival_minute,
                walking_minutes=payload.walking_minutes,
                minimum_buffer_minutes=payload.minimum_buffer_minutes,
                target_route_id=payload.second_route_id,
                candidate_arrivals=tuple(
                    Arrival(
                        station_id=payload.transfer_station_id,
                        route_id=payload.second_route_id,
                        arrival_minute=minute,
                    )
                    for minute in payload.next_vehicle_arrival_minutes
                ),
            ),
        ),
    )


def _dedupe_arrivals(arrivals: tuple[Arrival, ...]) -> tuple[Arrival, ...]:
    seen: set[tuple[str, str, int]] = set()
    unique: list[Arrival] = []
    for arrival in sorted(arrivals, key=lambda item: item.arrival_minute):
        key = (arrival.station_id, arrival.route_id, arrival.arrival_minute)
        if key in seen:
            continue
        seen.add(key)
        unique.append(arrival)
    return tuple(unique)


def _route_evaluation_to_dict(result: RouteEvaluation) -> dict[str, object]:
    return {
        "route_id": result.route_id,
        "status": result.status.value,
        "status_label": _status_label(result.status),
        "summary": _route_summary(result),
        "recommendation": _route_recommendation(result),
        "confidence_label": _confidence_label(result),
        "risk_warnings": _risk_warnings(result),
        "next_steps": _next_steps(result),
        "reliability_score": result.reliability_score,
        "total_minutes": result.total_minutes,
        "initial_wait_minutes": result.initial_wait_minutes,
        "ranking_score": result.ranking_score,
        "score_breakdown": {
            "meaning": "Lower ranking_score is better.",
            "total_minutes": result.total_minutes,
            "transfer_penalty": len(result.transfer_results) * 10.0,
            "status_penalty": _status_penalty(result.status),
            "reliability_penalty": round((1.0 - result.reliability_score) * 10.0, 3),
        },
        "transfers": [
            {
                "status": transfer.status.value,
                "status_label": _status_label(transfer.status),
                "required_minute": transfer.required_minute,
                "required_time": _format_clock_minute(transfer.required_minute),
                "board_minute": transfer.board_minute,
                "board_time": _format_clock_minute(transfer.board_minute),
                "wait_minutes": transfer.wait_minutes,
                "reason": transfer.reason,
                "message": _transfer_message(transfer),
            }
            for transfer in result.transfer_results
        ],
    }


def _confidence_label(result: RouteEvaluation) -> str:
    if result.status == TransferStatus.UNKNOWN:
        return "낮음"
    if result.reliability_score >= 0.85:
        return "높음"
    if result.reliability_score >= 0.55:
        return "보통"
    return "낮음"


def _risk_warnings(result: RouteEvaluation) -> list[str]:
    warnings: list[str] = []
    if result.initial_wait_minutes >= 30:
        warnings.append("첫 탑승까지 대기 시간이 긴 편입니다.")
    if result.status == TransferStatus.TIGHT:
        warnings.append("환승 여유가 짧아 지연이 생기면 실패할 수 있습니다.")
    if result.status == TransferStatus.MISSED:
        warnings.append("현재 후보 도착정보 기준으로 환승 가능 차량을 찾지 못했습니다.")
    if result.status == TransferStatus.UNKNOWN:
        warnings.append("도착정보가 부족해 실제 탑승 가능성을 판단하기 어렵습니다.")
    for transfer in result.transfer_results:
        if transfer.wait_minutes is not None and transfer.wait_minutes <= 2:
            warnings.append("환승 대기 여유가 2분 이하인 구간이 있습니다.")
            break
    return warnings


def _next_steps(result: RouteEvaluation) -> list[str]:
    if result.status == TransferStatus.SAFE:
        return [
            "지도에서 정류장 위치와 환승 지점을 확인하세요.",
            "실제 TAGO 도착정보를 연결하면 더 현실적인 평가가 가능합니다.",
        ]
    if result.status == TransferStatus.TIGHT:
        return [
            "다음 차량 도착 시각을 하나 더 추가해 대체 탑승 가능성을 확인하세요.",
            "도보 환승 시간을 실제 거리 기준으로 조금 더 넉넉하게 잡아보세요.",
        ]
    if result.status == TransferStatus.UNKNOWN:
        return [
            "환승 정류장의 후보 도착 시각을 입력하거나 TAGO 정류소ID를 연결하세요.",
            "목표 노선번호와 route_id 기준이 서로 맞는지 확인하세요.",
        ]
    return [
        "다음 차량 도착 시각을 더 늦은 후보까지 추가해보세요.",
        "환승 시간이 더 긴 다른 경로 후보를 비교하세요.",
    ]


def _status_label(status: TransferStatus) -> str:
    labels = {
        TransferStatus.SAFE: "안전",
        TransferStatus.TIGHT: "촉박",
        TransferStatus.UNKNOWN: "정보 부족",
        TransferStatus.MISSED: "환승 실패",
    }
    return labels[status]


def _status_penalty(status: TransferStatus) -> float:
    penalties = {
        TransferStatus.SAFE: 0.0,
        TransferStatus.TIGHT: 8.0,
        TransferStatus.UNKNOWN: 20.0,
        TransferStatus.MISSED: 10_000.0,
    }
    return penalties[status]


def _route_summary(result: RouteEvaluation) -> str:
    label = _status_label(result.status)
    return (
        f"{label}: 요청 시각부터 도착까지 {result.total_minutes}분, "
        f"첫 탑승 대기 {result.initial_wait_minutes}분, "
        f"안정성 {result.reliability_score:.3f}"
    )


def _route_recommendation(result: RouteEvaluation) -> str:
    if result.status == TransferStatus.SAFE:
        return "환승 여유가 있어 추천 가능한 후보입니다."
    if result.status == TransferStatus.TIGHT:
        return "탑승은 가능하지만 환승 여유가 짧으므로 지연에 주의하세요."
    if result.status == TransferStatus.UNKNOWN:
        return "필요한 도착정보가 부족합니다. TAGO 도착정보나 후보 도착 시각을 추가하세요."
    return "현재 후보 도착정보 기준으로는 환승에 실패할 가능성이 높습니다."


def _transfer_message(transfer) -> str:
    if transfer.status == TransferStatus.SAFE:
        return f"필요 시각 이후 {transfer.wait_minutes}분 여유가 있어 탑승 가능합니다."
    if transfer.status == TransferStatus.TIGHT:
        return f"탑승 가능하지만 여유가 {transfer.wait_minutes}분으로 짧습니다."
    if transfer.status == TransferStatus.UNKNOWN:
        return "해당 정류장 또는 목표 노선의 도착정보가 부족합니다."
    return "필요 시각 이후에 탈 수 있는 차량이 없습니다."


def _quick_demo_presets() -> dict[str, dict[str, object]]:
    return {
        "safe": {
            "label": "안전한 환승 예시",
            "description": "다음 차량까지 여유가 있어 추천 가능한 경로입니다.",
            "payload": {
                "id": "safe-demo",
                "requested_start_minute": 520,
                "first_route_id": "101",
                "second_route_id": "708",
                "first_departure_minute": 524,
                "transfer_arrival_minute": 540,
                "second_departure_minute": 552,
                "final_arrival_minute": 570,
                "walking_minutes": 4,
                "minimum_buffer_minutes": 3,
                "next_vehicle_arrival_minutes": [552, 560],
            },
        },
        "tight": {
            "label": "촉박한 환승 예시",
            "description": "탑승은 가능하지만 지연이 생기면 위험한 경로입니다.",
            "payload": {
                "id": "tight-demo",
                "requested_start_minute": 520,
                "first_route_id": "401",
                "second_route_id": "708",
                "first_departure_minute": 522,
                "transfer_arrival_minute": 542,
                "second_departure_minute": 550,
                "final_arrival_minute": 566,
                "walking_minutes": 4,
                "minimum_buffer_minutes": 3,
                "next_vehicle_arrival_minutes": [550],
            },
        },
        "missed": {
            "label": "환승 실패 예시",
            "description": "필요 시각 이후에 탈 수 있는 다음 차량이 없는 경로입니다.",
            "payload": {
                "id": "missed-demo",
                "requested_start_minute": 520,
                "first_route_id": "급행1",
                "second_route_id": "708",
                "first_departure_minute": 526,
                "transfer_arrival_minute": 548,
                "second_departure_minute": 552,
                "final_arrival_minute": 570,
                "walking_minutes": 5,
                "minimum_buffer_minutes": 4,
                "next_vehicle_arrival_minutes": [551, 552],
            },
        },
    }


def _demo_station_locations() -> dict[str, dict[str, object]]:
    return {
        "A": {"name": "대구역", "lat": 35.8759, "lon": 128.5961},
        "B": {"name": "반월당역", "lat": 35.8649, "lon": 128.5935},
        "C": {"name": "동대구역", "lat": 35.8797, "lon": 128.6282},
    }


def _segment_to_dict(segment: RouteSegment) -> dict[str, object]:
    return {
        "route_id": segment.route_id,
        "from_station_id": segment.from_station_id,
        "to_station_id": segment.to_station_id,
        "departure_minute": segment.departure_minute,
        "departure_time": _format_clock_minute(segment.departure_minute),
        "arrival_minute": segment.arrival_minute,
        "arrival_time": _format_clock_minute(segment.arrival_minute),
    }


def _segment_to_named_dict(
    segment: RouteSegment, station_locations: dict[str, dict[str, object]]
) -> dict[str, object]:
    result = _segment_to_dict(segment)
    result["from_station_name"] = station_locations.get(
        segment.from_station_id, {}
    ).get("name", segment.from_station_id)
    result["to_station_name"] = station_locations.get(segment.to_station_id, {}).get(
        "name", segment.to_station_id
    )
    return result


def _arrival_to_dict(arrival: Arrival) -> dict[str, object]:
    return {
        "station_id": arrival.station_id,
        "route_id": arrival.route_id,
        "arrival_minute": arrival.arrival_minute,
        "arrival_time": _format_clock_minute(arrival.arrival_minute),
    }


def _format_clock_minute(value: int | None) -> str | None:
    if value is None:
        return None
    day, minute_of_day = divmod(value, 24 * 60)
    hours, minutes = divmod(minute_of_day, 60)
    clock = f"{hours:02d}:{minutes:02d}"
    return f"+{day}일 {clock}" if day else clock


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
