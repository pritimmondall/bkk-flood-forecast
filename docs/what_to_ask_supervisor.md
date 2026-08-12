# If we get a live API, will the model work? — and what to say to Ajarn

## Part 1 — The answer: yes, with three honest conditions

**The model itself needs no retraining and no changes.** It is a saved LightGBM
model with a fixed contract: 50 numbers in, one probability out. Feed it those
50 numbers computed from live readings instead of from the archive and it
predicts exactly as it does today. Nothing about it knows or cares whether the
data arrived five minutes ago or five years ago.

Those 50 features break down like this:

| Where it comes from | Features | Have it live today? |
|---|---|---|
| BMA rain gauges (131 stations, 5-min) | **13** | No |
| BMA road flood sensors — each road's own recent depth | **12** | No |
| BMA canal water level and flow | **9** | No |
| GFS rainfall forecast | 3 | **Yes** — public |
| Terrain from the 1 m elevation model | 5 | **Yes** — static, computed once |
| Calendar and tide phase | 8 | **Yes** — computed from the clock |

**34 of the 50 come from BMA. The other 16 we already have.**

### The three conditions

**1. Someone has to build the live path — a few days, not research.**
Today `serving.py` reads the historical feature table. It needs a sibling that
computes the same 50 features from live readings instead. The *definitions* are
already written and tested in `features.py`, and the contract is documented in
`docs/reports/feature_contract.md`. This is plumbing, and the risk is low
precisely because the feature definitions do not change — same code path,
different source.

**2. It cannot answer for the first 24 hours.**
Several features look back a full day — `rain_rf24hr_mean`, `fl_max_24h`. Until
24 hours of live readings have accumulated, those inputs are incomplete and the
model must refuse to answer rather than guess. This is already enforced in the
collectors as a cold-start rule. Worth stating up front so nobody thinks it is
broken on day one.

**3. What we get depends on which feeds arrive.** All measured:

| Live feeds available | Floods caught per 100 |
|---|---|
| Rain + canal + road sensors *(everything)* | **53** |
| Rain + canal, **no road sensors** | **45** |
| Rain gauges only | ~43 |
| Canal only, no rain | 5 |
| Nothing — public data as today | 5 |

**Read the second row carefully.** Without the road flood sensors at all we still
reach 45 — about 85% of full performance. If BMA finds the road sensors harder to
share, rain and canal alone are nearly the whole prize. That is a useful thing to
know before negotiating.

And read the last two rows together: **canal water level without rainfall is
worth almost nothing.** Rain is the input that matters. Everything else
multiplies it.

---

## Part 2 — What to say to Ajarn

He is from Bangkok, so his real value here is **the introduction**, not the data.
Ask for the meeting, not for the files.

### The short version — if you have two minutes

> "Ajarn, the model works. On BMA's seven-year archive it catches 53 out of every
> 100 flood events in a year it has never seen.
>
> But right now it can only replay history, because we have no live data. If we
> ran it on what is publicly available today it would catch 5 in 100 instead of
> 53. The gap is not the model — it is that BMA's rain gauges are not available
> to us as a live feed.
>
> We do not need new data. We need a live version of the same three networks BMA
> already gave us seven years of history from: the rain gauges, the canal level
> and flow sensors, and the road flood sensors. With those, the system runs live
> and predicts one hour ahead.
>
> Could you help us reach the right person at the Department of Drainage and
> Sewerage? A short meeting where we show them the dashboard would be worth more
> than an email from us."

### If he asks "what exactly do you need?"

Four things, and be specific — vague asks are easy to defer:

1. **Live rain gauge readings** — the same 131 stations, 5-minute intervals.
   *The single most valuable item: 5 in 100 becomes about 43.*
2. **Live canal water level and flow.** *43 becomes about 85.*
3. **Live road flood sensor depths** — the 107 stations. *Useful, but the least
   critical: without them we still reach 45.*
4. **Station coordinates** — one spreadsheet, latitude and longitude, ideally
   with the water-level datum. *Costs BMA nothing and unlocks terrain analysis
   that currently contributes exactly 0%.*

Plus one small thing that is easy to say yes to and worth mentioning first
because it builds momentum: **a read-only account on the pump portal**
(`pumps.bangkok.go.th`). The map is already public in a browser, but automated
clients get 403. **The site has a LOGIN button** — so there is an authenticated
tier already, and BMA can simply create an account. That is a smaller internal
decision than allowlisting an IP: no firewall change, no security review of an
unknown address, and revocable in one click. Ask for the account; an API key or
allowlist is the fallback.

### One thing to report to them, not ask for

`weather.bangkok.go.th` — the Drainage Department's own telemetry site, the one
that publishes rainfall, canal level and flow as numbers — **could not be reached
from a browser in Bangkok on 11 August 2026.** `ERR_CONNECTION_RESET`. Not a
permission error; the connection is actively refused.

Do not present this as a complaint. Present it as information they may not have:

> "We also noticed `weather.bangkok.go.th` is not reachable from outside — the
> connection is reset, even from here in Bangkok. Is that site still running, or
> has it moved to something internal? If there is a current equivalent, that is
> the one we would want to talk about."

Two reasons this is worth raising. It may genuinely be news to them — a
public-facing service quietly down is the kind of thing nobody notices from
inside the network. And it changes what you are asking for: not "please document
this endpoint" but "please point us at whatever replaced it."

### If he asks "can they trust us with it?"

Say yes and mean it, then offer the conditions before they ask:

> "We will work under whatever conditions the department prefers — a fixed IP
> address, rate limits, a signed data agreement, or read-only access to a subset.
> We are polling once an hour, not continuously. And we would rather have their
> permission than find a way around them: there is a public BMA pump portal we
> could have scraped and deliberately did not."

That last point is true and it is worth saying. It is evidence of how we intend
to behave with everything else.

### If he asks "why should BMA bother?"

> "Because the sensors are already installed and already recording. The data is
> being collected whether or not anyone forecasts with it. We are asking to plug
> into something that already exists — and the seven years they gave us is what
> made the model possible in the first place."

### What NOT to promise

Be careful here — over-promising now is how the project loses credibility later.

- **Do not say "real-time flood prediction for Bangkok."** Say *one hour ahead,
  district level, about half of flood events caught.*
- **Do not promise 3-hour or 6-hour forecasts.** Those models are not built yet.
- **Do not imply street-level accuracy.** When a district floods only about a
  third of its sensors register it. District level is the honest resolution.
- **Do not hide the false alarms.** About 84% of alerts do not become floods. Say
  it before they find it — a system whose limits you volunteer is one people
  trust with the rest.

### The one sentence to end on

> "Everything is built and tested. The only thing between us and a live system is
> access to data BMA already collects."

---

## Part 3 — Have this ready before the meeting

- The dashboard running on the 13 November 2025 flood — `docs/runbook.md`
- The GFS panel, if the supervisor's earlier question comes up —
  `docs/gfs_demo_script.md`
- The written request, English and Thai — `docs/bma_data_request_email_2026-08.md`
- The honest status of the project — `docs/project_status_2026-08-11.md`
- For BMA's engineer, if they ask what format we need —
  `docs/reports/feature_contract.md`

Every number in this document traces to a file in `docs/reports/`. If Ajarn or
BMA asks "where does 53 come from", the answer is `phase4_findings.md`, and you
can open it in front of them.
