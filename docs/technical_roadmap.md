# Technical Roadmap

*Answers evaluator point 12. Status as of the version 2.0 rebuild.*

---

## Where the project stands

The system is **built end to end and demonstrable**: raw sensor CSV → cleaned
Parquet → features → trained models → FastAPI → React dashboard → CAP alerts. It
runs on a laptop with no database and no live feed, which means it can be shown
to anyone at any time.

It is **not yet operational**, and the gap is not mostly software. The two things
standing between this and a system BMA could rely on are a live data feed and
radar rainfall — one is an integration, the other is a permissions conversation.

| Component | State |
|---|---|
| Data pipeline | Complete. 52 GB → Parquet, all known quirks handled, quality scorecard |
| Flood event definition | Complete and evidenced (`notebooks/02`) |
| Feature engineering | Complete; leak-checked; forecast-rain and terrain joins wired |
| Baseline models | Complete — persistence and climatology |
| LightGBM forecaster | Complete — 3 tiers × 3 horizons, plus depth quantiles |
| Onset specialists | Complete — the models that actually forecast |
| Sequence models | Implemented; not promoted under the pre-registered rule |
| Evaluation | Complete — rolling origin, FP/FN analysis, calibration |
| FastAPI backend | Complete — all ten dashboard features served |
| React dashboard | Complete — map, monitoring, alerts, trends, hotspots |
| PostgreSQL + PostGIS | Schema and loaders complete; not yet the production path |
| CAP alerting | Complete; `status = Test` pending BMA authorisation |
| Live data feed | **Not built** — no live BMA sensor API exists |
| Radar rainfall | **Not obtained** — the highest-value missing input |

---

## Phase 0 — Foundation *(complete)*

Establish what the data actually is before modelling anything.

- Full audit of four datasets × seven years; every quirk documented and handled
- Flood event definition derived from evidence, not assumption
- Class imbalance quantified: roughly 1 positive row in 4,000 at the 15 cm tier
- Station registry: 568 stations, 401 placed geographically
- Bangkok district and sub-district boundaries; point-in-polygon station assignment

**The finding that shaped everything after:** `depth > 0` is not a flood. Most
non-zero readings are a few millimetres of sensor noise. Persistence-based
thresholds are mandatory.

---

## Phase 1 — Pipeline and baseline *(complete)*

- Chunked ingestion: 52 GB processed in under 2 GB of RAM
- Feature table: flood autoregressive, rainfall by district, citywide water and
  flow, calendar, tidal phase reconstructed from lunar periods
- Rolling-origin splits with an embargo at year boundaries
- Persistence and climatology baselines established first, so every later number
  has a bar next to it

**The finding:** persistence is strong at 1 hour and decays fast. That decay curve
is the space a real model has to work in, and it is where the model does in fact
beat it — at 3 and 6 hours.

---

## Phase 2 — Honest evaluation *(complete)*

This phase changed the project's self-understanding more than any modelling work.

- Recall decomposed into onset versus ongoing
- **Discovery:** 55% headline recall = ~100% on already-flooded rows, **9% on
  genuine onsets**. `fl_depth_now` accounted for ~72% of model gain. The system
  was a monitoring tool wearing a forecasting label.
- **Fix:** onset specialists trained on dry rows only. Genuine onset recall at
  1 hour: **9% → 63%**.
- Precision ~1% against a 0.01% base rate — a ~40x lift, enough for a Watch and
  not enough for a Warning. The alert ladder was designed around that constraint
  rather than around the number we wished we had.
- Isotonic calibration, so a displayed "risk %" is a real probability
- Per-station FP/FN analysis; misses sorted into "the signal was there and we
  missed it" versus "no rain was recorded anywhere" — the second bucket is a data
  request, not a modelling task

---

## Phase 3 — Application *(complete)*

- FastAPI with all ten dashboard features, OpenAPI docs, replay mode
- React + Leaflet: choropleth, station markers, monitoring charts, alerts with
  CAP XML, hotspots, trends, replay slider
- PostgreSQL + PostGIS schema with spatial indexes and convenience views
- CAP 1.2 generation with a deliberate `Test` interlock

**A design decision worth recording:** every honesty caveat is a *field in the
API response*, not a footnote in a document. `degraded`, `coord_quality`,
`cap_status`, `has_data`. The frontend can only show a caveat it has been given,
and a caveat that lives only in a PDF may as well not exist.

---

## Phase 4 — What comes next

Ordered by expected gain per unit of effort.

### 4.1 Radar rainfall *(highest value)*

Rainfall features carry ~76% of the onset model's gain, and our rainfall is a
district average. This is the binding constraint on the part of the system that
matters most. TMD registration; reachable remotely.

*Expected:* material improvement in onset detection at 1 h and 3 h.

### 4.2 Forecast rainfall in production

Already built and measured — archived forecast rain correlates with 6-hour flood
labels at 0.282 versus 0.091 for past rain, roughly three times stronger.
Notebook `03b` fetches it.

**The integration risk to watch:** after retraining on forecast-rain features,
the serving layer *must* supply them too. If it does not, the model receives NaN
for its most useful long-range input and silently reverts to climatology, with no
error anywhere.

### 4.3 Live data integration

There is no live BMA sensor API. Until there is, "live" mode falls back to
Open-Meteo rainfall with every BMA sensor feature missing — which the system
flags as `degraded`, but which is a much weaker forecast than the replay demo
implies. **This is the single biggest gap between demo and operations.**

### 4.4 Station coordinates → local water and flow features

Water and flow are citywide averages purely because we cannot join them to a
place. Coordinates fix it, and the fix is a data transfer rather than a model.

### 4.5 Graph neural networks

Sensible only *after* canal topology arrives. Flooding propagates along a
network, and a graph model is the natural fit — but a GNN without real topology
is an architecture in search of a problem.

### 4.6 Promote the GRU for the severe tier

The GRU lost the primary comparison by 0.0003 — a rounding error — and was
correctly not promoted under the pre-registered rule. But it was dramatically
better on the severe tier, where the LightGBM classifier had effectively failed
(PR-AUC 0.38 versus 0.0002). A targeted swap for that one tier is justified and
cheap.

### 4.7 A genuinely sealed holdout

The 2025 holdout is spent. 2026 data would restore an unimpeachable test.

---

## Risks

| Risk | Consequence | Mitigation |
|---|---|---|
| No live sensor feed materialises | System stays a demo | Push for the API; keep replay honest about what it is |
| Radar rainfall unavailable | Onset detection stays capped | Try gauge interpolation; expect less |
| Feature drift between training and serving | Silent accuracy loss | `features.json` is version-controlled and checked at load |
| Alert fatigue from onset watches | Operators stop reading | Watch never escalates; precision published on the dashboard |
| CAP status flipped to Actual prematurely | Real public alerts from an experimental model | Config-gated; requires a deliberate authorised change |
| Sensor network degrades | Coverage silently shrinks | Quality scorecard per station-year; offline share on the dashboard |

---

## What "operational" would require

Not a wish list — the actual blocking set.

1. **A live sensor feed from BMA.** Everything else is secondary.
2. **A retraining schedule.** Annual at minimum; the network changes.
3. **Formal CAP authorisation**, with a named accountable owner.
4. **Monitoring of the monitor** — alert on sensor dropout, stale forecasts,
   model drift.
5. **A validated operator workflow.** The dashboard is designed for a duty
   officer; no duty officer has used it yet.
6. **An agreed error budget.** "We miss roughly 40% of flood onsets at 1 hour" has
   to be acceptable to BMA *in advance*, in writing. A system whose limits are
   only discussed after the first miss will not survive the first miss.
