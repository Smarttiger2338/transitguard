# Changelog

- Fixed Gyeongsan Jain stops being reported as route-less when TAGO returns many
  legitimate branch/direction route IDs for a single GYB stop.

## 0.1.0-alpha.29

- Removed the browser planner's hidden `cityCode=22` default that forced every search through Daegu.
- Added separate origin/destination region controls, automatically populated from Kakao address data.
- Enforced `37100`/GYB for Gyeongsan-only trips and `22`/DGB for Daegu-boundary trips.
- Displayed the effective TAGO region policy directly in the live-plan diagnostics.
- Added regression tests for misleading mixed DGB/GYB nearby-stop ordering.

## 0.1.0-alpha.28

- Added explicit trip-region rules: Gyeongsan local uses 37100/GYB, while Daegu local and Daegu-Gyeongsan use 22/DGB.
- Replaced station-ID-only guidance with names sourced from complete route-stop data.
- Clearly distinguishes live boarding ETA from estimated travel/alighting times instead of presenting estimates as an exact timetable.

## 0.1.0-alpha.27

- Prioritized route-bearing Gyeongsan station IDs before empty DGB mirrors and searched same-city pairs first.
- Enabled live-arrival candidate discovery by default and kept topology candidates as explicit estimates.
- Added detailed route itineraries with boarding, all intermediate stops, alighting, clock times, and time provenance.

## 0.1.0-alpha.26

- Changed the station limit to count physical stops while automatically adding co-located DGB/GYB mirror IDs.
- Added consistent `HH:MM` and `+N일 HH:MM` fields to planner, segment, arrival, and transfer output.
- Updated route cards to display departure and arrival times for every segment.

## 0.1.0-alpha.25

- Fixed boundary searches that selected only DGB mirror stops even when usable GYB stops were present later in the same TAGO nearby-stop response.
- Nearby stop selection now alternates city codes, and the browser checks five stops per side with eight bounded pairs.

## 0.1.0-alpha.24

- Added multi-city-code planning for regional boundaries, a 10-70 call request budget, direct-route early stopping, and per-city request caches.
- Fixed subway parsing for the current TAGO response shape where `subwayRouteName` is the only line identifier.
- Improved chained transfer timing and ranking with minimum buffers and an explicit transfer penalty.
- Added Public Data Portal gateway XML error parsing and live validation for the supplied Gyeongsan-to-Daegu coordinates.

## 0.1.0-alpha.23

- Fixed the TAGO stop-route parameter casing so a stop lookup no longer returns a city's entire route catalogue.
- Added route de-duplication, single-page bounds, and a defensive city-wide-response check to reduce timeouts and false zero-candidate results.
- De-duplicated zero-result diagnostics by origin stop, capped displayed routes, and clarified Korean causes and suggestions.

## 0.1.0-alpha.22

- Added automatic nearest-subway-station lookup within 5 km through Kakao category search.
- Added one-transfer Daegu subway candidates through Banwoldang and Cheongna Hill.
- Improved Kakao place-name normalization for strings such as `대구2호선 임당역`.
- Fixed origin, transfer, and final subway station map-coordinate assignment.
- Kept subway times and first/last-mile access explicitly estimated.

## 0.1.0-alpha.21

- Added official TAGO SubwayInfo keyword station lookup.
- Added direct same-line subway candidates to coordinate planning.
- Added origin/destination place-name fields and automatic Kakao place-name transfer.
- Added subway endpoint parsing and integrated subway candidate tests.
- Clearly marks subway travel times as estimates; subway transfers are not yet supported.

## 0.1.0-alpha.20

- Changed coordinate planning to topology-first discovery instead of live-arrival-first discovery.
- Disabled expensive live-arrival route discovery by default; it remains available through `use_live_arrival_discovery`.
- Added `max_candidates` and stop checking after enough candidates are found.
- Reused topology route lists in diagnostics without an extra arrival API request.

## 0.1.0-alpha.19

- Increased the timeout for essential origin/destination nearby-stop requests to 12 seconds.
- Added one bounded retry for nearby-stop timeouts without multiplying every route lookup.
- Improved the Korean web message when the TAGO public-data server remains slow.

## 0.1.0-alpha.18

- Run route-topology discovery even when live-arrival discovery raises an error.
- Increased default stop, pair, and route coverage to avoid silently excluding valid routes.
- Added walking transfers between nearby stops with different TAGO node IDs.
- Reused station-route and route-stop responses across checked station pairs.
- Fixed shared loop state that could stop later route searches too early.

## 0.1.0-alpha.17

- Added a bounded stop-route topology fallback when live arrival discovery returns no candidates.
- Supports direct and one-transfer topology candidates using estimated times.
- Clearly labels topology fallback routes as estimates in API diagnostics and the web demo.

## 0.1.0-alpha.16

- Added structured diagnostics for zero-candidate coordinate planning results.
- Exposed checked origin/destination stops plus origin arrivals and route IDs without extra TAGO calls.
- Added Korean likely-cause and recovery suggestions to the API and web demo.
- Reduced default station, pair, route, and transfer search limits to lower timeout risk.
- Rendered zero results as a successful, actionable diagnostic state in the web demo.

## 0.1.0-alpha.15

- Simplified the web demo into a cleaner card-based interface.
- Reordered the demo around the real-use flow: choose places, run live TAGO planning, review results.
- Moved JSON and raw API details into an advanced section so first-time users are not overwhelmed.
- Kept the alpha.14 API and test behavior unchanged.

## 0.1.0-alpha.14

- Added practical live mode: `POST /api/routes/plan/tago` accepts origin/destination coordinates, finds nearby TAGO stops, and runs bounded live candidate discovery.
- Added a web-demo **실사용 모드** so users can save Kakao place coordinates as live origin/destination and run TAGO-based planning without manually knowing node IDs first.
- Added `examples/plan_tago_coordinates_payload.json`.
- Added station-location hints and attempted-pair diagnostics to practical live responses.
- Added tests for coordinate-based practical planning and graceful empty-result handling.

## 0.1.0-alpha.12

- Added `POST /api/routes/assess/quick` for form-style one-transfer assessment.
- Added Korean status labels, route summaries, recommendations, transfer messages, and score breakdowns to API responses.
- Added a web-demo quick input mode so users can test TransitGuard without manually editing JSON.
- Fixed duplicate web-demo output assignment and duplicate marker cleanup.
- Added `examples/assess_quick_payload.json` and API tests for the new friendly endpoint.

## 0.1.0-alpha.11

- Added optional Kakao Map integration to the browser demo.
- Added `GET /api/kakao/config` so the static demo can load the public Kakao JavaScript key from the API server.
- Added Kakao place search, map markers, route polyline visualization, and station-coordinate editing in `web-demo`.
- Added a nearby TAGO stop lookup flow from selected Kakao place coordinates.
- Added `KAKAO_MAP_JAVASCRIPT_KEY` to `.env.example` and setup diagnostics.
- Updated README and docs to clarify that Kakao Map is for visualization, not automatic transit routing.

## 0.1.0-alpha.10

- Refocused the project around existing route-candidate assessment instead of full route generation.
- Added `POST /api/routes/assess` as the primary API.
- Added optional `tago_arrival_sources` to merge real TAGO arrivals into transfer checks.
- Reworked the web demo so it evaluates supplied route candidates rather than presenting itself as a map/router.
- Added `examples/assess_routes_payload.json` and `examples/assess_routes_tago_payload.json`.
- Updated README and docs to avoid overstating the project as a complete route planner.

## Earlier alpha versions

- Added route evaluation, ranking, demo graph, TAGO helper APIs, Windows batch scripts, and setup diagnostics.
