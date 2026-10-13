# ADR 0005: Static and live modes from one code path

Status: accepted

## Context

A reviewer should be able to open the demo without installing Python, and the demo must be hostable for free. At the same time, uploading a broken feed needs a running service.

## Decision

1. The web app has two modes chosen at build time. `live` calls the FastAPI service started with `sikka serve`. `static` reads a precomputed snapshot under `web/public/snapshot`, built by `sikka snapshot`.
2. The snapshot is produced by calling the same service functions as the live API (`sikka.api.service.Service`), one JSON file per GET response, plus a precomputed report for every sample feed and its HTML rendering.
3. In static mode the upload area is replaced by a clear message, and choosing a sample shows its precomputed report.
4. The app uses hash based routing so that any static host serves every screen without rewrite rules.

## Consequences

- The static build can be deployed on a free static host such as Vercel with no backend.
- Static and live responses cannot drift apart silently: a slow test rebuilds the snapshot and compares it byte for byte with the committed files.
- Uploads are only possible in live mode, which also keeps untrusted files away from any shared host.
