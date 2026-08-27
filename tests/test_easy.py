import pytest

from transitguard.easy import (
    assess_simple_transfer,
    build_simple_transfer_route,
    hhmm_from_minute,
    minute_from_hhmm,
    status_label_ko,
)
from transitguard.core.models import TransferStatus


def test_minute_from_hhmm_accepts_common_time_text():
    assert minute_from_hhmm("08:40") == 520
    assert minute_from_hhmm("24:10") == 1450
    assert minute_from_hhmm(15) == 15


@pytest.mark.parametrize("value", ["", "0840", "08:AA", "08:60", -1])
def test_minute_from_hhmm_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        minute_from_hhmm(value)


def test_hhmm_from_minute_formats_next_day():
    assert hhmm_from_minute(520) == "08:40"
    assert hhmm_from_minute(1450) == "00:10(+1일)"


def test_build_simple_transfer_route_converts_human_input_to_core_model():
    route = build_simple_transfer_route(
        requested_start="08:35",
        origin_station="대구역앞",
        transfer_station="중앙로역",
        destination_station="동대구역건너",
        first_route="101",
        second_route="708",
        first_departure="08:40",
        transfer_arrival="08:55",
        second_departure="09:04",
        final_arrival="09:20",
        next_vehicle_arrivals=["09:04", "09:12"],
        walking_minutes=4,
        minimum_buffer_minutes=3,
    )

    assert route.requested_start_minute == 515
    assert route.segments[0].route_id == "101"
    assert route.segments[1].route_id == "708"
    assert route.transfers[0].target_route_id == "708"
    assert route.transfers[0].candidate_arrivals[0].arrival_minute == 544


def test_assess_simple_transfer_returns_korean_safe_summary():
    result = assess_simple_transfer(
        requested_start="08:35",
        origin_station="대구역앞",
        transfer_station="중앙로역",
        destination_station="동대구역건너",
        first_route="101",
        second_route="708",
        first_departure="08:40",
        transfer_arrival="08:55",
        second_departure="09:06",
        final_arrival="09:22",
        next_vehicle_arrivals=["09:06", "09:12"],
        walking_minutes=4,
        minimum_buffer_minutes=3,
    )

    assert result.evaluation.status == TransferStatus.SAFE
    assert "안전" in result.summary
    assert result.to_dict()["status_label"] == "안전"
    assert result.details["required_transfer_ready_time"] == "09:02"


def test_assess_simple_transfer_returns_korean_missed_summary():
    result = assess_simple_transfer(
        requested_start="08:35",
        origin_station="대구역앞",
        transfer_station="중앙로역",
        destination_station="동대구역건너",
        first_route="101",
        second_route="708",
        first_departure="08:40",
        transfer_arrival="08:55",
        second_departure="09:01",
        final_arrival="09:20",
        next_vehicle_arrivals=["09:01"],
        walking_minutes=4,
        minimum_buffer_minutes=3,
    )

    assert result.evaluation.status == TransferStatus.MISSED
    assert "환승 실패" in result.summary
    assert any("더 늦은" in suggestion for suggestion in result.suggestions)


def test_status_label_ko_covers_all_statuses():
    assert status_label_ko(TransferStatus.SAFE) == "안전"
    assert status_label_ko(TransferStatus.TIGHT) == "촉박"
    assert status_label_ko(TransferStatus.MISSED) == "환승 실패"
    assert status_label_ko(TransferStatus.UNKNOWN) == "정보 부족"
