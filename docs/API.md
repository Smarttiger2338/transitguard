# API notes

TransitGuard's main API is focused on assessing **existing route candidates**.
Kakao Map integration is optional and only supports the browser demo's map visualization.

## `GET /api/setup/check`

Checks local setup, TransitGuard version, timezone handling, TAGO key state, and Kakao Map key state.

## `GET /api/kakao/config`

Returns the public Kakao Map JavaScript configuration used by the browser demo.

This endpoint exposes only the browser JavaScript key configured as `KAKAO_MAP_JAVASCRIPT_KEY`.
Kakao JavaScript keys should still be protected with allowed web-platform domains in Kakao Developers.



## `POST /api/routes/plan/tago`

Practical live-flow endpoint. It accepts origin and destination coordinates, finds nearby TAGO stops, runs bounded live-arrival candidate discovery, and returns ranked transfer reliability results.

```bash
curl -X POST http://127.0.0.1:8000/api/routes/plan/tago \
  --header "Content-Type: application/json" \
  --data @examples/plan_tago_coordinates_payload.json
```

This endpoint is designed for the browser demo's **실사용 모드**. It reduces the need for a first-time user to manually know `node_id` or `route_id`. It is still bounded and may miss routes that are not present in live origin-arrival data.

When no route is found, the request still returns `200` with an empty `routes` list and a
`diagnostics` object. The diagnostics list checked origin/destination stops, origin arrivals
and routes, likely causes, and Korean suggestions. The defaults check three stops on each side
and at most six station pairs. Topology responses are cached across pairs to limit repeat calls.

Coordinate planning is topology-first. It stops after three candidates by default. Set
`use_live_arrival_discovery` to `true` only when the slower live-arrival discovery fallback
is explicitly needed; live arrival data is otherwise better used to evaluate found candidates.

When `origin_name` and `destination_name` are supplied, the planner also queries the official
TAGO SubwayInfo station-name endpoint. If both stations share a subway route ID, a direct subway
candidate is returned. Subway departure and travel times are estimates in this alpha version;
one subway transfer is supported for Daegu routes through Banwoldang or Cheongna Hill.
The browser demo supplies `origin_subway_name` and `destination_subway_name` by searching the
nearest Kakao subway category result within 5 km. First/last-mile access and subway times remain
estimates; a verified bus-to-subway timetable join is not yet provided.

## `POST /api/routes/assess/quick`

User-friendly endpoint for one-transfer scenarios. It accepts form-like fields instead of a full route JSON structure.

```bash
curl -X POST http://127.0.0.1:8000/api/routes/assess/quick \
  --header "Content-Type: application/json" \
  --data @examples/assess_quick_payload.json
```

It returns one evaluated route with Korean `status_label`, `summary`, `recommendation`, and a `score_breakdown`. This is the best endpoint for a simple demo or first-time user test.

## `POST /api/routes/assess`

Main endpoint. It accepts route candidates and returns transfer reliability evaluations.

```bash
curl -X POST http://127.0.0.1:8000/api/routes/assess \
  --header "Content-Type: application/json" \
  --data @examples/assess_routes_payload.json
```

The request may include `tago_arrival_sources`. Each source maps a real TAGO stop to the internal station ID used by the route candidate:

```json
{
  "station_id": "B",
  "city_code": "22",
  "node_id": "YOUR_TAGO_TRANSFER_NODE_ID",
  "route_key": "route_no"
}
```

`route_key` controls whether TAGO arrivals are compared by bus number (`route_no`) or official TAGO route ID (`route_id`).

## `POST /api/routes/rank`

Ranks route candidates using only the arrival data already embedded in the payload. This is useful for pure unit tests and offline demonstrations.

## TAGO helper endpoints

- `GET /api/tago/diagnostics`
- `GET /api/tago/arrivals`
- `GET /api/tago/stations/nearby`
- `GET /api/tago/route-stops`
- `POST /api/routes/plan/tago`

These are helper APIs for obtaining real public-data inputs. They do not turn TransitGuard into a full map application.

## Kakao Map in the browser demo

The web demo calls `GET /api/kakao/config`, loads Kakao Maps JavaScript SDK with the `services` library, and then uses Kakao Places search and map overlays in the browser.

Kakao Map is not used by the Python core. It is used for:

- place search
- station-coordinate editing for the sample assessment JSON
- markers and polylines on the map
- finding nearby TAGO stops from a selected coordinate

## Experimental candidate generation

The following endpoints are retained for experiments, but the project's main scope is assessment of supplied candidates:

- `POST /api/route-candidates/generate-graph`
- `POST /api/route-candidates/generate-tago`
- `POST /api/route-candidates/discover-tago`


## Demo presets

`GET /api/demo/quick-presets` returns classroom-friendly quick-form examples for safe, tight,
and missed transfer scenarios. These examples do not require TAGO or Kakao keys and are used by
the browser demo preset buttons.

The route assessment responses include user-facing fields such as `confidence_label`,
`risk_warnings`, and `next_steps` so the result is easier to explain in a report or presentation.
