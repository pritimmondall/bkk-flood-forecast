# Data we need, and what each dataset would buy

*Prepared for the BMA meeting. Answers evaluator point 10.*

Every item below is framed the same way: what it is, what it would change, and
what it costs BMA to provide. The ordering is by expected gain per unit of
effort, not by how interesting the data is.

The short version: **two datasets carry most of the value.** Radar rainfall and
station coordinates. Everything else is worth having and none of it moves the
needle as much as those two.

---

## Priority 1 — Radar rainfall

**What it is.** Gridded rainfall from the Thai Meteorological Department's
weather radar, roughly 1 km resolution, updated every 5–15 minutes. Historical
archive plus a live feed.

**The problem it solves.** Our rainfall input is a **district average** across
BMA gauges. Bangkok floods from convective cells two to five kilometres across,
which dump 40 mm on one sub-district and nothing two kilometres away. Averaging
over a 20 km² district removes exactly the peak that causes the flood, before
the model ever sees it.

**The evidence this is the binding constraint.** In the onset models — the ones
that genuinely forecast rather than monitor — rainfall features account for about
**76% of the total gain** (1-hour rain 56%, 3-hour rain 20%). The model is
leaning almost entirely on rainfall, and rainfall is the input we are degrading
most.

**What it would change.** Direct improvement to onset detection, which is the
weakest and most valuable part of the system. It would also help the 3-hour
horizon, where a cell that has formed but not yet arrived is currently invisible.

**Effort for BMA.** TMD registration; the data is reachable from outside
Thailand. A permissions conversation, not an engineering project.

---

## Priority 2 — Station coordinates and metadata

**What it is.** For all ~570 sensors: latitude and longitude, installation
height, gauge datum, sensor model, and installation date.

**The problem it solves.** Two separate problems, and both are severe.

*Coordinates.* Rain station codes share a district prefix with flood station
codes, so rainfall can be joined per district. Water and flow codes do **not** —
they are canal initialisms. `WL.STN.01` is a canal, not Sathon district. So
water level and flow currently enter the model as **citywide averages**: the
model can tell that the canal network as a whole is under stress, but not which
canal is failing next to which road.

*Datum.* We do not know what `wl_in` is measured from — mean sea level, canal
bed, or an arbitrary local reference. So we can only use *changes* in water
level, never absolute values. "The canal is 30 cm below its bank" is a far
stronger predictor than "the canal rose 8 cm", and we cannot compute it.

**What it would change.** Water and flow become local features instead of
citywide ones. Terrain features become meaningful, because they would be sampled
at the sensor rather than at a district centroid. The map stops approximating.

**Effort for BMA.** Almost certainly a spreadsheet that already exists in an
asset register.

---

## Priority 3 — Canal network topology

**What it is.** Which canal connects to which, in which direction, with gates and
pumping stations marked. A graph, not a map.

**The problem it solves.** Flooding propagates. Water arrives somewhere because
it left somewhere else, and our model has no representation of that at all —
each station is treated as independent.

**What it would change.** It would unlock graph neural networks, which are the
natural model class for a flow network, and more immediately it would let us
build upstream-condition features: "the canal that drains this road is already
full two kilometres upstream" is a strong signal we currently cannot express.

**Effort for BMA.** Likely exists in the Drainage and Sewerage Department's GIS.

---

## Priority 4 — Pump and drainage operation records

**What it is.** When pumping stations ran, at what capacity, and when gates were
opened or closed.

**The problem it solves.** The drainage system has an **operator**. Whether a
road floods depends partly on whether a pump was running, and the model cannot
see that. This is not noise — it is a control input the model is blind to, and
it is a plausible explanation for some of our least-explicable misses.

**What it would change.** Removes a systematic source of unexplained error. It
would also make the forecast *actionable* in a new way: if the model knows what
pumping does, it can begin to answer "what happens if we start this pump now?"

**Effort for BMA.** Operational logs; may need extraction from a SCADA system.

---

## Priority 5 — LiDAR / high-resolution road elevation

**What it is.** 1 m digital terrain model, ideally road-surface elevations along
centrelines. **BMA may already hold this** — there are 1 m DTM tiles in the data
folder.

**The problem it solves.** We tested terrain features and they came out weak,
every correlation under 0.08. The diagnosis is resolution: urban flooding
collects in dips 20–50 cm deep and a few metres across, and a 31 m SRTM pixel
averages them away completely.

**What it would change.** It would give the model a physical reason for *why* a
site floods, rather than only the statistical fact that it does. That matters
most for the hardest case: a newly installed sensor with no history, where
station identity carries no information.

**Effort for BMA.** May be zero — check whether the existing 1 m tiles cover the
sensor locations.

---

## Priority 6 — Chao Phraya tide gauge records

**What it is.** Measured water level at the river mouth, historical and live.

**The problem it solves.** The Chao Phraya is tidal, and at high tide the
drainage gates cannot discharge. The same rainfall floods at high tide and drains
away at low tide.

**Our current workaround.** We reconstruct tidal *phase* from the known lunar
periods (M2 = 12.42 h, spring–neap = 29.53 days). That is real physics and it is
free, but it gives phase without amplitude — and a spring tide during a storm
surge is a completely different situation from a neap tide.

**Effort for BMA.** Likely available from the Hydrographic Department or the
Royal Irrigation Department.

---

## Priority 7 — Historical flood reports

**What it is.** Records of actual flood incidents: complaints, road closures,
insurance claims, news reports, with dates and locations.

**The problem it solves.** Our labels come entirely from sensors. If a road
floods where there is no sensor, it did not happen as far as the model or the
evaluation is concerned. We have no independent check on the sensor-derived
ground truth.

**What it would change.** Validation against reality rather than against
instrumentation, plus an estimate of how much flooding the sensor network is
missing — which is a question nobody can currently answer.

---

## Priority 8 — 2026 data

**What it is.** The same four datasets, for 2026.

**Why it is here at all.** The 2025 holdout has already been opened. Once a
holdout has informed any decision it stops being a holdout, and every number from
it is optimistic by an amount nobody can quantify. A fresh year would restore a
genuinely sealed test, which is the difference between a number we can defend and
a number we have to caveat.

**Effort for BMA.** A file transfer.

---

## Summary

| Priority | Dataset | Main gain | Effort |
|---|---|---|---|
| 1 | Radar rainfall (TMD) | Fixes the district-average blind spot | Registration |
| 2 | Station coordinates + metadata | Water/flow become local, not citywide | Likely a spreadsheet |
| 3 | Canal topology | Flood propagation; graph models | GIS export |
| 4 | Pump and gate records | Removes a hidden control input | SCADA logs |
| 5 | LiDAR road elevation | Physical "why", not just statistical "does" | May already hold it |
| 6 | Tide gauge | Tidal amplitude, not just phase | Inter-agency |
| 7 | Flood incident reports | Independent ground truth | Records request |
| 8 | 2026 sensor data | Restores a clean sealed test | File transfer |

**If only one thing is possible: radar rainfall.**
**If two: radar rainfall and station coordinates.**
