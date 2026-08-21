import os

import pytest

from transitguard.adapters.tago import fetch_station_arrivals

pytestmark = pytest.mark.live_tago


def test_live_tago_arrivals_smoke_requires_explicit_ids():
    service_key = os.getenv("TAGO_SERVICE_KEY")
    city_code = os.getenv("TAGO_LIVE_CITY_CODE")
    node_id = os.getenv("TAGO_LIVE_NODE_ID")
    if not (service_key and city_code and node_id):
        pytest.skip("Set TAGO_SERVICE_KEY, TAGO_LIVE_CITY_CODE, and TAGO_LIVE_NODE_ID")

    arrivals = fetch_station_arrivals(
        city_code,
        node_id,
        current_minute=0,
        service_key=service_key,
        fetch_all_pages=False,
        strict_items=False,
    )

    assert isinstance(arrivals, tuple)
