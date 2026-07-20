/**
 * chart.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Centralised Recharts configuration helpers — dark-mode compatible defaults
 * for tooltips, axes, and colour palettes used across all chart components.
 *
 * Import these config objects into chart components to ensure visual consistency
 * without repeating dark-mode styling in each file.
 * ─────────────────────────────────────────────────────────────────────────────
 */

/** Shared dark tooltip style injected into every <Tooltip contentStyle={...} /> */
export const DARK_TOOLTIP_STYLE = {
  backgroundColor: "#1e293b",
  // bg-slate-800
  border: "1px solid #334155",
  // border-slate-700
  borderRadius: "8px",
  color: "#f1f5f9",
  // text-slate-100
  fontSize: "12px",
  boxShadow: "0 4px 24px rgba(0,0,0,0.4)"
};

/** Cursor overlay style for area / bar charts.
 * Typed as React.SVGProps<SVGElement> — the correct type for Recharts' cursor prop. */
export const DARK_CURSOR_STYLE = {
  stroke: "#334155",
  // Tailwind slate-700
  strokeWidth: 2,
  strokeDasharray: "4 4"
};

/** Common Recharts CartesianGrid stroke (subtle grid lines) */
export const GRID_STROKE = "#1e3a5f";

/** Axis tick text colour */
export const AXIS_TICK_COLOR = "#64748b"; // slate-500

/** Axis line colour (use 'none' to remove axis lines entirely) */
export const AXIS_LINE_COLOR = "none";

/** Semantic line/area colours for chart series */
export const CHART_COLORS = {
  upstreamFlow: "#3b82f6",
  // blue-500
  canalSukhumvit: "#a855f7",
  // purple-500
  canalBangkhen: "#06b6d4",
  // cyan-500
  criticalLine: "#ef4444",
  // red-500
  riskArea: "#f97316",
  // orange-500
  upperBand: "#f9731620",
  // orange-500 at 12% opacity
  lowerBand: "#f9731608",
  gridLine: "#1e3a5f"
};

/** Recharts default margin to remove blank padding on small containers */
export const COMPACT_MARGIN = {
  top: 4,
  right: 8,
  left: -16,
  bottom: 0
};

/** Recharts margin used when left axis labels are visible */
export const STANDARD_MARGIN = {
  top: 8,
  right: 16,
  left: 0,
  bottom: 0
};