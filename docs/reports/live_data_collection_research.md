# How can we collect the live data? — a research report

*Written 10 August 2026. Every source below was called or fetched during this
session unless the row says otherwise. Where something could not be verified, it
says so in the same sentence.*

This report supersedes the source survey in
`docs/reports/live_forecasting_feasibility.md` §2–2a. That report's **measured
model numbers still stand**. What changes is the list of places the data can
come from.

---

## 1. The headline

The previous survey concluded that BMA publishes nothing live except pump
levels, and that rainfall therefore has no public source. **That conclusion looks
wrong.**

BMA's Department of Drainage and Sewerage runs a public telemetry website at
`weather.bangkok.go.th` that publishes, right now, as numbers:

- 24-hour accumulated **rainfall**
- canal **water level**, split into inside-gate and outside-gate readings
- canal **flow rate** in m³/s

Those are three of the four networks the model trains on, in the same shape as
the training CSVs. And a search engine has indexed a REST endpoint on that same
host:

```
http://weather.bangkok.go.th/dds_webservices/api/rain/lastdata
```

Separately, **BMA operates two weather radars of its own** — Nong Chok and Nong
Khaem — and publishes the imagery publicly.

If the rain endpoint returns what its name suggests, the project's single
binding constraint has a public source that nobody has asked for yet.

**This must be verified before anyone acts on it.** See §6.

---

## 2. Finding 1 — BMA publishes its own telemetry (unverified schema)

### What was confirmed

`weather.bangkok.go.th` was fetched successfully during this session. The page is
titled as the Department of Drainage and Sewerage telemetry system
(ระบบตรวจวัดข้อมูลโทรมาตร) and renders live tables:

| Table on the page | Thai header | Matches our training column |
|---|---|---|
| 24-hour rainfall | ปริมาณฝนสะสม 24 ชั่วโมง | `rf24hr` |
| Water level, inside | ระดับน้ำด้านใน (ม.รทก.) | `wl_in` |
| Water level, outside | ระดับน้ำด้านนอก (ม.รทก.) | `wl_out01` |
| Flow rate | อัตราการไหล (ลบ.ม./วินาที) | `flow` |

The `ม.รทก.` unit is **metres above mean sea level** — which incidentally
answers the open datum question in `data_requests.md` Priority 2. We have been
assuming MSL; this says MSL.

15 water-level stations and 10 flow stations were visible on the front page,
named by district: Sai Mai, Lak Si, Min Buri, Wang Thonglang, Bang Kapi,
Watthana, Lat Krabang, Khlong Toei, Bang Sue, Ratchathewi, Thawi Watthana (×2),
Bang Khae, Bang Rak, Bang Na.

### What was NOT confirmed

The front page is a summary view. The full network (131 rain, 300 water, 30 flow)
is presumably behind the API. **The `dds_webservices` endpoint could not be
read.** Two attempts, two different failure modes:

- **WebFetch** → `ROBOTS_DISALLOWED` (the host's robots.txt could not be parsed,
  so the fetcher refused).
- **Your own Chrome**, navigated to the URL directly → Chrome error page. The
  site root failed too, over both http and https. So this is not about that one
  path; the host appears unreachable from your network.

The site *is* reachable from a US egress (that is how the front page above was
read). The most likely explanation is that the Thai government host is slow,
intermittent, or filtered from outside Thailand and reachable from some routes
and not others.

**So: the endpoint exists and is publicly indexed. Its response body is
unverified.** Nothing in this report assumes what it contains.

---

## 3. Finding 2 — BMA owns two weather radars

`data_requests.md` lists radar rainfall as Priority 1 and frames the ask as *"TMD
registration; the data is reachable from outside Thailand."*

That framing points at the wrong agency. Confirmed this session from two
independent pages:

| Radar | Operator | Page | Image |
|---|---|---|---|
| Nong Chok | **BMA** (สถานีเรดาร์ในความดูแลของกทม) | `weather.bangkok.go.th/radar/RadarNongchok.aspx` | `weather.bangkok.go.th/Images/Radar/radar.gif` |
| Nong Khaem | **BMA** | `weather.bangkok.go.th/radar/RadarNongkam.aspx` | — |
| Composite loop | BMA, mirrored by TMD | `weather.tmd.go.th/bma_ncLoop.php` | `pic_bmancLoop.gif` |

The radar GIF carries a cache-buster stamped `260811_0321`, i.e. it was being
regenerated within minutes of this research.

**Why this matters more than it sounds.** The measured bottleneck is that
rainfall enters the model as a *district average* — roughly a 5 km box — while
Bangkok floods from cells 2–5 km across. Radar at ~1 km is the fix. And the
agency that owns the radar is the agency we are already talking to. This is not
an inter-agency negotiation; it is BMA being asked for BMA's own instrument.

**Caveat, and it is a real one.** What is published is **pictures, not data**.
A coloured GIF can be reverse-mapped to reflectivity bands, but that is lossy,
undocumented, brittle against any palette change, and not a defensible input to a
warning system. The ask should be for the underlying volume or gridded product,
not the image. The image is only evidence that the product exists.

---

## 4. Finding 3 — ThaiWater confirmed live, and it carries a Chao Phraya gauge

Re-called this session, no authentication:

```
https://api-v3.thaiwater.net/api/v1/thaiwater30/provinces/waterlevel?province_code=10
```

**11 Bangkok stations, timestamped 2026-08-10 16:00**, hourly. Fields per record
include `waterlevel_msl` and `_previous` (level and its change), `flow_rate`,
`discharge`, `storage_percent`, `situation_level`, `diff_wl_bank`, bank and
ground levels, and **real `tele_station_lat` / `_long`**.

One station is **Chao Phraya 15** at 13.7003 N, 100.4928 E. That is a measured
river level on the Chao Phraya.

This partly closes `data_requests.md` Priority 6. We currently reconstruct tidal
*phase* from lunar periods (`tide_m2_sin`, `tide_spring_neap`) and have no
amplitude. A measured Chao Phraya level gives the actual state of the river the
drainage gates discharge into — which is the thing the tide features are a proxy
for. It is free and available today.

---

## 5. Everything else that was checked, and why it does not solve rainfall

| Candidate | Status | Verdict |
|---|---|---|
| **GSMaP / JAXA Global Rainfall Watch** | Free registration; global 60N–60S; **0.1° (~11 km)**, hourly, updated every 30 min (`GSMaP_NOW`); CSV/binary over FTP | **Too coarse.** 11 km is *coarser than our existing district averages* (~5 km). It would add satellite-observed rain where we currently have gauge-observed rain, at worse resolution. Not a fix. |
| **GPM IMERG Early Run** | 0.1°, 30-min, ~4 h latency | Same resolution problem, plus 4 h latency against a 1 h horizon. Dead. |
| **RainViewer API** | Free tier is **past radar tiles as PNG images**, max zoom 7, single colour scheme, "personal use" licence | Not usable. Images not values, coarse zoom, and the licence forbids the use we would put it to. |
| **TMD API** (`data.tmd.go.th`) | Previously tested: 3-hourly, 122–125 stations *nationally* → 2–3 in Bangkok, registration required, no radar API offered | Unchanged. Too sparse, too slow. |
| **Netatmo public weather map** | `Getpublicdata` returns crowdsourced personal weather stations in a bounding box, rain modules included, OAuth required | **Unverified — worth 30 minutes.** The question is purely how many Bangkok stations have a rain module. Netatmo density is high in Europe and unknown in Thailand. If there are 50+, this is a genuine dense rain network for free. If there are 5, it is nothing. |
| **`pumps.bangkok.go.th`** | Live, 148 stations, ~5 min, no login — previously confirmed | Still gated on project rule 8: **ask permission first**. No collector should be written before that email is answered. |
| **Traffy Fondue** | Live citizen reports, public API, already implemented in `external.py` | A lagging confirmation, not a predictor. Useful as an independent check on labels (Priority 7), not as a model input. |
| **Open-Meteo GFS** | Live, already implemented | 13 km grid. Measured at 3% event POD on its own. Keep as a forecast-rain input, never as the observation. |
| **Thai Hydrographic Dept tide gauges** | Searched; no public API found | Superseded anyway by the ThaiWater Chao Phraya station above. |

---

## 6. Verify before building — three checks, in order

Each of these is small, and each one changes what gets built.

**Check 1 — read the BMA rain endpoint.** Open in a browser, from a network that
can reach the host:

```
http://weather.bangkok.go.th/dds_webservices/api/rain/lastdata
```

Then try the obvious siblings by swapping the resource: `/api/waterlevel/lastdata`,
`/api/flow/lastdata`, and the API root `/dds_webservices/api/`.

What to record: how many stations, whether station codes match our `RF.*` /
`WL.*` / `FW.*` scheme, which rainfall accumulations are present (`rf5min`
through `rf24hr` or only the 24 h total), the timestamp, and **whether
coordinates are included**. Coordinates would be worth as much as the rainfall —
they are `data_requests.md` Priority 2, and their absence is why terrain
contributes 0% of model gain.

If the host is unreachable from your network too, this is a question for BMA
rather than a networking problem to solve.

**Check 2 — count Netatmo rain modules over Bangkok.** One OAuth app, one
`Getpublicdata` call over the Bangkok bounding box, count the stations reporting
rain. Half an hour, and it either opens a dense free rain network or closes the
idea permanently.

**Check 3 — ask BMA one email with three items.** Now much better targeted than
the version in `data_requests.md`:

1. Documentation and a stable access agreement for the `dds_webservices` API —
   *"we found it, we would rather use it with your blessing than scrape it."*
2. The **gridded output of your Nong Chok and Nong Khaem radars**, not the GIFs.
   Live feed, and the archive if one exists.
3. Permission for `pumps.bangkok.go.th`.

Item 2 is the one that matters. The archive question is the important half: with
a radar archive we can *measure* the gain the same way sets A–E were measured.
Without it, radar can only be added live and its value argued rather than shown.

---

## 7. If the checks come back well — what to build

Unchanged in shape from `dual_mode_design.md`, but the source list changes.

```
src/bkkflood/collectors/
    bma_dds.py       # rain + water level + flow, if §6 check 1 passes
    thaiwater.py     # 11 canal stations, hourly, real coordinates
    openmeteo.py     # reuse external.py, do not rewrite
    netatmo.py       # only if §6 check 2 finds density
    bma_pumps.py     # only after permission
```

Each exposes `fetch() -> DataFrame` and writes **append-only** Parquet to
`data/live/<source>/<date>.parquet`. Append-only is not a style preference: these
sources publish current values only, there is no downloadable past, and this
archive is the historical record being created. It must never be rewritten.

Three rules carried forward, all of them earned:

- **Do not impute a missing source.** LightGBM handles NaN natively, so the same
  booster serves both modes. An invented rain reading is worse than a NaN because
  the model cannot tell it was invented.
- **Cold start must be declared.** `fl_max_24h` and `rain_rf24hr_mean` look back
  24 hours. Until a collector has run a full day, live mode reports
  `"cold_start": true` and emits no alerts.
- **Every response carries its own measured performance.** Replay says 53%. Live
  says whatever live measures. If the dashboard looks the same in both modes,
  the design has failed.

### Start here regardless of the checks

`thaiwater.py`, scheduled hourly. It is verified working today, it needs nobody's
permission, and the history clock starts the day it starts. Every day it does not
run is real observations at real coordinates gone permanently.

---

## 8. What is still not obtainable

For honesty, and so nobody re-runs this search in three months:

- **Live road flood depth** (`FL.*`, the label itself). No public source. Set D
  measured that we can reach 85% of full performance without it, so this is the
  least urgent of the gaps.
- **Full-network live rainfall**, unless check 1 passes.
- **Pump and gate operating status**, until permission is granted. This remains
  a genuine blind spot: a flood a pump prevented is recorded in training as no
  flood.
- **Canal network topology.** No public source found. Still a GIS export request
  to BMA.

---

## 9. Summary table

| Source | Live? | Verified this session | Covers | Blocker |
|---|---|---|---|---|
| BMA `dds_webservices` API | Indexed, presumed | **No — unreachable** | rain, water level, flow | reachability, then permission |
| BMA radar (Nong Chok, Nong Khaem) | Yes, as images | Yes | rainfall at ~1 km | images not data; ask BMA |
| ThaiWater canal levels | Yes | **Yes — 11 stations, 16:00 today** | canal level, flow, Chao Phraya, coordinates | none |
| Open-Meteo GFS | Yes | Already in use | forecast rain, 13 km | resolution |
| `pumps.bangkok.go.th` | Yes | Previously | 148 pump levels | permission (rule 8) |
| Traffy Fondue | Yes | Already in use | citizen reports | lagging, not predictive |
| Netatmo | Yes | **No — density unknown** | crowdsourced rain | unknown coverage |
| GSMaP / IMERG | Yes | Documented | satellite rain, 11 km | too coarse |
| TMD API | Yes | Previously | 2–3 Bangkok stations | too sparse |
| RainViewer | Yes | Documented | radar images | licence, resolution |

---

## 10. The one thing to take away

The previous conclusion — *"no public source for rainfall, live mode caps at
4.9%"* — rested on a survey that did not include BMA's own telemetry website or
BMA's own radars. Both exist and both are public.

That does **not** mean live mode works now. The 4.9% figure is measured and
stands until something replaces the rainfall input. But it does mean the ask to
BMA is far smaller than we thought: not *"please build us a feed"* but *"please
let us use the feed you are already publishing, and give us the radar grid behind
the picture you are already showing."*
