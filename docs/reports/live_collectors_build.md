# Live collectors — build and verification

**Date:** 2026-08-10
**Date updated:** 2026-08-11 — the pumps API was read in the browser and this
report revised accordingly.
**Code:** `src/bkkflood/collectors/`, `notebooks/10_live_collect.ipynb`,
`tests/test_collectors.py` (47 tests), `scripts/`

---

## What this is, in one paragraph

Six collectors across five public services are polled on a schedule and every response is written to disk,
untouched and append-only, under `data/live/`. This does **not** make the flood
model work live — measured, the public sources reach 4.9% event POD against
replay's 53%. It is worth running because none of these services publish a
downloadable past, so the history starts the day collection starts, and because
the day BMA opens its rain feed one registry entry takes the same pipeline from
~5% to roughly 45% with nothing rebuilt.

---

## Sources: what was verified, and what is still a guess

| Source | Status | What it gives | Scheduled |
|---|---|---|---|
| `thaiwater` | **Verified live** — 11 Bangkok stations, response read 2026-08-10 | Canal level MSL + previous (so a signed rise), flow rate, storage %, bank clearance, **real lat/long**, a Chao Phraya river gauge | yes, hourly |
| `traffy` | **Verified live** — GeoJSON read, all 33 properties confirmed | Citizen flood reports with point coordinates. **Evaluation only** | yes, hourly |
| `openmeteo` | Already in use via `external.py` | Forecast rain 1/3/6 h on a 13 km GFS grid | yes, hourly |
| `pumps` | Schema read 2026-08-11 in a browser; **HTTP clients get 403** | `/api/water-levels?limit=2000` — pump-station level in cm and %, at 5-minute resolution across ~148 stations, `PH.<DIST>.NN` codes covering 27 of our 33 flood districts | **no — blocked, ask BMA** |
| `pumps_stations` | Schema read 2026-08-11 in a browser; **HTTP clients get 403** | `/api/stations/{id}` — **real lat/long**, tank depth, pump count, per-pump on/off status | **no — blocked, ask BMA** |
| `bma_dds` | **Never read.** Unreachable from every route tried | Would be the 131 rain gauges — the whole ballgame | **no** — discovery `probe()` only |

### The bug this build caught

The Traffy parser was looking for a property called **`comment`**. Reading the
live response showed the citizen's text is in **`description`**; `comment` does
not exist. Nothing would have crashed. The collector would have written
healthy-looking rows every hour in which `is_flood` was `False` for every English
report — and the conclusion drawn months later would have been "Traffy says
Bangkok barely floods", which is the opposite of true.

Two changes came out of that:

1. Every collector now keeps **all** original fields as `raw_*` columns alongside
   the mapped ones, so a wrong guess costs a rewrite of one function rather than
   a season of data.
2. `is_flood` also matches `น้ำขัง`, `น้ำรอระบาย` and `ท่วมขัง` — how people
   describe standing water when they do not use the flood category tag. Missing
   those would bias the sensor-coverage check in the direction that flatters our
   own network.

### The Bangkok filter was wrong too

The first version asked *"did any row match Bangkok?"* and skipped filtering when
none did. A response containing only upcountry reports therefore passed through
whole. It now asks whether the `province` field is **populated**, and falls back
to a bounding box when the field is genuinely absent. A Phrae flood entering the
coverage check would make our sensor network look worse than it is, invisibly.

---

## The pumps API, read on 2026-08-11

The site is a React Router app with a plain JSON API underneath. Reading it in
the browser network tab turned `pumps` from a guess into the best-documented
source in the package.

**`GET /api/water-levels?limit=N`** — newest-first, paginated
(`data`, `count`, `total`, `page`, `pageCount`). Fields: `id`, `stationId`,
`district`, `nameTH`, `nameEN`, `code`, `waterLevelPercent`, `waterLevelCM`,
`timestamp`.

Three things fell out of it:

- Readings arrive every ~5 minutes across ~148 stations, so an hour is ~1,776
  rows. **`limit=2000` in one request captures a full hour at five-minute
  resolution while polling only hourly.** We get 5-minute data for one HTTP
  request per hour.
- **Only `limit` is honoured.** `pageSize`, `perPage`, `take` and `size` are all
  accepted and silently ignored, returning the 20-row default. Renaming that
  parameter would cost 99% of every poll and raise nothing. There is a test.
- `total` was **12,370,842**, with the deepest pages reaching about two weeks
  back. It is a rolling window, not an archive — which is an argument for
  collecting sooner, not a reason to relax.

**`GET /api/stations/{id}`**, ids 1..~148 — `code`, `district`, `type`,
`isActive`, `tankDepth`, `noOfPumps`, `waterLevelCM`, `lastSync`, `status`, a
`pumps[]` array of `{id, status, power, operatingHrs}`, and **real `latitude`
and `longitude`**, all confirmed inside the Bangkok bounding box.

`/api/stations` (bulk) 404s, so the registry costs one request per station. That
is why it is a separate collector on a **daily** cadence — 148 requests once a
day is courteous, 148 every hour is not. The cost is that pump running status is
captured daily rather than at 5-minute resolution, and a bulk endpoint is now a
concrete, small thing to ask BMA for.

### It 403s from Python, and we are not going to work around that

The first real run confirmed the schema is right and the door is shut:

```
GET /api/water-levels?limit=2000  ->  403 Forbidden
GET /api/stations/{id}            ->  403 Forbidden
```

The host is behind Cloudflare. The browser got through because it passed a
managed challenge; `requests` does not. There is no `robots.txt` (404), so there
is no stated crawl policy — but a challenge is BMA's infrastructure saying
"browsers only", and the right answer to that is to ask, not to impersonate
Chrome. Forging browser fingerprints or replaying a `cf_clearance` cookie would
be circumventing an access control on a government system, and it would break
the next time the token expired regardless.

So both pump collectors are **off the schedule**, and `needs_permission` is now
`True` for each. A test asserts they are absent from `DEFAULT_SOURCES`, so the
pause is recorded as deliberate rather than looking like an oversight later.

The upside: this is now the *easiest* thing in the BMA request to grant. Not
"open your rain gauge network" — just "allowlist us, or issue a key, or tell us
what User-Agent you want." Everything downstream is already written and green;
the day access lands, two names go back into `DEFAULT_SOURCES` and nothing else
changes.

### Cadence gating

`collect_all()` now honours each spec's `cadence_minutes` via `is_due()`, so one
hourly job carries sources on different clocks and a skipped source is reported
as `skipped`, not as a success or a failure. The threshold is 0.8 × cadence
because launchd's hourly timer drifts — a strict `>= 60 min` test against an
hourly job would skip roughly every other run, which is data loss disguised as
politeness.

### Personal data is dropped, not stored

`/api/stations/{id}` also returns `contactPersonFirstName`,
`contactPersonLastName` and `phone` — named BMA staff and their phone numbers.
They have no scientific value here and there is no reason to hold them. They are
stripped recursively before anything is written, **including from the raw
payload**. That is the single exception to this package's keep-everything rule,
and it is deliberate. Two tests and the end-to-end smoke test assert that neither
the parquet nor the gzipped raw contains them.

---

## Why `pumps` was added

It is the only one of the five aimed at the **labels** rather than the features.

Every label in this project is "a BMA road sensor measured ≥ 15 cm". A flood that
a pump station prevented is therefore recorded as *no flood* — identical, in the
data, to a street that was never at risk. The model is being taught that heavy
rain over a well-pumped district is harmless. It is not; someone ran the pumps.
Pump activity is a confounder that cannot be corrected for from the road sensors
alone, and `PH.<DIST>.NN` codes join to 27 of our 33 flood districts.

It is explicitly **not** added to `features.py`. Sets A–E never measured pump
level, so nobody knows what it is worth; it accumulates until an ablation
including it is actually run.

---

## Design decisions worth remembering

**Append-only, with the raw payload kept.** `data/live/` is not a cache of
something re-downloadable — it *is* the record, and it exists only because the
collector ran. Every poll writes a new file; nothing is read-modify-written. The
gzipped raw JSON costs almost nothing and makes a parser bug found in three
months recoverable.

**One dead source never stops the others.** `run_collector` turns any exception
into a failed result row. An Open-Meteo outage costing an hour of ThaiWater would
be an unforced error, because that hour cannot be re-fetched.

**`BKKFLOOD_REPO` pins the write location.** launchd hands a job a working
directory nobody controls. History written to the wrong tree is indistinguishable
from working — until you go looking for six months of data and it is not there.

**Cold start is enforced, not documented.** `fl_max_24h` and `rain_rf24hr_mean`
look back 24 hours. `coverage()` reports `cold_start = True` until 24 hours of
continuous collection exist, and live mode must refuse to emit alerts while it
does. A confident "no flood" from a system with no history is the worst possible
output, because it looks exactly like a correct answer.

---

## Tests

47 offline tests, no network. The parsers are separated from `fetch()` for
exactly this reason — they parse undocumented government APIs and are the part
most likely to be quietly wrong.

Covered: nested-envelope discovery, coordinate ranges and lon/lat ordering, the
signed rise calculation, offline sensors staying NaN rather than zero, the Traffy
`description` regression, the upcountry filter, malformed pump codes returning NA
rather than a guessed district, unknown schemas costing a column and not the
poll, append-only writes colliding inside the same second, a crash becoming a
failed result, the cold-start threshold, and the status file recording failures
rather than looking like a run that never happened.

An end-to-end smoke test with the network faked out was also run: fetch → parse →
gzipped raw → parquet → `_status.json` → `coverage_report()` → `read_history()` →
the coordinates CSV. Two consecutive runs produce two files, not one.

---

## Follow-up: `bkkflood/__init__.py` is now lazy

Running the tests under a Python that is not the project venv failed at
collection — `No module named 'duckdb'` — before a single test ran, because
`import bkkflood` eagerly imported every submodule including `rawio`.

That was worth fixing properly rather than working around, because of where this
is going: `scripts/run_live_collect.sh` is meant to run hourly on a small
always-on box, and eager imports would have meant installing LightGBM and
rasterio on a Raspberry Pi to poll four public APIs.

`__init__.py` now resolves names on first use (PEP 562). All 74 previously
exported names were checked by AST against their modules — none missing — and
the collector tests now pass in an environment with **no duckdb, no LightGBM and
no rasterio** installed. Reaching for a heavy name still raises, but only when
you reach for it, and the error names the real dependency. Unknown names raise
`AttributeError` as before.

The one behaviour change: `bkkflood.terrain` used to be `None` when rasterio was
missing, and now raises `ImportError`. Nothing in the repo checked for that
`None` (grepped).

---

## First real run — 2026-08-11 05:19 UTC

Run by the user on their machine. Three of five sources collecting:

| source | rows | note |
|---|---|---|
| `thaiwater` | 11 | exactly the 11 Bangkok canal stations expected, reading stamped 12:00 |
| `openmeteo` | 4,800 | 50 district centroids x 96 hours (2 past + 2 forecast days) |
| `traffy` | 1,000 | asked for 2,000 — either a server-side cap or the Bangkok filter halving a national page. **Worth one check**, because if it is a cap then `limit` is not doing what the code assumes |
| `pumps` | — | 403 |
| `pumps_stations` | — | 403 |

`thaiwater` returning exactly 11 is the strongest single signal that the parser
is correct: it is the count read from the live response yesterday, arrived at
through a completely different code path.

---

## What the first collection exposed in ThaiWater — three bugs

The parquet and the saved raw payload from that 05:19 run were read back and
checked. All three of these are now fixed in `thaiwater.py` and pinned by tests
that run against `tests/fixtures/thaiwater_20260811T051921Z.json.gz` — the actual
response, copied out of `data/live/_raw/`.

**1. `waterlevel_datetime` is Asia/Bangkok, with no timezone marker.** Proved
arithmetically: the newest reading in a poll made at 05:19 UTC was stamped 12:00.
Read as UTC that is 6.7 hours in the future; read as UTC+7 it is 19 minutes old.

This was the dangerous one. Everything else in the project is UTC. A naive join
would have placed every canal reading seven hours away from the rainfall that
caused it — no error, no warning, just a destroyed correlation and the conclusion
"canal levels do not predict floods", which is the opposite of what Phase 5
measured. `ts` is now UTC; `ts_local` sits beside it; `age_minutes` records how
stale each reading was at fetch time.

**2. Two of eleven stations return `station_name = null`**, so
`groupby("station_name")` dropped them silently — pandas discards NaN keys by
default. That is exactly how the first coordinates export wrote **9 stations out
of 11**. Grouping is now by `station_id`, with a `station_label` that always has
a value (name → river → subdistrict → id).

**3. Station 11688984 reports `min_bank = 0.00`**, so `diff_wl_bank` comes back
0.00 and the API's own text reads `เท่าระดับตลิ่ง` — *water at bank level*. Every
other station's `min_bank` is between 0.62 and 4.46 m. It is a missing reference
value formatted as a maximum-severity reading, and any alert rule keyed on bank
clearance would have fired on it permanently. It is flagged (`bank_ref_valid`),
and `diff_wl_bank_clean` is NaN there, while `diff_wl_bank` keeps whatever the
API said — Phase 0's lesson about validity checks that quietly edit data.

Incidentally, freshness varies more than expected: 8 of 11 stations were 19
minutes old, one 79 minutes, one 199, one 279. `age_minutes` makes that visible
instead of implicit.

### The raw payloads paid for themselves within a day

Those three fixes landed *after* the first hour had already been written, so the
parquet on disk was missing all the new columns and every downstream cell would
have raised `KeyError` on a perfectly recoverable file.

`history(source)` re-parses the saved raw payloads and returns the rebuilt frame
when the parser has moved on. Verified against the real 05:19 file: 11 rows, all
five new columns recovered, `age_minutes` reconstructed relative to the original
fetch time rather than to now. **Nothing on disk is rewritten** — conforming old
data to today's parser would destroy the evidence of what the API actually sent.

### The first version of that repair was wrong, and the notebook caught it

`history()` originally decided whether to repair by comparing **column sets**.
That is sufficient for a parser that gains a field, and useless for a parser that
changes what a field *means*.

After the second collection the stored history held one file from the old parser
(`ts` in Bangkok local) and one from the new (`ts` in UTC). Every expected column
was present, so the column check said "fine" and returned a frame with two
timezones inside a single column. What caught it was the notebook's own
`assert (tw.ts <= tw._fetched_at_utc).all()` — *"a reading is in the future —
timezone lost"* — which stopped execution at section 5 rather than letting the
coordinates export and everything after it run on mixed data.

The fix is to key on the **version stamp** that every row already carries.
`COLLECTOR_VERSION` is now `1.1.0`, bumped because the meaning of `ts` changed,
and `history()` reparses whenever any stored row was written by a different
version. Columns remain a secondary trigger for a field added without a bump.

Two lessons worth keeping: **bump the version when a value's meaning changes, not
just when a column appears** — and the reason this was a ten-minute problem
rather than a silent one is that the notebook asserts an invariant instead of
printing a number for a human to notice.

---

## What could not be done from here, and why

The build sandbox has no route to any of these hosts, and the desktop bridge has
no network either. So no live poll was executed — the ThaiWater and Traffy
schemas were confirmed by fetching the endpoints through the web tool and reading
the field names back. **The first real collection run has to happen on your
machine**, and section 2 of the notebook (`dry_run=True`) exists to make that a
30-second check rather than an act of faith.

`weather.bangkok.go.th` remains unread: `robots.txt` could not be fetched
(connection timeout), so the endpoint stays a guess. That is the highest-value
open question in the project and it is a question for BMA, not a bug to fix in
code.

---

## Next

1. Run the notebook once by hand, confirm files land, then load the launchd job.
2. Ask BMA for a **bulk station endpoint** on the pumps API. Without one, pump
   on/off status is captured daily instead of every 5 minutes, and that status is
   the confounder the whole `pumps` collector exists for.
3. Send BMA the four asks, in value order: live rain gauges (5% → 43%), live
   canal level and flow (43% → 85%), station coordinates (one spreadsheet,
   unlocks terrain's current 0%), then documented access to `dds_webservices`,
   the pump portal, and the gridded radar output plus its archive.
4. Thirty minutes on Netatmo density over Bangkok. 50+ stations with rain modules
   would be a free dense network; 5 closes the idea permanently.

Related: `docs/reports/live_forecasting_feasibility.md`,
`docs/reports/live_data_collection_research.md`, `docs/dual_mode_design.md`.
