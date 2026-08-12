# Showing the supervisor GFS — a five-minute demo

The reply in `docs/gfs_reply_2026-08-11.md` answers the question in writing. This
is what to do on screen, because "yes it is integrated" lands very differently
when they can see it.

**Setup:** two terminals, then open `http://127.0.0.1:5173`.

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD/src:$PWD"
uvicorn backend.app.main:app --reload
```
```bash
cd frontend && npm run dev
```

---

## The five minutes

### 1. Start on the flood, not on the code (30 seconds)

The dashboard opens on **13 November 2025, 03:00** — 29 stations alerting, 25
already under water. Let them look at the map first. The point being made is that
there is a working system to have this conversation about.

### 2. Show that GFS is already in it (1 minute)

Open the **Limits** tab, or in a browser tab:

```
http://127.0.0.1:8000/api/model-card
```

Point at the feature list. `rain_fcst_1h`, `rain_fcst_3h`, `rain_fcst_6h` are
GFS, and they are 3 of the 50 inputs the deployed model uses. This is the whole
answer to "did you try it" — it went in after their earlier suggestion.

### 3. Show how well it actually does (2 minutes — this is the demo)

**Trends tab → "Forecast rain vs measured rain".**

Green solid is what the BMA gauges recorded. Pink dashed is what GFS predicted
for that same hour. Let them watch the two lines during the storm.

Three things to say while they look:

- The forecast has been **shifted onto the hour it describes**, so the gap
  between the lines is real disagreement and not a one-hour offset. (Worth
  saying out loud — it is the first thing a careful person suspects.)
- Across 1.38 million district-hours the two correlate at **0.014** on wet
  hours. GFS knows the region is wet. It does not know which district.
- That is the 13 km resolution they raised, made visible. Bangkok's storm cells
  are 2–5 km across.

### 4. Then say the surprising part (1 minute)

Despite that, GFS **earns its place**:

| | Onset recall | Precision | Floods caught |
|---|---|---|---|
| with GFS | 23.9% | 14.8% | **65.1%** |
| without GFS | 21.4% | 21.0% | 58.3% |

Seven more floods caught per hundred, six points of precision given up. Roughly
one extra false alarm per two extra catches. Frame it as a decision for BMA
rather than one we have quietly made for them.

### 5. Land on the ask (30 seconds)

The honest close. Public data today catches about **5 floods in 100**; BMA's own
archive catches **53**. A live rain-gauge feed takes live mode from 5 to roughly
43, and canal level and flow take it from 43 to about 85.

So: GFS is worth keeping, and no amount of work on GFS — downscaling included —
reaches the first row of that table.

---

## If they push on downscaling to 1 km

Do not dismiss it. Their advice is correct in the context it came from, and the
note they sent is about the Heatwave project, where downscaling to 1 km is
standard and works.

The distinction to draw:

> Temperature downscales well because it has a strong, stable relationship with
> things we already know at 1 km — elevation through the lapse rate, land cover,
> urban fraction. There is something real for the function to key on.
>
> Bangkok varies by about two metres of elevation across its whole width, so
> there is no orographic signal for rainfall to inherit. We would produce a 1 km
> map whose fine detail was invented — and invented detail is more dangerous on a
> screen than an honest coarse field, because it looks precise.

Then give them the version we *would* do: statistical downscaling needs ground
truth to calibrate against, and the 131 BMA gauges are exactly that. Get the
gauge feed and correcting GFS per district becomes a well-posed problem. Without
it there is no target.

That turns "no" into "yes, and here is what it needs" — which is also, usefully,
the same request as everything else on the list.

---

## Two questions they may ask, and the honest answers

**"Why is precision worse with GFS?"**
Because it fires on regional wet signals that do not become local floods. We took
that trade knowingly: a missed flood strands traffic, a false alarm sends a
patrol to a dry road. It is reversible in one config change if BMA prefers the
other side of it.

**"Can you forecast 3 or 6 hours ahead?"**
Not today, and be straight about it. The features exist and Phase 4 evaluated
those horizons, but only the 1-hour model was saved — there is no 3 h or 6 h
model file. It is a re-run of notebooks 07 and 08, not new research. See
`docs/project_status_2026-08-11.md`.

---

## What changed in the code for this demo

- `serving.observations()` now returns `rain_fcst_mm_1h`, shifted to valid time
  by `_align_forecast_to_valid_time()` — with a unit check proving that an
  unshifted comparison would have made the forecast look wrong when it was
  right.
- New `ForecastVsObserved` panel in the Trends tab. One axis (both series are
  mm/h — a second y-axis is the standard way to make two unrelated shapes look
  correlated), legend, forecast dashed so identity is not colour-alone.
- Rain is one colour everywhere now: `#5faa35`, snapped into the dark-surface
  lightness band. Paired with `#d55181` it passes CVD separation at ΔE 9.9.

**Known issue not fixed here:** the "City-wide" chart below still plots mm/h and
a count of sensors on one axis. Two different units on one scale is misleading
and should become two charts.
