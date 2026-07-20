/**
 * scenarios.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Pre-defined hydrological scenarios that operators can select to simulate
 * different flood severity levels on the dashboard.
 *
 * Selecting a scenario updates the global DashboardStateContext, which in turn
 * adjusts metrics, maps, and chart data visible to the operator.
 *
 * TODO: Replace with API call — GET /api/v1/scenarios
 * ─────────────────────────────────────────────────────────────────────────────
 */

// TODO: Replace with API call — GET /api/v1/scenarios

export const FLOOD_SCENARIOS = [{
  id: "scenario-normal",
  name: "Normal Operations",
  description: "Dry season baseline — all drainage systems within capacity.",
  rainRateMmHr: 5,
  canalLevelPct: 35,
  drainCapacityPct: 28,
  riskScore: 8,
  dominantSeverity: "normal"
}, {
  id: "scenario-moderate",
  name: "Moderate Rain Event",
  description: "Short convective shower — minor ponding in low-lying areas.",
  rainRateMmHr: 25,
  canalLevelPct: 58,
  drainCapacityPct: 55,
  riskScore: 32,
  dominantSeverity: "watch"
}, {
  id: "scenario-current",
  name: "Current Situation",
  description: "Active heavy rainfall — 4 critical canals, upstream surge incoming.",
  rainRateMmHr: 58,
  canalLevelPct: 82,
  drainCapacityPct: 73,
  riskScore: 68,
  dominantSeverity: "warning"
}, {
  id: "scenario-extreme",
  name: "Extreme Monsoon Event",
  description: "Record multi-day rainfall — widespread inundation, emergency response active.",
  rainRateMmHr: 95,
  canalLevelPct: 97,
  drainCapacityPct: 112,
  riskScore: 94,
  dominantSeverity: "critical"
}, {
  id: "scenario-dam-release",
  name: "Upstream Dam Release",
  description: "Bhumibol/Sirikit dam gates opened — Chao Phraya surge in 6–8 hours.",
  rainRateMmHr: 30,
  canalLevelPct: 75,
  drainCapacityPct: 68,
  riskScore: 78,
  dominantSeverity: "critical"
}];

/** The default active scenario ID - matches the "current situation" mock data */
export const DEFAULT_SCENARIO_ID = "scenario-current";