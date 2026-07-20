/**
 * mockForecast.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Hardcoded mock data powering the AI-Based Urban Flood Forecasting System.
 *
 * Coordinates and locations have been localized to the Bangkok Metropolitan
 * Area for live-tracking integration and local testing.
 *
 * TODO: Replace with API call — GET /api/v1/forecast/current
 * ─────────────────────────────────────────────────────────────────────────────
 */

// ─── Situation Summary Metrics ────────────────────────────────────────────────
export const SITUATION_METRICS_NOW = [{
  id: "rain-rate",
  label: "Current Rain Rate",
  value: "58",
  unit: "mm/hr",
  iconName: "CloudRain",
  severity: "critical",
  subLabel: "Heavy rainfall active"
}, {
  id: "flood-depth",
  label: "Flooding Depth Range",
  value: "22–45",
  unit: "cm",
  iconName: "Waves",
  severity: "critical",
  subLabel: "Deep water streets"
}, {
  id: "critical-canals",
  label: "Critical Canal Levels",
  value: "4",
  unit: "canals",
  iconName: "AlertTriangle",
  severity: "critical",
  subLabel: "10 high, 6 normal"
}, {
  id: "upstream-flow",
  label: "Upstream Flow",
  value: "960",
  unit: "m³/s",
  iconName: "Activity",
  severity: "warning",
  subLabel: "+12% vs 1hr ago"
}];
export const SITUATION_METRICS_FORECAST = [{
  id: "rain-rate",
  label: "Forecast Rain Rate",
  value: "72",
  unit: "mm/hr",
  iconName: "CloudRain",
  severity: "critical",
  subLabel: "Intensifying in 90 min"
}, {
  id: "flood-depth",
  label: "Projected Depth Range",
  value: "35–65",
  unit: "cm",
  iconName: "Waves",
  severity: "critical",
  subLabel: "Road closures likely"
}, {
  id: "critical-canals",
  label: "At-Risk Canal Levels",
  value: "7",
  unit: "canals",
  iconName: "AlertTriangle",
  severity: "critical",
  subLabel: "3 overflow imminent"
}, {
  id: "upstream-flow",
  label: "Projected Flow",
  value: "1140",
  unit: "m³/s",
  iconName: "Activity",
  severity: "critical",
  subLabel: "+18% vs current"
}];

// ─── Alert Status Badges ──────────────────────────────────────────────────────
export const ALERT_BADGES = [{
  id: "badge-critical",
  severity: "critical",
  count: 4,
  label: "Critical"
}, {
  id: "badge-warning",
  severity: "warning",
  count: 6,
  label: "Warning"
}, {
  id: "badge-watch",
  severity: "watch",
  count: 15,
  label: "Watch"
}];

// ─── Event Log Entries ────────────────────────────────────────────────────────
export const EVENT_LOG_ENTRIES = [{
  id: "evt-001",
  timestamp: "2026-03-04T14:38:00Z",
  timeDisplay: "14:38",
  severity: "critical",
  title: "Canal Overflow Detected",
  description: "Khlong Saen Saep breached bank — water entering Sukhumvit.",
  location: "Sukhumvit",
  acknowledged: false
}, {
  id: "evt-002",
  timestamp: "2026-03-04T14:32:00Z",
  timeDisplay: "14:32",
  severity: "critical",
  title: "Floodbot Sensor Alert",
  description: "Sensor FB-047 reports 45 cm standing water depth on Silom Road.",
  location: "Silom",
  acknowledged: false
}, {
  id: "evt-003",
  timestamp: "2026-03-04T14:25:00Z",
  timeDisplay: "14:25",
  severity: "critical",
  title: "Pump Station Failure",
  description: "Pump station P-12 (Sathorn) offline due to power fault.",
  location: "Sathorn",
  acknowledged: false
}, {
  id: "evt-004",
  timestamp: "2026-03-04T14:18:00Z",
  timeDisplay: "14:18",
  severity: "critical",
  title: "Drain Capacity Exceeded",
  description: "Ladkrabang drainage at 118% capacity — overflow active near station.",
  location: "Ladkrabang",
  acknowledged: false
}, {
  id: "evt-005",
  timestamp: "2026-03-04T14:10:00Z",
  timeDisplay: "14:10",
  severity: "warning",
  title: "Elevated Canal Level",
  description: "Khlong Phadung Krung Kasem at 87% bank-full, rising at +3 cm/min.",
  location: "Dusit",
  acknowledged: false
}, {
  id: "evt-006",
  timestamp: "2026-03-04T14:05:00Z",
  timeDisplay: "14:05",
  severity: "warning",
  title: "Traffic Disruption",
  description: "Vibhavadi Rangsit Road — 2 lanes closed, shallow flooding (18 cm).",
  location: "Vibhavadi Rangsit",
  acknowledged: true
}];

// ─── Flood Map Zones (Real GPS Coordinates for Bangkok) ───────────────────────
export const FLOOD_ZONES_NOW = [{
  id: "fz-01",
  district: "Sukhumvit",
  lat: 13.7367,
  lng: 100.5611,
  radius: 1200,
  severity: "critical",
  depthCm: 45
}, {
  id: "fz-02",
  district: "Silom",
  lat: 13.7276,
  lng: 100.5284,
  radius: 800,
  severity: "critical",
  depthCm: 38
}, {
  id: "fz-03",
  district: "Ladkrabang",
  lat: 13.7220,
  lng: 100.7760,
  radius: 1500,
  severity: "critical",
  depthCm: 40
}, {
  id: "fz-04",
  district: "Sathorn",
  lat: 13.7196,
  lng: 100.5289,
  radius: 900,
  severity: "warning",
  depthCm: 22
}, {
  id: "fz-05",
  district: "Bang Kapi",
  lat: 13.7650,
  lng: 100.6430,
  radius: 1100,
  severity: "warning",
  depthCm: 28
}, {
  id: "fz-06",
  district: "Chatuchak",
  lat: 13.8280,
  lng: 100.5560,
  radius: 1800,
  severity: "watch",
  depthCm: 15
}, {
  id: "fz-07",
  district: "Don Mueang",
  lat: 13.9180,
  lng: 100.6010,
  radius: 1000,
  severity: "watch",
  depthCm: 12
}];
export const FLOOD_ZONES_FORECAST = [{
  id: "fz-01",
  district: "Sukhumvit",
  lat: 13.7367,
  lng: 100.5611,
  radius: 1600,
  severity: "critical",
  depthCm: 65
}, {
  id: "fz-02",
  district: "Silom",
  lat: 13.7276,
  lng: 100.5284,
  radius: 1100,
  severity: "critical",
  depthCm: 55
}, {
  id: "fz-03",
  district: "Ladkrabang",
  lat: 13.7220,
  lng: 100.7760,
  radius: 2000,
  severity: "critical",
  depthCm: 58
}, {
  id: "fz-04",
  district: "Sathorn",
  lat: 13.7196,
  lng: 100.5289,
  radius: 1300,
  severity: "critical",
  depthCm: 40
}, {
  id: "fz-05",
  district: "Bang Kapi",
  lat: 13.7650,
  lng: 100.6430,
  radius: 1500,
  severity: "warning",
  depthCm: 42
}, {
  id: "fz-06",
  district: "Chatuchak",
  lat: 13.8280,
  lng: 100.5560,
  radius: 2200,
  severity: "warning",
  depthCm: 30
}, {
  id: "fz-07",
  district: "Don Mueang",
  lat: 13.9180,
  lng: 100.6010,
  radius: 1400,
  severity: "critical",
  depthCm: 35
}];

// ─── Floodbot Sensor Markers (Real GPS) ───────────────────────────────────────
export const FLOODBOT_MARKERS = [{
  id: "fb-01",
  label: "FB-047",
  lat: 13.7370,
  lng: 100.5615,
  depthCm: 45,
  severity: "critical"
}, {
  id: "fb-02",
  label: "FB-012",
  lat: 13.7280,
  lng: 100.5280,
  depthCm: 38,
  severity: "critical"
}, {
  id: "fb-03",
  label: "FB-088",
  lat: 13.7230,
  lng: 100.7750,
  depthCm: 40,
  severity: "critical"
}, {
  id: "fb-04",
  label: "FB-031",
  lat: 13.7200,
  lng: 100.5295,
  depthCm: 22,
  severity: "warning"
}];

// ─── Map Legend Items ─────────────────────────────────────────────────────────
export const MAP_LEGEND_ITEMS = [{
  label: "Critical Flood Zone",
  color: "#ef4444"
}, {
  label: "Warning Zone",
  color: "#f97316"
}, {
  label: "Watch Zone",
  color: "#eab308"
}, {
  label: "Observed Floodbot",
  color: "#3b82f6"
}, {
  label: "Near Overflow Canal",
  color: "#a855f7"
}];

// ─── Water Level Time-Series Line Chart ───────────────────────────────────────
export const WATER_LEVEL_DATA = [{
  time: "08:00",
  upstreamFlow: 650,
  canalSukhumvit: 58,
  canalBangkhen: 62,
  criticalThreshold: 90
}, {
  time: "10:00",
  upstreamFlow: 740,
  canalSukhumvit: 67,
  canalBangkhen: 70,
  criticalThreshold: 90
}, {
  time: "12:00",
  upstreamFlow: 860,
  canalSukhumvit: 79,
  canalBangkhen: 80,
  criticalThreshold: 90
}, {
  time: "14:00",
  upstreamFlow: 960,
  canalSukhumvit: 92,
  canalBangkhen: 91,
  criticalThreshold: 90
}, {
  time: "+1hr",
  upstreamFlow: 1020,
  canalSukhumvit: 97,
  canalBangkhen: 96,
  criticalThreshold: 90
}, {
  time: "+2hr",
  upstreamFlow: 1080,
  canalSukhumvit: 102,
  canalBangkhen: 101,
  criticalThreshold: 90
}, {
  time: "+3hr",
  upstreamFlow: 1140,
  canalSukhumvit: 108,
  canalBangkhen: 106,
  criticalThreshold: 90
}];

// ─── Risk Timeline Bar Chart ──────────────────────────────────────────────────
export const RISK_TIMELINE_DATA = [{
  time: "Now",
  probability: 45,
  severity: "warning"
}, {
  time: "+60m",
  probability: 66,
  severity: "warning"
}, {
  time: "+120m",
  probability: 81,
  severity: "critical"
}, {
  time: "+180m",
  probability: 91,
  severity: "critical"
}];

// ─── Forecast Risk Area Chart ─────────────────────────────────────────────────
export const FORECAST_RISK_DATA = [{
  time: "Now",
  riskScore: 45,
  upperBound: 52,
  lowerBound: 38
}, {
  time: "+60m",
  riskScore: 66,
  upperBound: 76,
  lowerBound: 56
}, {
  time: "+120m",
  riskScore: 81,
  upperBound: 91,
  lowerBound: 71
}, {
  time: "+180m",
  riskScore: 91,
  upperBound: 98,
  lowerBound: 84
}];

// ─── Major Hotspot Locations ──────────────────────────────────────────────────
export const HOTSPOT_LOCATIONS = [{
  id: "hs-01",
  name: "Sukhumvit Intersection",
  depthCm: 45,
  minutesToFlood: 8,
  severity: "critical",
  trend: "rising"
}, {
  id: "hs-02",
  name: "Silom Road",
  depthCm: 38,
  minutesToFlood: 14,
  severity: "critical",
  trend: "rising"
}, {
  id: "hs-03",
  name: "Vibhavadi Rangsit Road",
  depthCm: 40,
  minutesToFlood: 11,
  severity: "critical",
  trend: "rising"
}, {
  id: "hs-04",
  name: "Ladkrabang Intersection",
  depthCm: 42,
  minutesToFlood: 6,
  severity: "critical",
  trend: "rising"
}, {
  id: "hs-05",
  name: "Sathorn Road",
  depthCm: 22,
  minutesToFlood: 30,
  severity: "warning",
  trend: "stable"
}, {
  id: "hs-06",
  name: "Bang Kapi Junction",
  depthCm: 28,
  minutesToFlood: 22,
  severity: "warning",
  trend: "rising"
}];

// ─── Forecast Model Parameters ────────────────────────────────────────────────
export const FORECAST_MODEL_PARAMETERS = [{
  id: "p-01",
  label: "Rainfall Accumulation",
  value: "58",
  unit: "mm/hr",
  withinNormalRange: false
}, {
  id: "p-02",
  label: "Soil Moisture Index",
  value: "0.87",
  unit: "",
  withinNormalRange: false
}, {
  id: "p-03",
  label: "Upstream River Flow",
  value: "960",
  unit: "m³/s",
  withinNormalRange: false
}, {
  id: "p-04",
  label: "Canal Drain Capacity",
  value: "73",
  unit: "%",
  withinNormalRange: true
}, {
  id: "p-05",
  label: "Evapotranspiration",
  value: "2.1",
  unit: "mm/day",
  withinNormalRange: true
}, {
  id: "p-06",
  label: "Surface Runoff Coeff.",
  value: "0.72",
  unit: "",
  withinNormalRange: false
}];