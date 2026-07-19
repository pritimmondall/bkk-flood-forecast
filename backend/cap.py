#!/usr/bin/env python3
"""CAP 1.2 alert mapping for the BKK flood forecast prototype.

Maps one station forecast (the /forecast contract) to a Common Alerting
Protocol 1.2 message. Mapping rules (roadmap section 5.4):

  severity   highest tier alerting: >=30cm -> Severe, >=15 -> Moderate,
             >=5 -> Minor
  urgency    earliest alerting horizon: 1h -> Immediate (CAP defines
             Immediate as <1hr), 3h/6h -> Expected (1-12hr)
  certainty  Observed if the station is already at/above the tier now
             (sensor-confirmed), else Likely (forecast-only)
  status     ALWAYS "Test" in this prototype — never "Actual"

Returns None when no tier alerts at any horizon (no alert -> no message).
"""

from __future__ import annotations

import uuid
from xml.sax.saxutils import escape

import pandas as pd

TIER_SEVERITY = {30: "Severe", 15: "Moderate", 5: "Minor"}
HORIZON_URGENCY = {1: "Immediate", 3: "Expected", 6: "Expected"}

_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>{identifier}</identifier>
  <sender>bkk-flood-forecast-prototype</sender>
  <sent>{sent}</sent>
  <status>Test</status>
  <msgType>Alert</msgType>
  <scope>Public</scope>
  <info>
    <language>en-US</language>
    <category>Met</category>
    <event>Urban Flood Warning</event>
    <urgency>{urgency}</urgency>
    <severity>{severity}</severity>
    <certainty>{certainty}</certainty>
    <onset>{onset}</onset>
    <expires>{expires}</expires>
    <senderName>BKK Flood Forecast (prototype — ML engineer deliverable)</senderName>
    <headline>{headline}</headline>
    <description>{description}</description>
    <instruction>PROTOTYPE TEST MESSAGE — not an official warning. In a real deployment: avoid low-lying roads in the affected area; do not drive through standing water.</instruction>
    <parameter><valueName>station_code</valueName><value>{station}</value></parameter>
    <parameter><valueName>tier_cm</valueName><value>{tier}</value></parameter>
    <parameter><valueName>horizon_h</valueName><value>{horizon}</value></parameter>
    <parameter><valueName>risk_pct_calibrated</valueName><value>{risk}</value></parameter>
    <parameter><valueName>depth_p95_cm</valueName><value>{p95}</value></parameter>
    <area>
      <areaDesc>{area}</areaDesc>
    </area>
  </info>
</alert>
"""


def build_cap(station_forecast: dict, ts: pd.Timestamp) -> str | None:
    """Build a CAP 1.2 XML string from one station's /forecast entry."""
    code = station_forecast["station_code"]
    depth_now = station_forecast["depth_now_cm"]

    # find the highest alerting tier, and its earliest alerting horizon
    chosen_tier, chosen_h = None, None
    for tier in (30, 15, 5):
        hs = [h for h in (1, 3, 6)
              if station_forecast["horizons"][f"{h}h"]["alert"][f"ge{tier}cm"]]
        if hs:
            chosen_tier, chosen_h = tier, min(hs)
            break
    if chosen_tier is None:
        return None

    hz = station_forecast["horizons"][f"{chosen_h}h"]
    risk = hz["risk_pct"][f"ge{chosen_tier}cm"]
    p95 = hz["depth_cm"]["p95"]
    certainty = "Observed" if depth_now >= chosen_tier else "Likely"
    onset = ts + pd.Timedelta(hours=chosen_h)

    if certainty == "Observed":
        headline = (f"Road flooding ≥{chosen_tier}cm ONGOING "
                    f"at station {code}")
        basis = (f"Sensor-confirmed: current measured depth {depth_now}cm "
                 f"meets the {chosen_tier}cm tier. "
                 f"P95 depth forecast for the next {chosen_h}h: {p95}cm.")
    else:
        headline = (f"Road flooding ≥{chosen_tier}cm expected within "
                    f"{chosen_h}h at station {code}")
        basis = (f"Forecast-based: calibrated probability of "
                 f"≥{chosen_tier}cm within {chosen_h}h is {risk}%. "
                 f"P95 depth forecast: {p95}cm. Current depth {depth_now}cm.")
    description = (
        f"Issued {ts.isoformat()} for monitoring station {code} "
        f"(district {code.split('.')[1]}). {basis} "
        f"Model: LightGBM baseline, thresholds frozen on 2024 validation.")

    return _TEMPLATE.format(
        identifier=f"BKK-FF-{ts:%Y%m%d%H%M}-{code.replace('.', '-')}-"
                   f"{uuid.uuid4().hex[:6]}",
        sent=ts.isoformat() + "+07:00",
        urgency=HORIZON_URGENCY[chosen_h],
        severity=TIER_SEVERITY[chosen_tier],
        certainty=certainty,
        onset=onset.isoformat() + "+07:00",
        expires=(onset + pd.Timedelta(hours=3)).isoformat() + "+07:00",
        headline=escape(headline),
        description=escape(description),
        station=code, tier=chosen_tier, horizon=chosen_h,
        risk=risk, p95=p95,
        area=escape(f"Vicinity of flood monitoring station {code}, "
                    f"district {code.split('.')[1]}, Bangkok"),
    )
