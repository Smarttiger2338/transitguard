import json
from pathlib import Path

import pytest

from transitguard.adapters import tago
from transitguard.adapters.tago import (
    TagoApiError,
    TagoArrival,
    TagoRouteStop,
    build_tago_route_candidates,
    fetch_nearby_stations,
    fetch_route_stops,
    fetch_station_arrivals,
    fetch_station_routes,
    fetch_subway_stations,
    load_tago_config,
)


class _FakeHeaders:
    def get_content_charset(self):
        return "utf-8"


class _FakeResponse:
    headers = _FakeHeaders()

    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def test_fetch_station_routes_uses_lowercase_nodeid_and_deduplicates(monkeypatch):
    requested_urls = []

    def fake_urlopen(url, timeout):
        requested_urls.append(url)
        return _FakeResponse(
            '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
            '"body":{"pageNo":"1","numOfRows":"100","totalCount":"3",'
            '"items":{"item":['
            '{"routeid":"R1","routeno":"101"},'
            '{"routeid":"R1","routeno":"101"},'
            '{"routeid":"R2","routeno":"102"}]}}}}'
        )

    monkeypatch.setattr(tago, "urlopen", fake_urlopen)

    routes = fetch_station_routes("22", "STOP1", service_key="key")

    assert [route.route_id for route in routes] == ["R1", "R2"]
    assert "nodeid=STOP1" in requested_urls[0]
    assert "nodeId=" not in requested_urls[0]


def test_fetch_station_routes_rejects_city_wide_response(monkeypatch):
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {
                "items": {
                    "item": [
                        {"routeid": f"R{index}", "routeno": str(index)}
                        for index in range(61)
                    ]
                }
            },
        }
    }

    monkeypatch.setattr(
        tago,
        "urlopen",
        lambda url, timeout: _FakeResponse(json.dumps(payload)),
    )

    with pytest.raises(TagoApiError, match="unfiltered city-wide route list"):
        fetch_station_routes("22", "STOP1", service_key="key")


def test_fetch_station_routes_keeps_many_gyeongsan_branch_routes(monkeypatch):
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "OK"},
            "body": {
                "items": {
                    "item": [
                        {"routeid": f"GYB-R{index}", "routeno": "399"}
                        for index in range(96)
                    ]
                }
            },
        }
    }
    monkeypatch.setattr(
        tago,
        "urlopen",
        lambda url, timeout: _FakeResponse(json.dumps(payload)),
    )

    routes = fetch_station_routes(
        "37100", "GYB360034170", service_key="key"
    )

    assert len(routes) == 96


def test_topology_discovery_skips_one_broken_branch_route(monkeypatch):
    station_routes = {
        "A": (
            tago.TagoStationRoute("BROKEN", "399"),
            tago.TagoStationRoute("WORKING", "399"),
        ),
        "C": (),
    }
    monkeypatch.setattr(
        tago,
        "fetch_station_routes",
        lambda city_code, node_id, **kwargs: station_routes[node_id],
    )

    def fake_route_stops(city_code, route_id, **kwargs):
        if route_id == "BROKEN":
            raise TagoApiError("temporary malformed response")
        return (
            TagoRouteStop("37100", route_id, "399", "A", "자인정류장", 1, 35.8, 128.8),
            TagoRouteStop("37100", route_id, "399", "C", "경산역", 2, 35.82, 128.72),
        )

    monkeypatch.setattr(tago, "fetch_route_stops", fake_route_stops)

    candidates = tago.discover_tago_topology_candidates(
        city_code="37100",
        origin_node_id="A",
        destination_node_id="C",
        current_minute=480,
    )

    assert len(candidates) == 1
    assert candidates[0].segments[0].route_id == "399"


def test_tago_call_budget_stops_additional_http_requests(monkeypatch):
    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        return _FakeResponse(
            '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
            '"body":{"items":""}}}'
        )

    monkeypatch.setattr(tago, "urlopen", fake_urlopen)

    with tago.use_tago_call_budget(1) as budget:
        fetch_station_routes("22", "STOP1", service_key="key")
        with pytest.raises(TagoApiError, match="call budget exhausted"):
            fetch_station_routes("22", "STOP2", service_key="key")

    assert len(calls) == 1
    assert budget.used == 1
    assert budget.remaining == 0


def test_common_gateway_xml_is_reported_as_tago_api_error(monkeypatch):
    monkeypatch.setattr(
        tago,
        "urlopen",
        lambda url, timeout: _FakeResponse(
            "<OpenAPI_ServiceResponse><cmmMsgHeader>"
            "<errMsg>SERVICE ERROR</errMsg>"
            "<returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg>"
            "<returnReasonCode>22</returnReasonCode>"
            "</cmmMsgHeader></OpenAPI_ServiceResponse>"
        ),
    )

    with pytest.raises(TagoApiError, match="API error 22"):
        fetch_station_routes("22", "STOP1", service_key="key")


def test_subway_station_uses_route_name_when_route_id_is_omitted(monkeypatch):
    monkeypatch.setattr(
        tago,
        "urlopen",
        lambda url, timeout: _FakeResponse(
            '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
            '"body":{"items":{"item":{'
            '"subwayStationId":"MTRDG20243",'
            '"subwayStationName":"임당",'
            '"subwayRouteName":"2호선"}}}}}'
        ),
    )

    stations = fetch_subway_stations("임당", service_key="key")

    assert stations[0].route_id == "2호선"
    assert stations[0].route_name == "2호선"


def test_load_tago_config_reads_dotenv_when_environment_is_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("TAGO_SERVICE_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    Path(".env").write_text("TAGO_SERVICE_KEY=from-dotenv\n", encoding="utf-8")

    config = load_tago_config()

    assert config.available is True
    assert config.service_key == "from-dotenv"
    assert config.source == ".env"


def test_load_tago_config_can_use_explicit_env_file(monkeypatch, tmp_path):
    env_file = tmp_path / "custom.env"
    env_file.write_text("TAGO_SERVICE_KEY=explicit-key\n", encoding="utf-8")
    monkeypatch.delenv("TAGO_SERVICE_KEY", raising=False)
    monkeypatch.setenv("TRANSITGUARD_ENV_FILE", str(env_file))

    config = load_tago_config()

    assert config.service_key == "explicit-key"


def test_fetch_station_arrivals_parses_tago_json(monkeypatch):
    captured = {}

    def fake_urlopen(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return _FakeResponse(
            '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
            '"body":{"items":{"item":{'
            '"nodeid":"DGB123","nodenm":"동대구역","routeid":"DGB708",'
            '"routeno":"708","routetp":"간선","arrtime":"125",'
            '"arrprevstationcnt":"3","vehicletp":"저상버스"}}}}}'
        )

    monkeypatch.setattr(tago, "urlopen", fake_urlopen)

    arrivals = fetch_station_arrivals(
        "22",
        "DGB123",
        current_minute=520,
        service_key="encoded%2Bkey",
    )

    assert len(arrivals) == 1
    assert arrivals[0].route_id == "DGB708"
    assert arrivals[0].route_no == "708"
    assert arrivals[0].arrival_seconds == 125
    assert arrivals[0].arrival_minute == 523
    assert captured["url"].startswith("https://apis.data.go.kr/")
    assert "serviceKey=encoded%2Bkey" in captured["url"]
    assert "cityCode=22" in captured["url"]
    assert "nodeId=DGB123" in captured["url"]


def test_fetch_station_arrivals_raises_for_tago_error(monkeypatch):
    def fake_urlopen(url, timeout):
        return _FakeResponse(
            '{"response":{"header":{"resultCode":"99","resultMsg":"bad key"},'
            '"body":{"items":""}}}'
        )

    monkeypatch.setattr(tago, "urlopen", fake_urlopen)

    with pytest.raises(TagoApiError, match="99"):
        fetch_station_arrivals("22", "DGB123", current_minute=520, service_key="bad")


def test_fetch_nearby_stations_parses_tago_json(monkeypatch):
    def fake_urlopen(url, timeout):
        assert "getCrdntPrxmtSttnList" in url
        assert "gpsLati=35.87" in url
        assert "gpsLong=128.6" in url
        return _FakeResponse(
            '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
            '"body":{"items":{"item":{'
            '"citycode":"22","nodeid":"DGB001","nodenm":"대구역앞",'
            '"gpslati":"35.875","gpslong":"128.596"}}}}}'
        )

    monkeypatch.setattr(tago, "urlopen", fake_urlopen)

    stations = fetch_nearby_stations(lat=35.87, lon=128.60, service_key="key")

    assert len(stations) == 1
    assert stations[0].city_code == "22"
    assert stations[0].node_id == "DGB001"
    assert stations[0].lat == 35.875


def test_fetch_route_stops_parses_tago_json(monkeypatch):
    def fake_urlopen(url, timeout):
        assert "getRouteAcctoThrghSttnList" in url
        assert "routeId=DGB708" in url
        return _FakeResponse(
            '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
            '"body":{"items":{"item":['
            '{"citycode":"22","routeid":"DGB708","routeno":"708",'
            '"nodeid":"DGB002","nodenm":"중앙로","nodeord":"2"},'
            '{"citycode":"22","routeid":"DGB708","routeno":"708",'
            '"nodeid":"DGB001","nodenm":"대구역앞","nodeord":"1"}'
            ']}}}}'
        )

    monkeypatch.setattr(tago, "urlopen", fake_urlopen)

    stops = fetch_route_stops("22", "DGB708", service_key="key")

    assert [stop.node_id for stop in stops] == ["DGB001", "DGB002"]
    assert stops[0].order == 1


def test_fetch_subway_stations_parses_tago_json(monkeypatch):
    def fake_urlopen(url, timeout):
        assert "GetKwrdFndSubwaySttnList" in url
        assert "subwayStationName=%EB%8C%80%EA%B5%AC" in url
        return _FakeResponse(
            '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
            '"body":{"items":{"item":{'
            '"subwaystationid":"DGU001","subwaystationnm":"대구역",'
            '"subwayrouteid":"DGU1","subwayroutename":"대구 1호선"}}}}}'
        )

    monkeypatch.setattr(tago, "urlopen", fake_urlopen)

    stations = fetch_subway_stations("대구", service_key="key")

    assert stations[0].station_id == "DGU001"
    assert stations[0].route_id == "DGU1"
    assert stations[0].route_name == "대구 1호선"


def test_subway_discovery_connects_two_lines_at_banwoldang(monkeypatch):
    responses = {
        "임당": (tago.TagoSubwayStation("L2-A", "임당역", "L2", "대구 2호선"),),
        "대구": (tago.TagoSubwayStation("L1-C", "대구역", "L1", "대구 1호선"),),
        "반월당": (
            tago.TagoSubwayStation("L2-X", "반월당역", "L2", "대구 2호선"),
            tago.TagoSubwayStation("L1-X", "반월당역", "L1", "대구 1호선"),
        ),
        "청라언덕": (),
    }
    monkeypatch.setattr(
        tago, "fetch_subway_stations", lambda name, **kwargs: responses[name]
    )

    routes = tago.discover_subway_candidates(
        origin_name="대구2호선 임당역",
        destination_name="대구역",
        current_minute=500,
    )

    assert len(routes) == 1
    assert [segment.route_id for segment in routes[0].segments] == [
        "대구 2호선",
        "대구 1호선",
    ]
    assert routes[0].transfers[0].from_station_id == "L2-X"
    assert routes[0].transfers[0].to_station_id == "L1-X"


def test_build_tago_route_candidates_uses_real_route_stops_and_arrivals(monkeypatch):
    route_stops = {
        "R1": (
            TagoRouteStop("22", "R1", "1", "A", "출발", 1),
            TagoRouteStop("22", "R1", "1", "B", "환승", 2),
        ),
        "R2": (
            TagoRouteStop("22", "R2", "2", "B", "환승", 1),
            TagoRouteStop("22", "R2", "2", "C", "도착", 3),
        ),
    }

    def fake_fetch_route_stops(city_code, route_id, **kwargs):
        return route_stops[route_id]

    def fake_fetch_station_arrivals(city_code, node_id, *, current_minute, **kwargs):
        if node_id == "A":
            return (TagoArrival("A", "출발", "R1", "1", None, 60, current_minute + 1),)
        if node_id == "B":
            return (TagoArrival("B", "환승", "R2", "2", None, 720, current_minute + 12),)
        return ()

    monkeypatch.setattr(tago, "fetch_route_stops", fake_fetch_route_stops)
    monkeypatch.setattr(tago, "fetch_station_arrivals", fake_fetch_station_arrivals)

    routes = build_tago_route_candidates(
        city_code="22",
        origin_node_id="A",
        destination_node_id="C",
        route_ids=("R1", "R2"),
        current_minute=500,
        average_minutes_per_stop=2,
    )

    assert len(routes) == 1
    assert routes[0].id.startswith("tago-transfer")
    assert [segment.route_id for segment in routes[0].segments] == ["R1", "R2"]
    assert routes[0].transfers[0].candidate_arrivals[0].route_id == "R2"


def test_build_tago_route_candidates_handles_repeated_stops_by_forward_order(monkeypatch):
    route_stops = {
        "R1": (
            TagoRouteStop("22", "R1", "1", "A", "출발", 1),
            TagoRouteStop("22", "R1", "1", "B", "중간", 2),
            TagoRouteStop("22", "R1", "1", "A", "출발 반복", 5),
            TagoRouteStop("22", "R1", "1", "C", "도착", 6),
        )
    }

    def fake_fetch_route_stops(city_code, route_id, **kwargs):
        return route_stops[route_id]

    def fake_fetch_station_arrivals(city_code, node_id, *, current_minute, **kwargs):
        return (TagoArrival("A", "출발", "R1", "1", None, 60, current_minute + 1),)

    monkeypatch.setattr(tago, "fetch_route_stops", fake_fetch_route_stops)
    monkeypatch.setattr(tago, "fetch_station_arrivals", fake_fetch_station_arrivals)

    routes = build_tago_route_candidates(
        city_code="22",
        origin_node_id="A",
        destination_node_id="C",
        route_ids=("R1",),
        current_minute=500,
        average_minutes_per_stop=2,
    )

    assert len(routes) == 1
    assert routes[0].segments[0].arrival_minute == 503


def test_build_tago_route_candidates_keeps_route_directions_separate(monkeypatch):
    route_stops = {
        "R1": (
            TagoRouteStop("22", "R1", "1", "C", "도착", 1, updown_code="0"),
            TagoRouteStop("22", "R1", "1", "A", "출발", 2, updown_code="0"),
            TagoRouteStop("22", "R1", "1", "A", "출발", 1, updown_code="1"),
            TagoRouteStop("22", "R1", "1", "C", "도착", 3, updown_code="1"),
        )
    }

    def fake_fetch_route_stops(city_code, route_id, **kwargs):
        return route_stops[route_id]

    def fake_fetch_station_arrivals(city_code, node_id, *, current_minute, **kwargs):
        return (TagoArrival("A", "출발", "R1", "1", None, 60, current_minute + 1),)

    monkeypatch.setattr(tago, "fetch_route_stops", fake_fetch_route_stops)
    monkeypatch.setattr(tago, "fetch_station_arrivals", fake_fetch_station_arrivals)

    routes = build_tago_route_candidates(
        city_code="22",
        origin_node_id="A",
        destination_node_id="C",
        route_ids=("R1",),
        current_minute=500,
        average_minutes_per_stop=2,
    )

    assert len(routes) == 1
    assert routes[0].segments[0].arrival_minute == 505


def test_discover_tago_route_candidates_finds_direct_without_route_ids(monkeypatch):
    route_stops = {
        "R1": (
            TagoRouteStop("22", "R1", "1", "A", "출발", 1),
            TagoRouteStop("22", "R1", "1", "C", "도착", 4),
        )
    }

    def fake_fetch_route_stops(city_code, route_id, **kwargs):
        return route_stops[route_id]

    def fake_fetch_station_arrivals(city_code, node_id, *, current_minute, **kwargs):
        assert node_id == "A"
        return (TagoArrival("A", "출발", "R1", "1", None, 60, current_minute + 1),)

    monkeypatch.setattr(tago, "fetch_route_stops", fake_fetch_route_stops)
    monkeypatch.setattr(tago, "fetch_station_arrivals", fake_fetch_station_arrivals)

    routes = tago.discover_tago_route_candidates(
        city_code="22",
        origin_node_id="A",
        destination_node_id="C",
        current_minute=500,
        average_minutes_per_stop=2,
    )

    assert len(routes) == 1
    assert routes[0].id.startswith("tago-direct")
    assert routes[0].segments[0].route_id == "R1"


def test_discover_tago_route_candidates_finds_transfer_without_route_ids(monkeypatch):
    route_stops = {
        "R1": (
            TagoRouteStop("22", "R1", "1", "A", "출발", 1),
            TagoRouteStop("22", "R1", "1", "B", "환승", 2),
        ),
        "R2": (
            TagoRouteStop("22", "R2", "2", "B", "환승", 1),
            TagoRouteStop("22", "R2", "2", "C", "도착", 3),
        ),
    }

    def fake_fetch_route_stops(city_code, route_id, **kwargs):
        return route_stops[route_id]

    def fake_fetch_station_arrivals(city_code, node_id, *, current_minute, **kwargs):
        if node_id == "A":
            return (TagoArrival("A", "출발", "R1", "1", None, 60, current_minute + 1),)
        if node_id == "B":
            return (TagoArrival("B", "환승", "R2", "2", None, 720, current_minute + 12),)
        return ()

    monkeypatch.setattr(tago, "fetch_route_stops", fake_fetch_route_stops)
    monkeypatch.setattr(tago, "fetch_station_arrivals", fake_fetch_station_arrivals)

    routes = tago.discover_tago_route_candidates(
        city_code="22",
        origin_node_id="A",
        destination_node_id="C",
        current_minute=500,
        average_minutes_per_stop=2,
    )

    assert len(routes) == 1
    assert routes[0].id.startswith("tago-transfer")
    assert [segment.route_id for segment in routes[0].segments] == ["R1", "R2"]


def test_topology_fallback_supports_walking_between_different_stop_ids(monkeypatch):
    station_routes = {
        "A": (tago.TagoStationRoute("R1", "1"),),
        "C": (tago.TagoStationRoute("R2", "2"),),
    }
    route_stops = {
        "R1": (
            TagoRouteStop("22", "R1", "1", "A", "출발", 1, 35.0, 128.0),
            TagoRouteStop("22", "R1", "1", "B1", "환승하차", 2, 35.001, 128.001),
        ),
        "R2": (
            TagoRouteStop("22", "R2", "2", "B2", "환승승차", 1, 35.0011, 128.0011),
            TagoRouteStop("22", "R2", "2", "C", "도착", 3, 35.01, 128.01),
        ),
    }

    monkeypatch.setattr(
        tago,
        "fetch_station_routes",
        lambda city_code, node_id, **kwargs: station_routes[node_id],
    )
    monkeypatch.setattr(
        tago,
        "fetch_route_stops",
        lambda city_code, route_id, **kwargs: route_stops[route_id],
    )

    routes = tago.discover_tago_topology_candidates(
        city_code="22",
        origin_node_id="A",
        destination_node_id="C",
        current_minute=500,
        max_walking_transfer_m=400,
    )

    assert len(routes) == 1
    assert routes[0].segments[0].to_station_id == "B1"
    assert routes[0].segments[1].from_station_id == "B2"
    assert routes[0].transfers[0].from_station_id == "B1"
    assert routes[0].transfers[0].to_station_id == "B2"


def test_fetch_station_arrivals_fetches_all_pages(monkeypatch):
    requested_urls = []

    def fake_urlopen(url, timeout):
        requested_urls.append(url)
        if "pageNo=1" in url:
            return _FakeResponse(
                '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
                '"body":{"pageNo":"1","numOfRows":"1","totalCount":"2",'
                '"items":{"item":{"nodeid":"A","routeid":"R1","arrtime":"60"}}}}}'
            )
        return _FakeResponse(
            '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
            '"body":{"pageNo":"2","numOfRows":"1","totalCount":"2",'
            '"items":{"item":{"nodeid":"A","routeid":"R2","arrtime":"120"}}}}}'
        )

    monkeypatch.setattr(tago, "urlopen", fake_urlopen)

    arrivals = fetch_station_arrivals(
        "22",
        "A",
        current_minute=500,
        num_of_rows=1,
        service_key="key",
    )

    assert [arrival.route_id for arrival in arrivals] == ["R1", "R2"]
    assert len(requested_urls) == 2


def test_fetch_station_arrivals_rejects_missing_arrtime(monkeypatch):
    def fake_urlopen(url, timeout):
        return _FakeResponse(
            '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
            '"body":{"items":{"item":{"nodeid":"A","routeid":"R1"}}}}}'
        )

    monkeypatch.setattr(tago, "urlopen", fake_urlopen)

    with pytest.raises(TagoApiError, match="arrtime"):
        fetch_station_arrivals("22", "A", current_minute=500, service_key="key")


def test_fetch_nearby_stations_rejects_missing_coordinates(monkeypatch):
    def fake_urlopen(url, timeout):
        return _FakeResponse(
            '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
            '"body":{"items":{"item":{'
            '"citycode":"22","nodeid":"A","nodenm":"정류장"}}}}}'
        )

    monkeypatch.setattr(tago, "urlopen", fake_urlopen)

    with pytest.raises(TagoApiError, match="gpslati"):
        fetch_nearby_stations(lat=35.87, lon=128.6, service_key="key")


def test_build_tago_route_candidates_supports_walking_transfer_between_nearby_stops(
    monkeypatch,
):
    route_stops = {
        "R1": (
            TagoRouteStop("22", "R1", "1", "A", "출발", 1, 35.0, 128.0),
            TagoRouteStop("22", "R1", "1", "B1", "환승1", 2, 35.0000, 128.0000),
        ),
        "R2": (
            TagoRouteStop("22", "R2", "2", "B2", "환승2", 1, 35.0003, 128.0003),
            TagoRouteStop("22", "R2", "2", "C", "도착", 2, 35.0010, 128.0010),
        ),
    }

    def fake_fetch_route_stops(city_code, route_id, **kwargs):
        return route_stops[route_id]

    def fake_fetch_station_arrivals(city_code, node_id, *, current_minute, **kwargs):
        if node_id == "A":
            return (TagoArrival("A", "출발", "R1", "1", None, 60, 501),)
        if node_id == "B2":
            return (TagoArrival("B2", "환승2", "R2", "2", None, 420, 507),)
        return ()

    monkeypatch.setattr(tago, "fetch_route_stops", fake_fetch_route_stops)
    monkeypatch.setattr(tago, "fetch_station_arrivals", fake_fetch_station_arrivals)

    routes = build_tago_route_candidates(
        city_code="22",
        origin_node_id="A",
        destination_node_id="C",
        route_ids=("R1", "R2"),
        current_minute=500,
        average_minutes_per_stop=2,
        walking_minutes=0,
        minimum_buffer_minutes=0,
        max_walking_transfer_m=100,
    )

    assert len(routes) == 1
    route = routes[0]
    assert route.transfers[0].from_station_id == "B1"
    assert route.transfers[0].to_station_id == "B2"
    assert route.segments[1].from_station_id == "B2"


def test_build_tago_route_candidates_splits_uncoded_direction_runs(monkeypatch):
    route_stops = {
        "R1": (
            TagoRouteStop("22", "R1", "1", "C", "도착", 1),
            TagoRouteStop("22", "R1", "1", "A", "출발", 2),
            TagoRouteStop("22", "R1", "1", "A", "출발", 1),
            TagoRouteStop("22", "R1", "1", "C", "도착", 3),
        )
    }

    def fake_fetch_route_stops(city_code, route_id, **kwargs):
        return route_stops[route_id]

    def fake_fetch_station_arrivals(city_code, node_id, *, current_minute, **kwargs):
        return (TagoArrival("A", "출발", "R1", "1", None, 60, current_minute + 1),)

    monkeypatch.setattr(tago, "fetch_route_stops", fake_fetch_route_stops)
    monkeypatch.setattr(tago, "fetch_station_arrivals", fake_fetch_station_arrivals)

    routes = build_tago_route_candidates(
        city_code="22",
        origin_node_id="A",
        destination_node_id="C",
        route_ids=("R1",),
        current_minute=500,
        average_minutes_per_stop=2,
    )

    assert len(routes) == 1
    assert routes[0].segments[0].arrival_minute == 505


def test_discover_tago_route_candidates_includes_nearby_walking_transfer(monkeypatch):
    route_stops = {
        "R1": (
            TagoRouteStop("22", "R1", "1", "A", "출발", 1, 35.0, 128.0),
            TagoRouteStop("22", "R1", "1", "B1", "하차", 2, 35.0000, 128.0000),
        ),
        "R2": (
            TagoRouteStop("22", "R2", "2", "B2", "승차", 1, 35.0003, 128.0003),
            TagoRouteStop("22", "R2", "2", "C", "도착", 3, 35.0010, 128.0010),
        ),
    }

    def fake_fetch_route_stops(city_code, route_id, **kwargs):
        return route_stops[route_id]

    def fake_fetch_nearby_stations(**kwargs):
        return (tago.TagoStation("22", "B2", "승차", 35.0003, 128.0003),)

    def fake_fetch_station_arrivals(city_code, node_id, *, current_minute, **kwargs):
        if node_id == "A":
            return (TagoArrival("A", "출발", "R1", "1", None, 60, current_minute + 1),)
        if node_id == "B2":
            return (TagoArrival("B2", "승차", "R2", "2", None, 600, current_minute + 10),)
        return ()

    monkeypatch.setattr(tago, "fetch_route_stops", fake_fetch_route_stops)
    monkeypatch.setattr(tago, "fetch_nearby_stations", fake_fetch_nearby_stations)
    monkeypatch.setattr(tago, "fetch_station_arrivals", fake_fetch_station_arrivals)

    routes = tago.discover_tago_route_candidates(
        city_code="22",
        origin_node_id="A",
        destination_node_id="C",
        current_minute=500,
        average_minutes_per_stop=2,
        walking_minutes=0,
        minimum_buffer_minutes=0,
        max_walking_transfer_m=100,
    )

    assert len(routes) == 1
    assert routes[0].transfers[0].from_station_id == "B1"
    assert routes[0].transfers[0].to_station_id == "B2"


def test_fetch_station_arrivals_can_fetch_single_page(monkeypatch):
    requested_urls = []

    def fake_urlopen(url, timeout):
        requested_urls.append(url)
        return _FakeResponse(
            '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
            '"body":{"pageNo":"1","numOfRows":"1","totalCount":"2",'
            '"items":{"item":{"nodeid":"A","routeid":"R1","arrtime":"60"}}}}}'
        )

    monkeypatch.setattr(tago, "urlopen", fake_urlopen)

    arrivals = fetch_station_arrivals(
        "22",
        "A",
        current_minute=500,
        num_of_rows=1,
        service_key="key",
        fetch_all_pages=False,
    )

    assert [arrival.route_id for arrival in arrivals] == ["R1"]
    assert len(requested_urls) == 1


def test_fetch_station_arrivals_can_skip_bad_items_when_not_strict(monkeypatch):
    def fake_urlopen(url, timeout):
        return _FakeResponse(
            '{"response":{"header":{"resultCode":"00","resultMsg":"OK"},'
            '"body":{"items":{"item":['
            '{"nodeid":"A","routeid":"BAD"},'
            '{"nodeid":"A","routeid":"R1","arrtime":"60"}'
            ']}}}}'
        )

    monkeypatch.setattr(tago, "urlopen", fake_urlopen)

    arrivals = fetch_station_arrivals(
        "22",
        "A",
        current_minute=500,
        service_key="key",
        strict_items=False,
    )

    assert [arrival.route_id for arrival in arrivals] == ["R1"]
