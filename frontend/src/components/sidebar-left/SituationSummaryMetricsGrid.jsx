/**
 * SituationSummaryMetricsGrid.jsx  (sidebar-left/)
 * ─────────────────────────────────────────────────────────────────────────────
 * Four KPI metric cards displayed at the top of the left sidebar.
 * Data is dynamically derived from useDashboardState() with color-coding based
 * on configurable thresholds for each metric.
 *
 * Metrics displayed:
 *  • Current Rain: rainfall (mm/hr)
 *  • Active Floods: activeHotspots (count)
 *  • System Alerts: systemAlerts (count)
 *  • Upstream Flow: upstreamFlow (m³/s)
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { CloudRain, Waves, AlertTriangle, Activity } from "lucide-react";
import { useDashboardState } from "../../context/DashboardStateContext";
import { SEVERITY_COLOR } from "../../types/dashboard.types";
import { SectionHeader } from "../shared/SectionHeader";
import { forecastStations } from "../../lib/floodApi";

// ─── Icon registry ────────────────────────────────────────────────────────────
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const ICON_MAP = {
  CloudRain,
  Waves,
  AlertTriangle,
  Activity
};

/**
 * Determines severity level based on rainfall (mm/hr)
 */
function getRainfallSeverity(rainfall) {
  if (rainfall < 30) return "normal";
  if (rainfall < 60) return "watch";
  return "critical";
}

/**
 * Determines severity level based on active hotspot count
 */
function getHotspotSeverity(count) {
  if (count <= 2) return "normal";
  if (count <= 6) return "watch";
  return "critical";
}

/**
 * Determines severity level based on system alert count
 */
function getAlertSeverity(count) {
  if (count === 0) return "normal";
  if (count <= 3) return "watch";
  return "critical";
}

/**
 * Determines severity level based on upstream flow (m³/s)
 */
function getUpstreamFlowSeverity(flow) {
  if (flow < 1500) return "normal";
  if (flow < 2500) return "watch";
  return "critical";
}

/**
 * Gets the sub-label description for rainfall
 */
function getRainfallSubLabel(rainfall) {
  if (rainfall < 30) return "Minor waterlogging / Roads usable";
  if (rainfall < 60) return "Temporary street flooding";
  return "Rapid urban flooding";
}

/**
 * Gets the sub-label description for active hotspots
 */
function getHotspotSubLabel(count) {
  if (count <= 2) return "Localized pooling";
  if (count <= 6) return "Multiple districts affected";
  return "Widespread urban gridlock";
}

/**
 * Gets the sub-label description for alerts
 */
function getAlertSubLabel(count) {
  if (count === 0) return "All systems nominal";
  if (count <= 3) return "Review required";
  return "Immediate action required";
}

/**
 * Gets the sub-label description for upstream flow
 */
function getUpstreamFlowSubLabel(flow) {
  if (flow < 1500) return "Well below channel capacity";
  if (flow < 2500) return "Approaching wall limits";
  return "Max capacity breached";
}

/**
 * MetricCard — reusable card component
 */

function MetricCard({
  label,
  value,
  unit,
  subLabel,
  icon,
  severity,
  onClick
}) {
  const col = SEVERITY_COLOR[severity];
  const IconComponent = ICON_MAP[icon] ?? Activity;
  return /*#__PURE__*/_jsxs("div", {
    onClick: onClick,
    className: `rounded-lg border p-3 transition-all duration-300 ${col.bg} ${col.border} ${onClick ? "cursor-pointer hover:opacity-80" : ""}`,
    children: [/*#__PURE__*/_jsxs("div", {
      className: `mb-1.5 flex items-center gap-1.5 ${col.text}`,
      children: [/*#__PURE__*/_jsx(IconComponent, {
        className: "h-3.5 w-3.5 flex-shrink-0"
      }), /*#__PURE__*/_jsx("span", {
        className: "truncate text-xs font-medium tracking-wider uppercase text-slate-400",
        children: label
      })]
    }), /*#__PURE__*/_jsxs("div", {
      className: "flex items-baseline gap-1",
      children: [/*#__PURE__*/_jsx("span", {
        className: `text-xl leading-none font-bold font-mono ${col.text}`,
        children: value
      }), unit && /*#__PURE__*/_jsx("span", {
        className: "text-xs text-slate-500",
        children: unit
      })]
    }), /*#__PURE__*/_jsx("p", {
      className: "mt-1 truncate text-xs text-slate-500",
      children: subLabel
    })]
  });
}

/**
 * SituationSummaryMetricsGrid — 2×2 grid of KPI cards.
 * Gets data from useDashboardState() and applies dynamic color coding.
 */
export function SituationSummaryMetricsGrid({ liveFloodData }) {
  const {
    activeHotspots,
    viewMode,
    setActiveNavTab
  } = useDashboardState();
  
  const stations = forecastStations(liveFloodData);
  const activeFloods = stations.filter((station) => station.depth_now_cm >= 5).length;
  const alerts = stations.filter((station) => station.horizons?.["1h"]?.alert?.ge15cm).length;
  const averageDepth = stations.length
    ? stations.reduce((sum, station) => sum + (station.depth_now_cm || 0), 0) / stations.length
    : 0;

  return /*#__PURE__*/_jsxs("section", {
    className: "dashboard-card flex-shrink-0",
    children: [/*#__PURE__*/_jsx(SectionHeader, {
      title: "Situation Summary",
      subtitle: viewMode === "forecast" ? "Forecast — Next 3 Hours" : "Observed — Real Time",
      icon: /*#__PURE__*/_jsx(Activity, {
        className: "h-4 w-4"
      }),
      trailing: /*#__PURE__*/_jsx("span", {
        className: `rounded-full border px-2 py-0.5 text-xs font-medium ${viewMode === "forecast" ? "border-orange-500/40 bg-orange-500/20 text-orange-400" : "border-green-500/40 bg-green-500/20 text-green-400"}`,
        children: viewMode === "forecast" ? "+3hr" : "LIVE"
      })
    }), /*#__PURE__*/_jsxs("div", {
      className: "grid grid-cols-2 gap-2",
      children: [/*#__PURE__*/_jsx(MetricCard, {
        label: "Average Depth",
        value: stations.length ? averageDepth.toFixed(1) : "—",
        unit: "cm",
        subLabel: "Observed station depth",
        icon: "CloudRain",
        severity: averageDepth >= 30 ? "critical" : averageDepth >= 15 ? "watch" : "normal"
      }), /*#__PURE__*/_jsx(MetricCard, {
        label: "Active Floods",
        value: String(activeFloods),
        unit: "hotspots",
        subLabel: getHotspotSubLabel(activeFloods),
        icon: "Waves",
        severity: getHotspotSeverity(activeFloods),
        onClick: () => setActiveNavTab("resources")
      }), /*#__PURE__*/_jsx(MetricCard, {
        label: "System Alerts",
        value: String(alerts),
        unit: "active",
        subLabel: getAlertSubLabel(alerts),
        icon: "AlertTriangle",
        severity: getAlertSeverity(alerts),
        onClick: () => setActiveNavTab("alerts")
      }), /*#__PURE__*/_jsx(MetricCard, {
        label: "Peak P95",
        value: stations.length ? Math.max(...stations.map((station) => station.kpi?.peak_depth_p95_cm || 0)).toFixed(1) : "—",
        unit: "cm",
        subLabel: "Worst-case forecast depth",
        icon: "Activity",
        severity: averageDepth >= 30 ? "critical" : averageDepth >= 15 ? "watch" : "normal"
      })]
    })]
  });
}
