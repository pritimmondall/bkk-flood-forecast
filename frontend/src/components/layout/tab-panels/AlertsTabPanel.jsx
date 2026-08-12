/**
 * AlertsTabPanel.jsx  (layout/tab-panels/)
 * Full-width panel shown when the user navigates to the "Alerts" tab.
 * Displays an organised table of all alert log entries with filtering.
 */

import { useState } from "react";
import { Bell, Filter } from "lucide-react";
import { EVENT_LOG_ENTRIES, ALERT_BADGES } from "../../../data/mockForecast";
import { SEVERITY_COLOR, SEVERITY_LABEL } from "../../../types/dashboard.types";
import { SectionHeader } from "../../shared/SectionHeader";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
export function AlertsTabPanel() {
  const [filter, setFilter] = useState(null);
  const filtered = filter ? EVENT_LOG_ENTRIES.filter((e) => e.severity === filter) : EVENT_LOG_ENTRIES;
  return /*#__PURE__*/_jsx("div", {
    className: "flex-1 overflow-y-auto p-4",
    children: /*#__PURE__*/_jsxs("div", {
      className: "dashboard-card mx-auto max-w-5xl",
      children: [/*#__PURE__*/_jsx(SectionHeader, {
        title: "All Active Alerts",
        subtitle: `${EVENT_LOG_ENTRIES.length} total events — ${EVENT_LOG_ENTRIES.filter((e) => !e.acknowledged).length} unacknowledged`,
        icon: /*#__PURE__*/_jsx(Bell, {
          className: "h-4 w-4"
        }),
        trailing: /*#__PURE__*/_jsxs("div", {
          className: "flex items-center gap-2",
          children: [/*#__PURE__*/_jsx(Filter, {
            className: "h-3.5 w-3.5 text-slate-500"
          }), /*#__PURE__*/_jsx("button", {
            onClick: () => setFilter(null),
            className: `rounded px-2 py-0.5 text-xs transition-colors ${!filter ? "bg-slate-600 text-slate-100" : "text-slate-400 hover:text-slate-200"}`,
            children: "All"
          }), ALERT_BADGES.map((b) => /*#__PURE__*/_jsxs("button", {
            onClick: () => setFilter((f) => f === b.severity ? null : b.severity),
            className: `rounded border px-2 py-0.5 text-xs transition-colors ${filter === b.severity ? `${SEVERITY_COLOR[b.severity].bg} ${SEVERITY_COLOR[b.severity].text} ${SEVERITY_COLOR[b.severity].border}` : "border-slate-700 text-slate-400 hover:text-slate-200"}`,
            children: [b.label, " (", b.count, ")"]
          }, b.id))]
        })
      }), /*#__PURE__*/_jsx("div", {
        className: "mt-2 space-y-1.5",
        children: filtered.map((entry) => {
          const col = SEVERITY_COLOR[entry.severity];
          return /*#__PURE__*/_jsxs("div", {
            className: `flex items-start gap-3 rounded-lg border p-3 ${col.bg} ${col.border} ${entry.acknowledged ? "opacity-50" : ""} transition-opacity hover:opacity-100`,
            children: [/*#__PURE__*/_jsx("span", {
              className: `mt-0.5 font-mono text-xs ${col.text}`,
              children: entry.timeDisplay
            }), /*#__PURE__*/_jsxs("div", {
              className: "min-w-0 flex-1",
              children: [/*#__PURE__*/_jsx("div", {
                className: `text-sm font-semibold ${col.text}`,
                children: entry.title
              }), entry.description && /*#__PURE__*/_jsx("div", {
                className: "mt-0.5 text-xs text-slate-400",
                children: entry.description
              })]
            }), entry.location && /*#__PURE__*/_jsx("span", {
              className: "text-xs whitespace-nowrap text-slate-500",
              children: entry.location
            }), /*#__PURE__*/_jsx("span", {
              className: `rounded border px-1.5 py-0.5 text-xs ${col.bg} ${col.text} ${col.border} whitespace-nowrap`,
              children: SEVERITY_LABEL[entry.severity]
            })]
          }, entry.id);
        })
      })]
    })
  });
}