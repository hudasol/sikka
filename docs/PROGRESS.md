# Progress

Status of the build phases. Each phase is tagged when its gate holds.

| Phase | Scope | Status | Tag | Evidence |
| --- | --- | --- | --- | --- |
| P0 | Foundation: layout, tooling, CI, `sikka check`, import contracts, ADR 0001 | done | v0.1.0 | `sikka check` passes: ruff, ruff format, mypy strict, 2 import contracts kept, tests with coverage above 85 percent |
| P1 | L0 contract | done | v0.2.0 | `sikka docs build --check` reports 12 fresh artefacts; contract tests pass; `sikka contract diff v1 v1.1` reports one minor change |
| P2 | L1 synthetic world and fault catalogue | done | v0.3.0 | Byte identity tests for the same seed pass; every fault F01 to F25 is logged to `ground_truth/faults.json` and changes at least one feed; committed samples are fresh |
| P3 | L2 ingestion and L3 conformance | done | v0.4.0 | 39 rules in six families, each with a unit and a property based test; every fault F01 to F25 maps to at least one registered rule (test); `sikka eval --smoke` writes `build/eval-smoke/e1_fault_detection.json` |
| P4 | Walking skeleton: API, web shell, static snapshot | done | v0.5.0 | API tests for every endpoint and the problem+json contract pass; 75 web unit tests and 12 Playwright tests with axe pass on the static build; live mode checked in a browser with `sikka serve` (overview and sample validation) |
| P5 | L4 harmonisation and lineage | next | | |
| P6 | Preregistration, then L5 analytics | planned | | |
| P7 | Evaluation E1 to E4 | planned | | |
| P8 | Full web app | planned | | |
| P9 | L6 tasking and E5 | planned | | |
| P10 | Hardening, review, documentation | planned | | |

## In progress

Nothing in progress.

## Next

P5: producer adapters as mapping tables, the canonical model with lineage, entity resolution with match, non match and unresolved outcomes, and an E2 smoke run.

## Blockers

None.

## Resuming

Read this file and `docs/DECISIONS.md`, run `sikka check`, then continue with the first phase that is not marked done.
