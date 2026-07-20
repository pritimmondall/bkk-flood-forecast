/**
 * SectionHeader.jsx
 * ─────────────────────────────────────────────────────────────────────────────
 * Reusable section-header primitive rendered at the top of every dashboard
 * card panel.  Accepts an icon, title, optional badge/action slot on the right,
 * and an optional expandable toggle for collapsible panels.
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { ChevronDown, ChevronRight } from "lucide-react";
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * SectionHeader — visual header for every dashboard card panel.
 *
 * Usage:
 *   <SectionHeader
 *     title="Situation Summary"
 *     icon={<BarChart2 className="w-4 h-4" />}
 *     trailing={<span className="text-xs text-slate-400">Live</span>}
 *   />
 */
export function SectionHeader({
  title,
  subtitle,
  icon,
  trailing,
  isExpanded,
  onToggleExpand,
  className = ""
}) {
  const hasToggle = isExpanded !== undefined && onToggleExpand !== undefined;
  return /*#__PURE__*/_jsxs("div", {
    className: `mb-3 flex items-center justify-between ${className}`,
    children: [/*#__PURE__*/_jsxs("div", {
      className: "flex min-w-0 items-center gap-2",
      children: [icon && /*#__PURE__*/_jsx("span", {
        className: "flex-shrink-0 text-slate-400",
        children: icon
      }), /*#__PURE__*/_jsxs("div", {
        className: "min-w-0",
        children: [/*#__PURE__*/_jsx("h3", {
          className: "truncate text-sm leading-tight font-semibold text-slate-100",
          children: title
        }), subtitle && /*#__PURE__*/_jsx("p", {
          className: "mt-0.5 truncate text-xs leading-tight text-slate-500",
          children: subtitle
        })]
      })]
    }), /*#__PURE__*/_jsxs("div", {
      className: "flex flex-shrink-0 items-center gap-2",
      children: [trailing, hasToggle && /*#__PURE__*/_jsxs("button", {
        onClick: onToggleExpand,
        title: isExpanded ? "Collapse section" : "Expand section",
        className: "flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-slate-500 transition-colors duration-150 hover:bg-slate-700 hover:text-slate-300",
        "aria-expanded": isExpanded,
        children: [/*#__PURE__*/_jsx("span", {
          className: `inline-block transition-transform duration-200 ${isExpanded ? "rotate-90" : "rotate-0"} `,
          children: isExpanded ? /*#__PURE__*/_jsx(ChevronDown, {
            className: "h-3.5 w-3.5"
          }) : /*#__PURE__*/_jsx(ChevronRight, {
            className: "h-3.5 w-3.5"
          })
        }), /*#__PURE__*/_jsx("span", {
          className: "xs:inline hidden",
          children: isExpanded ? "Collapse" : "Expand"
        })]
      })]
    })]
  });
}