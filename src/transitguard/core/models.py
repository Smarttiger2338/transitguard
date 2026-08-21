from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import asin, cos, radians, sin, sqrt


class TransferStatus(str, Enum):
    SAFE = "safe"
    TIGHT = "tight"
    MISSED = "missed"
    UNKNOWN = "unknown"


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class Coordinate:
    lat: float
    lon: float

    def __post_init__(self) -> None:
        if not -90 <= self.lat <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not -180 <= self.lon <= 180:
            raise ValueError("longitude must be between -180 and 180")

    def distance_to(self, other: Coordinate) -> float:
        earth_radius_m = 6_371_000
        dlat = radians(other.lat - self.lat)
        dlon = radians(other.lon - self.lon)
        lat1 = radians(self.lat)
        lat2 = radians(other.lat)
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        return earth_radius_m * c


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    coordinate: Coordinate
    opposite_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.id, "station id")
        _require_text(self.name, "station name")
        if self.opposite_id is not None and not self.opposite_id.strip():
            object.__setattr__(self, "opposite_id", None)


@dataclass(frozen=True)
class Arrival:
    station_id: str
    route_id: str
    arrival_minute: int

    def __post_init__(self) -> None:
        _require_text(self.station_id, "arrival station_id")
        _require_text(self.route_id, "arrival route_id")
        if self.arrival_minute < 0:
            raise ValueError("arrival_minute must be non-negative")


@dataclass(frozen=True)
class Transfer:
    from_station_id: str
    to_station_id: str
    arrival_minute: int
    walking_minutes: int
    minimum_buffer_minutes: int
    candidate_arrivals: tuple[Arrival, ...]
    target_route_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.from_station_id, "transfer from_station_id")
        _require_text(self.to_station_id, "transfer to_station_id")
        if self.target_route_id is not None and not self.target_route_id.strip():
            object.__setattr__(self, "target_route_id", None)
        if self.arrival_minute < 0:
            raise ValueError("arrival_minute must be non-negative")
        if self.walking_minutes < 0:
            raise ValueError("walking_minutes must be non-negative")
        if self.minimum_buffer_minutes < 0:
            raise ValueError("minimum_buffer_minutes must be non-negative")
        object.__setattr__(self, "candidate_arrivals", tuple(self.candidate_arrivals))


@dataclass(frozen=True)
class TransferEvaluation:
    status: TransferStatus
    board_minute: int | None
    required_minute: int
    wait_minutes: int | None
    risk_score: float
    reason: str


@dataclass(frozen=True)
class RouteSegment:
    route_id: str
    from_station_id: str
    to_station_id: str
    departure_minute: int
    arrival_minute: int

    def __post_init__(self) -> None:
        _require_text(self.route_id, "segment route_id")
        _require_text(self.from_station_id, "segment from_station_id")
        _require_text(self.to_station_id, "segment to_station_id")
        if self.departure_minute < 0 or self.arrival_minute < 0:
            raise ValueError("segment times must be non-negative")
        if self.arrival_minute < self.departure_minute:
            raise ValueError("arrival_minute must be greater than or equal to departure_minute")


@dataclass(frozen=True)
class RouteCandidate:
    id: str
    segments: tuple[RouteSegment, ...]
    transfers: tuple[Transfer, ...] = field(default_factory=tuple)
    requested_start_minute: int | None = None

    def __post_init__(self) -> None:
        _require_text(self.id, "route candidate id")
        object.__setattr__(self, "segments", tuple(self.segments))
        object.__setattr__(self, "transfers", tuple(self.transfers))
        if not self.segments:
            raise ValueError("route candidate must contain at least one segment")
        if self.requested_start_minute is not None:
            if self.requested_start_minute < 0:
                raise ValueError("requested_start_minute must be non-negative")
            if self.requested_start_minute > self.segments[0].departure_minute:
                raise ValueError("requested_start_minute must not be after first departure")
        self._validate_transfer_sequence()
        self._validate_segment_sequence()

    def _validate_segment_sequence(self) -> None:
        if len(self.segments) <= 1:
            return
        segment_pairs = zip(self.segments, self.segments[1:], strict=False)
        for index, (previous, current) in enumerate(segment_pairs):
            if previous.arrival_minute > current.departure_minute:
                raise ValueError("route segments must be ordered by time")
            if self.transfers:
                transfer = self.transfers[index]
                if previous.to_station_id != transfer.from_station_id:
                    raise ValueError(
                        "transfer from_station_id must match previous segment arrival station"
                    )
                if transfer.to_station_id != current.from_station_id:
                    raise ValueError(
                        "transfer to_station_id must match next segment departure station"
                    )
            elif previous.to_station_id != current.from_station_id:
                raise ValueError("route segments must connect at the same station")

    def _validate_transfer_sequence(self) -> None:
        if not self.transfers:
            return
        if len(self.transfers) != max(0, len(self.segments) - 1):
            raise ValueError("transfer count must match route segment transitions")
        for index, transfer in enumerate(self.transfers):
            previous = self.segments[index]
            next_segment = self.segments[index + 1]
            if transfer.arrival_minute != previous.arrival_minute:
                raise ValueError("transfer arrival_minute must match previous segment arrival time")
            if transfer.target_route_id and transfer.target_route_id != next_segment.route_id:
                raise ValueError("transfer target_route_id must match next segment route_id")


@dataclass(frozen=True)
class RouteEvaluation:
    route_id: str
    status: TransferStatus
    reliability_score: float
    total_minutes: int
    transfer_results: tuple[TransferEvaluation, ...]
    initial_wait_minutes: int = 0
    ranking_score: float = 0.0
