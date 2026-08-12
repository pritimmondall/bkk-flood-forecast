# GFS update — reply draft

---

Dear Ajarn,

Thank you for the GFS suggestion — we tested it properly and it is now part of
the system. Short version: **it does not predict Bangkok rainfall well, but it
still improves the flood warnings.** Details below.

**1. As a rainfall forecast for Bangkok, GFS is weak.**

We compared the GFS forecast for each district-hour against what the BMA rain
gauges actually recorded, over 1.38 million district-hours (2021–2025):

- correlation on wet hours: **0.014**
- hit rate on wet hours: **16%**

We report wet hours only, because 78% of hours are dry everywhere and an overall
agreement figure would mostly measure agreement about nothing happening.

This is what your note about resolution predicted. At roughly 13 km, a few grid
cells cover the whole city, while Thai convective rain cells are 2–5 km across.
GFS can see that the region is wet; it cannot say which district.

**2. Even so, it makes the flood model measurably better.**

We trained the onset model — the one that predicts flooding on roads that are
currently dry — with and without the GFS features, on three cross-validation
folds. At 15 cm depth, one hour ahead:

| | Onset recall | Precision | Floods caught before the water arrived |
|---|---|---|---|
| with GFS | **23.8%** | 13.6% | **64.4%** |
| without GFS | 20.8% | 19.6% | 55.2% |

Consistent in direction across all three folds. GFS accounts for about 5% of the
model's total split gain.

**3. It is a trade, and we think it is worth taking.**

Nine more floods caught per hundred, in exchange for six points of precision —
roughly one extra false alarm for every two extra catches. Since a missed flood
strands traffic and a false alarm sends a patrol to a dry road, we have kept GFS
in. But this is really BMA's judgement to make, and we would like to put the
trade to them in these terms rather than decide it ourselves.

**4. Two limitations we are not hiding.**

- The GFS archive starts **23 March 2021**, so our earliest cross-validation
  fold has no forecast data and is trained without it.
- GFS goes only into the onset model. Adding it to the general model made
  results worse — it helps where a forecast is needed and adds noise where the
  current sensor reading already answers the question.

**5. On downscaling.**

We have not attempted the 1 km downscaling you mentioned. Given how weak the raw
hour-to-hour signal is (correlation 0.014), we are not confident downscaling
would recover much — it would sharpen the spatial detail of a field that is not
tracking the observed rain in the first place. We would rather discuss this with
you before investing in it.

**6. What is actually limiting us.**

For context: our current models beat a simple rainfall-threshold rule by only
about one percentage point on the metric that matters. The largest single gap is
not the weather model — it is that we have **no coordinates for the canal water
level and flow sensors**, so all canal features are city-wide averages and our
1 m terrain analysis contributes nothing (every station in a district is given
the same elevation). One spreadsheet of station codes with latitude and longitude
would do more for accuracy than any modelling change we can make.

Happy to walk through any of this in more detail.

Best regards,
Satoru
