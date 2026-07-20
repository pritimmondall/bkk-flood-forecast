/**
 * ReportsTabPanel.jsx  (layout/tab-panels/)
 * Full-width panel shown when the user navigates to the "Reports" tab.
 * Displays a historical incident report archive.
 */

import { FileText, Download, Calendar } from "lucide-react";
import { SectionHeader } from "../../shared/SectionHeader";

// Mock report records — TODO: Replace with API call — GET /api/v1/reports
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const HISTORICAL_REPORTS = [{
  id: "r-2026-014",
  date: "2026-03-04",
  title: "Major Flood Event — Pre-event Briefing",
  type: "Briefing",
  severity: "critical",
  pages: 8
}, {
  id: "r-2026-013",
  date: "2026-02-28",
  title: "February 2026 Monthly Drainage Operations Report",
  type: "Monthly",
  severity: "info",
  pages: 22
}, {
  id: "r-2026-012",
  date: "2026-02-22",
  title: "Sukhumvit Flooding Incident — After-Action Review",
  type: "Incident",
  severity: "warning",
  pages: 15
}, {
  id: "r-2026-011",
  date: "2026-02-15",
  title: "Canal Level Sensor Calibration Report",
  type: "Technical",
  severity: "normal",
  pages: 6
}, {
  id: "r-2026-010",
  date: "2026-02-08",
  title: "Upstream Flow Anomaly — Root Cause Analysis",
  type: "Incident",
  severity: "warning",
  pages: 11
}, {
  id: "r-2026-009",
  date: "2026-01-31",
  title: "January 2026 Monthly Drainage Operations Report",
  type: "Monthly",
  severity: "info",
  pages: 20
}, {
  id: "r-2026-008",
  date: "2026-01-18",
  title: "AI Model Performance Evaluation Q4 2025",
  type: "Technical",
  severity: "info",
  pages: 34
}, {
  id: "r-2026-007",
  date: "2026-01-10",
  title: "New Year Flooding Incident — After-Action Review",
  type: "Incident",
  severity: "critical",
  pages: 18
}];
function severityBadgeClass(severity) {
  switch (severity) {
    case "critical":
      return "bg-red-500/20 text-red-400 border-red-500/40";
    case "warning":
      return "bg-orange-500/20 text-orange-400 border-orange-500/40";
    case "normal":
      return "bg-green-500/20 text-green-400 border-green-500/40";
    default:
      return "bg-blue-500/20 text-blue-400 border-blue-500/40";
  }
}
export function ReportsTabPanel() {
  return /*#__PURE__*/_jsx("div", {
    className: "flex-1 overflow-y-auto p-4",
    children: /*#__PURE__*/_jsxs("div", {
      className: "dashboard-card mx-auto max-w-4xl",
      children: [/*#__PURE__*/_jsx(SectionHeader, {
        title: "Incident & Operations Reports",
        subtitle: "Historical archive \u2014 click to view, download button to export PDF",
        icon: /*#__PURE__*/_jsx(FileText, {
          className: "h-4 w-4"
        })
      }), /*#__PURE__*/_jsx("div", {
        className: "mt-2 space-y-2",
        children: HISTORICAL_REPORTS.map((report) => /*#__PURE__*/_jsxs("div", {
          className: "group flex cursor-pointer items-center gap-4 rounded-lg border border-slate-700/50 bg-slate-700/30 p-3 transition-all duration-150 hover:border-slate-600 hover:bg-slate-700/60",
          children: [/*#__PURE__*/_jsxs("div", {
            className: "flex items-center gap-1.5 text-xs whitespace-nowrap text-slate-500",
            children: [/*#__PURE__*/_jsx(Calendar, {
              className: "h-3.5 w-3.5"
            }), report.date]
          }), /*#__PURE__*/_jsxs("div", {
            className: "min-w-0 flex-1",
            children: [/*#__PURE__*/_jsx("span", {
              className: "block truncate text-sm text-slate-200 group-hover:text-slate-100",
              children: report.title
            }), /*#__PURE__*/_jsxs("span", {
              className: "text-xs text-slate-500",
              children: [report.pages, " pages"]
            })]
          }), /*#__PURE__*/_jsx("span", {
            className: "hidden text-xs whitespace-nowrap text-slate-500 sm:block",
            children: report.type
          }), /*#__PURE__*/_jsx("span", {
            className: `rounded border px-2 py-0.5 text-xs whitespace-nowrap capitalize ${severityBadgeClass(report.severity)}`,
            children: report.severity
          }), /*#__PURE__*/_jsx("button", {
            onClick: (e) => {
              e.stopPropagation();
              alert(`Downloading ${report.id}.pdf`);
            },
            className: "flex h-7 w-7 items-center justify-center rounded text-slate-500 transition-colors duration-150 hover:bg-blue-500/10 hover:text-blue-400",
            title: "Download PDF",
            children: /*#__PURE__*/_jsx(Download, {
              className: "h-3.5 w-3.5"
            })
          })]
        }, report.id))
      })]
    })
  });
}