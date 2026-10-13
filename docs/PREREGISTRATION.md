# Preregistration

Registered on 2026-10-13, before any evaluation run, before the analytics layer (L5) and the tasking layer (L6) were written. This file is committed on its own; the git history shows that it precedes every file in `results/`. Changes after this commit are added as dated amendments at the end; the original text stays.

## Scope and honesty statement

- Every experiment runs on the synthetic world in `sikka.synth`. No real crash, traffic or road data is used.
- The synthetic world, the fault catalogue, the rules, the adapters and the ranking method were all written by the same author. Agreement between method and world is therefore expected to be better than it would be on real data. Results say how the method behaves on this world, not how it would behave on real feeds.
- Before this registration, smoke runs were made on the development seed 1001: one E1 run at a 5 percent rate (every fault was detected with precision 1.0; recall for F03 was 0.96) and one E2 run (clean world: precision 1.0, recall 0.98, abstention 3 percent; every fault at 5 percent: precision 1.0, recall 0.66, abstention 10 percent). The E1 and E2 predictions below were written after seeing those smoke numbers and are therefore informed by them. Nothing in the method was changed after seeing them.
- No analytics or tasking result of any kind has been seen. E3, E4 and E5 predictions are made blind.
- Evaluation seeds are 2001 to 2020 (20 seeds). Seed 1001 is reserved for development and smoke tests and is never part of the evaluation. No method parameter is tuned on seeds 2001 to 2020.

## Reporting conventions

- One command, `sikka eval`, runs every experiment and writes `results/*.json`. Documents are rendered from those files, and a test fails if a number in `docs/EVALUATION.md` differs from its source file.
- Means over seeds are reported with a 95 percent Student t interval.
- A prediction given as a range is a **HIT** when the observed mean over seeds lies inside the range, otherwise a **MISS**. A prediction given as an inequality is a HIT when the inequality holds for the observed mean (or for the stated count of seeds). Every prediction is reported, hits and misses alike.

## Method fixed by this registration (analytics, L5)

These choices are fixed now so that the evaluation cannot shape them.

1. **Data.** Analytics read the harmonised dataset (L4): canonical crashes with their segment and local year, and the daily traffic estimate per segment from station counts. Observation window: the five local calendar years 2021 to 2025.
2. **Safety performance function (SPF).** Negative binomial (NB2) regression of the five year crash count per segment on log daily traffic, log length in kilometres, road class (indicator variables) and lane count, with log of the years in the window as offset. Fitted by maximum likelihood with `statsmodels` on segments that have exposure and are not abstained.
3. **Empirical Bayes (Hauer).** For segment i with predicted count P_i over the window and observed count O_i, w_i = 1 / (1 + P_i / k) with k = 1 / alpha (the fitted overdispersion), EB_i = w_i P_i + (1 - w_i) O_i. Potential for safety improvement PSI_i = (EB_i - P_i) / Y per year.
4. **Rank intervals.** 4,000 posterior draws. Each draw samples SPF coefficients from their estimated normal distribution, then each segment's long run count from the gamma posterior Gamma(k + O_i, rate (k + P_i) / P_i). Segments are ranked by drawn PSI (rank 1 is the largest). Reported per segment: median rank, 90 percent rank interval (5th to 95th percentile), probability of being in the top k (k = 12 by default).
5. **Quality propagation (EB+QP).** Segments are grouped by corridor owner. In each group the Chapman estimator on the two producers that both cover it (A and B, or C and B) gives the number of crashes including those missed by both, N = (n1 + 1)(n2 + 1) / (m + 1) - 1, with its usual variance. In each draw the observed counts of the group are multiplied by a factor drawn from the sampling distribution of N / U (U is the number reported by either producer). In each draw each unresolved duplicate pair on a segment is also counted once or twice with equal probability.
6. **Abstention.** A segment is not ranked when it has no exposure estimate (`no_exposure`), when its observation window is under 3 years (`short_window`), or when the mean monthly delivery coverage of the producers expected on its corridor is below 0.75 (`low_coverage`). Abstained segments are listed with the reason.
7. **Baselines.** Raw crash count over the window (ranks every segment, exposure or not), and crash rate per million vehicle kilometres (ranks segments with exposure).

## E1: fault detection

- **Question.** Do the conformance rules flag the records, series and files that carry each catalogued fault, and only those?
- **Hypothesis.** Each fault's expected rules detect it with high recall and high precision at every injection rate, because each rule targets a specific fault signature.
- **Design.** For each seed, each fault F01 to F25 and each rate (1, 5 and 20 percent): inject the fault alone into the clean world, validate the feeds it can touch with only its expected rules, and compare flagged units with the ground truth (rows for record faults, stations for F11, files for F23 to F25). A second, combined scenario injects all 25 faults at 5 percent at once and reports, per fault, recall and the share of flagged units that carry any injected fault ("precision against any fault").
- **Metrics.** Recall and precision per fault and rate, mean over seeds with 95 percent intervals.
- **Baseline.** The schema only check (pydantic model validation of every record against the contract) applied to the same records, as the obvious simpler competitor: recall of the schema check per fault at 5 percent.
- **Seeds.** 2001 to 2020.
- **Predictions.**
  - P1.1: in isolation, at least 22 of the 25 faults have mean recall of at least 0.95 at every rate.
  - P1.2: in isolation, every fault has mean precision of at least 0.95 at every rate where at least one unit is flagged.
  - P1.3: F03 (local time labelled as UTC) has mean recall between 0.85 and 0.99 at 5 percent, because crash records that no other producer reported cannot be compared.
  - P1.4: in the combined scenario, mean recall over the 25 faults is between 0.85 and 1.00.
  - P1.5: in the combined scenario, mean precision against any fault over the 25 faults is at least 0.95.
  - P1.6: the schema only baseline detects fewer than 13 of the 25 faults with recall of at least 0.5, because many faults (swapped axes, wrong units, stuck sensors, duplicates, offsets, gaps, partial periods) produce records that are each individually valid.

## E2: entity resolution

- **Question.** How well are crashes reported by more than one producer merged, and how often does the matcher abstain?
- **Hypothesis.** On the clean world the matcher is precise and finds nearly all duplicates; with faults it stays precise but loses recall and abstains more.
- **Design.** Harmonise all feeds of each world; predicted pairs are records of different producers in the same canonical crash; truth pairs share a true crash id. Scenarios: `clean`, and `faults_5pct` (all 25 faults at 5 percent).
- **Metrics.** Pairwise precision, recall and F1; abstention rate (unresolved share of candidate pairs); relative error of the canonical crash count against the number of distinct true crashes reported.
- **Baseline.** A naive rule matching any two records of different producers within 15 minutes and 150 metres (the tolerance named in the brief), without abstention.
- **Seeds.** 2001 to 2020.
- **Predictions.**
  - P2.1: clean F1 between 0.97 and 1.00.
  - P2.2: clean precision of at least 0.99.
  - P2.3: clean abstention rate between 0.01 and 0.06.
  - P2.4: faults_5pct recall between 0.55 and 0.80.
  - P2.5: faults_5pct precision of at least 0.98.
  - P2.6: faults_5pct abstention rate between 0.05 and 0.15.
  - P2.7: the naive baseline has lower clean precision than the matcher.

## E3: blackspot ranking

- **Question.** Do the ranked lists find the 12 planted blackspots, and are the rank intervals honest?
- **Hypothesis.** Empirical Bayes finds more planted blackspots than raw counts and than crash rates; its 90 percent rank intervals contain the true rank close to 90 percent of the time; quality propagation widens intervals and raises coverage.
- **Design.** Clean world per seed, harmonised, then ranked by four methods: raw count, rate, EB, EB+QP. Truth: the 12 segments with hazard multiplier above 1. True PSI per segment is the true long run rate minus the true SPF mean (from the hidden truth file); the true rank is taken among the segments a method ranked.
- **Metrics.** Top 12 recall of planted blackspots: over all 12 (`recall_all`) and over the planted blackspots that have exposure (`recall_rankable`). Coverage of the 90 percent rank intervals (EB and EB+QP). Mean width of the 90 percent rank interval.
- **Baselines.** Raw count and rate, as above.
- **Seeds.** 2001 to 2020.
- **Predictions.**
  - P3.1: EB `recall_rankable` between 0.45 and 0.80.
  - P3.2: EB `recall_rankable` is higher than rate `recall_rankable`.
  - P3.3: EB `recall_rankable` is higher than raw count `recall_rankable`.
  - P3.4: raw count `recall_all` is between 0.20 and 0.50.
  - P3.5: EB 90 percent rank interval coverage between 0.80 and 0.95.
  - P3.6: EB+QP coverage is at least EB coverage, and EB+QP mean interval width is larger than EB mean width.
  - P3.7: EB+QP `recall_rankable` is within 0.05 of EB `recall_rankable`.

## E4: robustness

- **Question.** How stable is the EB ranking when data quality drops?
- **Design.** For each seed, the EB ranking of the clean world is the reference. Degraded scenarios: drop producer A, drop B, drop C, drop D (their crash feeds are removed), and all faults at 5 and at 20 percent. Each degraded world is harmonised and ranked with EB.
- **Metrics.** Kendall tau between the reference and degraded PSI rankings over segments ranked in both; overlap of the two top 12 lists (share of shared segments).
- **Baseline.** The same metrics for the raw count ranking, as the simple competitor.
- **Seeds.** 2001 to 2020.
- **Predictions.**
  - P4.1: dropping D (fatal and serious crashes only, mostly duplicates of B) leaves Kendall tau of at least 0.90.
  - P4.2: dropping B gives the lowest Kendall tau of the four producer drops.
  - P4.3: Kendall tau at 5 percent faults is between 0.75 and 0.95.
  - P4.4: Kendall tau at 20 percent faults is lower than at 5 percent faults.
  - P4.5: top 12 overlap at 20 percent faults is between 0.40 and 0.80.

## E5: tasking

- **Question.** For the same flight budget, does value of information tasking reduce rank uncertainty more than random tasking and more than greedy tasking by crash count?
- **Design.** For each seed, start from the EB+QP ranking of the clean world. A survey of a segment is simulated as one additional independent observation of its true long run rate, equivalent to two more years of crash data drawn from the hidden truth. Three strategies choose segments under the same budget (the same number of missions with the default drone profile): value of information (p(1 - p) for top 12 membership, weighted by length and survey cost), random, and greedy by observed crash count. After the surveys the ranking and its intervals are recomputed.
- **Metric.** Relative reduction of the total top 12 uncertainty mass, the sum over segments of p(1 - p).
- **Baselines.** Random and greedy by crash count.
- **Seeds.** 2001 to 2020.
- **Predictions.**
  - P5.1: value of information reduces the uncertainty mass by more than random in at least 18 of 20 seeds.
  - P5.2: value of information reduces it by more than greedy by crash count in at least 15 of 20 seeds.
  - P5.3: the mean relative reduction with value of information is between 0.10 and 0.40.

## What would count against the method

- A MISS on P3.2 or P3.3 would mean Empirical Bayes adds nothing over simpler rankings on this world.
- Coverage below 0.80 (P3.5) would mean the intervals overstate certainty.
- A MISS on P5.1 would mean the tasking layer is no better than chance.

## Amendments

None yet.
