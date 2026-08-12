/**
 * HotspotLocationCardList.jsx  (sidebar-right/)
 * ─────────────────────────────────────────────────────────────────────────────
 * List of the most at-risk flood hotspot locations, each displayed as a
 * compact card showing:
 *   • Location name
 *   • Current flood depth (cm)
 *   • Minutes until canal overflow / road closure
 *   • Rising / stable / falling trend arrow
 *   • Severity colour treatment
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { useMemo } from "react";
import { MapPin, TrendingUp, TrendingDown, Minus, Timer, Droplets } from "lucide-react";
import { SEVERITY_COLOR } from "../../types/dashboard.types";
import { SectionHeader } from "../shared/SectionHeader";
import { forecastStations, stationSeverity } from "../../lib/floodApi";

// ─── Trend icon resolver ──────────────────────────────────────────────────────
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
function TrendIcon({ trend }) {
  switch (trend) {
    case "rising":
      return /*#__PURE__*/_jsx(TrendingUp, { className: "h-3 w-3 text-red-400" });
    case "falling":
      return /*#__PURE__*/_jsx(TrendingDown, { className: "h-3 w-3 text-green-400" });
    case "stable":
      return /*#__PURE__*/_jsx(Minus, { className: "h-3 w-3 text-yellow-400" });
    default:
      return null;
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export function HotspotLocationCardList({ liveFloodData }) {
  const hotspots = useMemo(() => forecastStations(liveFloodData)
    .filter((station) => stationSeverity(station) !== "normal")
    .sort((a, b) => (b.kpi?.peak_risk_pct || 0) - (a.kpi?.peak_risk_pct || 0))
    .slice(0, 8)
    .map((station) => ({
      id: station.station_code,
      name: station.district || station.station_code,
      severity: stationSeverity(station),
      depthCm: station.depth_now_cm,
      minutesToFlood: station.kpi?.time_to_warning_h == null ? "—" : station.kpi.time_to_warning_h * 60,
      trend: "rising"
    })), [liveFloodData]);

  const criticalCount = hotspots.filter((h) => h.severity === "critical").length;

  return /*#__PURE__*/_jsxs("section", {
    className: "dashboard-card flex flex-shrink-0 flex-col",
    children: [/*#__PURE__*/_jsx(SectionHeader, {
      title: "Major Hotspots",
      subtitle: `${criticalCount} critical locations`,
      icon: /*#__PURE__*/_jsx(MapPin, {
        className: "h-4 w-4"
      }),
      trailing: /*#__PURE__*/_jsxs("span", {
        className: "text-xs text-slate-500",
        children: [hotspots.length, " total"]
      })
    }), 
    hotspots.length === 0 ? /*#__PURE__*/_jsx("div", {
      className: "flex items-center justify-center p-4 text-xs text-slate-500 font-mono",
      children: "No critical hotspots."
    }) : /*#__PURE__*/_jsx("div", {
      className: "space-y-1.5 flex-1 min-h-0 overflow-y-auto",
      children: hotspots.map((hotspot) => {
        const col = SEVERITY_COLOR[hotspot.severity] || SEVERITY_COLOR.info;
        const isUrgent = typeof hotspot.minutesToFlood === "number" && hotspot.minutesToFlood <= 15;
        return /*#__PURE__*/_jsxs("div", {
          className: `flex items-center gap-2 rounded-lg border px-2.5 py-2 transition-all duration-150 hover:scale-[1.01] active:scale-100 ${col.bg} ${col.border} `,
          children: [/*#__PURE__*/_jsx(MapPin, {
            className: `h-3.5 w-3.5 flex-shrink-0 ${col.text}`
          }), /*#__PURE__*/_jsx("div", {
            className: "min-w-0 flex-1",
            children: /*#__PURE__*/_jsx("p", {
              className: `truncate text-xs font-semibold ${col.text}`,
              children: hotspot.name
            })
          }), /*#__PURE__*/_jsxs("div", {
            className: "flex items-center gap-0.5 text-xs font-mono whitespace-nowrap text-slate-400",
            children: [/*#__PURE__*/_jsx(Droplets, {
              className: "h-3 w-3"
            }), /*#__PURE__*/_jsxs("span", {
              children: [hotspot.depthCm, "cm"]
            })]
          }), /*#__PURE__*/_jsxs("div", {
            className: `flex items-center gap-0.5 text-xs font-mono whitespace-nowrap ${isUrgent ? "font-bold text-red-400 animate-pulse" : "text-slate-400"}`,
            children: [/*#__PURE__*/_jsx(Timer, {
              className: "h-3 w-3"
            }), /*#__PURE__*/_jsxs("span", {
              children: [hotspot.minutesToFlood, "m"]
            })]
          }), /*#__PURE__*/_jsx(TrendIcon, {
            trend: hotspot.trend
          })]
        }, hotspot.id);
      })
    })]
  });
}
