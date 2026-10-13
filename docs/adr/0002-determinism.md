# ADR 0002: Determinism strategy

Status: accepted

## Context

Every figure Sikka publishes must be reproducible from the code in this repository. The synthetic world, fault injection, posterior sampling and evaluation all draw random numbers. Reviewers must be able to regenerate any file and obtain the same bytes.

## Decision

1. Every stochastic function takes an explicit integer `seed`. There is no global random state.
2. `sikka.core.rng(seed, *stream)` builds a NumPy `PCG64` generator from a `SeedSequence` of the seed and SHA 256 derived keys for a named stream path (for example `rng(seed, "crashes", "producer_b")`). Adding a new stream never shifts the numbers of an existing one, and the key does not depend on Python's salted `hash`.
3. JSON outputs are written with `stable_json_dumps` (sorted keys, fixed separators, UTF 8) after `round_floats` (six decimal places), so floating point noise in the last bits does not change bytes.
4. Line endings are forced to LF by `.gitattributes`, so committed artefacts are byte identical on Windows, macOS and Linux.
5. Timestamps written into generated files come from the synthetic clock, never from the wall clock.

## Consequences

- Tests can assert byte identity for repeated runs with the same seed.
- Results depend on the NumPy bit generator; a NumPy upgrade that changes `PCG64` or a distribution sampler would change outputs. The lock file pins versions, and the staleness tests would catch such a change.
