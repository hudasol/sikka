# Progress

Status of the build phases. Each phase is tagged when its gate holds.

| Phase | Scope | Status | Tag | Evidence |
| --- | --- | --- | --- | --- |
| P0 | Foundation: layout, tooling, CI, `sikka check`, import contracts, ADR 0001 | done | v0.1.0 | `sikka check` passes: ruff, ruff format, mypy strict, 2 import contracts kept, tests with coverage above 85 percent |
| P1 | L0 contract | done | v0.2.0 | `sikka docs build --check` reports 12 fresh artefacts; contract tests pass; `sikka contract diff v1 v1.1` reports one minor change |
| P2 | L1 synthetic world and fault catalogue | next | | |
| P3 | L2 ingestion and L3 conformance | planned | | |
| P4 | Walking skeleton: API, web shell, static snapshot | planned | | |
| P5 | L4 harmonisation and lineage | planned | | |
| P6 | Preregistration, then L5 analytics | planned | | |
| P7 | Evaluation E1 to E4 | planned | | |
| P8 | Full web app | planned | | |
| P9 | L6 tasking and E5 | planned | | |
| P10 | Hardening, review, documentation | planned | | |

## In progress

Nothing in progress.

## Next

P2: synthetic network, exposure, crashes, four producers, the fault catalogue F01 to F25 with ground truth sidecars, and committed sample feeds.

## Blockers

None.

## Resuming

Read this file and `docs/DECISIONS.md`, run `sikka check`, then continue with the first phase that is not marked done.
