from fastapi.testclient import TestClient

from transitguard import __version__
from transitguard.adapters.tago import (
    TagoApiError,
    TagoArrival,
    TagoRouteBuildError,
    TagoRouteStop,
    TagoStation,
)
from transitguard.api import app as app_module
from transitguard.api.app import app
from transitguard.core.models import RouteCandidate, RouteSegment

client = TestClient(app)


def test_plan_nearby_lookup_retries_a_timeout_once(monkeypatch):
    calls = []

    def flaky_fetch(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise TagoApiError("TAGO request timed out")
        return (TagoStation("22", "A", "출발", 35.0, 128.0),)

    monkeypatch.setattr(app_module, "fetch_nearby_stations", flaky_fetch)

    stations = app_module._fetch_plan_nearby_stations(
        lat=35.0, lon=128.0, num_of_rows=20
    )

    assert stations[0].node_id == "A"
    assert len(calls) == 2
    assert calls[0]["timeout_seconds"] == 12.0


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_uses_package_version():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["version"] == __version__


def test_rank_endpoint_rejects_invalid_negative_time():
    response = client.post(
        "/api/routes/rank",
        json={
            "routes": [
                {
                    "id": "bad-route",
                    "segments": [
                        {
                            "route_id": "R1",
                            "from_station_id": "A",
                            "to_station_id": "B",
                            "departure_minute": -1,
                            "arrival_minute": 10,
                        }
                    ],
                }
            ]
        },
    )

    assert response.status_code == 422


def test_rank_endpoint_rejects_whitespace_only_ids():
    response = client.post(
        "/api/routes/rank",
        json={
            "routes": [
                {
                    "id": "   ",
                    "segments": [
                        {
                            "route_id": "R1",
                            "from_station_id": "A",
                            "to_station_id": "B",
                            "departure_minute": 1,
                            "arrival_minute": 2,
                        }
                    ],
                }
            ]
        },
    )

    assert response.status_code == 422

def test_rank_endpoint_filters_target_route_id():
    response = client.post(
        "/api/routes/rank",
        json={
            "routes": [
                {
                    "id": "route-a",
                    "segments": [
                        {
                            "route_id": "R1",
                            "from_station_id": "A",
                            "to_station_id": "B",
                            "departure_minute": 90,
                            "arrival_minute": 100,
                        },
                        {
                            "route_id": "R2",
                            "from_station_id": "B",
                            "to_station_id": "C",
                            "departure_minute": 115,
                            "arrival_minute": 130,
                        },
                    ],
                    "transfers": [
                        {
                            "from_station_id": "B",
                            "to_station_id": "B",
                            "arrival_minute": 100,
                            "walking_minutes": 5,
                            "minimum_buffer_minutes": 3,
                            "target_route_id": "R2",
                            "candidate_arrivals": [
                                {"station_id": "B", "route_id": "WRONG", "arrival_minute": 108},
                                {"station_id": "B", "route_id": "R2", "arrival_minute": 115},
                            ],
                        }
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200
    transfer = response.json()["routes"][0]["transfers"][0]
    assert transfer["board_minute"] == 115


def test_api_health_alias_exposes_version():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "version" in response.json()


def test_graph_overview_returns_demo_graph():
    response = client.get("/api/graph/overview")

    assert response.status_code == 200
    data = response.json()
    assert data["station_count"] >= 1
    assert data["edge_count"] >= 1
    assert data["stations"][0]["id"]


def test_station_search_by_text():
    response = client.get("/api/graph/stations/search", params={"q": "대구역"})

    assert response.status_code == 200
    names = {station["name"] for station in response.json()["stations"]}
    assert "대구역앞" in names


def test_generate_graph_route_candidates():
    response = client.post(
        "/api/route-candidates/generate-graph",
        json={
            "origin": "대구역",
            "destination": "동대구역건너",
            "current_minute": 520,
            "include_graph": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["origin"]["id"] == "S1"
    assert data["destination"]["id"] == "S4"
    assert len(data["routes"]) >= 2
    assert "graph" in data
    assert "segments" in data["routes"][0]


def test_arrival_refresh_returns_arrivals():
    response = client.get(
        "/api/arrivals/refresh",
        params={"station_id": "S3", "current_minute": 520},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["station_id"] == "S3"
    assert data["arrivals"][0]["arrival_minute"] == 546


def test_tago_diagnostics_returns_configuration_state():
    response = client.get("/api/tago/diagnostics")

    assert response.status_code == 200
    data = response.json()
    assert "configured" in data
    assert "checked_at" in data


def test_generate_graph_does_not_create_nonexistent_reverse_routes():
    response = client.post(
        "/api/route-candidates/generate-graph",
        json={
            "origin": "동대구역건너",
            "destination": "대구역앞",
            "current_minute": 520,
            "include_graph": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["routes"] == []


def test_arrival_refresh_rejects_unknown_station():
    response = client.get(
        "/api/arrivals/refresh",
        params={"station_id": "UNKNOWN", "current_minute": 520},
    )

    assert response.status_code == 404


def test_tago_arrivals_requires_service_key(monkeypatch):
    monkeypatch.delenv("TAGO_SERVICE_KEY", raising=False)
    response = client.get(
        "/api/tago/arrivals",
        params={"city_code": "22", "node_id": "DGB123", "current_minute": 520},
    )

    assert response.status_code == 503


def test_arrival_refresh_tago_requires_city_and_node():
    response = client.get("/api/arrivals/refresh", params={"source": "tago"})

    assert response.status_code == 422


def test_tago_nearby_stations_endpoint_uses_live_adapter(monkeypatch):
    def fake_fetch_nearby_stations(**kwargs):
        assert kwargs["lat"] == 35.87
        assert kwargs["lon"] == 128.6
        return (TagoStation("22", "DGB001", "대구역앞", 35.875, 128.596),)

    monkeypatch.setattr(app_module, "fetch_nearby_stations", fake_fetch_nearby_stations)

    response = client.get("/api/tago/stations/nearby", params={"lat": 35.87, "lon": 128.6})

    assert response.status_code == 200
    assert response.json()["source"] == "tago"
    assert response.json()["stations"][0]["node_id"] == "DGB001"


def test_tago_route_stops_endpoint_uses_live_adapter(monkeypatch):
    def fake_fetch_route_stops(city_code, route_id, **kwargs):
        assert city_code == "22"
        assert route_id == "DGB708"
        return (TagoRouteStop("22", "DGB708", "708", "DGB001", "대구역앞", 1),)

    monkeypatch.setattr(app_module, "fetch_route_stops", fake_fetch_route_stops)

    response = client.get(
        "/api/tago/route-stops",
        params={"city_code": "22", "route_id": "DGB708"},
    )

    assert response.status_code == 200
    assert response.json()["stops"][0]["node_id"] == "DGB001"


def test_generate_tago_route_candidates_endpoint(monkeypatch):
    def fake_build_tago_route_candidates(**kwargs):
        assert kwargs["city_code"] == "22"
        assert kwargs["origin_node_id"] == "A"
        assert kwargs["destination_node_id"] == "B"
        return (
            RouteCandidate(
                id="tago-direct-1-R1",
                segments=(
                    RouteSegment(
                        route_id="R1",
                        from_station_id="A",
                        to_station_id="B",
                        departure_minute=501,
                        arrival_minute=511,
                    ),
                ),
            ),
        )

    monkeypatch.setattr(app_module, "build_tago_route_candidates", fake_build_tago_route_candidates)

    response = client.post(
        "/api/route-candidates/generate-tago",
        json={
            "city_code": "22",
            "origin_node_id": "A",
            "destination_node_id": "B",
            "route_ids": ["R1"],
            "current_minute": 500,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "tago"
    assert data["arrival_source"] == "tago_live_arrivals"
    assert data["routes"][0]["segments"][0]["route_id"] == "R1"


def test_discover_tago_route_candidates_endpoint(monkeypatch):
    def fake_discover_tago_route_candidates(**kwargs):
        assert kwargs["city_code"] == "22"
        assert kwargs["origin_node_id"] == "A"
        assert kwargs["destination_node_id"] == "B"
        return (
            RouteCandidate(
                id="tago-direct-1-R1",
                segments=(
                    RouteSegment(
                        route_id="R1",
                        from_station_id="A",
                        to_station_id="B",
                        departure_minute=501,
                        arrival_minute=511,
                    ),
                ),
            ),
        )

    monkeypatch.setattr(
        app_module,
        "discover_tago_route_candidates",
        fake_discover_tago_route_candidates,
    )
    monkeypatch.setattr(
        app_module,
        "discover_tago_topology_candidates",
        lambda **kwargs: (),
    )

    response = client.post(
        "/api/route-candidates/discover-tago",
        json={
            "city_code": "22",
            "origin_node_id": "A",
            "destination_node_id": "B",
            "current_minute": 500,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "discovered_from_live_origin_arrivals"
    assert data["routes"][0]["segments"][0]["route_id"] == "R1"


def test_rank_endpoint_includes_initial_wait_from_requested_start():
    response = client.post(
        "/api/routes/rank",
        json={
            "routes": [
                {
                    "id": "wait-route",
                    "requested_start_minute": 100,
                    "segments": [
                        {
                            "route_id": "R1",
                            "from_station_id": "A",
                            "to_station_id": "B",
                            "departure_minute": 130,
                            "arrival_minute": 150,
                        }
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200
    route = response.json()["routes"][0]
    assert route["initial_wait_minutes"] == 30
    assert route["total_minutes"] == 50


def test_arrival_refresh_tago_uses_node_id_as_core_station_by_default(monkeypatch):
    def fake_fetch_station_arrivals(**kwargs):
        return (
            TagoArrival(
                "NODE1",
                "정류장",
                "R1",
                "1",
                None,
                60,
                521,
            ),
        )

    monkeypatch.setattr(app_module, "fetch_station_arrivals", fake_fetch_station_arrivals)

    response = client.get(
        "/api/arrivals/refresh",
        params={
            "source": "tago",
            "city_code": "22",
            "node_id": "NODE1",
            "current_minute": 520,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["station_id"] == "NODE1"
    assert data["core_arrivals"][0]["station_id"] == "NODE1"


def test_setup_check_is_user_friendly():
    response = client.get("/api/setup/check")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["timezone"]["windows_safe"] is True
    assert "start_all_windows.bat" in body["windows_commands"]


def test_assess_existing_routes_accepts_static_arrivals():
    response = client.post(
        "/api/routes/assess",
        json={
            "current_minute": 520,
            "routes": [
                {
                    "id": "candidate-a",
                    "requested_start_minute": 520,
                    "segments": [
                        {
                            "route_id": "101",
                            "from_station_id": "A",
                            "to_station_id": "B",
                            "departure_minute": 524,
                            "arrival_minute": 540,
                        },
                        {
                            "route_id": "708",
                            "from_station_id": "B",
                            "to_station_id": "C",
                            "departure_minute": 552,
                            "arrival_minute": 570,
                        },
                    ],
                    "transfers": [
                        {
                            "from_station_id": "B",
                            "to_station_id": "B",
                            "arrival_minute": 540,
                            "walking_minutes": 4,
                            "minimum_buffer_minutes": 3,
                            "target_route_id": "708",
                            "candidate_arrivals": [
                                {"station_id": "B", "route_id": "708", "arrival_minute": 552}
                            ],
                        }
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "existing_route_assessment"
    assert "does not claim to replace" in data["scope"]
    assert data["routes"][0]["status"] == "safe"
    assert data["routes"][0]["initial_wait_minutes"] == 4


def test_assess_existing_routes_can_merge_live_tago_arrivals(monkeypatch):
    def fake_fetch_station_arrivals(**kwargs):
        assert kwargs["city_code"] == "22"
        assert kwargs["node_id"] == "NODE-B"
        return (
            TagoArrival("NODE-B", "환승정류장", "ROUTE708", "708", None, 120, 552),
        )

    monkeypatch.setattr(app_module, "fetch_station_arrivals", fake_fetch_station_arrivals)

    response = client.post(
        "/api/routes/assess",
        json={
            "current_minute": 520,
            "tago_arrival_sources": [
                {
                    "station_id": "B",
                    "city_code": "22",
                    "node_id": "NODE-B",
                    "route_key": "route_no",
                }
            ],
            "routes": [
                {
                    "id": "candidate-live",
                    "requested_start_minute": 520,
                    "segments": [
                        {
                            "route_id": "101",
                            "from_station_id": "A",
                            "to_station_id": "B",
                            "departure_minute": 524,
                            "arrival_minute": 540,
                        },
                        {
                            "route_id": "708",
                            "from_station_id": "B",
                            "to_station_id": "C",
                            "departure_minute": 552,
                            "arrival_minute": 570,
                        },
                    ],
                    "transfers": [
                        {
                            "from_station_id": "B",
                            "to_station_id": "B",
                            "arrival_minute": 540,
                            "walking_minutes": 4,
                            "minimum_buffer_minutes": 3,
                            "target_route_id": "708",
                            "candidate_arrivals": [],
                        }
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["live_arrival_sources"][0]["arrival_count"] == 1
    assert data["routes"][0]["transfers"][0]["board_minute"] == 552


def test_kakao_config_reports_missing_key(monkeypatch):
    def fake_read_config_value(name):
        assert name == "KAKAO_MAP_JAVASCRIPT_KEY"
        return None, None

    monkeypatch.setattr(app_module, "read_config_value", fake_read_config_value)

    response = client.get("/api/kakao/config")

    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is False
    assert data["app_key"] is None


def test_kakao_config_returns_public_javascript_key(monkeypatch):
    def fake_read_config_value(name):
        if name == "KAKAO_MAP_JAVASCRIPT_KEY":
            return "js-key", ".env"
        return None, None

    monkeypatch.setattr(app_module, "read_config_value", fake_read_config_value)

    response = client.get("/api/kakao/config")

    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is True
    assert data["app_key"] == "js-key"
    assert data["sdk_url"] == "https://dapi.kakao.com/v2/maps/sdk.js"


def test_quick_assessment_endpoint_is_friendly():
    response = client.post(
        "/api/routes/assess/quick",
        json={
            "id": "quick",
            "requested_start_minute": 520,
            "origin_station_id": "A",
            "transfer_station_id": "B",
            "destination_station_id": "C",
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
    )

    assert response.status_code == 200
    route = response.json()["route"]
    assert route["status_label"] == "안전"
    assert "추천" in route["recommendation"]
    assert route["transfers"][0]["status_label"] == "안전"
    assert route["segments"][0]["route_id"] == "101"


def test_quick_assessment_rejects_bad_time_order():
    response = client.post(
        "/api/routes/assess/quick",
        json={
            "requested_start_minute": 600,
            "first_route_id": "101",
            "second_route_id": "708",
            "first_departure_minute": 590,
            "transfer_arrival_minute": 610,
            "second_departure_minute": 620,
            "final_arrival_minute": 640,
            "next_vehicle_arrival_minutes": [620],
        },
    )

    assert response.status_code == 422


def test_route_assessment_includes_korean_explanation():
    response = client.post(
        "/api/routes/rank",
        json={
            "routes": [
                {
                    "id": "simple",
                    "requested_start_minute": 100,
                    "segments": [
                        {
                            "route_id": "R1",
                            "from_station_id": "A",
                            "to_station_id": "B",
                            "departure_minute": 105,
                            "arrival_minute": 120,
                        }
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200
    route = response.json()["routes"][0]
    assert route["status_label"] == "안전"
    assert "summary" in route
    assert route["score_breakdown"]["meaning"] == "Lower ranking_score is better."


def test_quick_demo_presets_endpoint_is_classroom_friendly():
    response = client.get("/api/demo/quick-presets")

    assert response.status_code == 200
    data = response.json()
    assert "safe" in data["presets"]
    assert "tight" in data["presets"]
    assert "missed" in data["presets"]
    assert data["station_locations"]["A"]["name"] == "대구역"
    assert "TAGO" in data["message"]


def test_route_assessment_includes_guidance_fields():
    response = client.post(
        "/api/routes/assess/quick",
        json={
            "id": "tight",
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
    )

    assert response.status_code == 200
    route = response.json()["route"]
    assert route["confidence_label"] in {"높음", "보통", "낮음"}
    assert route["risk_warnings"]
    assert route["next_steps"]


def test_plan_tago_from_coordinates_uses_nearby_stations_and_discovery(monkeypatch):
    def fake_fetch_nearby_stations(**kwargs):
        lat = kwargs["lat"]
        if lat > 35.87:
            return (
                TagoStation("22", "ORIGIN1", "출발정류장", 35.875, 128.596),
                TagoStation("22", "ORIGIN2", "출발정류장2", 35.876, 128.597),
            )
        return (TagoStation("22", "DEST1", "도착정류장", 35.864, 128.593),)

    def fake_discover_tago_route_candidates(**kwargs):
        kwargs["diagnostics"].update(
            {
                "origin_arrivals": [
                    {"route_id": "R1", "route_no": "101", "arrival_minute": 505}
                ],
                "origin_routes": [{"route_id": "R1", "route_no": "101"}],
            }
        )
        assert kwargs["city_code"] == "22"
        assert kwargs["origin_node_id"] == "ORIGIN1"
        assert kwargs["destination_node_id"] == "DEST1"
        return (
            RouteCandidate(
                id="live-plan-1",
                requested_start_minute=500,
                segments=(
                    RouteSegment(
                        route_id="R1",
                        from_station_id="ORIGIN1",
                        to_station_id="DEST1",
                        departure_minute=505,
                        arrival_minute=530,
                    ),
                ),
            ),
        )

    monkeypatch.setattr(app_module, "fetch_nearby_stations", fake_fetch_nearby_stations)
    monkeypatch.setattr(
        app_module,
        "discover_tago_route_candidates",
        fake_discover_tago_route_candidates,
    )

    response = client.post(
        "/api/routes/plan/tago",
        json={
            "city_code": "22",
            "origin": {"lat": 35.8759, "lon": 128.5961},
            "destination": {"lat": 35.8649, "lon": 128.5935},
            "current_minute": 500,
            "max_origin_stations": 1,
            "max_destination_stations": 1,
            "max_station_pairs": 1,
            "use_live_arrival_discovery": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "coordinate_to_nearby_station_plan"
    assert data["origin_stations"][0]["node_id"] == "ORIGIN1"
    assert data["destination_stations"][0]["node_id"] == "DEST1"
    assert data["attempts"][0]["route_count"] == 1
    assert data["routes"][0]["segments"][0]["route_id"] == "R1"
    assert data["station_locations"]["ORIGIN1"]["name"] == "출발정류장"
    assert data["diagnostics"]["status"] == "routes_found"
    assert data["diagnostics"]["origin_arrivals"][0]["routes"][0]["route_no"] == "101"


def test_plan_tago_from_coordinates_returns_empty_routes_with_attempt_errors(monkeypatch):
    def fake_fetch_nearby_stations(**kwargs):
        if kwargs["lat"] > 35.87:
            return (TagoStation("22", "ORIGIN1", "출발정류장", 35.875, 128.596),)
        return (TagoStation("22", "DEST1", "도착정류장", 35.864, 128.593),)

    def fake_discover_tago_route_candidates(**kwargs):
        raise TagoRouteBuildError("no usable route")

    monkeypatch.setattr(app_module, "fetch_nearby_stations", fake_fetch_nearby_stations)
    monkeypatch.setattr(
        app_module,
        "discover_tago_route_candidates",
        fake_discover_tago_route_candidates,
    )
    monkeypatch.setattr(
        app_module,
        "discover_tago_topology_candidates",
        lambda **kwargs: (),
    )

    response = client.post(
        "/api/routes/plan/tago",
        json={
            "origin": {"lat": 35.8759, "lon": 128.5961},
            "destination": {"lat": 35.8649, "lon": 128.5935},
            "current_minute": 500,
            "max_station_pairs": 1,
            "use_live_arrival_discovery": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["city_code"] == "22"
    assert data["routes"] == []
    assert data["attempts"][0]["error"] == "no usable route"
    assert data["diagnostics"]["status"] == "no_routes"
    assert data["diagnostics"]["checked_origin_stops"][0]["name"] == "출발정류장"
    assert data["diagnostics"]["checked_destination_stops"][0]["name"] == "도착정류장"
    assert data["diagnostics"]["possible_causes"]
    assert data["diagnostics"]["suggestions"]


def test_zero_route_diagnostics_deduplicate_and_bound_origin_routes():
    origin = (TagoStation("22", "ORIGIN1", "출발정류장", 35.875, 128.596),)
    destination = (
        TagoStation("22", "DEST1", "도착정류장1", 35.864, 128.593),
        TagoStation("22", "DEST2", "도착정류장2", 35.863, 128.592),
    )
    routes = [
        {"route_id": f"R{index}", "route_no": str(index)}
        for index in range(25)
    ]
    attempts = [
        {
            "origin_node_id": "ORIGIN1",
            "origin_name": "출발정류장",
            "destination_node_id": destination[index].node_id,
            "origin_routes": routes,
            "origin_arrivals": [],
        }
        for index in range(2)
    ]

    diagnostics = app_module._live_plan_diagnostics(
        ranked_count=0,
        origin_candidates=origin,
        destination_candidates=destination,
        attempts=attempts,
    )

    assert len(diagnostics["origin_arrivals"]) == 1
    detail = diagnostics["origin_arrivals"][0]
    assert detail["route_count"] == 25
    assert len(detail["routes"]) == 20
    assert detail["routes_truncated"] is True


def test_plan_city_codes_preserve_boundary_regions():
    origin = (TagoStation("22", "A", "대구정류장", 35.8, 128.6),)
    destination = (TagoStation("37100", "B", "경산정류장", 35.82, 128.72),)

    codes = app_module._select_plan_city_codes(
        requested_city_code=None,
        requested_city_codes=[],
        origin_stations=origin,
        destination_stations=destination,
    )

    assert codes == ("22",)


def test_plan_city_codes_use_gyeongsan_only_for_gyeongsan_trip():
    origin = (TagoStation("37100", "GYB-A", "자인정류장", 35.82, 128.72),)
    destination = (
        TagoStation("37100", "GYB-B", "경산중앙병원", 35.81, 128.74),
    )

    codes = app_module._select_plan_city_codes(
        requested_city_code=None,
        requested_city_codes=[],
        origin_stations=origin,
        destination_stations=destination,
    )

    assert codes == ("37100",)

    mixed_stations = (
        TagoStation("22", "DGB-A", "자인정류장", 35.82, 128.72),
        TagoStation("37100", "GYB-A", "자인정류장", 35.82, 128.72),
    )
    selected = app_module._station_candidates_for_cities(
        mixed_stations, codes, limit=5
    )
    assert [station.node_id for station in selected] == ["GYB-A"]


def test_explicit_gyeongsan_regions_override_misleading_dgb_nearby_order():
    dgb = TagoStation("22", "DGB-A", "자인정류장", 35.82, 128.72)
    gyb = TagoStation("37100", "GYB-A", "자인정류장", 35.82, 128.72)

    codes = app_module._select_plan_city_codes(
        requested_city_code=None,
        requested_city_codes=[],
        origin_stations=(dgb, gyb),
        destination_stations=(dgb, gyb),
        origin_region="gyeongsan",
        destination_region="gyeongsan",
    )

    assert codes == ("37100",)


def test_explicit_daegu_gyeongsan_trip_uses_daegu_boundary_feed():
    dgb = TagoStation("22", "DGB-A", "대구정류장", 35.86, 128.60)
    gyb = TagoStation("37100", "GYB-A", "경산정류장", 35.82, 128.72)

    codes = app_module._select_plan_city_codes(
        requested_city_code=None,
        requested_city_codes=[],
        origin_stations=(gyb, dgb),
        destination_stations=(dgb, gyb),
        origin_region="gyeongsan",
        destination_region="daegu",
    )

    assert codes == ("22",)


def test_station_candidates_include_mirrors_outside_physical_stop_limit():
    stations = (
        TagoStation("22", "DGB-A", "자인정류장", 35.8, 128.7),
        TagoStation("22", "DGB-B", "자인정류장 건너", 35.8, 128.7),
        TagoStation("22", "DGB-C", "자인초교", 35.8, 128.7),
        TagoStation("37100", "GYB-A", "자인정류장", 35.8, 128.7),
        TagoStation("37100", "GYB-B", "자인정류장 건너", 35.8, 128.7),
    )

    selected = app_module._station_candidates_for_cities(
        stations, ("22", "37100"), limit=3
    )

    assert [station.node_id for station in selected] == [
        "DGB-A",
        "GYB-A",
        "DGB-B",
        "GYB-B",
        "DGB-C",
    ]


def test_clock_format_uses_hhmm_and_day_offset():
    assert app_module._format_clock_minute(5) == "00:05"
    assert app_module._format_clock_minute(520) == "08:40"
    assert app_module._format_clock_minute(1450) == "+1일 00:10"


def test_plan_tago_uses_topology_fallback_when_live_discovery_is_empty(monkeypatch):
    def fake_fetch_nearby_stations(**kwargs):
        if kwargs["lat"] > 35.87:
            return (TagoStation("22", "ORIGIN1", "출발정류장", 35.875, 128.596),)
        return (TagoStation("22", "DEST1", "도착정류장", 35.864, 128.593),)

    fallback = RouteCandidate(
        id="topology-fallback",
        requested_start_minute=500,
        segments=(
            RouteSegment(
                route_id="101",
                from_station_id="ORIGIN1",
                to_station_id="DEST1",
                departure_minute=510,
                arrival_minute=530,
            ),
        ),
    )
    monkeypatch.setattr(app_module, "fetch_nearby_stations", fake_fetch_nearby_stations)
    def failed_live_discovery(**kwargs):
        raise TagoRouteBuildError("live arrivals unavailable")

    monkeypatch.setattr(
        app_module, "discover_tago_route_candidates", failed_live_discovery
    )
    monkeypatch.setattr(
        app_module, "discover_tago_topology_candidates", lambda **kwargs: (fallback,)
    )

    response = client.post(
        "/api/routes/plan/tago",
        json={
            "origin": {"lat": 35.8759, "lon": 128.5961},
            "destination": {"lat": 35.8649, "lon": 128.5935},
            "current_minute": 500,
            "max_station_pairs": 1,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["routes"][0]["route_id"] == "topology-fallback"
    assert data["attempts"][0]["discovery_source"] == "route_topology_primary"
    assert data["attempts"][0]["live_error"] == "live arrivals unavailable"
    assert "추정값" in data["attempts"][0]["notice"]


def test_route_itinerary_lists_board_via_and_alight_stops():
    route = RouteCandidate(
        id="tago-topology-direct-R1",
        requested_start_minute=500,
        segments=(RouteSegment("101", "A", "C", 510, 530),),
    )
    stops = (
        TagoRouteStop("22", "R1", "101", "A", "출발정류장", 1),
        TagoRouteStop("22", "R1", "101", "B", "중간정류장", 2),
        TagoRouteStop("22", "R1", "101", "C", "도착정류장", 3),
    )

    itinerary = app_module._route_itinerary(
        route,
        route_stop_caches={"22": {"R1": stops}},
        station_locations={},
    )

    assert itinerary[0]["board_stop_name"] == "출발정류장"
    assert itinerary[0]["via_stop_names"] == ["중간정류장"]
    assert itinerary[0]["alight_stop_name"] == "도착정류장"
    assert itinerary[0]["board_time"] == "08:30"
    assert itinerary[0]["arrival_estimated"] is True
    assert "정확한 정류소별 운행 시간표가 아닙니다" in itinerary[0][
        "accuracy_notice"
    ]


def test_plan_tago_includes_direct_subway_candidate_from_place_names(monkeypatch):
    def fake_fetch_nearby_stations(**kwargs):
        if kwargs["lat"] > 35.87:
            return (TagoStation("22", "BUS-A", "대구역버스", 35.875, 128.596),)
        return (TagoStation("22", "BUS-C", "반월당버스", 35.864, 128.593),)

    subway = RouteCandidate(
        id="tago-subway-direct-DGU1-A-C",
        requested_start_minute=500,
        segments=(
            RouteSegment(
                route_id="대구 1호선",
                from_station_id="SUBWAY-A",
                to_station_id="SUBWAY-C",
                departure_minute=505,
                arrival_minute=525,
            ),
        ),
    )
    monkeypatch.setattr(app_module, "fetch_nearby_stations", fake_fetch_nearby_stations)
    monkeypatch.setattr(
        app_module, "discover_subway_candidates", lambda **kwargs: (subway,)
    )
    monkeypatch.setattr(
        app_module, "discover_tago_topology_candidates", lambda **kwargs: ()
    )

    response = client.post(
        "/api/routes/plan/tago",
        json={
            "origin": {"lat": 35.8759, "lon": 128.5961},
            "destination": {"lat": 35.8649, "lon": 128.5935},
            "origin_name": "대구역",
            "destination_name": "반월당역",
            "current_minute": 500,
            "max_station_pairs": 1,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["routes"][0]["segments"][0]["route_id"] == "대구 1호선"
    assert data["attempts"][0]["discovery_source"] == "tago_subway_same_line"
    assert data["station_locations"]["SUBWAY-A"]["name"] == "대구역"
