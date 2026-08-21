const output = document.querySelector('#output');
const apiBase = document.querySelector('#apiBase');
const checkSetup = document.querySelector('#checkSetup');
const loadSample = document.querySelector('#loadSample');
const setupStatus = document.querySelector('#setupStatus');
const routeJson = document.querySelector('#routeJson');
const stationLocationsJson = document.querySelector('#stationLocationsJson');
const liveStationId = document.querySelector('#liveStationId');
const liveCityCode = document.querySelector('#liveCityCode');
const liveNodeId = document.querySelector('#liveNodeId');
const routeKey = document.querySelector('#routeKey');
const assessRoutes = document.querySelector('#assessRoutes');
const routeCards = document.querySelector('#routeCards');
const loadKakaoMap = document.querySelector('#loadKakaoMap');
const mapStatus = document.querySelector('#mapStatus');
const mapElement = document.querySelector('#map');
const placeKeyword = document.querySelector('#placeKeyword');
const searchPlace = document.querySelector('#searchPlace');
const placeResults = document.querySelector('#placeResults');
const nearbyStations = document.querySelector('#nearbyStations');
const originVisualId = document.querySelector('#originVisualId');
const transferVisualId = document.querySelector('#transferVisualId');
const destinationVisualId = document.querySelector('#destinationVisualId');
const quickAssess = document.querySelector('#quickAssess');
const quickToJson = document.querySelector('#quickToJson');
const quickPresetSafe = document.querySelector('#quickPresetSafe');
const quickPresetTight = document.querySelector('#quickPresetTight');
const quickPresetMissed = document.querySelector('#quickPresetMissed');
const quickStart = document.querySelector('#quickStart');
const quickFirstRoute = document.querySelector('#quickFirstRoute');
const quickSecondRoute = document.querySelector('#quickSecondRoute');
const quickFirstDeparture = document.querySelector('#quickFirstDeparture');
const quickTransferArrival = document.querySelector('#quickTransferArrival');
const quickFinalArrival = document.querySelector('#quickFinalArrival');
const quickNextArrivals = document.querySelector('#quickNextArrivals');
const quickWalking = document.querySelector('#quickWalking');
const quickBuffer = document.querySelector('#quickBuffer');
const quickOriginId = document.querySelector('#quickOriginId');
const quickTransferId = document.querySelector('#quickTransferId');
const quickDestinationId = document.querySelector('#quickDestinationId');

const planOriginRegion = document.querySelector('#planOriginRegion');
const planDestinationRegion = document.querySelector('#planDestinationRegion');
const planOriginName = document.querySelector('#planOriginName');
const planOriginSubwayName = document.querySelector('#planOriginSubwayName');
const planOriginLat = document.querySelector('#planOriginLat');
const planOriginLon = document.querySelector('#planOriginLon');
const planDestinationLat = document.querySelector('#planDestinationLat');
const planDestinationName = document.querySelector('#planDestinationName');
const planDestinationSubwayName = document.querySelector('#planDestinationSubwayName');
const planDestinationLon = document.querySelector('#planDestinationLon');
const planStartTime = document.querySelector('#planStartTime');
const planMaxOriginStations = document.querySelector('#planMaxOriginStations');
const planMaxDestinationStations = document.querySelector('#planMaxDestinationStations');
const planMaxStationPairs = document.querySelector('#planMaxStationPairs');
const runLivePlan = document.querySelector('#runLivePlan');
const livePlanStatus = document.querySelector('#livePlanStatus');
const livePlanDiagnostics = document.querySelector('#livePlanDiagnostics');

let kakaoMap = null;
let kakaoPlaces = null;
let kakaoReady = false;
let mapMarkers = [];
let mapPolylines = [];
let lastRoutes = [];
let lastLocations = {};

function minuteNow() {
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes();
}

function apiUrl(path) {
  return `${apiBase.value.replace(/\/$/, '')}${path}`;
}

function parseClockMinute(value) {
  const trimmed = String(value || '').trim();
  const match = trimmed.match(/^(\d{1,2}):(\d{2})$/);
  if (!match) {
    throw new Error(`시간 형식이 올바르지 않습니다: ${trimmed || '(비어 있음)'}`);
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours < 0 || hours > 47 || minutes < 0 || minutes > 59) {
    throw new Error(`시간 범위가 올바르지 않습니다: ${trimmed}`);
  }
  return hours * 60 + minutes;
}

function parseArrivalList(value) {
  const parts = String(value || '')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) {
    throw new Error('다음 차량 도착 시각을 1개 이상 입력하세요. 예: 09:12, 09:20');
  }
  return parts.map(parseClockMinute);
}


function parseRequiredNumber(value, label) {
  const number = Number(String(value || '').trim());
  if (!Number.isFinite(number)) {
    throw new Error(`${label} 값을 숫자로 입력하세요.`);
  }
  return number;
}

function parseOptionalStartMinute(value) {
  const text = String(value || '').trim();
  if (!text || text === '지금') return minuteNow();
  return parseClockMinute(text);
}

function livePlanPayload() {
  return {
    origin_region: planOriginRegion.value,
    destination_region: planDestinationRegion.value,
    origin_name: planOriginName.value.trim() || undefined,
    destination_name: planDestinationName.value.trim() || undefined,
    origin_subway_name: planOriginSubwayName.value.trim() || undefined,
    destination_subway_name: planDestinationSubwayName.value.trim() || undefined,
    origin: {
      lat: parseRequiredNumber(planOriginLat.value, '출발 위도'),
      lon: parseRequiredNumber(planOriginLon.value, '출발 경도'),
    },
    destination: {
      lat: parseRequiredNumber(planDestinationLat.value, '도착 위도'),
      lon: parseRequiredNumber(planDestinationLon.value, '도착 경도'),
    },
    current_minute: parseOptionalStartMinute(planStartTime.value),
    max_origin_stations: Number(planMaxOriginStations.value || 5),
    max_destination_stations: Number(planMaxDestinationStations.value || 5),
    max_station_pairs: Number(planMaxStationPairs.value || 8),
  };
}

function setPlanCoordinate(kind, place, lat, lon) {
  const inferredRegion = inferRegionFromPlace(place);
  if (kind === 'origin') {
    planOriginName.value = place.place_name;
    planOriginLat.value = String(lat);
    planOriginLon.value = String(lon);
    planOriginRegion.value = inferredRegion;
    livePlanStatus.textContent = `출발 좌표를 ${place.place_name}로 저장했습니다.`;
    findNearestSubwayStation('origin', lat, lon);
    return;
  }
  planDestinationName.value = place.place_name;
  planDestinationLat.value = String(lat);
  planDestinationLon.value = String(lon);
  planDestinationRegion.value = inferredRegion;
  livePlanStatus.textContent = `도착 좌표를 ${place.place_name}로 저장했습니다.`;
  findNearestSubwayStation('destination', lat, lon);
}

function inferRegionFromPlace(place) {
  const address = `${place.address_name || ''} ${place.road_address_name || ''}`;
  if (address.includes('경산시') || address.includes('경상북도 경산')) return 'gyeongsan';
  if (address.includes('대구광역시') || address.includes('대구 ')) return 'daegu';
  return 'auto';
}

function findNearestSubwayStation(kind, lat, lon) {
  if (!kakaoPlaces || !window.kakao?.maps?.services) return;
  const location = new window.kakao.maps.LatLng(lat, lon);
  kakaoPlaces.categorySearch(
    'SW8',
    (places, status) => {
      if (status !== window.kakao.maps.services.Status.OK || !places.length) return;
      const nearest = places[0];
      if (kind === 'origin') {
        planOriginSubwayName.value = nearest.place_name;
      } else {
        planDestinationSubwayName.value = nearest.place_name;
      }
      livePlanStatus.textContent = `${kind === 'origin' ? '출발' : '도착'} 인근 지하철역을 ${nearest.place_name}으로 설정했습니다.`;
    },
    {
      location,
      radius: 5000,
      sort: window.kakao.maps.services.SortBy.DISTANCE,
    },
  );
}

async function runLivePlanner() {
  livePlanDiagnostics.hidden = true;
  livePlanDiagnostics.textContent = '';
  livePlanStatus.textContent = '실제 TAGO 데이터로 주변 정류소와 후보 경로를 찾는 중입니다.';
  output.textContent = '실사용 모드 실행 중입니다. TAGO API 호출이 여러 번 일어날 수 있습니다.';
  const data = await postJson('/api/routes/plan/tago', livePlanPayload());
  lastRoutes = data.routes || [];
  lastLocations = data.station_locations || {};
  stationLocationsJson.value = JSON.stringify(lastLocations, null, 2);
  renderRoutes(lastRoutes);
  renderLivePlanDiagnostics(data.diagnostics, data.region_policy);
  renderMap(lastRoutes[0] || null, lastLocations);
  const count = lastRoutes.length;
  const attempts = data.attempts?.length || 0;
  livePlanStatus.textContent = count
    ? `완료: 정류소 조합 ${attempts}개를 확인했고 후보 경로 ${count}개를 찾았습니다.`
    : `탐색 완료: 정류소 조합 ${attempts}개를 확인했지만 현재 조건에서는 후보가 없습니다.`;
  output.textContent = JSON.stringify(data, null, 2);
}

function appendDiagnosticList(parent, heading, values) {
  const title = document.createElement('h4');
  title.textContent = heading;
  parent.appendChild(title);
  const list = document.createElement('ul');
  (values.length ? values : ['확인된 정보가 없습니다.']).forEach((value) => {
    const item = document.createElement('li');
    item.textContent = value;
    list.appendChild(item);
  });
  parent.appendChild(list);
}

function renderLivePlanDiagnostics(diagnostics, regionPolicy) {
  if (!diagnostics) return;
  livePlanDiagnostics.hidden = false;
  livePlanDiagnostics.textContent = '';
  livePlanDiagnostics.classList.toggle('zero-result', diagnostics.status === 'no_routes');
  const title = document.createElement('h3');
  title.textContent = diagnostics.title;
  livePlanDiagnostics.appendChild(title);
  if (regionPolicy) {
    const policy = document.createElement('p');
    policy.className = 'region-policy';
    policy.textContent = `적용 지역: ${regionPolicy}`;
    livePlanDiagnostics.appendChild(policy);
  }
  if (diagnostics.message) {
    const message = document.createElement('p');
    message.textContent = diagnostics.message;
    livePlanDiagnostics.appendChild(message);
  }
  appendDiagnosticList(
    livePlanDiagnostics,
    '확인한 출발 정류소',
    (diagnostics.checked_origin_stops || []).map((stop) => `${stop.name} (${stop.node_id})`),
  );
  appendDiagnosticList(
    livePlanDiagnostics,
    '확인한 도착 정류소',
    (diagnostics.checked_destination_stops || []).map((stop) => `${stop.name} (${stop.node_id})`),
  );
  const routeLabels = [];
  (diagnostics.origin_arrivals || []).forEach((stop) => {
    (stop.routes || []).forEach((route) => {
      routeLabels.push(`${stop.name}: ${route.route_no || route.route_id} (${route.route_id})`);
    });
    if (stop.routes_truncated) {
      routeLabels.push(`${stop.name}: 총 ${stop.route_count}개 중 20개만 표시`);
    }
  });
  appendDiagnosticList(livePlanDiagnostics, '출발 정류소에서 확인된 노선', routeLabels);
  if (diagnostics.status === 'no_routes') {
    appendDiagnosticList(livePlanDiagnostics, '가능한 원인', diagnostics.possible_causes || []);
    appendDiagnosticList(livePlanDiagnostics, '다음에 해볼 방법', diagnostics.suggestions || []);
  }
}

function quickPayload() {
  return {
    id: 'quick-candidate',
    requested_start_minute: parseClockMinute(quickStart.value),
    origin_station_id: quickOriginId.value.trim() || 'A',
    transfer_station_id: quickTransferId.value.trim() || 'B',
    destination_station_id: quickDestinationId.value.trim() || 'C',
    first_route_id: quickFirstRoute.value.trim(),
    second_route_id: quickSecondRoute.value.trim(),
    first_departure_minute: parseClockMinute(quickFirstDeparture.value),
    transfer_arrival_minute: parseClockMinute(quickTransferArrival.value),
    second_departure_minute: parseArrivalList(quickNextArrivals.value)[0],
    final_arrival_minute: parseClockMinute(quickFinalArrival.value),
    walking_minutes: Number(quickWalking.value || 0),
    minimum_buffer_minutes: Number(quickBuffer.value || 0),
    next_vehicle_arrival_minutes: parseArrivalList(quickNextArrivals.value),
  };
}

function quickPayloadAsAssessJson() {
  const quick = quickPayload();
  return {
    current_minute: quick.requested_start_minute,
    routes: [
      {
        id: quick.id,
        requested_start_minute: quick.requested_start_minute,
        segments: [
          {
            route_id: quick.first_route_id,
            from_station_id: quick.origin_station_id,
            to_station_id: quick.transfer_station_id,
            departure_minute: quick.first_departure_minute,
            arrival_minute: quick.transfer_arrival_minute,
          },
          {
            route_id: quick.second_route_id,
            from_station_id: quick.transfer_station_id,
            to_station_id: quick.destination_station_id,
            departure_minute: quick.second_departure_minute,
            arrival_minute: quick.final_arrival_minute,
          },
        ],
        transfers: [
          {
            from_station_id: quick.transfer_station_id,
            to_station_id: quick.transfer_station_id,
            arrival_minute: quick.transfer_arrival_minute,
            walking_minutes: quick.walking_minutes,
            minimum_buffer_minutes: quick.minimum_buffer_minutes,
            target_route_id: quick.second_route_id,
            candidate_arrivals: quick.next_vehicle_arrival_minutes.map((minute) => ({
              station_id: quick.transfer_station_id,
              route_id: quick.second_route_id,
              arrival_minute: minute,
            })),
          },
        ],
      },
    ],
  };
}

async function postJson(path, payload) {
  const response = await fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data;
}

async function getJson(path) {
  const response = await fetch(apiUrl(path));
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data;
}

function samplePayload() {
  return {
    current_minute: 520,
    routes: [
      {
        id: 'candidate-a',
        requested_start_minute: 520,
        segments: [
          {
            route_id: '101',
            from_station_id: 'A',
            to_station_id: 'B',
            departure_minute: 524,
            arrival_minute: 540,
          },
          {
            route_id: '708',
            from_station_id: 'B',
            to_station_id: 'C',
            departure_minute: 552,
            arrival_minute: 570,
          },
        ],
        transfers: [
          {
            from_station_id: 'B',
            to_station_id: 'B',
            arrival_minute: 540,
            walking_minutes: 4,
            minimum_buffer_minutes: 3,
            target_route_id: '708',
            candidate_arrivals: [
              { station_id: 'B', route_id: '708', arrival_minute: 552 },
              { station_id: 'B', route_id: '708', arrival_minute: 560 },
            ],
          },
        ],
      },
      {
        id: 'candidate-b-tight',
        requested_start_minute: 520,
        segments: [
          {
            route_id: '401',
            from_station_id: 'A',
            to_station_id: 'B',
            departure_minute: 522,
            arrival_minute: 542,
          },
          {
            route_id: '708',
            from_station_id: 'B',
            to_station_id: 'C',
            departure_minute: 550,
            arrival_minute: 566,
          },
        ],
        transfers: [
          {
            from_station_id: 'B',
            to_station_id: 'B',
            arrival_minute: 542,
            walking_minutes: 4,
            minimum_buffer_minutes: 3,
            target_route_id: '708',
            candidate_arrivals: [
              { station_id: 'B', route_id: '708', arrival_minute: 550 },
            ],
          },
        ],
      },
    ],
  };
}

function sampleStationLocations() {
  return {
    A: { name: '대구역', lat: 35.8759, lon: 128.5961 },
    B: { name: '반월당역', lat: 35.8649, lon: 128.5935 },
    C: { name: '동대구역', lat: 35.8797, lon: 128.6282 },
  };
}

function loadSamplePayload() {
  routeJson.value = JSON.stringify(samplePayload(), null, 2);
  stationLocationsJson.value = JSON.stringify(sampleStationLocations(), null, 2);
  output.textContent = '예시 경로를 불러왔습니다. 환승 안정성 평가 버튼을 눌러보세요.';
  lastLocations = sampleStationLocations();
  if (kakaoReady) {
    renderMap(lastRoutes[0] || null, lastLocations);
  }
}

async function runSetupCheck() {
  setupStatus.textContent = 'API 서버 상태 확인 중';
  try {
    const data = await getJson('/api/setup/check');
    const tagoMessage = data.tago?.configured
      ? `TAGO 키 설정됨 (${data.tago.service_key_source || 'source unknown'})`
      : 'TAGO 키 없음: JSON에 직접 넣은 도착정보 평가는 가능함';
    const kakaoMessage = data.kakao_map?.configured
      ? '카카오맵 키 설정됨'
      : '카카오맵 키 없음: 지도 시각화 비활성';
    setupStatus.textContent = `API 정상 · 버전 ${data.version} · ${tagoMessage} · ${kakaoMessage}`;
    output.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    setupStatus.textContent =
      'API 서버에 연결할 수 없습니다. start_api.bat 또는 start_all_windows.bat를 먼저 실행하세요.';
    output.textContent = `실행 상태 확인 실패: ${error.message}`;
  }
}

async function applyQuickPreset(name) {
  output.textContent = '예시를 불러오는 중입니다.';
  const data = await getJson('/api/demo/quick-presets');
  const preset = data.presets?.[name];
  if (!preset) {
    throw new Error(`알 수 없는 예시입니다: ${name}`);
  }
  fillQuickForm(preset.payload);
  stationLocationsJson.value = JSON.stringify(data.station_locations || {}, null, 2);
  lastLocations = data.station_locations || {};
  output.textContent = `${preset.label}: ${preset.description}`;
}

function fillQuickForm(payload) {
  quickStart.value = formatMinute(payload.requested_start_minute);
  quickFirstRoute.value = payload.first_route_id;
  quickSecondRoute.value = payload.second_route_id;
  quickFirstDeparture.value = formatMinute(payload.first_departure_minute);
  quickTransferArrival.value = formatMinute(payload.transfer_arrival_minute);
  quickFinalArrival.value = formatMinute(payload.final_arrival_minute);
  quickNextArrivals.value = (payload.next_vehicle_arrival_minutes || [])
    .map((minute) => formatMinute(minute))
    .join(', ');
  quickWalking.value = payload.walking_minutes;
  quickBuffer.value = payload.minimum_buffer_minutes;
  quickOriginId.value = payload.origin_station_id || 'A';
  quickTransferId.value = payload.transfer_station_id || 'B';
  quickDestinationId.value = payload.destination_station_id || 'C';
}

async function runQuickAssessment() {
  output.textContent = '간편 입력 경로를 평가 중입니다.';
  const data = await postJson('/api/routes/assess/quick', quickPayload());
  lastRoutes = data.route ? [data.route] : [];
  lastLocations = parseStationLocationsSafe();
  renderRoutes(lastRoutes);
  renderMap(lastRoutes[0] || null, lastLocations);
  output.textContent = JSON.stringify(data, null, 2);
}

function quickToJsonInput() {
  const payload = quickPayloadAsAssessJson();
  routeJson.value = JSON.stringify(payload, null, 2);
  output.textContent = '간편 입력 내용을 고급 JSON으로 변환했습니다.';
}

function buildAssessmentPayload() {
  let payload;
  try {
    payload = JSON.parse(routeJson.value);
  } catch (error) {
    throw new Error(`경로 후보 JSON 형식이 올바르지 않습니다: ${error.message}`);
  }
  if (payload.current_minute === null || payload.current_minute === undefined) {
    payload.current_minute = minuteNow();
  }

  const nodeId = liveNodeId.value.trim();
  if (nodeId) {
    payload.tago_arrival_sources = [
      {
        station_id: liveStationId.value.trim() || 'B',
        city_code: liveCityCode.value.trim(),
        node_id: nodeId,
        route_key: routeKey.value,
      },
    ];
  }
  return payload;
}

function parseStationLocations() {
  if (!stationLocationsJson.value.trim()) {
    return {};
  }
  try {
    return JSON.parse(stationLocationsJson.value);
  } catch (error) {
    throw new Error(`정류장 좌표 JSON 형식이 올바르지 않습니다: ${error.message}`);
  }
}

async function runAssessment() {
  output.textContent = '기존 경로 후보의 환승 안정성 평가 중';
  const payload = buildAssessmentPayload();
  const data = await postJson('/api/routes/assess', payload);
  lastRoutes = data.routes || [];
  lastLocations = parseStationLocations();
  renderRoutes(lastRoutes);
  renderMap(lastRoutes[0] || null, lastLocations);
  output.textContent = JSON.stringify(data, null, 2);
}

function renderRoutes(routes) {
  routeCards.textContent = '';
  if (routes.length === 0) {
    routeCards.textContent = '평가할 경로가 없습니다.';
    return;
  }

  routes.forEach((route, index) => {
    const article = document.createElement('article');
    article.className = 'card';

    const title = document.createElement('strong');
    title.textContent = `${index + 1}. ${route.route_id}`;
    article.appendChild(title);

    const status = document.createElement('span');
    status.className = `status ${route.status}`;
    status.textContent = route.status_label || route.status;
    article.appendChild(status);

    const summary = document.createElement('p');
    summary.textContent =
      route.summary ||
      `안정성 ${route.reliability_score} · 총 ${route.total_minutes}분 · 첫 대기 ${route.initial_wait_minutes}분`;
    article.appendChild(summary);

    if (route.recommendation) {
      const recommendation = document.createElement('p');
      recommendation.className = 'recommendation';
      recommendation.textContent = route.recommendation;
      article.appendChild(recommendation);
    }

    if (route.confidence_label) {
      const confidence = document.createElement('p');
      confidence.textContent = `판단 신뢰도: ${route.confidence_label}`;
      article.appendChild(confidence);
    }

    if (route.risk_warnings?.length) {
      const warnings = document.createElement('ul');
      warnings.className = 'warning-list';
      route.risk_warnings.forEach((message) => {
        const item = document.createElement('li');
        item.textContent = message;
        warnings.appendChild(item);
      });
      article.appendChild(warnings);
    }

    if (route.next_steps?.length) {
      const steps = document.createElement('ol');
      steps.className = 'next-steps';
      route.next_steps.forEach((message) => {
        const item = document.createElement('li');
        item.textContent = message;
        steps.appendChild(item);
      });
      article.appendChild(steps);
    }

    const segments = document.createElement('p');
    segments.textContent = (route.segments || [])
      .map(
        (segment) =>
          `${formatMinute(segment.departure_minute)}–${formatMinute(segment.arrival_minute)} · ${segment.route_id}: ${segment.from_station_name || segment.from_station_id} → ${segment.to_station_name || segment.to_station_id}`
      )
      .join(' / ');
    article.appendChild(segments);

    if (route.itinerary?.length) {
      const itinerary = document.createElement('ol');
      itinerary.className = 'next-steps';
      route.itinerary.forEach((leg) => {
        const item = document.createElement('li');
        const via = leg.via_stop_names?.length
          ? ` · 경유 ${leg.via_stop_names.join(' → ')}`
          : '';
        item.textContent =
          `${leg.board_time} ${leg.board_stop_name}에서 ${leg.route_id} 탑승 → ` +
          `${leg.alight_time} ${leg.alight_stop_name} 하차${via} · ${leg.time_source} · ` +
          `${leg.accuracy_notice}`;
        itinerary.appendChild(item);
      });
      article.appendChild(itinerary);
    }

    const transfers = document.createElement('p');
    if (!route.transfers || route.transfers.length === 0) {
      transfers.textContent = '환승 없음';
    } else {
      transfers.textContent = route.transfers
        .map(
          (transfer) =>
            `${transfer.status_label || transfer.status}: 필요 ${formatMinute(transfer.required_minute)}, 탑승 ${formatMinute(transfer.board_minute)}, 대기 ${transfer.wait_minutes ?? '-'}분 · ${transfer.message || transfer.reason}`
        )
        .join(' / ');
    }
    article.appendChild(transfers);

    const mapButton = document.createElement('button');
    mapButton.type = 'button';
    mapButton.textContent = '이 경로 지도에 표시';
    mapButton.addEventListener('click', () => renderMap(route, lastLocations));
    article.appendChild(mapButton);

    routeCards.appendChild(article);
  });
}

async function loadKakaoMapSdk() {
  mapStatus.textContent = '카카오맵 설정 확인 중';
  const config = await getJson('/api/kakao/config');
  if (!config.configured) {
    mapStatus.textContent =
      '카카오맵 키가 없습니다. .env에 KAKAO_MAP_JAVASCRIPT_KEY를 넣고 API 서버를 다시 시작하세요.';
    return;
  }
  if (window.kakao?.maps) {
    initializeKakaoMap();
    return;
  }
  const script = document.createElement('script');
  const params = new URLSearchParams({
    appkey: config.app_key,
    libraries: 'services',
    autoload: 'false',
  });
  script.src = `${config.sdk_url}?${params.toString()}`;
  script.addEventListener('load', () => {
    window.kakao.maps.load(initializeKakaoMap);
  });
  script.addEventListener('error', () => {
    mapStatus.textContent = '카카오맵 SDK를 불러오지 못했습니다. 키와 도메인 등록을 확인하세요.';
  });
  document.head.appendChild(script);
}

function initializeKakaoMap() {
  if (kakaoReady) {
    mapStatus.textContent = '카카오맵이 이미 준비되었습니다.';
    return;
  }
  const center = new window.kakao.maps.LatLng(35.8714, 128.6014);
  kakaoMap = new window.kakao.maps.Map(mapElement, { center, level: 6 });
  kakaoPlaces = new window.kakao.maps.services.Places(kakaoMap);
  kakaoReady = true;
  mapStatus.textContent = '카카오맵 준비 완료. 장소를 검색하거나 평가 결과를 지도에 표시할 수 있습니다.';
  renderMap(lastRoutes[0] || null, parseStationLocationsSafe());
}

function parseStationLocationsSafe() {
  try {
    return parseStationLocations();
  } catch {
    return {};
  }
}

function ensureKakaoReady() {
  if (!kakaoReady || !kakaoMap || !kakaoPlaces) {
    throw new Error('카카오맵이 아직 켜지지 않았습니다. 카카오맵 켜기 버튼을 먼저 누르세요.');
  }
}

function searchPlaces() {
  try {
    ensureKakaoReady();
  } catch (error) {
    mapStatus.textContent = error.message;
    return;
  }
  const keyword = placeKeyword.value.trim();
  if (!keyword) {
    mapStatus.textContent = '검색어를 입력하세요.';
    return;
  }
  placeResults.textContent = '카카오 장소 검색 중';
  kakaoPlaces.keywordSearch(keyword, (data, status) => {
    if (status !== window.kakao.maps.services.Status.OK) {
      placeResults.textContent = '검색 결과가 없습니다.';
      return;
    }
    renderPlaceResults(data.slice(0, 8));
  });
}

function renderPlaceResults(places) {
  placeResults.textContent = '';
  const bounds = new window.kakao.maps.LatLngBounds();
  places.forEach((place) => {
    const lat = Number(place.y);
    const lon = Number(place.x);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    const position = new window.kakao.maps.LatLng(lat, lon);
    bounds.extend(position);
    addMarker(position, place.place_name, '검색 결과');

    const item = document.createElement('article');
    item.className = 'result-item';

    const title = document.createElement('strong');
    title.textContent = place.place_name;
    item.appendChild(title);

    const address = document.createElement('p');
    address.textContent = place.road_address_name || place.address_name || `${lat}, ${lon}`;
    item.appendChild(address);

    item.appendChild(makeButton('실사용 출발 좌표로 저장', () => setPlanCoordinate('origin', place, lat, lon)));
    item.appendChild(makeButton('실사용 도착 좌표로 저장', () => setPlanCoordinate('destination', place, lat, lon)));
    item.appendChild(makeButton('출발 A로 저장', () => setLocationForStation(originVisualId.value, place, lat, lon)));
    item.appendChild(makeButton('환승 B로 저장', () => setLocationForStation(transferVisualId.value, place, lat, lon)));
    item.appendChild(makeButton('도착 C로 저장', () => setLocationForStation(destinationVisualId.value, place, lat, lon)));
    item.appendChild(makeButton('근처 TAGO 정류소 찾기', () => findNearbyTagoStations(lat, lon)));
    placeResults.appendChild(item);
  });
  kakaoMap.setBounds(bounds);
}

function setLocationForStation(stationId, place, lat, lon) {
  const normalizedId = (stationId || '').trim();
  if (!normalizedId) {
    mapStatus.textContent = '내부 정류장 ID가 비어 있습니다.';
    return;
  }
  const locations = parseStationLocationsSafe();
  locations[normalizedId] = {
    name: place.place_name,
    lat,
    lon,
  };
  stationLocationsJson.value = JSON.stringify(locations, null, 2);
  lastLocations = locations;
  mapStatus.textContent = `${normalizedId} 좌표를 ${place.place_name}로 저장했습니다.`;
  renderMap(lastRoutes[0] || null, locations);
}

async function findNearbyTagoStations(lat, lon) {
  nearbyStations.textContent = '근처 TAGO 정류소 조회 중';
  try {
    const params = new URLSearchParams({
      lat: String(lat),
      lon: String(lon),
      num_of_rows: '10',
    });
    const data = await getJson(`/api/tago/stations/nearby?${params.toString()}`);
    renderNearbyStations(data.stations || []);
  } catch (error) {
    nearbyStations.textContent = `TAGO 정류소 조회 실패: ${error.message}`;
  }
}

function renderNearbyStations(stations) {
  nearbyStations.textContent = '';
  if (stations.length === 0) {
    nearbyStations.textContent = '근처 TAGO 정류소가 없습니다.';
    return;
  }
  stations.forEach((station) => {
    const item = document.createElement('article');
    item.className = 'result-item';

    const title = document.createElement('strong');
    title.textContent = `${station.node_name || station.name || '정류소'} (${station.node_id})`;
    item.appendChild(title);

    const meta = document.createElement('p');
    meta.textContent = `위도 ${station.lat}, 경도 ${station.lon}`;
    item.appendChild(meta);

    item.appendChild(makeButton('TAGO 환승 정류소로 사용', () => {
      liveNodeId.value = station.node_id;
      mapStatus.textContent = `${station.node_id}를 TAGO 도착정보 조회 정류소로 넣었습니다.`;
    }));
    nearbyStations.appendChild(item);
  });
}

function renderMap(route, locations) {
  if (!kakaoReady || !kakaoMap) return;
  clearMapOverlays();
  if (!route) {
    drawStoredLocations(locations);
    return;
  }
  const stationIds = routeStationIds(route);
  const positions = [];
  const missing = [];

  stationIds.forEach((stationId) => {
    const location = locations[stationId];
    if (!location) {
      missing.push(stationId);
      return;
    }
    const position = new window.kakao.maps.LatLng(Number(location.lat), Number(location.lon));
    positions.push(position);
    addMarker(position, `${location.name || stationId} (${stationId})`, '경로 정류장');
  });

  if (positions.length >= 2) {
    const polyline = new window.kakao.maps.Polyline({
      path: positions,
      strokeWeight: 5,
      strokeOpacity: 0.85,
    });
    polyline.setMap(kakaoMap);
    mapPolylines.push(polyline);
    const bounds = new window.kakao.maps.LatLngBounds();
    positions.forEach((position) => bounds.extend(position));
    kakaoMap.setBounds(bounds);
  } else if (positions.length === 1) {
    kakaoMap.setCenter(positions[0]);
  }

  if (missing.length > 0) {
    mapStatus.textContent = `지도 표시 일부 누락: ${missing.join(', ')} 좌표가 없습니다.`;
  } else {
    mapStatus.textContent = `${route.route_id} 경로를 카카오맵에 표시했습니다.`;
  }
}

function drawStoredLocations(locations) {
  const entries = Object.entries(locations || {});
  if (entries.length === 0) return;
  const bounds = new window.kakao.maps.LatLngBounds();
  entries.forEach(([stationId, location]) => {
    const position = new window.kakao.maps.LatLng(Number(location.lat), Number(location.lon));
    bounds.extend(position);
    addMarker(position, `${location.name || stationId} (${stationId})`, '저장 좌표');
  });
  kakaoMap.setBounds(bounds);
}

function routeStationIds(route) {
  const ids = [];
  (route.segments || []).forEach((segment, index) => {
    if (index === 0) ids.push(segment.from_station_id);
    ids.push(segment.to_station_id);
  });
  return [...new Set(ids)];
}

function addMarker(position, title, label) {
  const marker = new window.kakao.maps.Marker({ position });
  marker.setMap(kakaoMap);
  mapMarkers.push(marker);
  const info = new window.kakao.maps.InfoWindow({
    content: `<div class="info-window"><strong>${escapeHtml(title)}</strong><br>${escapeHtml(label)}</div>`,
  });
  window.kakao.maps.event.addListener(marker, 'click', () => info.open(kakaoMap, marker));
}

function clearMapOverlays() {
  mapMarkers.forEach((marker) => marker.setMap(null));
  mapPolylines.forEach((polyline) => polyline.setMap(null));
  mapMarkers = [];
  mapPolylines = [];
}

function makeButton(text, onClick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = text;
  button.addEventListener('click', onClick);
  return button;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatMinute(value) {
  if (value === null || value === undefined) return '-';
  const day = Math.floor(value / 1440);
  const minuteOfDay = value % 1440;
  const hours = String(Math.floor(minuteOfDay / 60)).padStart(2, '0');
  const minutes = String(minuteOfDay % 60).padStart(2, '0');
  return day > 0 ? `+${day}일 ${hours}:${minutes}` : `${hours}:${minutes}`;
}

checkSetup.addEventListener('click', runSetupCheck);
loadSample.addEventListener('click', loadSamplePayload);
loadKakaoMap.addEventListener('click', () => {
  loadKakaoMapSdk().catch((error) => {
    mapStatus.textContent = `카카오맵 초기화 실패: ${error.message}`;
  });
});
searchPlace.addEventListener('click', searchPlaces);
placeKeyword.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') searchPlaces();
});
runLivePlan.addEventListener('click', () => {
  runLivePlanner().catch((error) => {
    const timedOut = /timed out|network request failed/i.test(error.message);
    const message = timedOut
      ? 'TAGO 공공데이터 서버 응답이 늦습니다. 자동 재시도 후에도 실패했습니다. 잠시 뒤 다시 실행하거나 탐색 범위를 줄여보세요.'
      : error.message;
    livePlanStatus.textContent = `실사용 모드 오류: ${message}`;
    output.textContent = `실사용 모드 오류: ${message}`;
  });
});

assessRoutes.addEventListener('click', () => {
  runAssessment().catch((error) => {
    output.textContent = `오류: ${error.message}`;
  });
});
quickAssess.addEventListener('click', () => {
  runQuickAssessment().catch((error) => {
    output.textContent = `간편 평가 오류: ${error.message}`;
  });
});

quickPresetSafe.addEventListener('click', () => {
  applyQuickPreset('safe').catch((error) => {
    output.textContent = `예시 불러오기 오류: ${error.message}`;
  });
});
quickPresetTight.addEventListener('click', () => {
  applyQuickPreset('tight').catch((error) => {
    output.textContent = `예시 불러오기 오류: ${error.message}`;
  });
});
quickPresetMissed.addEventListener('click', () => {
  applyQuickPreset('missed').catch((error) => {
    output.textContent = `예시 불러오기 오류: ${error.message}`;
  });
});

quickToJson.addEventListener('click', () => {
  try {
    quickToJsonInput();
  } catch (error) {
    output.textContent = `JSON 변환 오류: ${error.message}`;
  }
});

loadSamplePayload();
