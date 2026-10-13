# ADR 0008: Empirical Bayes with posterior rank intervals

Status: accepted

## Context

Ranking road segments by raw crash counts favours long, busy segments and is dominated by chance on short or quiet ones (regression to the mean). Crash rates divide by exposure but are unstable when counts are small. A ranking used to choose where to look must say how sure it is.

## Decision

1. A safety performance function (negative binomial NB2, `statsmodels`) predicts the expected count of each segment from daily traffic, length, road class and lanes.
2. The Empirical Bayes estimate (Hauer) combines prediction and observation with weight w = 1 / (1 + P / k), where k is the inverse of the fitted overdispersion and P is the prediction over the whole window. The potential for safety improvement is (EB - P) per year.
3. Uncertainty is shown as rank intervals from 4,000 posterior draws: SPF coefficients from their estimated normal distribution, then each segment's long run count from its gamma posterior. Every segment carries a median rank, a 90 percent rank interval and the probability of being in the top 12.
4. Raw count and crash rate rankings are always computed and shown beside the EB ranking.

## Consequences

- Short or quiet segments with a few unlucky crashes are pulled towards their prediction; long busy segments are judged against what is expected of them.
- The ranking needs exposure, so segments without a station are not ranked (abstention `no_exposure`); raw counts still list them.
- The method assumes the SPF form is right. On this synthetic world the true model has the same functional form, which flatters the method; on real data a misspecified SPF would bias PSI.
