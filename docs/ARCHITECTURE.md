# Architecture

TransitGuard is structured as a small assessment engine rather than a complete route planner.

```text
existing route candidates
        |
        v
core assessment logic
        |
        v
safe / tight / missed / unknown + ranking score
```

## Core

`src/transitguard/core` contains pure Python logic. It validates route candidates, checks transfer timing, calculates reliability, and ranks supplied candidates.

The core layer does not fetch TAGO data, does not load Kakao Map, and does not depend on FastAPI.

## Adapters

`src/transitguard/adapters` contains optional input adapters.

- `tago.py`: reads configuration, fetches TAGO arrivals/stops/route-stop data, and converts live arrivals into core `Arrival` objects.
- `timetable_csv.py`: small CSV loader for local experiments.

The adapters provide data to the assessment engine. They are not the central route-search engine.

## API

`src/transitguard/api/app.py` exposes the assessment workflow through FastAPI.

The main endpoint is:

```text
POST /api/routes/assess
```

It accepts route candidates and optional TAGO arrival sources. TAGO route-discovery endpoints are kept as experimental helpers, but they are not the primary project claim.

The API also exposes:

```text
POST /api/routes/plan/tago
GET /api/kakao/config
```

`/api/routes/plan/tago` is a practical live wrapper: it turns coordinates into nearby TAGO stops, then uses bounded TAGO discovery to evaluate candidate reliability. It is intentionally limited so API calls remain reasonable. `/api/kakao/config` only helps the static browser demo load Kakao Map with a configured JavaScript key.

## Web demo

`web-demo` is a small UI for quick examples, existing-route JSON assessment, and a practical live mode.

When `KAKAO_MAP_JAVASCRIPT_KEY` is configured, the same demo can load Kakao Map, search places, save map coordinates to internal station IDs or live origin/destination coordinates, find nearby TAGO stops, and draw assessed route candidates as markers and polylines.

Kakao Map is a visualization layer. It does not replace the TransitGuard assessment engine and does not make the project a full transit router.
