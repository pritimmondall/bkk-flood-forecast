/**
 * dashboard.types.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Centralised TypeScript definitions for every entity used in the
 * AI-Based Urban Flood Forecasting System dashboard.
 *
 * These interfaces are intentionally shaped to mirror future REST/WebSocket API
 * response bodies so that swapping mock data for live data requires only
 * replacing the data import, not refactoring component code.
 * ─────────────────────────────────────────────────────────────────────────────
 */

// ─── Severity / Risk levels ───────────────────────────────────────────────────

/** Uniform severity scale used across alerts, hotspots, and map overlays */

/** Human-readable display label for each severity level */
export const SEVERITY_LABEL = {
  critical: "Critical",
  warning: "Warning",
  watch: "Watch",
  normal: "Normal",
  info: "Info"
};

/** Tailwind colour tokens mapped to each severity (bg + text variants) */
export const SEVERITY_COLOR = {
  critical: {
    bg: "bg-red-500/20",
    text: "text-red-400",
    border: "border-red-500/50"
  },
  warning: {
    bg: "bg-orange-500/20",
    text: "text-orange-400",
    border: "border-orange-500/50"
  },
  watch: {
    bg: "bg-yellow-500/20",
    text: "text-yellow-400",
    border: "border-yellow-500/50"
  },
  normal: {
    bg: "bg-green-500/20",
    text: "text-green-400",
    border: "border-green-500/50"
  },
  info: {
    bg: "bg-blue-500/20",
    text: "text-blue-400",
    border: "border-blue-500/50"
  }
};

// ─── View Mode ────────────────────────────────────────────────────────────────

/** Controls whether the dashboard displays real-time or forecast data */

// ─── Navigation ───────────────────────────────────────────────────────────────

/** Top navigation tab identifiers */

/** Drill-down zoom level for map views */

// ─── Situation Summary Metrics ────────────────────────────────────────────────

/**
 * SituationMetric — one KPI card in the Situation Summary strip.
 * e.g. "Current Rain Rate: 58 mm/hr"
 */

// ─── Alert Badge ─────────────────────────────────────────────────────────────

/**
 * AlertBadgeItem — one clickable badge in the Alert Status panel.
 * Clicking a badge filters the Event Log to show only matching entries.
 */

// ─── Event Log ────────────────────────────────────────────────────────────────

/**
 * EventLogEntry — one row inside the scrollable Event Log.
 * Rows are filtered based on the currently selected AlertBadgeItem.
 */

// ─── Map Overlay ─────────────────────────────────────────────────────────────

/**
 * FloodZone — a discrete flooded area drawn on the map SVG layer.
 * Coordinates are expressed as % offsets relative to the map container
 * so the layout stays responsive without a mapping library.
 */

/**
 * FloodBotMarker — an observed sensor / floodbot location.
 */

/**
 * MapLegendItem — one entry in the map colour legend.
 */

// ─── Charts ───────────────────────────────────────────────────────────────────

/**
 * WaterLevelDataPoint — one row in the Water Level time-series line chart.
 */

/**
 * RiskTimelineDataPoint — one bar in the Risk Timeline bar chart.
 * Represents flood probability at a future time slice.
 */

/**
 * ForecastRiskDataPoint — one point in the Forecast Risk area chart.
 */

// ─── Hotspots ─────────────────────────────────────────────────────────────────

/**
 * HotspotLocation — one card in the Major Hotspots list.
 */

// ─── Forecast Model Parameters ────────────────────────────────────────────────

/**
 * ForecastModelParameter — one hydrological input used by the ML model.
 * Displayed in the left sidebar for operator awareness.
 */

// ─── Scenarios ────────────────────────────────────────────────────────────────

/**
 * FloodScenario — a preset hydrological scenario the operator can select.
 * Used by ScenarioControls to update the entire dashboard state.
 */

// ─── Dashboard Context State ──────────────────────────────────────────────────

/**
 * DashboardState — the complete shape of the global React context.
 */

/**
 * DashboardActions — all mutating actions dispatched into context.
 */