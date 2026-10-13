# Limitations

Sikka is a proposal seed prepared by a student. It runs on synthetic data only and has no endorsement from any entity. The points below say what its results do not show.

## Data

1. **Synthetic only.** No real crash, traffic or road record is used. Every number in this repository describes the synthetic world.
2. **One author.** The synthetic world, the fault catalogue, the rules, the adapters, the ranking method and the evaluation were written by the same author. They agree with each other better than any of them would agree with real feeds.
3. **Invented scale.** The network size and the number of crashes were chosen to be plausible in order of magnitude ([CONTEXT.md](CONTEXT.md)); they do not replicate any real figure.
4. **Simple exposure.** True daily traffic is constant over five years and is estimated from one week of hourly counts at about 60 percent of segments.

## Conformance

5. **Known faults only.** Detection rates in E1 cover the 25 catalogued faults. Defects that were not anticipated are not measured.
6. **Profile rule.** `SK-V013` cannot see a clock offset shared by half or more of the stations ([KNOWN_ISSUES.md](KNOWN_ISSUES.md)).
7. **No semantic truth.** Rules check consistency and plausibility. A wrong but plausible value (for example a crash placed on the neighbouring segment) passes.

## Harmonisation

8. **Assumed matching parameters.** The entity resolution models are assumptions written down before evaluation, not fitted values.
9. **Legacy codes are lossy.** The legacy severity code 2 mixes serious and minor injuries and is mapped to minor injury.

## Ranking

10. **Model form.** The synthetic crash process has the same functional form as the safety performance function, which flatters Empirical Bayes.
11. **Capture recapture.** Chapman's estimator assumes independent detection with equal catchability. Real reporting is correlated, so completeness would be overstated.
12. **Quality propagation does not widen intervals as intended.** In E3 the quality propagated intervals were no wider than plain Empirical Bayes intervals (K05 in [KNOWN_ISSUES.md](KNOWN_ISSUES.md)).
13. **Empirical Bayes did not beat crash rates here.** In E3, Empirical Bayes found planted blackspots with exposure no more often than a ranking by crash rate (prediction P3.2 missed). It ranks by excess crashes, which favours busy segments over quiet ones with the same relative hazard.
14. **Abstention reduces coverage.** Segments without a counting station are not ranked; a planted blackspot there cannot be found by Empirical Bayes even when raw counts would list it.
15. **Screening, not diagnosis.** A high rank says where to look, not what is wrong or what to do.

## Tasking

16. **Small benefit from value of information.** In E5, value of information tasking reduced the top 12 uncertainty more than random and greedy tasking on average, but only slightly and not in every seed; all three preregistered predictions missed.
17. **Simulated surveys.** E5 models a survey as two extra years of crash data drawn from the hidden truth. A real survey yields other information (road condition, conflicts, signage) that this model does not capture.
18. **No flight claim.** Mission plans are for simulation and review only. Real flights need the operator's own safety case and the regulator's approval; no plan here has been flown.

## Interface

19. **Arabic text.** The Arabic interface and field descriptions are a machine drafted first version that needs review by a native speaker.
20. **English rule text in the Arabic interface.** Rule and fault titles are shown in Arabic, but rule descriptions, rationales, fix hints, fault descriptions, finding details and lineage notes come from the server in English only. In the Arabic interface they are marked as English text written left to right, so screen readers and the layout treat them correctly, but they are not translated.
