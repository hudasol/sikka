# ADR 0004: Stage feeds in DuckDB as raw JSON, check them in SQL

Status: accepted

## Context

Feeds can be large (the performance budget is one million crash rows in under 60 seconds on a laptop), arrive as NDJSON, CSV or GeoJSON, and are often wrong in ways a typed loader would hide: a number sent as text, an epoch number in a timestamp field, a renamed column. The rules must see the raw value and its JSON type.

## Decision

1. Parsers stream each file and yield one JSON text per record. CSV cells are typed from the contract only when they parse cleanly with ASCII digits; anything else stays a string.
2. Records are inserted into an in memory DuckDB table in batches of 100,000 rows, as `(_row, _raw)`.
3. A typed table is then derived in SQL with, per contract field, the text value, its JSON type, a numeric value and a parsed timestamp. Invalid JSON lines are kept aside with their row numbers.
4. Rules are functions over this typed table, mostly SQL. Distances use a local equirectangular projection and a 1 km grid index of segment pieces.

## Consequences

- Memory use is bounded by the batch size during staging; DuckDB handles the rest.
- Type errors remain visible as data, so they can be reported per rule and per row.
- GeoJSON is parsed as one document, which is fine for registries but not for very large point files; this is listed in `docs/KNOWN_ISSUES.md`.
- DuckDB is an embedded library with no server and no network access, which keeps the deployment free and offline.
