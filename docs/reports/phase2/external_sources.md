# Phase 2 — External data sources

*What we collect, what we deliberately do not, and the questions that unblock the rest.*

Every URL below was checked and responded as described. **Reachable is not the
same as permitted** — that is a separate question for each source, and it is the
main output of this document.

---

## 1. The rule that governs this whole phase

Open-Meteo publishes two rainfall archives that look interchangeable and are not.

| | What it is | Safe as |
|---|---|---|
| `historical-forecast-api` | What the weather model **predicted** at the time | `rain_fcst_*` — a forecast feature |
| `archive-api` (ERA5) | What **actually fell**, reconstructed afterwards | `era5_*` — a past-rain feature |

ERA5 is built from observations that did not exist when a forecast would have
been issued. Using it as a forecast feature means training the model on the
answer sheet. In production the model would receive a real forecast instead — a
much weaker input — and its accuracy would collapse with no error raised
anywhere.

Rainfall carries roughly three quarters of the forecasting signal in this
project, so this is not a technicality. It is the single most damaging mistake
available in Phase 2.

**Enforcement:** two functions, two output files, two column prefixes. The
prefixes are what make the mistake hard to commit by accident in notebook 05.

---

## 2. Sources we collect

### 2.1 Open-Meteo — archived forecast rain

- **Endpoint:** `https://historical-forecast-api.open-meteo.com/v1/forecast`
- **Model:** `ecmwf_ifs_hres` (~9 km)
- **Licence:** free for non-commercial use, no API key
- **Why this model:** Open-Meteo's documentation lists IFS HRES as archived from
  **2017-01-01**, the only model in their table that would span all seven of our
  years. Every other model starts in 2021–2022.
- **Status: UNVERIFIED.** That start date is a row in a documentation table, not
  something we have seen. Notebook 04 runs a deliberate smoke test on **January
  2019** — the year most likely to be missing — before the long pull, then
  reports real coverage per year in
  `docs/reports/phase2/forecast_coverage_by_year.csv`.
- **If early years are missing:** leave them missing. Filling 2019–2021 with ERA5
  would create a feature that is a genuine forecast in some years and a peek at
  the answer in others — impossible to reason about during evaluation, and worse
  than a gap. LightGBM handles `NaN` natively.

### 2.2 Open-Meteo — ERA5 reanalysis

- **Endpoint:** `https://archive-api.open-meteo.com/v1/archive`
- **Resolution:** ~25 km, from 1940
- **Role:** past rain only. Its value is that it is **independent of BMA's gauge
  network** — it can see between the gauges, which is precisely where our own
  rainfall data is weakest.

### 2.3 Traffy Fondue — citizen flood reports

- **Endpoint:** `https://publicapi.traffy.in.th/teamchadchart-stat-api/geojson/v1`
- **Verified:** 2026-08-07, returns GeoJSON with coordinates, timestamp,
  district, sub-district, Thai description, problem categories, photo URL, and
  an AI-generated summary block.
- **Operator:** NECTEC (NSTDA), used by BMA.

**Why this matters more than it looks.** Our flood labels come from 107 sensors.
A road that floods where there is no sensor did not flood, as far as the model
*and its evaluation* are concerned. Nobody on this project has ever been able to
say how much that misses. These reports are the first independent measurement of
it.

**Use for evaluation before training.** A report means "a person complained", not
"the depth reached 15 cm". Reporting is biased towards populated, connected,
smartphone-carrying areas. As a check on the sensor network's blind spot it is
excellent; as a training label it would need considerably more care.

**Open question — how far back does it go?** The public endpoint is a live feed.
Notebook 04 measures the actual year distribution rather than assuming. If it
only reaches back a year or two, it validates the *current* system and cannot
re-label 2019–2022. A historical bulk export would be a request to NECTEC.

---

## 3. The resolution problem, stated plainly

IFS HRES is about 9 km. ERA5 is about 25 km. Bangkok is about 40 km across.

Several districts will therefore share a grid cell, and with ERA5 the entire city
is only a handful of cells. **These are regional rainfall series labelled by
district, not district-specific measurements.**

They cannot see a convective cell sitting over one khet — which is the thing that
actually floods Bangkok. This is not a flaw in the pull; it is the arithmetic
reason TMD radar sits at priority 1 on the data request. Anything built on this
data must carry that caveat into the API response, not just into a document.

---

## 4. Deliberately NOT collected: `pumps.bangkok.go.th`

BMA's Drainage and Sewerage Department portal.

| | |
|---|---|
| Stations | **148 pump stations**, citywide |
| Cadence | live water level, updating roughly every 5 minutes |
| History | a date-range query page reporting **≈10.3 million records** |
| Codes | `PH.<district>.NN` — **27 of our 33 flood-district prefixes appear** |
| Map | the homepage renders a station map, so **coordinates exist server-side** |
| Access | public, no login required to view |

This is the most useful thing found in the entire research phase. It sits in the
open. It would address the project's two largest gaps at once: a live data feed,
and real sensor coordinates.

**No collector was written for it, and that is a decision rather than an
oversight.**

It is a government system with no published API and no stated reuse terms. The
entire purpose of this project is a working relationship with BMA. An
unauthorised scraper is a poor opening move — especially when the ask is easy,
because they are already publishing the data. Scraping first and asking later
converts a simple request into an awkward conversation.

**A guess worth checking after permission, not before:** the site behaves like a
modern JavaScript application, which usually means a JSON endpoint exists behind
it. A plain guess at `/api/stations` returned nothing, and no further probing was
done on purpose.

---

## 5. ThaiWater — a standard, not a feed

`https://standard.thaiwater.net` — published by HII (สสน.).

Important distinction: this is Thailand's **national water-data exchange
standard**. It specifies *how* agencies should publish water data. It is not an
endpoint you can call today.

Two parts of it are directly useful to us:

**5.1 The water-level datum convention** (`การวัดระดับน้ำ`). Our single largest
interpretive gap is that we do not know what `wl_in = 0` means — mean sea level,
canal bed, or a local benchmark — so we can only use *changes* in canal level,
never absolute ones. There may already be a national answer to this. **Read this
page before asking BMA**; the answer may be "MSL, per the national standard",
which costs nothing and unblocks a whole class of features.

**5.2 The national alerting standard** (`มาตรฐานข้อมูลน้ำเพื่อการเตือนภัย`).
Defines flood (`น้ำท่วม`), alert levels and their colour symbols, and station
criteria for alerting. **Our 5 / 15 / 30 cm tiers and the DDPM mapping in spec
§E.11 should be checked against this.** If Thailand has a national alert-level
standard, aligning to it is far stronger than inventing our own — and much easier
to defend in a meeting.

Both are in Thai. Neither has been read in full yet; that is a task, not a
blocker.

---

## 6. TMD radar — still the priority, still blocked

Bangkok is covered by TMD radars at **Nong Chok** (`weather.tmd.go.th/bma_nck.php`),
**Nong Khaem** (`bma_nkm.php`) and Khao Khiao (240 km range).

What is public is **rendered PNG imagery**. No documented API for gridded values
was found.

**Do not build a training pipeline on coloured PNGs.** Deriving rainfall rates
from a colour scale is lossy, fragile, and breaks silently the day someone
changes the palette. A formal request to TMD for gridded products — archive and
live — remains the highest-value outstanding data item in the project.

---

## 7. Questions to put to BMA, in priority order

Each is phrased to be answerable in one reply.

| # | Question | Why it matters | Effort for them |
|---|---|---|---|
| 1 | *"You already publish live pump-station data at pumps.bangkok.go.th. May we consume it programmatically, and is there an API behind it?"* | Unblocks live operation and gives us real coordinates for 148 stations | Very low — it is already published |
| 2 | *"What datum is `wl_in` measured against, and do you hold install height and bank/deck elevation per station?"* | Turns canal level from a change-only signal into "how close is this canal to overflowing" | Low — likely one field in an asset register |
| 3 | *"Can you supply lat/lon for all 568 sensors?"* | Water and flow stop being citywide averages; the map stops approximating | Low — likely a spreadsheet that exists |
| 4 | *"Can TMD provide gridded radar rainfall, archive and live, via BMA endorsement?"* | The single largest expected accuracy gain | Medium — inter-agency |
| 5 | *"Does the Drainage Department hold canal network topology as GIS, with flow direction and gates?"* | Upstream features now, graph models later | Medium |
| 6 | *"Are pump and gate operation logs retrievable from SCADA?"* | The drainage system has an operator the model currently cannot see | Medium |
| 7 | *"RF.PYT.02 is missing its last day every year since 2022, and RF.BKY.02 logged 762 mm in 24 h in 2023 against its own 73 mm hourly maximum. Known issues?"* | Small, but shows we have actually read the data | Very low |
| 8 | *"Can NECTEC provide a historical export of Traffy Fondue flood reports?"* | Independent ground truth over the full archive period | Low |

---

## 8. Summary of status

| Source | Reachable | Permitted | Collected |
|---|---|---|---|
| Open-Meteo archived forecast | Yes | Yes — free, non-commercial | Yes |
| Open-Meteo ERA5 | Yes | Yes — free, non-commercial | Yes, as past rain only |
| Traffy Fondue | Yes | Public API, terms not explicitly stated | Yes, for evaluation |
| `pumps.bangkok.go.th` | Yes | **Unknown — ask first** | **No, on purpose** |
| ThaiWater standard | Yes | Public documentation | Read, not implemented |
| TMD radar (gridded) | No API found | Requires request | No |
