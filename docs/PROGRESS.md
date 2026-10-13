# Progress

Status of the build phases. Each phase is tagged when its gate holds.

| Phase | Scope | Status | Tag | Evidence |
| --- | --- | --- | --- | --- |
| P0 | Foundation: layout, tooling, CI, `sikka check`, import contracts, ADR 0001 | done | v0.1.0 | `sikka check` passes: ruff, ruff format, mypy strict, 2 import contracts kept, tests with coverage above 85 percent |
| P1 | L0 contract | done | v0.2.0 | `sikka docs build --check` reports 12 fresh artefacts; contract tests pass; `sikka contract diff v1 v1.1` reports one minor change |
| P2 | L1 synthetic world and fault catalogue | done | v0.3.0 | Byte identity tests for the same seed pass; every fault F01 to F25 is logged to `ground_truth/faults.json` and changes at least one feed; committed samples are fresh |
| P3 | L2 ingestion and L3 conformance | done | v0.4.0 | 39 rules in six families, each with a unit and a property based test; every fault F01 to F25 maps to at least one registered rule (test); `sikka eval --smoke` writes `build/eval-smoke/e1_fault_detection.json` |
| P4 | Walking skeleton: API, web shell, static snapshot | done | v0.5.0 | API tests for every endpoint and the problem+json contract pass; 75 web unit tests and 12 Playwright tests with axe pass on the static build; live mode checked in a browser with `sikka serve` (overview and sample validation) |
| P5 | L4 harmonisation and lineage | done | v0.6.0 | Harmonisation tests pass; `GET /v1/lineage/{id}` serves every canonical crash, exposure estimate and segment; an E2 smoke run on seed 1001 scores cluster level precision, recall and abstention against the ground truth (numbers are reported in P7, not here) |
| P6 | Preregistration, then L5 analytics | done | v0.7.0 | `docs/PREREGISTRATION.md` committed before any analytics code; EB matches two hand worked examples; abstention reasons tested case by case; ranking of 240 segments with 4,000 draws passes the 10 second performance test |
| P7 | Evaluation E1 to E4 | done | v0.8.0 | `sikka eval` on seeds 2001 to 2020 wrote `results/e1` to `e4`; `docs/EVALUATION.md` is generated from them and a test fails if it is stale; 23 predictions hit and 2 missed (P3.2, P3.6), all reported |
| P8 | Full web app | done | v0.9.0 | Nine screens in English and Arabic, light and dark; 83 Vitest tests; 12 Playwright tests with axe (WCAG 2.2 AA tags) pass on the static build with no foreign requests and no console errors; screenshots reviewed in all four combinations |
| P9 | L6 tasking and E5 | done | v0.10.0 | Every planned mission's `.plan` passes the structural validator (API test); the validator rejects every single structural defect (property test); E5 ran on seeds 2001 to 2020 and its three predictions missed, as reported in EVALUATION |
| P10 | Hardening, review, documentation | done | v1.0.0 | Independent review run; every finding fixed and recorded (D32, D33), none rejected; all five experiments rerun with the final code and the result files were identical byte for byte (PREREGISTRATION, Amendment 2); performance budgets measured in `results/performance.json` and all met; a clean clone on Windows ran the README commands and `sikka all --no-evaluation` with exit code 0; 86 Vitest tests and 40 Playwright tests pass, with axe on every screen in English and Arabic, light and dark |

## In progress

Nothing in progress.

## Next

All phases are done. Possible next steps are listed in `docs/PILOT.md`.

## Blockers

None.

## Resuming

Read this file and `docs/DECISIONS.md`, run `sikka check`, then continue with the first phase that is not marked done.
