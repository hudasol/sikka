# ADR 0009: Capture recapture (Chapman) for producer undercount

Status: accepted

## Context

No producer sees every crash. When two producers cover the same corridors, the overlap between their reports carries information about how many crashes both missed. Ignoring this makes rankings look more certain than they are, and it penalises corridors whose producers are less complete.

## Decision

1. Segments are grouped by corridor owner. In each group the Chapman estimator is applied to the owner and the police producer: N = (n1 + 1)(n2 + 1) / (m + 1) - 1, with its standard variance.
2. In each posterior draw of the quality propagated ranking (EB+QP), the observed counts of the group are multiplied by a factor drawn from the sampling distribution of N / U, where U is the number of crashes seen by either producer. Each unresolved duplicate pair is counted once or twice with equal probability.
3. The estimates, their intervals and the implied completeness are published with the ranking.

## Consequences

- Intervals widen where data quality is uncertain, and corridors with lower completeness are corrected upwards.
- Chapman assumes independent detection with equal catchability. Severe crashes are more likely to be reported by everyone, which biases the total downwards; matching errors in harmonisation bias it in either direction. The published completeness is therefore an optimistic bound, and this is stated in METHOD and LIMITATIONS.
