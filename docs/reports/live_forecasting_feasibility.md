# Can this run live? A measured answer

> **Updated 10 August 2026.** A survey of non-BMA sources found a working national
> API that covers Bangkok canals. See section 2a — it changes the conclusion.

Written 10 August 2026, after checking what BMA actually publishes and then
testing what the model can do without the data we would lose.

---

## 1. The question

Everything built so far runs on **historical replay**: seven years of CSV files,
ending December 2025. To forecast live we would need the same inputs arriving in
real time. This report establishes exactly which inputs matter and which do not.

---

## 2. What BMA publishes live, checked today

`pumps.bangkok.go.th` is **live and working**. Fetched 10 August 2026: 148
stations, most recent readings stamped 06:21 the same morning, no login
required. Station codes use the same district scheme as our data
(`PH.DDG.06`, `PH.KTY.03`, `PH.HKG.05`).

It publishes **pump-station water levels in metres**. It does **not** publish
road flood depth, rain gauges or canal flow.

| Input | Live today? | Notes |
|---|---|---|
| Road flood depth (`FL.*`) | **No** | the target sensor; CSV only, ends Dec 2025 |
| Rain gauges (131) | **No** | CSV only |
| Canal water level / flow | **No** | CSV only |
| Pump-station levels (148) | **Yes** | `pumps.bangkok.go.th`, ~5 min updates |
| GFS forecast rain | **Yes** | Open-Meteo public API |
| Traffy Fondue citizen reports | **Yes** | public API |

---

## 2a. Non-BMA sources, surveyed and tested 10 August 2026

Every source below was called directly, not read about.

### ThaiWater (HII) — WORKS, and it is the important one

`https://api-v3.thaiwater.net/api/v1/thaiwater30/provinces/waterlevel?province_code=10`

Public JSON, **no authentication**, responded immediately. Returns **11 Bangkok
canal and river stations**, timestamped `2026-08-10 16:00` — hourly and current.

Operated by the **Hydro-Informatics Institute (HII)** and the **Royal Irrigation
Department (RID)** — national agencies, not BMA.

What each record carries:

| Field | Why it matters |
|---|---|
| `waterlevel_msl` + `_previous` | level and its change — the rise signal the model uses |
| `tele_station_lat` / `_long` | **real coordinates**, not district centroids |
| `river_name` | actual canals: Saen Saep, Lat Phrao, Phasi Charoen, Thawi Watthana, Maha Sawat, Lam Pla Thio, Bang Bua, Hok Wa |
| `left_bank`, `right_bank`, `min_bank`, `ground_level` | how far below the bank the water is |
| `storage_percent`, `diff_wl_bank`, `situation_level` | HII's own flood-risk framing |
| `amphoe_name.en` | district in English — joins to our data |

Stations sit in Thon Buri, Dusit, Lat Krabang, Taling Chan, Bang Khen, Sai Mai,
Bang Khae, Vadhana and Lat Phrao.

**This is the canal water-level input that section 3 measures as worth 43% → 85%
of event POD — and it is available today without asking anyone.**

Two honest limits. Eleven stations against the 300 in our training data, so it is
a much sparser network. And it is hourly, not 5-minute.

### ThaiWater rainfall — NOT available for Bangkok

`/provinces/rainfall?province_code=10` and `/provinces/rain?province_code=10`
both return empty. The national `/public/rain_24h` endpoint returns data but
contains **no Bangkok stations** — it appears to be a ranked national subset.

**Rain remains the gap.** It is also the higher-value of the two (3% → 43%).

### Everything else checked

| Source | Status |
|---|---|
| `pumps.bangkok.go.th` (BMA) | live, 148 stations, ~5 min — but BMA, and needs permission |
| Open-Meteo GFS | live, already used; 13 km grid, measured at 3% on its own |
| TMD (`data.tmd.go.th/api`) | **tested — not a substitute.** 3-hourly observations from 122–125 stations *nationally*, so 2–3 in Bangkok. Requires registration. No radar API is offered, only forecasts, warnings and station observations. Against BMA's 131 gauges at 5-minute resolution this is far too sparse and far too slow. |
| Traffy Fondue | live citizen reports; a lagging confirmation, not a predictor |

---

## 3. The experiment that changes the answer

Phase 4 reported that **87% of the onset model's gain** comes from the station's
own depth history. Read casually, that says live forecasting is impossible
without live road sensors.

Share of *gain* is not the same as *necessity*. Gain measures how much a feature
contributed in the presence of all the others; it says nothing about how well the
model does when that feature is removed and the rest are allowed to compensate.

So the model was retrained four times on the same fold — train 2019–2023,
validate 2024, test 2025 — dropping feature families to simulate each live
scenario.

| Feature set | Features | Onset recall | Precision | **Event POD** | % of full |
|---|---|---|---|---|---|
| **A** everything (current system) | 50 | 0.204 | 0.138 | **0.533** | 100% |
| **D** everything **except road depth** | 38 | 0.173 | 0.132 | **0.451** | **85%** |
| **C** rain gauges + calendar + terrain | 29 | 0.083 | 0.131 | 0.230 | 43% |
| **B** GFS + calendar + terrain *(live today)* | 16 | 0.011 | 0.002 | 0.016 | **3%** |

### Two findings, in order of importance

**Road flood depth is not essential.** Set D has no road-sensor history at all
and still catches **45% of floods before the water arrives**, against 53% for the
full system — 85% of the performance. The 87%-of-gain figure was misleading about
what the system *needs*. Rain and canal state can carry most of the load when
depth history is taken away.

**What is public today is not enough.** Set B — GFS forecast rain, calendar, tide
phase and terrain, the only inputs fetchable right now — catches **1.6% of
floods** at 0.2% precision. Building a live system on that would produce a
dashboard that looks operational and is worthless. It should not be built.

*(Set B's 45-minute median lead is an artefact of firing almost at random, on the
16 events it caught. Ignore it.)*

---

## 3a. The decisive test: is there ANY viable live combination?

Section 2a found live canal levels. So the obvious question is whether canal
levels plus GFS — everything obtainable today without asking BMA for anything —
is enough on its own. Measured on the same fold:

| Feature set | Features | Onset recall | **Event POD** | % of full |
|---|---|---|---|---|
| A everything (current system) | 50 | 0.204 | **0.533** | 100% |
| **E canal + GFS + calendar + terrain** *(all obtainable today)* | 25 | 0.011 | **0.049** | **9%** |
| B GFS + calendar + terrain | 16 | 0.011 | 0.016 | 3% |

**The answer is no.** Adding live canal levels to GFS moves detection from 1.6%
to 4.9%. Better than nothing and nowhere near usable.

### Why canal levels help in set D but not in set E

In section 3, adding canal state took the model from 23% (set C) to 45% (set D)
— a large gain. Here the same features add almost nothing.

The difference is rain. Canal level tells you the drainage network is loaded; it
does not tell you a storm is arriving over a particular district. Given rainfall,
canal state sharpens the picture considerably. Without rainfall there is nothing
for it to sharpen. **Canal levels are a multiplier on rain, not a replacement for
it.**

### Which makes rainfall the irreplaceable input

And no public non-BMA source provides it at the required resolution:

| Candidate | Why it fails |
|---|---|
| GFS via Open-Meteo | 13 km grid; Bangkok storm cells are 2–5 km. Measured at 3%. |
| TMD API | 3-hourly, 2–3 Bangkok stations, registration required |
| ThaiWater | no Bangkok rainfall stations exposed |
| ERA5 | 5-day publication lag — already excluded for this reason |

**BMA's 131 rain gauges at 5-minute resolution have no public substitute.** That
is the single point on which live forecasting turns.

---

## 4. What this means for the BMA request

The ask changes shape. It is no longer "give us everything". It is:

> **A live feed of the rain gauge and canal networks would deliver about 85% of
> the system's demonstrated performance. Road flood sensors, which are the
> hardest thing to ask for, turn out to be the least necessary.**

Ranked by measured value:

| Rank | Ask | What it buys |
|---|---|---|
| 1 | **Live rain gauge feed** (131 stations) | 3% → 43% of full event POD |
| 2 | ~~Live canal water level~~ — **partly solved via ThaiWater** | see 2a; 11 stations available now without asking |
| 3 | Station coordinates (water + flow sensors) | terrain becomes usable; currently contributes 0% |
| 4 | Live road flood sensors | 85% → 100% |
| 5 | Weather radar | rain stops being a district average |

Items 1 and 2 are the same networks BMA already gave us seven years of history
for. The request is for a live tap on data they are already collecting, not for
anything new to be built or installed.

---

## 5. The pump feed is worth having for a different reason

Phase 5 listed pump and gate status as a known blind spot: **a flood a pump
prevented is recorded in our training data as no flood**, so the model is partly
trained against a counterfactual.

`pumps.bangkok.go.th` covers 148 stations — more than our 107 flood sensors — at
what appear to be real pump locations rather than district centroids.

Two things stop it being used immediately:

1. **No history.** It shows current values only. Nothing can be trained on it
   until a collector has run for a season.
2. **Permission.** It is a government system and no collector was written on
   purpose (project rule 8). Asking costs one email and is the right opening move
   with the agency we are about to request live feeds from.

---

## 6. Recommendation

**Do not build a live forecast on currently available public data.** Measured at
4.9% event POD with every public source combined — including the ThaiWater canal
feed — it would be a system that looks operational and warns nobody.

**Do three things instead:**

1. **Put the ranked request in section 4 to BMA.** It is a much easier ask than
   the previous framing, and it is backed by measurement rather than assertion.
2. **Ask permission for the pump feed and start collecting immediately if
   granted.** History accumulates from the day the collector starts, and it fixes
   a known blind spot. There is nothing to gain by waiting.
3. **Build the collector architecture now**, source-agnostic, so that the day a
   feed opens the system runs. The model already scores a full city in
   milliseconds; the missing piece is a poller that computes the same features
   every 15 minutes.

**One operational caveat for whenever it does go live:** features such as
`fl_max_24h` and `rain_rf24hr_mean` look back 24 hours. A collector must run for
a full day before its predictions mean anything. On a cold start the system is
close to blind, and it must say so rather than emitting confident zeros.
