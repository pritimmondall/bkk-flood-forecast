# Supervisor-Provided Reference Docs — Review

*Reviewed 2026-07-15: `BKK_FF_Dashboard Scheme.docx`, `Project Dashboard – Display Description PS 3-12-2026.pptx`, `CAP Standard.pdf`.*

## What each document actually is

- **`BKK_FF_Dashboard Scheme.docx`** — the real spec: a 10-panel dashboard design specifically for Bangkok, written by whoever drafted it (possibly your supervisor). Matches the team's roadmap almost exactly (same 4-tier depth thresholds: <5/5–15/15–30/>30cm), but goes further on specifics — see below.
- **`Project Dashboard – Display Description PS 3-12-2026.pptx`** — **not Bangkok.** This is "PHARE Municipality" / the Yom River Monitoring Network in Phrae province, a different, already-deployed system (real station names: KY.1, KL.1, KM.1, KS.1, Y.20, Y.1C, Y.34, Y.38; real vendor hardware: RK-series sensors, SIKA/Haiwell cloud). Confirmed with the supervisor (2026-07-15): this is a UI reference only, not a BKK requirement — treat it as design inspiration + a source of transferable ideas, not literal spec.
- **`CAP Standard.pdf`** — the OASIS CAP 1.2 JSON schema with a bilingual (EN/Thai) field-by-field explainer, sourced from a Khon Kaen University alert-system reference (sri-alert.kku.ac.th). Confirms and sharpens the roadmap's CAP section.

## What's new / actionable for the ML portion

**Exact KPIs the model must be able to produce** (this is more specific than the roadmap's "quantile head"):
- Risk chart: Peak Risk (%), Peak Time, Time to Warning.
- Depth chart: Peak Depth (cm), Peak Time, Time to 15cm / Time to 30cm.
- Both are **spatially aggregated** outputs — the model produces per-station/point predictions, and the dashboard aggregates for a selected area using **P95 as the primary line** (worst-case-in-area) and **area-weighted mean as secondary**. This is a concrete instruction: the quantile-regression head's P95 output isn't just a nice-to-have uncertainty band, it's the actual headline number a chart will display — worth prioritizing getting P95 well-calibrated, not just point estimates.

**Flood depth formula, stated explicitly**: `Flood Depth = Water Level − Road Elevation`. This implies "Road Elevation" as a specific required layer — more specific than a generic DEM. Worth checking with the Data/GIS engineer whether `DTM_1M`/SRTM can serve this directly or whether road-surface elevation needs separate extraction (road centerlines × DEM). Not a blocker for training your time-series model on the existing `flood` column (which is presumably already this computed depth), but matters for the "Current Flood Map (Observed)" panel's own live recomputation.

**CAP urgency has more granularity than the roadmap assumed**: `Immediate` = within 1hr, `Expected` = 1–12hr, `Future` = >12hr. Your three forecast horizons map cleanly: a 1h-ahead crossing → `Immediate` if onset is under an hour out; 3h/6h-ahead crossings both land in `Expected`. Worth handing this exact mapping to whoever builds the CAP generator, since it's driven directly by which horizon bucket your model's threshold-crossing prediction falls into.

## Two things worth flagging back to your supervisor

1. **The three screenshots in the docx are generic dashboard-template mockups, not real BKK data** — station labels read "Salt Lake" and "Park Street," and one panel ("Model Parameters — AI hydrological inputs") lists Soil Moisture Index and Evapotranspiration as model inputs, which aren't in any of your four datasets. That's almost certainly why the doc's own author left "I am not sure what these UI are" / "Current or the Future??" next to them. Confirmed with the supervisor (2026-07-15): illustrative only, not a literal UI/data spec — ignore Soil Moisture Index / Evapotranspiration as required inputs.
2. **Threshold philosophy conflict between the two dashboard docs.** BKK's scheme uses one universal depth threshold set for every station (5/15/30cm). The Phrae reference system instead calibrates thresholds per station (e.g., station Y.1C alone has 8 tiers from Normal <7.3m to Severe ≥12m, because each river reach has a different baseline). My take: BKK's universal thresholds are the right call for this sprint — 300 water stations don't have enough individual history yet to calibrate reliably, and a single depth threshold is what the CAP mapping and evaluator both already assume. But per-station calibration (percentile-based, once each station has 2+ years of clean history) is a natural phase-2 improvement worth noting in the roadmap's "next steps," since the Phrae example shows it's the more hydrologically defensible approach once you can afford it.

## One new data lead

The pptx links Thai Water's public API docs (`standard.thaiwater.net`) for real-time rainfall/water-level data from RID and HII (ThaiWater.NET) — a national service, not Phrae-specific. Worth the Data/GIS engineer checking whether this covers Bangkok stations too; it could be a path to live data feeds later without waiting on BMA's own export pipeline.
