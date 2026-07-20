const DEFAULT_API_URL = "http://127.0.0.1:8000";

export const API_URL = (import.meta.env.VITE_API_URL || DEFAULT_API_URL).replace(/\/$/, "");
export const DEMO_TIMESTAMP = "2025-11-13T03:00:00";

/** Fetch map-ready station forecasts from the FastAPI service. */
export async function getForecastGeoJson({ demo, signal }) {
  // A compact model-only deployment has no replay parquet. Ask the service
  // before requesting the fixed demo timestamp and gracefully use live mode.
  let replayAvailable = demo;
  if (demo) {
    const health = await fetch(`${API_URL}/health`, { signal });
    if (health.ok) replayAvailable = (await health.json()).replay_available !== false;
  }
  const endpoint = replayAvailable
    ? `/forecast?ts=${encodeURIComponent(DEMO_TIMESTAMP)}&format=geojson`
    : "/forecast/live?format=geojson";
  const response = await fetch(`${API_URL}${endpoint}`, { signal });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Forecast request failed (${response.status})`);
  }
  return response.json();
}

export function forecastStations(forecast) {
  if (forecast?.type === "FeatureCollection") {
    return forecast.features.map((feature) => ({
      ...feature.properties,
      lon: feature.geometry?.coordinates?.[0],
      lat: feature.geometry?.coordinates?.[1]
    }));
  }
  return forecast?.stations || [];
}

export function stationSeverity(station) {
  const alert = station?.horizons?.["1h"]?.alert;
  if (alert?.ge30cm) return "critical";
  if (alert?.ge15cm) return "warning";
  if (alert?.ge5cm) return "watch";
  return "normal";
}
