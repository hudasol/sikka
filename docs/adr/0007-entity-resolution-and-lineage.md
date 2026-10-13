# ADR 0007: Entity resolution with abstention, and lineage as data

Status: accepted

## Context

The same crash is often reported by several producers with small differences in time, place and attributes. Counting every report would inflate crash counts; merging too eagerly would hide real crashes. Reviewers also need to see how any number was produced from the source records.

## Decision

1. Every canonical record carries a `Lineage` object: its source records (producer, file, row, record id), the adapter and its version, every transformation with the value before and after, the conformance findings that touched it, its status (accepted, repaired, rejected) and the records it was merged from. Values of personal fields are never kept: the transformation records that a field was dropped, not what it held.
2. Adapters are mapping tables per producer (`sikka.harmonise.tables`) plus small functions. Record level repairs are triggered by conformance findings (for example a swap of latitude and longitude only when `SK-V004` fired), so behaviour is traceable to a rule.
3. Duplicate crashes across producers are resolved with a Fellegi and Sunter style log likelihood ratio over time difference, distance, severity and vehicles, with stated match and non match models. Pairs scoring at least 4 are matched, below 0 are not, and pairs in between are left unresolved and kept separate. Matching is one to one per producer pair.
4. Unresolved pairs are counted per segment and passed to the analytics layer, which widens intervals by their share.

## Consequences

- Every canonical crash, exposure estimate and segment can be traced back through `GET /v1/lineage/{canonical_id}`.
- The parameters of the matcher are assumptions written down before evaluation (E2); they are not fitted to the ground truth.
- Abstention lowers recall when evidence is weak; E2 reports the abstention rate next to precision and recall.
