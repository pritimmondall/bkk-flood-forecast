/**
 * FloodAlertStatusBadges.jsx  (sidebar-left/)
 * ─────────────────────────────────────────────────────────────────────────────
 * Three clickable alert-count badges displayed below the Situation Summary.
 *
 * Badge rows:
 *  • 4 Critical  (red)
 *  • 6 Warning   (orange)
 *  • 15 Watch    (yellow)
 *
 * Clicking a badge:
 *  → Filters the EventLogScrollableList to show only entries with that severity.
 *  → Clicking the active badge again clears the filter (shows all entries).
 *
 * The selected badge gets a highlighted border and background.
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { AlertCircle, AlertTriangle, Eye, Bell } from "lucide-react";
import { useForecast } from "../../hooks/useForecast";
import { useDashboardState } from "../../context/DashboardStateContext";
import { SEVERITY_COLOR, SEVERITY_LABEL } from "../../types/dashboard.types";
import { SectionHeader } from "../shared/SectionHeader";

// ─── Badge icon map ───────────────────────────────────────────────────────────
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
function BadgeIcon({
  severity
}) {
  const cls = `w-4 h-4 ${SEVERITY_COLOR[severity].text}`;
  switch (severity) {
    case "critical":
      return /*#__PURE__*/_jsx(AlertCircle, {
        className: cls
      });
    case "warning":
      return /*#__PURE__*/_jsx(AlertTriangle, {
        className: cls
      });
    case "watch":
      return /*#__PURE__*/_jsx(Eye, {
        className: cls
      });
    default:
      return /*#__PURE__*/_jsx(Bell, {
        className: cls
      });
  }
}

/**
 * FloodAlertStatusBadges — clickable severity badge row.
 * Controls the EventLog filter via DashboardStateContext.
 */
export function FloodAlertStatusBadges() {
  const {
    alertBadges
  } = useForecast();
  const {
    selectedAlertSeverity,
    setSelectedAlertSeverity
  } = useDashboardState();
  return /*#__PURE__*/_jsxs("section", {
    className: "dashboard-card flex-shrink-0",
    children: [/*#__PURE__*/_jsx(SectionHeader, {
      title: "Alert Status",
      icon: /*#__PURE__*/_jsx(Bell, {
        className: "h-4 w-4"
      }),
      trailing: selectedAlertSeverity ?
      /*#__PURE__*/
      // "Clear filter" button appears when a badge is selected
      _jsx("button", {
        onClick: () => setSelectedAlertSeverity(null),
        className: "text-xs text-slate-500 underline underline-offset-2 transition-colors hover:text-slate-300",
        children: "Clear filter"
      }) : /*#__PURE__*/_jsx("span", {
        className: "text-xs text-slate-500",
        children: "Click to filter log"
      })
    }), /*#__PURE__*/_jsx("div", {
      className: "space-y-2",
      children: alertBadges.map((badge) => {
        const col = SEVERITY_COLOR[badge.severity];
        const isSelected = selectedAlertSeverity === badge.severity;
        return /*#__PURE__*/_jsxs("button", {
          onClick: () => setSelectedAlertSeverity(badge.severity),
          "aria-pressed": isSelected,
          className: `flex w-full items-center justify-between rounded-lg border px-3 py-2.5 transition-all duration-150 hover:scale-[1.01] active:scale-100 ${isSelected ? `${col.bg} ${col.border} ring-1 ring-inset ${col.text.replace("text-", "ring-")}` : `border-slate-700 bg-slate-700/30 hover:${col.bg} hover:${col.border}`} `,
          children: [/*#__PURE__*/_jsxs("div", {
            className: "flex items-center gap-2",
            children: [/*#__PURE__*/_jsx(BadgeIcon, {
              severity: badge.severity
            }), /*#__PURE__*/_jsx("span", {
              className: `text-sm font-semibold ${col.text}`,
              children: SEVERITY_LABEL[badge.severity]
            })]
          }), /*#__PURE__*/_jsx("span", {
            className: `rounded-md px-2 py-0.5 text-lg leading-none font-bold font-mono ${col.bg} ${col.text} `,
            children: badge.count
          })]
        }, badge.id);
      })
    })]
  });
}