/**
 * LandingPage.jsx  (landing/)
 * ─────────────────────────────────────────────────────────────────────────────
 * Premium Bangkok-themed landing page for the AI-Based Urban Flood Forecasting
 * System. Features a cinematic hero section with nighttime cityscape backdrop,
 * holographic system overview panel, and two glow-effect login buttons:
 *
 *  • Citizen Login — gold/brass metallic, warm glow
 *  • Gov Login     — cool blue/teal, neon glow
 *
 * Clicking either button triggers the onLogin callback which transitions
 * the user into the main flood command dashboard.
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { useState } from "react";
import { Shield, Droplets, Cpu, Radio, Map, BarChart3, ChevronDown, Users, Building2, Waves, Zap, Globe, ArrowRight } from "lucide-react";
import { LoginButton } from "./LoginButton";

// ─── Types ────────────────────────────────────────────────────────────────────

// ─── Feature card data ────────────────────────────────────────────────────────
import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const FEATURES = [{
  id: "ai",
  icon: /*#__PURE__*/_jsx(Cpu, {
    className: "h-6 w-6"
  }),
  title: "AI Prediction",
  description: "Deep learning models analyze rainfall, soil moisture, and canal capacity to predict floods 3 hours ahead."
}, {
  id: "realtime",
  icon: /*#__PURE__*/_jsx(Radio, {
    className: "h-6 w-6"
  }),
  title: "Real-Time Monitoring",
  description: "Live data from 200+ IoT sensors, weather stations, and floodbot drones across Bangkok's canal network."
}, {
  id: "mapping",
  icon: /*#__PURE__*/_jsx(Map, {
    className: "h-6 w-6"
  }),
  title: "Flood Zone Mapping",
  description: "Interactive GIS maps showing flood depth, critical infrastructure, and evacuation routes in real time."
}, {
  id: "analytics",
  icon: /*#__PURE__*/_jsx(BarChart3, {
    className: "h-6 w-6"
  }),
  title: "Risk Analytics",
  description: "Probability escalation timelines and confidence-band forecasts for operational flood response planning."
}];

// ─── Navigation items ─────────────────────────────────────────────────────────

const NAV_LINKS = ["Home", "About us", "Resource", "Pricing", "Contact"];

// ─── Component ────────────────────────────────────────────────────────────────

export function LandingPage({
  onLogin
}) {
  const [hoveredFeature, setHoveredFeature] = useState(null);
  return /*#__PURE__*/_jsxs("div", {
    className: "landing-page",
    children: [/*#__PURE__*/_jsxs("section", {
      className: "landing-hero",
      children: [/*#__PURE__*/_jsx("div", {
        className: "landing-hero-bg"
      }), /*#__PURE__*/_jsx("div", {
        className: "landing-hero-overlay"
      }), /*#__PURE__*/_jsx("nav", {
        className: "landing-nav",
        children: /*#__PURE__*/_jsxs("div", {
          className: "landing-nav-inner",
          children: [/*#__PURE__*/_jsxs("div", {
            className: "flex items-center gap-3",
            children: [/*#__PURE__*/_jsx("div", {
              className: "flex h-9 w-9 items-center justify-center rounded-lg border border-cyan-500/30 bg-cyan-600/20",
              children: /*#__PURE__*/_jsx(Waves, {
                className: "h-5 w-5 text-cyan-400"
              })
            }), /*#__PURE__*/_jsx("span", {
              className: "text-lg font-bold tracking-tight text-white",
              children: "Bangkok"
            }), /*#__PURE__*/_jsxs("button", {
              className: "ml-2 flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-slate-400 transition-colors hover:text-white",
              children: ["Features ", /*#__PURE__*/_jsx(ChevronDown, {
                className: "h-3.5 w-3.5"
              })]
            })]
          }), /*#__PURE__*/_jsx("div", {
            className: "hidden items-center gap-6 md:flex",
            children: NAV_LINKS.map((link) => /*#__PURE__*/_jsx("a", {
              href: "#",
              className: "text-sm text-slate-400 transition-colors hover:text-white",
              children: link
            }, link))
          })]
        })
      }), /*#__PURE__*/_jsxs("div", {
        className: "landing-hero-content",
        children: [/*#__PURE__*/_jsx("div", {
          className: "mb-6 flex justify-center",
          children: /*#__PURE__*/_jsxs("div", {
            className: "flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-4 py-1.5 backdrop-blur-sm",
            children: [/*#__PURE__*/_jsxs("span", {
              className: "relative flex h-2 w-2",
              children: [/*#__PURE__*/_jsx("span", {
                className: "absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75"
              }), /*#__PURE__*/_jsx("span", {
                className: "relative inline-flex h-2 w-2 rounded-full bg-cyan-500"
              })]
            }), /*#__PURE__*/_jsx("span", {
              className: "text-xs font-medium tracking-wider uppercase text-cyan-400",
              children: "System Online \u2014 v3.1"
            })]
          })
        }), /*#__PURE__*/_jsxs("h1", {
          className: "landing-title",
          children: [/*#__PURE__*/_jsx("span", {
            className: "block text-slate-300",
            children: "AI-Powered"
          }), /*#__PURE__*/_jsx("span", {
            className: "landing-title-gradient",
            children: "Urban Flood Forecasting"
          })]
        }), /*#__PURE__*/_jsx("p", {
          className: "mx-auto mt-4 max-w-2xl text-center text-base leading-relaxed text-slate-400 md:text-lg",
          children: "Protecting Bangkok's 10 million residents with real-time hydrological monitoring, predictive AI models, and automated early warning systems."
        }), /*#__PURE__*/_jsx("div", {
          className: "landing-holo-panel",
          children: /*#__PURE__*/_jsxs("div", {
            className: "landing-holo-inner",
            children: [/*#__PURE__*/_jsxs("div", {
              className: "mb-4 flex items-center justify-between border-b border-cyan-500/20 pb-3",
              children: [/*#__PURE__*/_jsxs("div", {
                className: "flex items-center gap-2",
                children: [/*#__PURE__*/_jsx(Shield, {
                  className: "h-4 w-4 text-cyan-400"
                }), /*#__PURE__*/_jsx("span", {
                  className: "text-xs font-medium tracking-wider uppercase text-cyan-400",
                  children: "System Overview"
                })]
              }), /*#__PURE__*/_jsxs("div", {
                className: "flex items-center gap-1.5",
                children: [/*#__PURE__*/_jsx("span", {
                  className: "h-1.5 w-1.5 rounded-full bg-green-500"
                }), /*#__PURE__*/_jsx("span", {
                  className: "text-xs text-green-400",
                  children: "All Systems Operational"
                })]
              })]
            }), /*#__PURE__*/_jsx("div", {
              className: "grid grid-cols-2 gap-4 md:grid-cols-4",
              children: [{
                label: "Active Sensors",
                value: "247",
                icon: /*#__PURE__*/_jsx(Radio, {
                  className: "h-4 w-4"
                })
              }, {
                label: "Canal Monitors",
                value: "89",
                icon: /*#__PURE__*/_jsx(Droplets, {
                  className: "h-4 w-4"
                })
              }, {
                label: "AI Accuracy",
                value: "94.2%",
                icon: /*#__PURE__*/_jsx(Cpu, {
                  className: "h-4 w-4"
                })
              }, {
                label: "Coverage Area",
                value: "1,568 km²",
                icon: /*#__PURE__*/_jsx(Globe, {
                  className: "h-4 w-4"
                })
              }].map((stat) => /*#__PURE__*/_jsxs("div", {
                className: "text-center",
                children: [/*#__PURE__*/_jsx("div", {
                  className: "mb-1 flex justify-center text-cyan-400/60",
                  children: stat.icon
                }), /*#__PURE__*/_jsx("div", {
                  className: "font-mono text-xl font-bold text-white",
                  children: stat.value
                }), /*#__PURE__*/_jsx("div", {
                  className: "text-xs font-medium tracking-wider uppercase text-slate-500",
                  children: stat.label
                })]
              }, stat.label))
            })]
          })
        }), /*#__PURE__*/_jsxs("div", {
          className: "mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center",
          children: [/*#__PURE__*/_jsx(LoginButton, {
            variant: "citizen",
            icon: /*#__PURE__*/_jsx(Users, {
              className: "h-5 w-5"
            }),
            onClick: () => onLogin("citizen")
          }), /*#__PURE__*/_jsx(LoginButton, {
            variant: "gov",
            icon: /*#__PURE__*/_jsx(Building2, {
              className: "h-5 w-5"
            }),
            onClick: () => onLogin("gov")
          })]
        }), /*#__PURE__*/_jsx("p", {
          className: "mt-4 text-center text-xs text-slate-500",
          children: "Select your access level to enter the Flood Command Dashboard"
        })]
      })]
    }), /*#__PURE__*/_jsx("section", {
      className: "landing-features",
      children: /*#__PURE__*/_jsxs("div", {
        className: "mx-auto max-w-6xl px-6",
        children: [/*#__PURE__*/_jsxs("div", {
          className: "mb-12 text-center",
          children: [/*#__PURE__*/_jsx("h2", {
            className: "text-2xl font-bold text-white md:text-3xl",
            children: "Intelligent Flood Protection"
          }), /*#__PURE__*/_jsx("p", {
            className: "mx-auto mt-3 max-w-2xl text-sm text-slate-400",
            children: "Four pillars of our AI-driven urban flood response system"
          })]
        }), /*#__PURE__*/_jsx("div", {
          className: "grid gap-6 md:grid-cols-2 lg:grid-cols-4",
          children: FEATURES.map((feature) => /*#__PURE__*/_jsxs("div", {
            className: "landing-feature-card",
            onMouseEnter: () => setHoveredFeature(feature.id),
            onMouseLeave: () => setHoveredFeature(null),
            children: [/*#__PURE__*/_jsx("div", {
              className: `mb-3 flex h-11 w-11 items-center justify-center rounded-lg border transition-all duration-300 ${hoveredFeature === feature.id ? "border-cyan-500/40 bg-cyan-500/20 text-cyan-400" : "border-slate-700/50 bg-slate-800/50 text-slate-500"}`,
              children: feature.icon
            }), /*#__PURE__*/_jsx("h3", {
              className: "mb-1.5 text-sm font-semibold text-white",
              children: feature.title
            }), /*#__PURE__*/_jsx("p", {
              className: "text-xs leading-relaxed text-slate-500",
              children: feature.description
            })]
          }, feature.id))
        }), /*#__PURE__*/_jsx("div", {
          className: "mt-12 flex justify-center",
          children: /*#__PURE__*/_jsxs("button", {
            onClick: () => onLogin("citizen"),
            className: "landing-cta-link",
            children: [/*#__PURE__*/_jsx("span", {
              children: "Request System Demo"
            }), /*#__PURE__*/_jsx(ArrowRight, {
              className: "h-4 w-4"
            }), /*#__PURE__*/_jsx(Zap, {
              className: "h-3.5 w-3.5 text-amber-400"
            })]
          })
        })]
      })
    }), /*#__PURE__*/_jsx("footer", {
      className: "border-t border-slate-800 bg-[#060b18] px-6 py-8",
      children: /*#__PURE__*/_jsxs("div", {
        className: "mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 md:flex-row",
        children: [/*#__PURE__*/_jsxs("div", {
          className: "flex items-center gap-2",
          children: [/*#__PURE__*/_jsx(Waves, {
            className: "h-4 w-4 text-cyan-500"
          }), /*#__PURE__*/_jsx("span", {
            className: "text-sm font-semibold text-slate-400",
            children: "Bangkok Flood Command"
          })]
        }), /*#__PURE__*/_jsx("p", {
          className: "text-xs text-slate-600",
          children: "\xA9 2026 Department of Drainage & Sewerage, Bangkok Metropolitan Administration. Powered by AI."
        })]
      })
    })]
  });
}