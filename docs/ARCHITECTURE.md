# Architecture

Sikka is organised in nine layers plus a cross cutting core. Dependencies point downward only: a layer may import the layers below it and never the layers above. Two import contracts in `pyproject.toml`, checked by `import-linter` inside `sikka check`, enforce this, and a second contract forbids the product layers (L2 to L7) from importing the synthetic world, so the hidden ground truth can only reach the evaluation harness.

All data in this repository is synthetic.

## Layers

```mermaid
flowchart TB
  L8["L8 Presentation<br/>web/ React, TypeScript"]
  L7["L7 Service<br/>sikka.api FastAPI, static snapshot"]
  EV["Evaluation<br/>sikka.evaluation E1 to E5"]
  L6["L6 Tasking<br/>sikka.tasking value of information, missions"]
  L5["L5 Analytics<br/>sikka.analytics SPF, Empirical Bayes, rank intervals"]
  L4["L4 Harmonisation<br/>sikka.harmonise adapters, entity resolution, lineage"]
  L3["L3 Conformance<br/>sikka.conformance rules, engine, reports, scores"]
  L2["L2 Ingestion<br/>sikka.ingest parsers, DuckDB staging, profiling"]
  L1["L1 Synthetic world<br/>sikka.synth network, crashes, producers, faults"]
  L0["L0 Contract<br/>sikka.contract models, schemas, versions"]
  X["Core<br/>sikka.core config, ids, time, errors, metrics, geo, determinism"]
  CLI["CLI<br/>sikka.cli"]
  CLI --> EV --> L7 --> L6 --> L5 --> L4 --> L3 --> L2 --> L1 --> L0 --> X
  L8 -. HTTP or snapshot files .-> L7
```

| Layer | Package | Public interface (examples) |
| --- | --- | --- |
| Core | `sikka.core` | `rng`, `stable_json_dumps`, `wilson_interval`, `parse_utc`, `Paths`, error classes |
| L0 | `sikka.contract` | `RoadSegment`, `CrashRecord`, `TrafficCount`, `version_schemas`, `diff_versions` |
| L1 | `sikka.synth` | `build_world`, `inject`, `CATALOGUE`, `write_world` |
| L2 | `sikka.ingest` | `open_text`, `stage`, `profile_feed` |
| L3 | `sikka.conformance` | `run_validation`, `build_report`, `REGISTRY`, `render_rules_md` |
| L4 | `sikka.harmonise` | `harmonise`, `HarmonisedDataset`, `resolve`, `Lineage` |
| L5 | `sikka.analytics` | `rank_dataset`, `fit_spf`, `empirical_bayes`, `rank_stability` |
| L6 | `sikka.tasking` | `plan_missions`, `compare_strategies`, `to_plan`, `validate_plan` |
| L7 | `sikka.api` | `create_app`, `Service`, `snapshot_files` |
| Evaluation | `sikka.evaluation` | `run_experiments`, `PREDICTIONS`, `render_evaluation` |

The evaluation harness sits above the service layer because it needs the synthetic world and its truth, which the product layers may not import. The command line interface is the single entry point (`sikka`).

## Data flow

```mermaid
flowchart LR
  F1[(Road segment<br/>registry feeds)] --> I
  F2[(Crash record<br/>feeds, four producers)] --> I
  F3[(Traffic station<br/>count feeds)] --> I
  I["L2 parse and stage<br/>raw JSON in DuckDB"] --> C["L3 rules<br/>39 checks, six families"]
  C --> R["Reports<br/>JSON and HTML,<br/>Wilson scores"]
  C --> H["L4 adapters<br/>repairs driven by findings"]
  H --> S["Snapping to segments"]
  S --> E["Entity resolution<br/>match, non match, unresolved"]
  E --> CC[("Canonical crashes<br/>with lineage")]
  H --> EX[("Exposure per segment<br/>with lineage")]
  CC --> A["L5 SPF and Empirical Bayes"]
  EX --> A
  A --> Q["Quality propagation<br/>Chapman, unresolved pairs"]
  Q --> RK[("Ranking with rank intervals<br/>and abstentions")]
  RK --> T["L6 value of information"]
  T --> M["Missions<br/>GeoJSON, KML, .plan"]
```

## Deployment

```mermaid
flowchart LR
  subgraph Live["Live mode (local machine)"]
    U1[Browser] -->|HTTP| W1["Vite dev server<br/>or built web app"]
    W1 -->|fetch /v1/...| API["sikka serve<br/>FastAPI under uvicorn"]
    API --> D1[(data/samples)]
  end
  subgraph Static["Static mode (free static host)"]
    U2[Browser] --> W2["Built web app<br/>web/dist"]
    W2 -->|fetch snapshot/v1/*.json| SN[(Precomputed snapshot<br/>web/public/snapshot)]
  end
  B["sikka snapshot"] -->|same service functions| SN
```

In static mode uploads are disabled; every other screen works from the snapshot. No request leaves the product in either mode: fonts are self hosted, maps use no tiles, and there is no analytics.

## Sequence: validating an upload

```mermaid
sequenceDiagram
  actor User
  participant Web as Web app (L8)
  participant API as FastAPI (L7)
  participant Engine as Rule engine (L3)
  participant Stage as DuckDB staging (L2)
  User->>Web: drop a feed file
  Web->>API: POST /v1/validate (multipart)
  API->>API: check content type and size limit
  API->>Engine: run_validation(upload, clean samples as context)
  Engine->>Stage: stream records in batches
  Stage-->>Engine: typed tables
  Engine->>Engine: build registry, run every applicable rule
  Engine-->>API: findings, profiles, scores
  API->>API: report id = hash of inputs and contract version
  API-->>Web: 201 {report_id}
  Web->>API: GET /v1/reports/{report_id}
  API-->>Web: JSON report (quarantined values withheld)
  Web-->>User: results by family, examples, map, downloads
```

## Design rules

- **Contract first.** L0 is the single source of truth; JSON Schema, the field dictionary, the TypeScript types and the API models are generated from it, and a test fails when a generated file is stale.
- **Determinism.** Every random step takes an explicit seed and a named stream (ADR 0002); the same inputs give the same bytes.
- **Pure core, thin edges.** Rules and analytics are functions over DuckDB tables or data frames; file and network I/O happen in L2 and L7.
- **Explainability.** Every finding names its rule, row and field; every canonical record carries its lineage; every rank carries its interval and a structured explanation.
