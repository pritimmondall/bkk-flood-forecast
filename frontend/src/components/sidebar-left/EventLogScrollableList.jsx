/**
 * EventLogScrollableList.jsx  (sidebar-left/)
 * ─────────────────────────────────────────────────────────────────────────────
 * Scrollable list of flood event log entries displayed in the left sidebar.
 *
 * Features:
 *  • Filtered by the selectedAlertSeverity from DashboardStateContext
 *    (badge click in FloodAlertStatusBadges controls the filter)
 *  • Each row shows: timestamp, severity icon, event title, location
 *  • Acknowledged events are dimmed
 *  • Hover state highlights the entry row
 *  • Smooth scrolling with custom dark scrollbar
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { ScrollText, AlertCircle, AlertTriangle, Eye, Info } from "lucide-react";
import { useForecast } from "../../hooks/useForecast";
import { useDashboardState } from "../../context/DashboardStateContext";
import { SEVERITY_COLOR } from "../../types/dashboard.types";
import { SectionHeader } from "../shared/SectionHeader";

// ─── Severity icon resolver ───────────────────────────────────────────────────
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
function EventSeverityIcon({
  severity
}) {
  const cls = `w-3.5 h-3.5 flex-shrink-0 ${SEVERITY_COLOR[severity].text}`;
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
      return /*#__PURE__*/_jsx(Info, {
        className: cls
      });
  }
}

/**
 * EventLogScrollableList — filtered, scrollable event log.
 * Reads filtered entries from useForecast (filter driven by context state).
 */
export function EventLogScrollableList() {
  const {
    filteredEventLog
  } = useForecast();
  const {
    selectedAlertSeverity
  } = useDashboardState();
  const unacknowledgedCount = filteredEventLog.filter((e) => !e.acknowledged).length;
  return /*#__PURE__*/_jsxs("section", {
    className: "dashboard-card flex flex-col",
    style: {
      minHeight: "200px"
    },
    children: [/*#__PURE__*/_jsx(SectionHeader, {
      title: "Event Log",
      subtitle: selectedAlertSeverity ? `Filtered: ${selectedAlertSeverity} — ${filteredEventLog.length} entries` : `${filteredEventLog.length} entries`,
      icon: /*#__PURE__*/_jsx(ScrollText, {
        className: "h-4 w-4"
      }),
      trailing: unacknowledgedCount > 0 ? /*#__PURE__*/_jsxs("span", {
        className: "rounded-full border border-red-500/40 bg-red-500/20 px-1.5 py-0.5 text-xs text-red-400",
        children: [unacknowledgedCount, " new"]
      }) : undefined
    }), /*#__PURE__*/_jsx("div", {
      className: "scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent min-h-0 flex-1 space-y-1 overflow-y-auto pr-1",
      role: "log",
      "aria-label": "Flood event log",
      "aria-live": "polite",
      children: filteredEventLog.length === 0 ?
      /*#__PURE__*/
      // Empty state shown when filter returns no entries
      _jsxs("div", {
        className: "flex flex-col items-center justify-center py-8 text-slate-500",
        children: [/*#__PURE__*/_jsx(ScrollText, {
          className: "mb-2 h-8 w-8 opacity-40"
        }), /*#__PURE__*/_jsx("span", {
          className: "text-xs",
          children: "No events match this filter"
        })]
      }) : filteredEventLog.map((entry) => {
        const col = SEVERITY_COLOR[entry.severity];
        return /*#__PURE__*/_jsxs("div", {
          className: `group flex cursor-default items-start gap-2 rounded-lg border px-2.5 py-2 transition-all duration-150 hover:border-slate-600 hover:bg-slate-700/50 ${entry.acknowledged ? "border-slate-700/30 bg-slate-800/30 opacity-50" : `${col.bg} ${col.border}`} `,
          title: entry.description,
          children: [/*#__PURE__*/_jsx("span", {
            className: `mt-0.5 flex-shrink-0 font-mono text-xs ${col.text}`,
            children: entry.timeDisplay
          }), /*#__PURE__*/_jsx("span", {
            className: "mt-0.5",
            children: /*#__PURE__*/_jsx(EventSeverityIcon, {
              severity: entry.severity
            })
          }), /*#__PURE__*/_jsxs("div", {
            className: "min-w-0 flex-1",
            children: [/*#__PURE__*/_jsx("p", {
              className: `truncate text-xs leading-tight font-medium ${entry.acknowledged ? "text-slate-400" : "text-slate-200"}`,
              children: entry.title
            }), entry.location && /*#__PURE__*/_jsx("p", {
              className: "truncate text-xs text-slate-500",
              children: entry.location
            })]
          }), !entry.acknowledged && /*#__PURE__*/_jsx("span", {
            className: `mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full ${col.text.replace("text-", "bg-")}`
          })]
        }, entry.id);
      })
    })]
  });
}