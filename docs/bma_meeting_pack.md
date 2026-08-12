# BMA Meeting Pack

*Answers evaluator point 11. A briefing, not a sales document.*

**Meeting goal, in one sentence:** show BMA a working flood forecasting system,
be honest about what it can and cannot do, and leave with two datasets and one
decision.

---

## The three asks

Everything else in this document supports these.

1. **Radar rainfall access** (TMD). The single largest improvement available.
2. **Station coordinates and metadata.** Probably a spreadsheet that already
   exists.
3. **A decision on live alerting.** Not "yes" — a decision about *what would have
   to be true* before yes, and who owns it.

If the meeting achieves only the first two, it was worth having.

---

## Opening — 2 minutes

> We have built a flood forecasting system for Bangkok using BMA's own sensor
> data from 2019 to 2025. It predicts road flooding at sensor sites one, three
> and six hours ahead, shows it on a live map, and produces standard emergency
> alert messages.
>
> It works. It is also clearly limited, and we would rather walk you through the
> limits ourselves than have you find them later. Two datasets would remove most
> of them.

---

## The demonstration — 10 minutes

Run in replay mode. No internet dependency, nothing to go wrong live.

**1. The map, at a quiet moment.** Establish what normal looks like. Note that
districts with no sensor are grey, not green — unmeasured is not the same as safe.

**2. Wind the clock to 2 November 2025, 23:15.** A real storm. The system raises
three Warnings, eight Advisories and fifteen Watches. Open a Warning: current
depth, forecast worst case, and the plain-language reason — *"18 mm of rain in
the past hour; 43% of canal gauges are rising."*

**3. Show the CAP message.** Explain in one sentence why it matters: it is
machine-readable, so it can go straight to SMS gateways, sirens and broadcast
systems with nobody retyping it. Point out `status = Test` and say why.

**4. Show a miss.** Deliberately. Pick a flood the system did not catch and
explain which kind it is — signal present and missed, or no rain recorded
anywhere. The second kind is a data request, not a modelling failure.

*Showing a miss on purpose is the most valuable thirty seconds of the meeting. It
is what makes everything else credible.*

**5. Hotspots and trends.** Move from "today" to "every year". This is the view
that speaks to drainage investment rather than to the duty roster.

---

## What the system does — one slide

| | |
|---|---|
| **Predicts** | Road flooding at ~107 BMA flood sensors |
| **How far ahead** | 1, 3 and 6 hours |
| **From** | Rainfall, canal water level, canal flow, recent flood depth |
| **Alert levels** | Watch (possible) · Advisory (≥15 cm likely) · Warning (≥30 cm likely) |
| **Outputs** | Live map, monitoring dashboards, CAP 1.2 alert messages |
| **Trained on** | 2019–2025, ~17 million rows |
| **Validated by** | Rolling-origin cross-validation across four independent test years |

---

## What a flood is, here — and why it matters

> Water at or above a threshold for at least two consecutive 5-minute readings.
> 5 cm nuisance · **15 cm advisory** · 30 cm severe.

Worth spending a minute on, because it is the foundation of every number that
follows.

The obvious definition — any depth above zero — is useless. In 2021 one station
logged 21,754 non-zero readings averaging 0.3 cm. That is a sensor breathing.
Build on it and you get a model that brilliantly predicts sensor noise.

---

## Performance, stated honestly

**Do not lead with the headline number.** Lead with the decomposition, because
somebody will ask and it is far better coming from you.

> At 15 cm, one hour ahead, the system catches about 55% of flood readings.
>
> But that number is misleading, and here is why. If a road is *already* flooded,
> predicting it will still be flooded in an hour is trivial — you just repeat the
> current reading. That is monitoring, not forecasting.
>
> Split the two apart:
>
> - Roads already flooded: near 100%. A one-line rule achieves the same.
> - Roads currently dry — genuine forecasts: **9%**.
>
> So we built a second model that only looks at dry sites. It raises genuine
> onset detection from 9% to **63%** one hour ahead.
>
> The trade-off is that only about 1 in 100 of its notices leads to flooding.
> That is still forty times better than chance, but it is not good enough to
> close a road on. So those notices raise a *Watch* — check this — and never a
> Warning.

**Anticipated question: "so how often are you wrong?"**

> At one hour we miss roughly 40% of flood onsets, and most watches do not lead
> to flooding. At six hours the model is close to climatology — it is largely
> saying "this place floods often". We publish these numbers on the dashboard
> itself, because a forecasting tool that hides its error rate earns trust it has
> not deserved and loses all of it on the first miss.

---

## Why it is limited, in one causal chain

This framing makes the asks self-evident rather than requiring a pitch.

> Bangkok floods from small, intense storm cells — two to five kilometres across.
>
> Our rainfall data is a **district average**. A cell dumping 40 mm on one
> sub-district becomes 8 mm once averaged across the district.
>
> The model's onset detection draws about **76% of its signal from rainfall**.
>
> So we are degrading the most important input to the most valuable part of the
> system, and we can measure that we are doing it.
>
> Radar rainfall would fix it directly.

The same shape works for coordinates:

> Rain station codes share a district prefix with flood station codes, so we can
> match rainfall to a place. Water and flow codes do not — they are canal names.
> `WL.STN.01` is a canal, not Sathon.
>
> So canal water level and flow enter the model as **citywide averages**. We can
> tell the network as a whole is under stress. We cannot tell which canal is
> about to fail next to which road.
>
> A coordinate list fixes it. It is almost certainly already in an asset register.

---

## The CAP decision

Frame this as a governance question, not a technical one.

> The system generates standard CAP emergency alert messages. Every one currently
> carries `status = Test`, which means downstream systems will not treat it as a
> real public warning.
>
> That is deliberate. A CAP message marked `Actual` gets routed to the public
> automatically, and an experimental model must not be able to do that by
> accident.
>
> We are not asking you to switch it on today. We are asking: what would need to
> be true first, and who owns that decision?

Suggested preconditions, if they ask:

1. A live sensor feed (without it, live mode is much weaker than the demo).
2. An agreed error budget — the miss rate stated and accepted **in writing, in
   advance**.
3. A named accountable owner.
4. A human-in-the-loop review step for the first operational season.
5. A defined cancellation and correction procedure.

---

## Likely questions

**"Can it predict flooding where there is no sensor?"**
> No. It only knows about places with a sensor, and so does our evaluation —
> flooding elsewhere is invisible to both. That is a coverage question rather than
> a model question, and expanding the network would expand what we can forecast.

**"Why is six hours so much worse than one hour?"**
> Because at six hours nothing in our data tells the model about a storm that has
> not arrived yet. Every rainfall input is rain that has already fallen. Weather
> forecast rainfall helps measurably — about three times more predictive than past
> rain at that horizon — and radar would help more.

**"How is this different from what we have now?"**
> Current practice is monitoring: it tells you where water is. This adds a
> forecast, an uncertainty range rather than a single number, and machine-readable
> alerts that can be routed automatically.

**"What if it misses a major flood?"**
> It will. We would rather agree in advance what an acceptable miss rate is than
> discover the disagreement afterwards. That is why we publish the error rate on
> the dashboard and why onset watches can never escalate themselves to a warning.

**"How much would radar rainfall actually help?"**
> We cannot promise a number without testing it. What we can say is that rainfall
> carries about 76% of the onset signal and we are currently averaging it away, so
> the direction is not in doubt. We would measure the gain and report it, including
> if it is smaller than hoped.

---

## Closing

> Three things would take this from a working prototype to something you could
> rely on: radar rainfall, station coordinates, and a live sensor feed.
>
> The first two are permissions and a spreadsheet. The third is an engineering
> project, and we would like to talk about what it would involve.

---

## Leave-behind

| Document | For |
|---|---|
| `docs/data_inventory.md` | What we hold and its condition |
| `docs/data_requests.md` | The asks, with justification and effort estimates |
| `docs/model_report.md` | Full evaluation for anyone technical |
| `docs/technical_roadmap.md` | Where this goes next |
| `docs/sample_cap_alert.xml` | A real CAP message, for the IT team |
