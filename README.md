# TransitGuard

TransitGuard는 기존 경로 후보에 TAGO 공공데이터 API의 버스 도착예정정보와 정류소 정보를 결합해 환승 안정성을 분석하는 오픈소스 프로젝트이다. 사용자가 입력한 출발 정류소, 도착 정류소, 후보 노선 정보를 바탕으로 첫차 대기시간, 환승 가능 시각, 도보 환승 시간, 다음 차량 도착 시각을 계산하고 경로별 안정성 점수를 제공한다. 완성형 길찾기 서비스보다는 대중교통 경로를 더 현실적으로 평가하기 위한 보조 분석 엔진에 가깝다.

Current development tag: `v0.1.0-alpha.29` (`0.1.0a29` as a Python package version).

> 공개 저장소에는 실제 API 키, `.env`, 개인 PC 경로, 대회 접수정보를 포함하지 않습니다.
> 실행 전 `.env.example`을 `.env`로 복사하고 본인의 키를 입력하세요.

### 0.1.0-alpha.28: explicit Daegu/Gyeongsan policy and honest times

- Enforces Gyeongsan-to-Gyeongsan as `cityCode=37100` with GYB stops only.
- Enforces Daegu-to-Gyeongsan and Daegu-to-Daegu as `cityCode=22` with DGB stops only.
- Enriches every cached route stop into the station-name lookup and returns names alongside IDs.
- Separates real-time boarding ETA from estimated alighting time and explicitly warns that topology timing is not an exact per-stop timetable.

### 0.1.0-alpha.27: routable Gyeongsan stops and actionable guidance

- Preflights origin stop-route data and prioritizes stops that actually expose routes, preventing empty DGB mirrors from consuming the Gyeongsan pair budget.
- Tries same-city destination counterparts first and enables live-arrival discovery by default.
- Prefers live candidates while retaining topology estimates as a fallback under the request budget.
- Returns a per-leg itinerary with boarding time/stop, complete intermediate stop names, alighting time/stop, and an explicit live-versus-estimated time source.
- Renders the full boarding, via-stop, and alighting guidance in the browser route cards.

### 0.1.0-alpha.26: paired stop mirrors and clock times

- Applies the nearby-stop limit to physical stops, then automatically includes every DGB/GYB mirror within 120 m that has the same normalized name.
- Returns `HH:MM` time fields alongside minute values and uses `+N일 HH:MM` after midnight.
- Shows departure and arrival clocks on every web route segment and formatted readiness/boarding clocks for transfers.

### 0.1.0-alpha.25: regional mirrored-stop fallback

- Selects nearby stops in a city-code round robin instead of truncating the raw TAGO order.
- Keeps both DGB and GYB representations near Daegu–Gyeongsan boundaries, so a route-less mirror ID cannot hide the routable stop.
- Raises the browser defaults to five stops per side and eight stop pairs while retaining the 60-call API budget.

### 0.1.0-alpha.24: multimodal routing hardening

- Preserves multiple TAGO city codes around regional boundaries such as Daegu and Gyeongsan.
- Adds a per-request API budget, request-local caches, direct-route early stopping, and bounded diagnostics.
- Fixes current TAGO subway responses that provide `subwayRouteName` without a separate route ID.
- Chains transfer readiness as arrival + walking + minimum buffer and adds a 10-minute transfer penalty to ranking.
- Parses common Public Data Portal gateway error XML into actionable TAGO errors.
- Verified the supplied Gyeongsan-to-Daegu coordinates against live TAGO data and produced a subway-transfer candidate.

### 0.1.0-alpha.23: reliable stop-route filtering and bounded diagnostics

- Uses TAGO's lowercase `nodeid` parameter for stop-route lookup instead of the arrival API's camel-case parameter.
- Rejects suspicious city-wide route catalogues and de-duplicates route IDs before topology search.
- Shows each origin stop once and limits displayed routes to 20 while retaining the total count.

### 0.1.0-alpha.22: nearby subway and transfer support

- Treats a zero-candidate live search as a completed search, not an application error.
- Shows checked origin/destination stops and routes seen in live origin arrivals.
- Provides likely causes and practical next steps in Korean.
- Uses smaller live-search defaults to reduce TAGO calls and timeout risk.
- Falls back to TAGO stop-route topology for direct or one-transfer candidates when live arrivals are sparse; fallback times are explicitly estimated.
- Continues topology search after live API errors, checks more routes and station pairs, supports walking between different transfer-stop IDs, and reuses TAGO results across pairs.
- Gives the two essential nearby-stop lookups a 12-second timeout and one automatic retry, while presenting a clearer Korean message if the public-data server remains unavailable.
- Finds route candidates from stop-route topology first, stops after three candidates, and makes the expensive live-arrival discovery path opt-in.
- Sends Kakao place names to the planner and uses the official TAGO SubwayInfo station search to add direct same-line subway candidates. Subway times are currently estimates.
- Automatically finds nearby subway stations through Kakao category search and supports one subway transfer through Daegu's Banwoldang or Cheongna Hill hubs.

The web demo now uses a simpler card layout with fewer visual distractions. The main flow is arranged as: live TAGO planning, quick transfer assessment, then advanced JSON/API details. No API behavior changed in this release.

**TransitGuard** is an open-source **public-transit transfer reliability assessment engine**. It is not a replacement for a full map or route-finding app. Instead, it takes route candidates that already exist and evaluates whether their transfers are realistic using waiting time, walking time, buffer time, and optional TAGO live bus-arrival data.

> 한국어 요약: 트랜짓가드는 새로운 길을 처음부터 찾아주는 지도앱이 아니라, 기존 길찾기 결과나 직접 만든 경로 후보가 실제로 환승 가능한지 평가하는 보조 분석 엔진입니다.

## What it does

- Evaluates each transfer as `safe`, `tight`, `missed`, or `unknown`
- Ranks provided route candidates using total time, initial wait time, transfer risk, and reliability
- Accepts manually supplied arrival candidates for simple offline tests
- Optionally fetches TAGO live arrivals and merges them into transfer checks
- Rejects disconnected, empty, or time-reversed route candidates before evaluation
- Provides a FastAPI server and a browser demo for testing the assessment flow
- Includes a quick form mode so users can test a one-transfer route without hand-writing JSON
- Returns Korean status labels, summaries, recommendations, and score breakdowns for easier interpretation
- Optionally integrates Kakao Map for place search, nearby-stop lookup, and result visualization
- Adds a practical live mode that accepts origin/destination coordinates, finds nearby TAGO stops, and ranks bounded live candidates
- Keeps experimental route-generation/TAGO-discovery endpoints separate from the main assessment engine
- Includes Windows-friendly batch files for setup and execution

## What it does not claim

TransitGuard is **not** a nationwide automatic route planner. It does not guarantee exhaustive discovery of every possible route in a city. The main intended workflow is:

```text
existing route candidate -> transfer timing analysis -> reliability score
```

Experimental TAGO route-generation and discovery endpoints remain available for exploration, but the main project goal is now route assessment, not full route creation.

## Windows quick start

For Windows users, run the included batch files from the project folder:

```text
1. Double-click setup_windows.bat
2. Double-click start_all_windows.bat
3. Open http://127.0.0.1:8080
```

`setup_windows.bat` creates `.venv`, installs dependencies, creates `.env` if missing, and runs tests. `start_all_windows.bat` starts the API and web demo in separate command windows.

If PowerShell blocks `Activate.ps1`, use the batch files or run Python directly from `.venv`; you do not need to activate the environment manually.

## Manual start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev,api]
pytest
uvicorn transitguard.api.app:app --reload
```

Windows without activation:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,api]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn transitguard.api.app:app --reload
```

Useful pages:

- API docs: `http://127.0.0.1:8000/docs`
- Setup check: `http://127.0.0.1:8000/api/setup/check`
- Web demo: `http://127.0.0.1:8080`

## Optional Kakao Map visualization

Kakao Map is used only in the browser demo. It does not create public-transit routes for TransitGuard.
Its role is:

```text
Kakao Map -> place search, markers, polylines, visual route explanation
TAGO      -> live bus-stop and bus-arrival data
TransitGuard -> transfer reliability assessment
```

To enable the map demo:

1. Create a Kakao Developers app and copy the **JavaScript Key**.
2. Add `http://127.0.0.1:8080` to the Kakao web platform domain list.
3. Put the key in `.env`:

```env
KAKAO_MAP_JAVASCRIPT_KEY=your_kakao_javascript_key
```

4. Restart the API server and open the web demo.

The web demo can then search places with Kakao Places, save coordinates for internal station IDs
such as `A`, `B`, and `C`, query nearby TAGO stops, and draw the assessed route on the Kakao map.

The demo now starts with a **간편 입력 모드**. Users can enter times like `08:40`, route numbers, and next-vehicle arrivals without editing JSON. It also includes safe/tight/missed preset buttons so a teacher or first-time user can immediately see how the score changes. Advanced JSON input is still available below it.

## Practical live flow: coordinates to live TAGO candidates

This is the closest flow to "actually using" the project. With `TAGO_SERVICE_KEY` set, send origin and destination coordinates. TransitGuard will find nearby TAGO stops, try bounded live-arrival candidate discovery, and return ranked transfer reliability results. It is still not an exhaustive national route planner, but it removes the need to manually know `node_id` or `route_id` before the first attempt.

```bash
curl -X POST http://127.0.0.1:8000/api/routes/plan/tago \
  --header "Content-Type: application/json" \
  --data @examples/plan_tago_coordinates_payload.json
```

The browser demo exposes the same flow as **실사용 모드**. Search a place in Kakao Map, save it as the live origin or destination coordinate, and press **실제 TAGO 데이터로 후보 찾기**.

The origin and destination region selectors are filled from Kakao address data. For
Gyeongsan-to-Gyeongsan searches the planner uses TAGO city code `37100` and GYB
stops only; trips crossing into Daegu use city code `22` and DGB stops. You can
override either selector when entering coordinates manually, and the applied policy
is shown with the search diagnostics.

## Quick API: assess one transfer route

For the most user-friendly API flow, send form-like values to the quick endpoint:

```bash
curl -X POST http://127.0.0.1:8000/api/routes/assess/quick \
  --header "Content-Type: application/json" \
  --data @examples/assess_quick_payload.json
```

This endpoint builds one two-leg transfer candidate, evaluates it, and returns Korean labels such as `안전`, `촉박`, `정보 부족`, or `환승 실패` with a short recommendation, confidence label, risk warnings, and suggested next steps.

## Main API: assess existing routes

Static arrival data:

```bash
curl -X POST http://127.0.0.1:8000/api/routes/assess \
  --header "Content-Type: application/json" \
  --data @examples/assess_routes_payload.json
```

With live TAGO arrivals merged into the transfer stop:

```bash
curl -X POST http://127.0.0.1:8000/api/routes/assess \
  --header "Content-Type: application/json" \
  --data @examples/assess_routes_tago_payload.json
```

The live TAGO payload maps a real TAGO `node_id` to an internal transfer station ID used by the supplied route candidate. If your route segments use bus numbers such as `708`, keep `route_key` as `route_no`. If they use TAGO route IDs, set `route_key` to `route_id`.

## Minimal Python usage

```python
from transitguard import evaluate_route
from transitguard.core.models import Arrival, RouteCandidate, RouteSegment, Transfer

route = RouteCandidate(
    id="candidate-a",
    requested_start_minute=520,
    segments=(
        RouteSegment("101", "A", "B", 524, 540),
        RouteSegment("708", "B", "C", 552, 570),
    ),
    transfers=(
        Transfer(
            from_station_id="B",
            to_station_id="B",
            arrival_minute=540,
            walking_minutes=4,
            minimum_buffer_minutes=3,
            candidate_arrivals=(Arrival("B", "708", 552),),
            target_route_id="708",
        ),
    ),
)

result = evaluate_route(route)
print(result.status, result.reliability_score, result.total_minutes)
```

## Optional TAGO utilities

After setting `TAGO_SERVICE_KEY` in `.env`, you can use these helper endpoints:

- `GET /api/demo/quick-presets`
- `GET /api/tago/diagnostics`
- `GET /api/tago/arrivals?city_code=22&node_id=...`
- `GET /api/tago/stations/nearby?lat=...&lon=...`
- `GET /api/tago/route-stops?city_code=22&route_id=...`

Experimental endpoints that try to generate or discover candidates from TAGO data are still included, but they are not the core claim of the project:

- `POST /api/routes/plan/tago`
- `POST /api/route-candidates/generate-tago`
- `POST /api/route-candidates/discover-tago`
- `POST /api/route-candidates/generate-graph`

## Environment variables

Copy `.env.example` to `.env` and fill in only what you need:

```bash
TAGO_SERVICE_KEY=your_public_data_service_key
KAKAO_MAP_JAVASCRIPT_KEY=your_kakao_javascript_key
TRANSITGUARD_CORS_ORIGINS=*
```

Never commit real service keys. Windows note: `tzdata` is installed automatically on Windows and the code also has a KST fallback, so `Asia/Seoul` timezone lookup should not break local tests.

## Project structure

```text
transitguard
├─ src/transitguard
│  ├─ core          # Pure route and transfer assessment logic
│  ├─ adapters      # CSV and TAGO adapters
│  └─ api           # Optional FastAPI interface
├─ examples         # Request examples
├─ tests            # Unit tests
├─ web-demo         # Browser demo for route assessment and optional Kakao Map visualization
└─ docs             # Architecture and API notes
```

## License

MIT License
