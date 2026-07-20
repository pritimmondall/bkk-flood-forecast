/**
 * WaterLevelLineChart.jsx  (sidebar-right/)
 * ─────────────────────────────────────────────────────────────────────────────
 * Multi-series Recharts LineChart plotting canal water levels and upstream
 * river flow over a 6-hour observed window plus a 3-hour forecast extension.
 *
 * HUD Enhancement 3: Gradient-filled areas beneath each line series with
 * glowing drop-shadow strokes for a premium instrument readout feel.
 *
 * HUD Enhancement 4: Monospace font on tooltip data values.
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Legend } from "recharts";
import { Activity } from "lucide-react";
import { useForecast } from "../../hooks/useForecast";
import { DARK_TOOLTIP_STYLE, DARK_CURSOR_STYLE, AXIS_TICK_COLOR, AXIS_LINE_COLOR, CHART_COLORS, COMPACT_MARGIN, GRID_STROKE } from "../../lib/chart";
import { SectionHeader } from "../shared/SectionHeader";

// ─── Custom dark tooltip ──────────────────────────────────────────────────────
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
function WaterLevelTooltip({
  active,
  label,
  payload
}) {
  if (!active || !payload?.length) return null;
  // Filter out the gradient Area entries (they duplicate the Line entries)
  const filtered = payload.filter((item) => !item.name.startsWith("_"));
  return /*#__PURE__*/_jsxs("div", {
    style: DARK_TOOLTIP_STYLE,
    className: "rounded-lg px-3 py-2 text-xs",
    children: [/*#__PURE__*/_jsx("p", {
      className: "mb-1.5 font-medium text-slate-400",
      children: label
    }), filtered.map((item) => /*#__PURE__*/_jsxs("div", {
      className: "flex items-center justify-between gap-4",
      children: [/*#__PURE__*/_jsx("span", {
        style: {
          color: item.color
        },
        children: item.name
      }), /*#__PURE__*/_jsx("span", {
        className: "font-mono text-slate-100",
        children: item.value
      })]
    }, item.name))]
  });
}

// ─── Component ────────────────────────────────────────────────────────────────

/**
 * WaterLevelLineChart — multi-series canal + river flow trend chart.
 * Renders at the bottom of the centre panel.
 */
export function WaterLevelLineChart() {
  const {
    waterLevelData
  } = useForecast();
  return /*#__PURE__*/_jsxs("section", {
    className: "dashboard-card flex flex-shrink-0 flex-col",
    style: {
      minHeight: "180px"
    },
    children: [/*#__PURE__*/_jsx(SectionHeader, {
      title: "Water Levels",
      subtitle: "Observed 6hr + Forecast 3hr",
      icon: /*#__PURE__*/_jsx(Activity, {
        className: "h-4 w-4"
      }),
      trailing: /*#__PURE__*/_jsxs("div", {
        className: "flex items-center gap-3 text-xs",
        children: [/*#__PURE__*/_jsxs("span", {
          className: "flex items-center gap-1",
          children: [/*#__PURE__*/_jsx("span", {
            className: "inline-block h-0.5 w-3 rounded-full bg-blue-500"
          }), /*#__PURE__*/_jsx("span", {
            className: "text-xs font-medium tracking-wider uppercase text-slate-500",
            children: "Flow"
          })]
        }), /*#__PURE__*/_jsxs("span", {
          className: "flex items-center gap-1",
          children: [/*#__PURE__*/_jsx("span", {
            className: "inline-block h-0.5 w-3 rounded-full bg-purple-500"
          }), /*#__PURE__*/_jsx("span", {
            className: "text-xs font-medium tracking-wider uppercase text-slate-500",
            children: "Sukhumvit"
          })]
        }), /*#__PURE__*/_jsxs("span", {
          className: "flex items-center gap-1",
          children: [/*#__PURE__*/_jsx("span", {
            className: "inline-block h-0.5 w-3 rounded-full bg-cyan-500"
          }), /*#__PURE__*/_jsx("span", {
            className: "text-xs font-medium tracking-wider uppercase text-slate-500",
            children: "Bangkhen"
          })]
        })]
      })
    }), /*#__PURE__*/_jsx("div", {
      className: "flex-1",
      style: {
        minHeight: "130px"
      },
      children: /*#__PURE__*/_jsx(ResponsiveContainer, {
        width: "100%",
        height: "100%",
        children: /*#__PURE__*/_jsxs(ComposedChart, {
          data: waterLevelData,
          margin: COMPACT_MARGIN,
          children: [/*#__PURE__*/_jsxs("defs", {
            children: [/*#__PURE__*/_jsxs("linearGradient", {
              id: "gradientFlow",
              x1: "0",
              y1: "0",
              x2: "0",
              y2: "1",
              children: [/*#__PURE__*/_jsx("stop", {
                offset: "5%",
                stopColor: CHART_COLORS.upstreamFlow,
                stopOpacity: 0.3
              }), /*#__PURE__*/_jsx("stop", {
                offset: "95%",
                stopColor: CHART_COLORS.upstreamFlow,
                stopOpacity: 0.02
              })]
            }), /*#__PURE__*/_jsxs("linearGradient", {
              id: "gradientSukhumvit",
              x1: "0",
              y1: "0",
              x2: "0",
              y2: "1",
              children: [/*#__PURE__*/_jsx("stop", {
                offset: "5%",
                stopColor: CHART_COLORS.canalSukhumvit,
                stopOpacity: 0.3
              }), /*#__PURE__*/_jsx("stop", {
                offset: "95%",
                stopColor: CHART_COLORS.canalSukhumvit,
                stopOpacity: 0.02
              })]
            }), /*#__PURE__*/_jsxs("linearGradient", {
              id: "gradientBangkhen",
              x1: "0",
              y1: "0",
              x2: "0",
              y2: "1",
              children: [/*#__PURE__*/_jsx("stop", {
                offset: "5%",
                stopColor: CHART_COLORS.canalBangkhen,
                stopOpacity: 0.3
              }), /*#__PURE__*/_jsx("stop", {
                offset: "95%",
                stopColor: CHART_COLORS.canalBangkhen,
                stopOpacity: 0.02
              })]
            })]
          }), /*#__PURE__*/_jsx(CartesianGrid, {
            stroke: GRID_STROKE,
            strokeDasharray: "3 3",
            vertical: false
          }), /*#__PURE__*/_jsx(XAxis, {
            dataKey: "time",
            tick: {
              fill: AXIS_TICK_COLOR,
              fontSize: 10
            },
            axisLine: {
              stroke: AXIS_LINE_COLOR
            },
            tickLine: false,
            interval: 1
          }), /*#__PURE__*/_jsx(YAxis, {
            yAxisId: "canal",
            tick: {
              fill: AXIS_TICK_COLOR,
              fontSize: 10
            },
            axisLine: {
              stroke: AXIS_LINE_COLOR
            },
            tickLine: false,
            domain: [0, 120],
            tickFormatter: (v) => `${v}%`,
            width: 32
          }), /*#__PURE__*/_jsx(YAxis, {
            yAxisId: "flow",
            orientation: "right",
            tick: {
              fill: AXIS_TICK_COLOR,
              fontSize: 10
            },
            axisLine: {
              stroke: AXIS_LINE_COLOR
            },
            tickLine: false,
            domain: [600, 1200],
            tickFormatter: (v) => `${v}`,
            width: 38
          }), /*#__PURE__*/_jsx(Tooltip, {
            content: /*#__PURE__*/_jsx(WaterLevelTooltip, {}),
            cursor: DARK_CURSOR_STYLE
          }), /*#__PURE__*/_jsx(ReferenceLine, {
            yAxisId: "canal",
            y: 90,
            stroke: CHART_COLORS.criticalLine,
            strokeDasharray: "4 2",
            strokeWidth: 1.5,
            label: {
              value: "Critical",
              position: "insideTopRight",
              fill: "#ef4444",
              fontSize: 9
            }
          }), /*#__PURE__*/_jsx(Area, {
            yAxisId: "canal",
            type: "monotone",
            dataKey: "canalSukhumvit",
            name: "_sukhumvitArea",
            stroke: "none",
            fill: "url(#gradientSukhumvit)",
            fillOpacity: 1
          }), /*#__PURE__*/_jsx(Area, {
            yAxisId: "canal",
            type: "monotone",
            dataKey: "canalBangkhen",
            name: "_bangkhenArea",
            stroke: "none",
            fill: "url(#gradientBangkhen)",
            fillOpacity: 1
          }), /*#__PURE__*/_jsx(Area, {
            yAxisId: "flow",
            type: "monotone",
            dataKey: "upstreamFlow",
            name: "_flowArea",
            stroke: "none",
            fill: "url(#gradientFlow)",
            fillOpacity: 1
          }), /*#__PURE__*/_jsx(Line, {
            yAxisId: "canal",
            type: "monotone",
            dataKey: "canalSukhumvit",
            name: "Sukhumvit Canal %",
            stroke: CHART_COLORS.canalSukhumvit,
            strokeWidth: 2,
            dot: false,
            activeDot: {
              r: 4,
              strokeWidth: 0
            },
            style: {
              filter: "drop-shadow(0px 3px 6px rgba(168,85,247,0.5))"
            }
          }), /*#__PURE__*/_jsx(Line, {
            yAxisId: "canal",
            type: "monotone",
            dataKey: "canalBangkhen",
            name: "Bangkhen Canal %",
            stroke: CHART_COLORS.canalBangkhen,
            strokeWidth: 2,
            dot: false,
            activeDot: {
              r: 4,
              strokeWidth: 0
            },
            style: {
              filter: "drop-shadow(0px 3px 6px rgba(6,182,212,0.5))"
            }
          }), /*#__PURE__*/_jsx(Line, {
            yAxisId: "flow",
            type: "monotone",
            dataKey: "upstreamFlow",
            name: "Upstream Flow m\xB3/s",
            stroke: CHART_COLORS.upstreamFlow,
            strokeWidth: 2,
            strokeDasharray: "5 2",
            dot: false,
            activeDot: {
              r: 4,
              strokeWidth: 0
            },
            style: {
              filter: "drop-shadow(0px 3px 6px rgba(59,130,246,0.5))"
            }
          }), /*#__PURE__*/_jsx(Legend, {
            wrapperStyle: {
              fontSize: "10px",
              color: AXIS_TICK_COLOR,
              paddingTop: "4px"
            },
            iconSize: 8,
            content: () => /*#__PURE__*/_jsx("div", {
              style: {
                display: "flex",
                gap: "12px",
                justifyContent: "center",
                fontSize: "10px",
                paddingTop: "4px"
              },
              children: [{
                label: "Sukhumvit Canal %",
                color: CHART_COLORS.canalSukhumvit
              }, {
                label: "Bangkhen Canal %",
                color: CHART_COLORS.canalBangkhen
              }, {
                label: "Upstream Flow m³/s",
                color: CHART_COLORS.upstreamFlow
              }].map((item) => /*#__PURE__*/_jsxs("span", {
                style: {
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                  color: AXIS_TICK_COLOR
                },
                children: [/*#__PURE__*/_jsx("span", {
                  style: {
                    display: "inline-block",
                    width: 8,
                    height: 2,
                    borderRadius: 1,
                    backgroundColor: item.color
                  }
                }), item.label]
              }, item.label))
            })
          })]
        })
      })
    })]
  });
}