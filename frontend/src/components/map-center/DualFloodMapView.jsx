/**
 * DualFloodMapView.jsx  (map-center/)
 * ─────────────────────────────────────────────────────────────────────────────
 * Two side-by-side interactive Leaflet map panels showing flood coverage.
 * Now using real map tiles and live geolocation.
 *
 * HUD Enhancements:
 *  • Custom pulsing L.divIcon markers (red critical / blue watch)
 *  • Radial-gradient heatmap forecast zone with slow throb animation
 */

import { useState, useEffect } from "react";
import { Map as MapIcon } from "lucide-react";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useForecast } from "../../hooks/useForecast";
import { useDashboardState } from "../../context/DashboardStateContext";
import { MAP_LEGEND_ITEMS } from "../../data/mockForecast";
import { SectionHeader } from "../shared/SectionHeader";

// ─── LEAFLET ICON FIX ────────────────────────────────────────────────────────
// Fix for default Leaflet marker icons not showing up in React
import icon from "leaflet/dist/images/marker-icon.png";
import iconShadow from "leaflet/dist/images/marker-shadow.png";
import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
const DefaultIcon = L.icon({
  iconUrl: icon,
  shadowUrl: iconShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41]
});
L.Marker.prototype.options.icon = DefaultIcon;

// ─── Custom Pulsing Map Marker Icons ─────────────────────────────────────────
// HUD Enhancement 1: Replace default pins with glowing sonar-blip markers.

function createPulsingIcon(color) {
  const coreColor = color === "red" ? "#ef4444" : "#3b82f6";
  const glowColor = color === "red" ? "rgba(239,68,68,0.4)" : "rgba(59,130,246,0.4)";
  const pingClass = color === "red" ? "marker-ping-red" : "marker-ping-blue";
  return L.divIcon({
    className: "",
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -14],
    html: `
      <div style="position:relative;width:24px;height:24px;display:flex;align-items:center;justify-content:center;">
        <span class="${pingClass}" style="
          position:absolute;
          width:24px;height:24px;
          border-radius:50%;
          background:${glowColor};
        "></span>
        <span style="
          position:relative;
          width:10px;height:10px;
          border-radius:50%;
          background:${coreColor};
          box-shadow: 0 0 8px 2px ${glowColor}, 0 0 16px 4px ${glowColor};
        "></span>
      </div>
    `
  });
}
const criticalMarkerIcon = createPulsingIcon("red");
const watchMarkerIcon = createPulsingIcon("blue");

// ─── 📍 LOCATION CONFIGURATION ───────────────────────────────────────────────

// 👇 THIS IS WHERE YOU CHANGE TO A DESIRED LOCATION 👇
// To use the browser's live GPS location, set this to null.
// To force a specific city, provide the [Latitude, Longitude].

// const OVERRIDE_LOCATION: [number, number] | null = [22.5726, 88.3639]; // Currently set to Kolkata
const OVERRIDE_LOCATION = [13.7563, 100.5018]; // Bangkok
// const OVERRIDE_LOCATION: [number, number] | null = null; // Use Live GPS Location

// 👆 ──────────────────────────────────────────────────────────────────────────

// Helper component to auto-center the map when location changes
const RecenterAutomatically = ({
  lat,
  lng
}) => {
  const map = useMap();
  useEffect(() => {
    map.setView([lat, lng]);
  }, [lat, lng, map]);
  return null;
};

// ─── Heatmap Forecast Zone Overlay ───────────────────────────────────────────
// HUD Enhancement 5: Radial-gradient SVG overlay replaces flat red Circle.

function ForecastHeatmapZone({
  center
}) {
  const map = useMap();
  const [style, setStyle] = useState({});
  useEffect(() => {
    const updatePosition = () => {
      const point = map.latLngToContainerPoint(center);
      // Convert 800m radius to pixels at current zoom
      const radiusPoint = map.latLngToContainerPoint([center[0] + 0.0072,
      // ~800m in latitude
      center[1]]);
      const radiusPx = Math.abs(point.y - radiusPoint.y) * 2;
      setStyle({
        width: `${radiusPx}px`,
        height: `${radiusPx}px`,
        left: `${point.x}px`,
        top: `${point.y}px`,
        background: `radial-gradient(circle, rgba(239,68,68,0.6) 0%, rgba(249,115,22,0.35) 35%, rgba(249,115,22,0.12) 65%, transparent 100%)`
      });
    };
    updatePosition();
    map.on("move zoom moveend zoomend", updatePosition);
    return () => {
      map.off("move zoom moveend zoomend", updatePosition);
    };
  }, [map, center]);
  return /*#__PURE__*/_jsx("div", {
    className: "forecast-zone-pulse",
    style: style
  });
}

// ─── Individual interactive map panel ────────────────────────────────────────

function FloodMapPanel({
  title,
  mode,
  isActive
}) {
  const [position, setPosition] = useState(OVERRIDE_LOCATION);
  const [geoError, setGeoError] = useState(() => {
    if (OVERRIDE_LOCATION) return null;
    return typeof navigator !== "undefined" && navigator.geolocation ? null : "Geolocation is not supported";
  });

  // Handle Live Geolocation if no override is provided
  useEffect(() => {
    if (OVERRIDE_LOCATION || geoError) {
      return;
    }
    const watchId = navigator.geolocation.watchPosition((pos) => setPosition([pos.coords.latitude, pos.coords.longitude]), (err) => setGeoError(err.message), {
      enableHighAccuracy: true,
      timeout: 5000,
      maximumAge: 0
    });
    return () => navigator.geolocation.clearWatch(watchId);
  }, [geoError]);
  return /*#__PURE__*/_jsxs("div", {
    className: `relative flex-1 overflow-hidden rounded-xl border transition-all duration-300 ${isActive ? "border-blue-500/50 ring-1 ring-blue-500/20" : "border-slate-700/50"} bg-slate-900`,
    style: {
      minHeight: "220px"
    },
    children: [/*#__PURE__*/_jsxs("div", {
      className: `absolute top-0 right-0 left-0 z-[1000] flex items-center gap-2 px-3 py-1.5 ${isActive ? "bg-blue-600/20" : "bg-slate-800/80"} border-b backdrop-blur-sm ${isActive ? "border-blue-500/30" : "border-slate-700/50"} `,
      children: [/*#__PURE__*/_jsx(MapIcon, {
        className: `h-3.5 w-3.5 ${isActive ? "text-blue-400" : "text-slate-500"}`
      }), /*#__PURE__*/_jsx("span", {
        className: `text-xs font-semibold ${isActive ? "text-blue-300" : "text-slate-400"}`,
        children: title
      }), isActive && /*#__PURE__*/_jsxs("span", {
        className: "ml-auto flex items-center gap-1",
        children: [/*#__PURE__*/_jsxs("span", {
          className: "relative flex h-1.5 w-1.5",
          children: [/*#__PURE__*/_jsx("span", {
            className: "absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75"
          }), /*#__PURE__*/_jsx("span", {
            className: "relative inline-flex h-1.5 w-1.5 rounded-full bg-blue-500"
          })]
        }), /*#__PURE__*/_jsx("span", {
          className: "text-xs text-blue-400",
          children: "Active"
        })]
      })]
    }), /*#__PURE__*/_jsx("div", {
      className: "absolute inset-0 h-full w-full pt-8",
      children: !position ? /*#__PURE__*/_jsx("div", {
        className: "flex h-full items-center justify-center text-sm text-slate-500",
        children: geoError ? `Location Error: ${geoError}` : "Locating..."
      }) : /*#__PURE__*/_jsxs(MapContainer, {
        center: position,
        zoom: 13,
        scrollWheelZoom: true,
        zoomControl: false // Hiding default zoom to keep UI clean
        ,
        style: {
          height: "100%",
          width: "100%",
          backgroundColor: "#0f172a"
        },
        children: [/*#__PURE__*/_jsx(TileLayer, {
          attribution: "\xA9 <a href=\"https://www.openstreetmap.org/copyright\">OSM</a> contributors \xA9 <a href=\"https://carto.com/attributions\">CARTO</a>",
          url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        }), /*#__PURE__*/_jsx(RecenterAutomatically, {
          lat: position[0],
          lng: position[1]
        }), /*#__PURE__*/_jsx(Marker, {
          position: position,
          icon: watchMarkerIcon,
          children: /*#__PURE__*/_jsxs(Popup, {
            className: "font-sans text-xs",
            children: [/*#__PURE__*/_jsx("div", {
              className: "font-semibold text-slate-800",
              children: "Tracking Location"
            }), /*#__PURE__*/_jsx("div", {
              className: "text-slate-600",
              children: "Live monitoring active."
            })]
          })
        }), mode === "forecast" && /*#__PURE__*/_jsxs(_Fragment, {
          children: [/*#__PURE__*/_jsx(ForecastHeatmapZone, {
            center: [position[0] + 0.01, position[1] + 0.01]
          }), /*#__PURE__*/_jsx(Marker, {
            position: [position[0] + 0.01, position[1] + 0.01],
            icon: criticalMarkerIcon,
            children: /*#__PURE__*/_jsx(Popup, {
              children: "Critical Flood Zone Forecast"
            })
          })]
        })]
      })
    })]
  });
}

// ─── Drill-down tab bar config ────────────────────────────────────────────────

const DRILL_LEVELS = [{
  id: "city",
  label: "City"
}, {
  id: "district",
  label: "District"
}, {
  id: "local",
  label: "Local"
}];

// ─── Main component ───────────────────────────────────────────────────────────

export function DualFloodMapView() {
  const {
    mapDrillLevel,
    setMapDrillLevel
  } = useDashboardState();
  const {
    isForecastMode
  } = useForecast();
  return /*#__PURE__*/_jsxs("section", {
    className: "dashboard-card flex flex-shrink-0 flex-col gap-2",
    style: {
      minHeight: "280px"
    },
    children: [/*#__PURE__*/_jsxs("div", {
      className: "flex items-center justify-between",
      children: [/*#__PURE__*/_jsx(SectionHeader, {
        title: "Flood Map View",
        subtitle: "Real-time Tracking Area",
        icon: /*#__PURE__*/_jsx(MapIcon, {
          className: "h-4 w-4"
        }),
        className: "mb-0 flex-1"
      }), /*#__PURE__*/_jsx("div", {
        className: "flex items-center gap-1 rounded-lg bg-slate-700/40 p-0.5",
        children: DRILL_LEVELS.map((dl) => /*#__PURE__*/_jsx("button", {
          onClick: () => setMapDrillLevel(dl.id),
          className: `rounded px-2.5 py-1 text-xs font-medium transition-all duration-150 ${mapDrillLevel === dl.id ? "bg-slate-600 text-slate-100 shadow-sm" : "text-slate-500 hover:text-slate-300"} `,
          children: dl.label
        }, dl.id))
      })]
    }), /*#__PURE__*/_jsx("div", {
      className: "flex flex-1 gap-2",
      style: {
        minHeight: "240px"
      },
      children: !isForecastMode ? /*#__PURE__*/_jsx(FloodMapPanel, {
        title: "Observed Now",
        mode: "now",
        isActive: true,
        drillLevel: mapDrillLevel
      }, "now") : /*#__PURE__*/_jsx(FloodMapPanel, {
        title: "Forecast: Next 3 Hours",
        mode: "forecast",
        isActive: true,
        drillLevel: mapDrillLevel
      }, "forecast")
    }), /*#__PURE__*/_jsxs("div", {
      className: "flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-700/50 pt-2",
      children: [MAP_LEGEND_ITEMS.map((item) => /*#__PURE__*/_jsxs("div", {
        className: "flex items-center gap-1.5",
        children: [/*#__PURE__*/_jsx("span", {
          className: "h-2 w-3 flex-shrink-0 rounded-sm",
          style: {
            backgroundColor: item.color,
            opacity: 0.75
          }
        }), /*#__PURE__*/_jsx("span", {
          className: "text-xs text-slate-500",
          children: item.label
        })]
      }, item.label)), /*#__PURE__*/_jsxs("div", {
        className: "flex items-center gap-1.5",
        children: [/*#__PURE__*/_jsx("span", {
          className: "h-2.5 w-2.5 flex-shrink-0 rounded-full bg-blue-500"
        }), /*#__PURE__*/_jsx("span", {
          className: "text-xs text-slate-500",
          children: "Live GPS Location"
        })]
      })]
    })]
  });
}