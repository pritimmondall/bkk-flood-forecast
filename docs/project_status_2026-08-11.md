# Where the project actually stands — 11 August 2026

Written as an honest audit against the goal as originally stated, not against
the roadmap. Every number here was read off the repository or measured in an
experiment; nothing is estimated.

---

## The one-paragraph answer

The learning half of the idea is built, measured and works. The serving half
exists but answers questions about the **past**, not the present. Two-thirds of
the forecast horizon you asked for — the 3-hour and 6-hour models — do not exist
as files. And four days of work is currently sitting uncommitted in git, which is
the only problem here that can permanently lose something.

---

## The original goal, step by step

> *"Using the previous years' datasets the model will learn that on that date and
> time, for this amount of rain, this amount of flow, this amount of water, these
> areas flooded. Now the model collects the data it needs from the API and tells
> whether it is flooding now in Bangkok, and in the next 1 hr, 3 hr, 6 hr will it
> flood, and its risk."*

| Step | Status | Where it lives |
|---|---|---|
| 1. Learn the pattern from past years | **Done** | `notebooks/00–09`, `src/bkkflood/` |
| 2. Collect what it needs from an API | **Half done** — collectors run hourly, nothing reads them | `src/bkkflood/collectors/`, `notebooks/10` |
| 3. Is it flooding now? | **Done, but on history** — replays a past timestamp | `backend/app/main.py`, `src/bkkflood/serving.py` |
| 4a. Next **1 hour** | **Done** | `models/onset_t15_h1_final` |
| 4b. Next **3 and 6 hours** | **Missing — no model file exists** | — |
| 5. Risk | **Done** | calibrated probability, 5/15/30 cm tiers, CAP alerts |

---

## What exists today

- **~7,000 lines** of library code in 22 modules, and **118 tests** across 7
  files, all passing.
- **Seven years ingested and verified**: 393 million sensor readings, 51 GiB of
  raw CSV compressed to 1.1 GiB of Parquet, 837 flood events at the 15 cm mark.
- **A trained and evaluated model**: on a year it had never seen, it correctly
  identifies **53 of every 100 flood events**.
- **An API with 13 endpoints** and a working map dashboard — forecast, district
  risk roll-up, CAP 1.2 alerts, observations, station history, hotspots.
- **A terrain layer** built from the 1 m elevation model — sink depth, slope, TWI.
- **Live collectors running hourly since this morning**: ThaiWater canal levels,
  Open-Meteo forecast rain, Traffy citizen reports.
- **Fourteen written reports** in `docs/reports/`, including the measurements
  behind every claim above.

That is a real system. The gaps below are specific, not general.

---

## Gap 1 — the 3-hour and 6-hour models do not exist

`config/config.yaml` declares `horizons_hours: [1, 3, 6]`. Phase 4 trained models
across all three horizons to compare them. But `models/` contains exactly two
files:

```
general_t15_h1_final   tier 15 cm, horizon 1 h, 47 features
onset_t15_h1_final     tier 15 cm, horizon 1 h, 50 features
```

There is no `h3` or `h6` artifact anywhere in the repository. `serving.py` reads
the horizon out of the model's own metadata, so the API is *physically incapable*
of answering for 3 or 6 hours — not because of a missing feature flag, but
because the model that would answer was never saved.

**What it costs:** re-run notebooks 07 and 08 with `SAVE=True` at horizons 3 and
6. The code path already exists and was exercised in Phase 4. It runs over the
full feature table, so budget hours of compute rather than minutes.

---

## Gap 2 — the collectors are not connected to the model

Two halves that never meet:

- The collectors write to `data/live/` every hour.
- `serving.py` is fixed at `DATA_MODE = "replay"` and reads the historical
  feature table. It contains no reference to `data/live/` at all.

So the system answers *"was it flooding at this past moment"*, not *"is it
flooding now"*. `docs/dual_mode_design.md` specifies the `live.py` that would
join them; that file was never written.

**What it costs:** a few days. But read the next section before deciding it is
worth doing now.

---

## The limit that building cannot fix

Two measured facts that shape what the finished system can honestly be:

**Live mode would score about 5 out of 100, not 53.** The model learned on BMA's
131 rain gauges at five-minute intervals. Nothing public replaces them — we
tested the satellite products, the national weather API and the commercial radar
services, and each is too coarse, too slow, or has no Bangkok stations. Wiring
the collectors in today produces a system that misses 19 floods in 20.

**The median warning lead is 15 minutes.** One time step. Three-quarters of
correct detections give only that. So even with the 3-hour and 6-hour models
trained, those answers will rest almost entirely on a rainfall *forecast* on a
13 km grid — over a city that floods from storm cells 2 to 5 kilometres across.
You will get an honest number, but it will be a weak signal.

Neither is a modelling problem, and neither gets better with more engineering.
Both are answered by the same thing: **a live feed from BMA's rain gauge
network**, which takes live performance from 5 in 100 to roughly 43. That request
is drafted in `docs/bma_data_request_email_2026-08.md`.

This is why the honest order of work is: **ask BMA first, build second.** The
build is a few days either way; the access determines whether it is worth having.

---

## Gap 3 — four days of work is uncommitted

`git status` shows **164 changed files**, and the most recent commit predates the
entire v3 rebuild. Uncommitted right now: Phases 0 through 5, all of
`src/bkkflood/`, every notebook, both trained models, and this morning's
collectors. The branch is also 12 behind and 9 ahead of `main`.

This is the cheapest problem on the page and the only one that can lose work
permanently. Ten minutes.

**Also worth clearing:** `data/parquet/` (3.4 GB) and `data/training/` (7.6 GB)
are leftover v2 artifacts, not supervisor data — 11 GB recoverable whenever you
want it.

---

## Recommended order

1. **Commit everything.** Ten minutes. Removes the only risk of losing work.
2. **Send the BMA request.** It has a multi-week turnaround and it determines
   whether Gap 2 is worth building. Nothing else should wait on it.
3. **Train and save the 3 h and 6 h models.** Closes the largest gap against the
   original goal, and needs no one's permission.
4. **Then `live.py` and dual mode** — by which point you will know whether live
   mode is being fed 5-in-100 data or 43-in-100 data, and the design should
   differ accordingly.

---

## One thing to keep

Every claim in this document is checkable. The 53 comes from
`docs/reports/phase4_findings.md`, the 5 from
`docs/reports/live_forecasting_feasibility.md`, the 15-minute lead from
`docs/reports/phase5_findings.md`, and the model horizons from the JSON files in
`models/`. If a number in a future slide deck cannot be traced back to a file
like these, it should not be in the slide deck.
