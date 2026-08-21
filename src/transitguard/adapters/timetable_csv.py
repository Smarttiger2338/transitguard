import csv
from pathlib import Path

from transitguard.core.models import Arrival, Coordinate, Station


def load_stations(path: str | Path) -> list[Station]:
    return [
        Station(
            id=row["id"],
            name=row["name"],
            coordinate=Coordinate(float(row["lat"]), float(row["lon"])),
            opposite_id=row.get("opposite_id") or None,
        )
        for row in _read_rows(path)
    ]


def load_arrivals(path: str | Path) -> list[Arrival]:
    return [
        Arrival(
            station_id=row["station_id"],
            route_id=row["route_id"],
            arrival_minute=int(row["arrival_minute"]),
        )
        for row in _read_rows(path)
    ]


def _read_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))
