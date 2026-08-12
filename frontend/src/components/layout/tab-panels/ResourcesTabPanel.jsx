/**
 * ResourcesTabPanel.jsx  (layout/tab-panels/)
 * Full-width panel shown when the user navigates to the "Resources" tab.
 * Displays Bangkok Metropolitan Administration (BMA) emergency resource status.
 */

import { Package, Truck, Users, Zap, CheckCircle, AlertTriangle } from "lucide-react";
import { SectionHeader } from "../../shared/SectionHeader";
import { HotspotLocationCardList } from "../../sidebar-right/HotspotLocationCardList";

// Mock resources data — TODO: Replace with API call — GET /api/v1/resources
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const RESOURCE_GROUPS = [{
  group: "Pump Stations",
  icon: Zap,
  items: [{
    name: "Pump Station P-01 (Chatuchak)",
    status: "operational",
    capacity: "85 m³/s"
  }, {
    name: "Pump Station P-06 (Bang Kapi)",
    status: "operational",
    capacity: "60 m³/s"
  }, {
    name: "Pump Station P-12 (Lat Phrao)",
    status: "offline",
    capacity: "0 m³/s"
  }, {
    name: "Pump Station P-18 (Suan Luang)",
    status: "operational",
    capacity: "145 m³/s"
  }, {
    name: "Pump Station P-22 (Min Buri)",
    status: "degraded",
    capacity: "40 m³/s"
  }]
}, {
  group: "Emergency Vehicles",
  icon: Truck,
  items: [{
    name: "Fire & Rescue Fleet — Central",
    status: "deployed",
    capacity: "24 units"
  }, {
    name: "Flood Response Boats — East Zone",
    status: "operational",
    capacity: "12 boats"
  }, {
    name: "Medical Evacuation Units",
    status: "standby",
    capacity: "8 units"
  }, {
    name: "Heavy Equipment (Backhoes)",
    status: "operational",
    capacity: "5 units"
  }]
}, {
  group: "Personnel",
  icon: Users,
  items: [{
    name: "BMA Drainage Operations Team",
    status: "deployed",
    capacity: "340 staff"
  }, {
    name: "Emergency Response Unit",
    status: "deployed",
    capacity: "120 staff"
  }, {
    name: "Community Volunteers Network",
    status: "operational",
    capacity: "600+ active"
  }]
}, {
  group: "Supplies",
  icon: Package,
  items: [{
    name: "Sandbag Inventory — Depot A",
    status: "operational",
    capacity: "18,000 bags"
  }, {
    name: "Sandbag Inventory — Depot B",
    status: "degraded",
    capacity: "4,200 bags"
  }, {
    name: "Emergency Water Supply (Litres)",
    status: "operational",
    capacity: "500,000 L"
  }, {
    name: "Temporary Shelter Capacity",
    status: "operational",
    capacity: "3,200 people"
  }]
}];
function statusStyle(status) {
  switch (status) {
    case "operational":
      return {
        text: "text-green-400",
        icon: /*#__PURE__*/_jsx(CheckCircle, {
          className: "h-3.5 w-3.5"
        })
      };
    case "deployed":
      return {
        text: "text-blue-400",
        icon: /*#__PURE__*/_jsx(CheckCircle, {
          className: "h-3.5 w-3.5"
        })
      };
    case "standby":
      return {
        text: "text-yellow-400",
        icon: /*#__PURE__*/_jsx(CheckCircle, {
          className: "h-3.5 w-3.5"
        })
      };
    case "degraded":
      return {
        text: "text-orange-400",
        icon: /*#__PURE__*/_jsx(AlertTriangle, {
          className: "h-3.5 w-3.5"
        })
      };
    case "offline":
      return {
        text: "text-red-400",
        icon: /*#__PURE__*/_jsx(AlertTriangle, {
          className: "h-3.5 w-3.5"
        })
      };
    default:
      return {
        text: "text-slate-400",
        icon: null
      };
  }
}
export function ResourcesTabPanel() {
  return /*#__PURE__*/_jsx("div", {
    className: "flex-1 overflow-y-auto p-4",
    children: /*#__PURE__*/_jsxs("div", {
      className: "mx-auto flex max-w-5xl flex-col gap-4",
      children: [/*#__PURE__*/_jsx(HotspotLocationCardList, {}), /*#__PURE__*/_jsx("div", {
        className: "grid grid-cols-2 gap-4",
        children: RESOURCE_GROUPS.map(({
          group,
          icon: Icon,
          items
        }) => /*#__PURE__*/_jsxs("div", {
          className: "dashboard-card",
          children: [/*#__PURE__*/_jsx(SectionHeader, {
            title: group,
            icon: /*#__PURE__*/_jsx(Icon, {
              className: "h-4 w-4"
            })
          }), /*#__PURE__*/_jsx("div", {
            className: "space-y-2",
            children: items.map((item) => {
              const {
                text,
                icon
              } = statusStyle(item.status);
              return /*#__PURE__*/_jsxs("div", {
                className: "flex items-center justify-between border-b border-slate-700/50 py-1.5 last:border-0",
                children: [/*#__PURE__*/_jsx("span", {
                  className: "text-xs text-slate-300",
                  children: item.name
                }), /*#__PURE__*/_jsxs("div", {
                  className: "flex items-center gap-2",
                  children: [/*#__PURE__*/_jsx("span", {
                    className: "text-xs text-slate-500",
                    children: item.capacity
                  }), /*#__PURE__*/_jsxs("span", {
                    className: `flex items-center gap-1 text-xs font-medium capitalize ${text}`,
                    children: [icon, item.status]
                  })]
                })]
              }, item.name);
            })
          })]
        }, group))
      })]
    })
  });
}