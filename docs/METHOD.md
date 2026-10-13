# Method

This page describes how Sikka checks feeds, harmonises them, ranks road segments and plans survey missions. Every step runs on synthetic data in this repository. Parameters named here are configuration values in the code, not results; results are in [EVALUATION.md](EVALUATION.md), rendered from `results/*.json`.

## 1. Contract and conformance

- The data contract (v1.0.0, [CONTRACT.md](CONTRACT.md)) defines three feeds, a provenance header, units, time conventions and a list of prohibited personal fields.
- Feeds are streamed into an in memory DuckDB database as raw JSON text, then exposed as typed columns per contract field, so a number sent as text stays visible as a type error ([ADR 0004](adr/0004-duckdb-staging.md)).
- The rule registry ([RULES.md](RULES.md)) holds 39 rules in six families: structural (S), semantic (V), referential (R), cross feed (X), timeliness and completeness (T) and privacy (P). Each rule has an id, a severity, a description, a rationale, a fix hint and a check function.
- **Scores.** A record passes a family when no error or warning rule of that family flagged it, directly or through its station series. The share passing is reported per producer and family with a Wilson 95 percent interval. The overall index (share passing every family) is always shown beside the family scores. Informational findings (possible duplicates across producers) and file level findings are reported separately.
- **Privacy.** Records with prohibited fields or values that look like phone or identity numbers are quarantined: their values are never shown in reports, maps, lineage or logs.

## 2. Harmonisation

- One adapter per producer, written as mapping tables (identifier style, severity codes, field aliases, segment id scheme) plus small functions. Repairs are triggered by conformance findings, for example swapping latitude and longitude only when rule SK-V004 fired, and each repair is recorded with its value before and after.
- Crashes are assigned to the nearest segment centre line within 250 metres, or to the producer's segment reference when it lies within 500 metres.
- **Entity resolution.** Candidate pairs come from different producers within 30 minutes and 1 kilometre. A log likelihood ratio combines time difference (match model normal with 6 minutes standard deviation), distance (Rayleigh with 60 metres), severity agreement and vehicle count agreement. Pairs scoring at least 4 are matched, below 0 not matched, and in between left unresolved and kept separate ([ADR 0007](adr/0007-entity-resolution-and-lineage.md)).
- **Exposure.** Daily traffic per segment is the mean flow per minute over the valid intervals of its counting station, times 1,440. Intervals that are negative, stuck or unreadable are excluded and counted in the lineage.

## 3. Ranking

- **Safety performance function.** A negative binomial (NB2) regression, fitted by maximum likelihood with `statsmodels`, of the five year crash count on log daily traffic, log length, road class and lanes, with log years as offset.
- **Empirical Bayes (Hauer).** For predicted count P and observed count O over the window, w = 1 / (1 + P / k) with k the inverse overdispersion; EB = w P + (1 - w) O; potential for safety improvement PSI = (EB - P) per year ([ADR 0008](adr/0008-empirical-bayes.md)).
- **Rank intervals.** 4,000 posterior draws: SPF coefficients from their estimated normal distribution, then each segment's long run count from Gamma(k + O, scale P / (k + P)). Each segment gets a median rank, a 90 percent rank interval and the probability of being in the top 12.
- **Quality propagation.** Per corridor owner, Chapman's capture recapture estimator on the owner and the police producer gives the expected number of crashes missed by both; in each draw counts are scaled by a factor drawn from its sampling distribution, and each unresolved duplicate pair is counted once or twice with equal probability ([ADR 0009](adr/0009-capture-recapture.md)). The published ranking uses this (EB+QP); plain EB is shown beside it.
- **Abstention.** A segment is not ranked without a traffic estimate (`no_exposure`), with an observation window under 3 years (`short_window`), or when the producers expected on its corridor delivered data in under 75 percent of the months (`low_coverage`). Abstained segments are listed with the reason.
- **Baselines.** Raw crash count and crash rate per million vehicle kilometres are computed for every ranking and shown next to it.
- **Sensitivity.** `rank_stability` compares two rankings with Kendall tau and the overlap of their top 12 lists.

## 4. Tasking

- The value of information of a segment is p (1 - p), with p its probability of being in the top 12; the planner works with value per kilometre surveyed.
- Missions follow a corridor over adjacent segments and fly straight back to the take off point. The default drone profile is 25 minutes endurance, 12 m/s, 20 percent battery reserve and 60 metres altitude; missions that exceed the usable time are refused and listed.
- Exports: GeoJSON, KML and a QGroundControl `.plan` file per mission, checked by a structural validator.
- Every plan states that it is for simulation and review only; real flights need the operator's own safety case and the regulator's approval.

## 5. Assumptions and where they break

| Assumption | Where it could break on real data |
| --- | --- |
| Crash counts follow the NB2 SPF form | Unmodelled factors (curvature, junctions, enforcement) bias PSI |
| Traffic is constant over the window | Growth or seasonality changes exposure year by year |
| Producers detect crashes independently | Severe crashes are reported by everyone, so completeness is overstated |
| Duplicates differ by minutes and tens of metres | Larger reporting delays or rounded locations lower recall |
| Local time is UTC+04:00 without daylight saving | Holds for Asia/Dubai; feeds from elsewhere need their own zone |

See [LIMITATIONS.md](LIMITATIONS.md) for the full list.
