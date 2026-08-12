/**
 * useForecast.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Custom hook that derives fully-resolved forecast data from the global
 * dashboard state.  Components import this hook instead of consuming mock data
 * directly, so that later API integration only requires modifying this file.
 *
 * TODO: Replace mock data returns with API calls using the patterns below.
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { useMemo } from "react";
import { useDashboardState } from "../context/DashboardStateContext";
import { SITUATION_METRICS_NOW, SITUATION_METRICS_FORECAST, FLOOD_ZONES_NOW, FLOOD_ZONES_FORECAST, FLOODBOT_MARKERS, MAP_LEGEND_ITEMS, WATER_LEVEL_DATA, RISK_TIMELINE_DATA, FORECAST_RISK_DATA, HOTSPOT_LOCATIONS, FORECAST_MODEL_PARAMETERS, EVENT_LOG_ENTRIES, ALERT_BADGES } from "../data/mockForecast";
import { FLOOD_SCENARIOS } from "../data/scenarios";

// ─── Return type ──────────────────────────────────────────────────────────────

// ─── Hook ─────────────────────────────────────────────────────────────────────

/**
 * useForecast — derives all display data from global state and mock data.
 *
 * TODO: Replace with API call — useQuery('/api/v1/forecast/current')
 */
export function useForecast() {
  const {
    viewMode,
    selectedAlertSeverity,
    activeScenarioId,
    rainfall,
    upstreamFlow
  } = useDashboardState();
  const isForecastMode = viewMode === "forecast";

  // API data is loaded once by DashboardLayout and passed to dashboard panels.
  const liveRiskScore = null;
  const liveWeather = null;

  // Situation metrics swap based on viewMode and backend data
  const situationMetrics = useMemo(() => {
    const metrics = isForecastMode ? [...SITUATION_METRICS_FORECAST] : [...SITUATION_METRICS_NOW];
    return metrics.map((metric) => {
      // Override Rainfall with simulation/dashboard state
      if (metric.id === "rain-rate") {
        return {
          ...metric,
          value: String(rainfall),
          subLabel: liveWeather?.Rainfall_Intensity !== undefined ? "Live Local/Simulation" : "ML Simulation Data"
        };
      }
      // Override flood depth via risk score for forecast
      if (metric.id === "flood-depth" && liveRiskScore !== null && isForecastMode) {
        return {
          ...metric,
          value: (liveRiskScore * 0.5).toFixed(1) + "–" + (liveRiskScore * 0.8).toFixed(1),
          subLabel: "ML Model Prediction"
        };
      }
      return metric;
    });
  }, [isForecastMode, liveWeather, liveRiskScore]);

  // Adjust ForecastModelParameters with live fetched data
  const forecastModelParameters = useMemo(() => {
    // Clone array and clone objects to avoid mutating global mock data
    const params = FORECAST_MODEL_PARAMETERS.map((p) => ({
      ...p
    }));
    const mappedRainfall = params.find((p) => p.id === "p-01");
    if (mappedRainfall) {
      mappedRainfall.value = rainfall.toString();
      mappedRainfall.withinNormalRange = rainfall < 20;
    }
    const mappedUpstream = params.find((p) => p.id === "p-03");
    if (mappedUpstream) {
      mappedUpstream.value = upstreamFlow.toString();
      mappedUpstream.withinNormalRange = upstreamFlow < 1500;
    }

    // Add real ML prediction risk to top of list
    if (liveRiskScore !== null) {
      params.unshift({
        id: "ml-risk-score",
        label: "Overall ML Risk Score",
        value: liveRiskScore.toFixed(2),
        unit: "%",
        withinNormalRange: liveRiskScore < 50
      });
    }

    // Add Live temperature
    if (liveWeather) {
      params.unshift({
        id: "live-temp",
        label: "Open-Meteo Temp",
        value: liveWeather.Temperature?.toString() || "--",
        unit: "°C",
        withinNormalRange: true
      });
    }
    return params;
  }, [liveRiskScore, liveWeather, rainfall, upstreamFlow]);

  // Flood zone extents grow in forecast mode (zones expand as water rises)
  const floodZones = useMemo(() => isForecastMode ? FLOOD_ZONES_FORECAST : FLOOD_ZONES_NOW, [isForecastMode]);

  // Event log filtered by the currently selected alert severity badge
  const filteredEventLog = useMemo(() => {
    if (!selectedAlertSeverity) return EVENT_LOG_ENTRIES;
    return EVENT_LOG_ENTRIES.filter((entry) => entry.severity === selectedAlertSeverity);
  }, [selectedAlertSeverity]);

  // Active scenario resolved from the scenario ID
  const activeScenario = useMemo(() => FLOOD_SCENARIOS.find((s) => s.id === activeScenarioId), [activeScenarioId]);
  return {
    situationMetrics,
    floodZones,
    floodbotMarkers: FLOODBOT_MARKERS,
    mapLegendItems: MAP_LEGEND_ITEMS,
    waterLevelData: WATER_LEVEL_DATA,
    riskTimelineData: RISK_TIMELINE_DATA,
    forecastRiskData: FORECAST_RISK_DATA,
    hotspotLocations: HOTSPOT_LOCATIONS,
    forecastModelParameters,
    filteredEventLog,
    alertBadges: ALERT_BADGES,
    activeScenario,
    allScenarios: FLOOD_SCENARIOS,
    isForecastMode
  };
}
