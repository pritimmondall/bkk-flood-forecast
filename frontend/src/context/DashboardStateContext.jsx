/**
 * DashboardStateContext.jsx
 * ─────────────────────────────────────────────────────────────────────────────
 * Global React context that manages all interactive UI state for the
 * AI-Based Urban Flood Forecasting System dashboard.
 *
 * All child components read state via the `useDashboardState` hook and
 * dispatch actions via the action functions exposed on the same context value.
 *
 * Architecture decision: Using a flat context object (state + actions merged)
 * instead of useReducer so that individual action handlers are ergonomic to
 * call from deeply nested event handlers without boilerplate.
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { createContext, useContext, useState, useCallback } from "react";
import { DEFAULT_SCENARIO_ID } from "../data/scenarios";

// ─── Context Creation ─────────────────────────────────────────────────────────
import { jsx as _jsx } from "react/jsx-runtime";
const DashboardStateContext = /*#__PURE__*/createContext(null);

// ─── Provider ─────────────────────────────────────────────────────────────────

/**
 * DashboardStateProvider — wrap the application root with this to make global
 * flood dashboard state available to every descendant component.
 */
export function DashboardStateProvider({
  children
}) {
  // ViewMode controls whether the dashboard displays real-time or forecast data
  const [viewMode, setViewModeState] = useState("now");

  // Active top navigation tab — determines which tab content panel is rendered
  const [activeNavTab, setActiveNavTabState] = useState("dashboard");

  // Map drill-down level toggles between city / district / local zoom contexts
  const [mapDrillLevel, setMapDrillLevelState] = useState("city");

  // selectedAlertSeverity filters the Event Log to show only matching entries
  const [selectedAlertSeverity, setSelectedAlertSeverityState] = useState(null);

  // activeScenarioId determines which scenario preset is loaded
  const [activeScenarioId, setActiveScenarioIdState] = useState(DEFAULT_SCENARIO_ID);

  // isSidebarExpanded toggles the left sidebar expanded/collapsed state
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(true);

  // upstreamFlow represents the upstream water flow rate (m³/s)
  const [upstreamFlow, setUpstreamFlowState] = useState(960);

  // activeHotspots tracks the number of active flood hotspots
  const [activeHotspots, setActiveHotspotsState] = useState(0);

  // systemAlerts tracks the number of active system alerts
  const [systemAlerts, setSystemAlertsState] = useState(0);

  // rainfall represents the current rainfall rate (mm/hr)
  const [rainfall, setRainfallState] = useState(58);

  // ─── Stable action callbacks ────────────────────────────────────────────────

  /** Switch between "Now" / "Forecast" view modes — updates maps and all metrics */
  const setViewMode = useCallback((mode) => {
    setViewModeState(mode);
  }, []);

  /** Navigate to a top-level tab (Dashboard / Alerts / Resources / Reports) */
  const setActiveNavTab = useCallback((tab) => {
    setActiveNavTabState(tab);
  }, []);

  /** Drill down or zoom out on the map view */
  const setMapDrillLevel = useCallback((level) => {
    setMapDrillLevelState(level);
  }, []);

  /**
   * Filter Event Log by severity — clicking the same badge again clears the filter.
   * Clicking a badge filters/highlights related Event Log entries.
   */
  const setSelectedAlertSeverity = useCallback((severity) => {
    setSelectedAlertSeverityState((prev) => prev === severity ? null : severity);
  }, []);

  /** Load a pre-defined flood scenario preset */
  const setActiveScenarioId = useCallback((id) => {
    setActiveScenarioIdState(id);
  }, []);

  /** Toggle the expandable left sidebar */
  const toggleSidebar = useCallback(() => {
    setIsSidebarExpanded((prev) => !prev);
  }, []);

  /** Set the upstream flow rate (m³/s) */
  const setUpstreamFlow = useCallback((value) => {
    setUpstreamFlowState(value);
  }, []);

  /** Set the number of active flood hotspots */
  const setActiveHotspots = useCallback((value) => {
    setActiveHotspotsState(value);
  }, []);

  /** Set the number of active system alerts */
  const setSystemAlerts = useCallback((value) => {
    setSystemAlertsState(value);
  }, []);

  /** Set the rainfall rate (mm/hr) */
  const setRainfall = useCallback((value) => {
    setRainfallState(value);
  }, []);

  // ─── Composed context value ─────────────────────────────────────────────────

  const contextValue = {
    // State
    viewMode,
    activeNavTab,
    mapDrillLevel,
    selectedAlertSeverity,
    activeScenarioId,
    isSidebarExpanded,
    upstreamFlow,
    activeHotspots,
    systemAlerts,
    rainfall,
    // Actions
    setViewMode,
    setActiveNavTab,
    setMapDrillLevel,
    setSelectedAlertSeverity,
    setActiveScenarioId,
    toggleSidebar,
    setUpstreamFlow,
    setActiveHotspots,
    setSystemAlerts,
    setRainfall
  };
  return /*#__PURE__*/_jsx(DashboardStateContext.Provider, {
    value: contextValue,
    children: children
  });
}

// ─── Consumer Hook ────────────────────────────────────────────────────────────

/**
 * useDashboardState — retrieve global dashboard state and action dispatchers.
 * Must be called inside a DashboardStateProvider tree.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useDashboardState() {
  const ctx = useContext(DashboardStateContext);
  if (!ctx) {
    throw new Error("useDashboardState must be used inside <DashboardStateProvider>");
  }
  return ctx;
}