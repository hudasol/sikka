# Security

Sikka is a proposal seed that runs on synthetic data. The live API is meant for a local machine (`sikka serve` binds to 127.0.0.1 by default); the public demo is a static build with no backend. This page records the threat model for the API and the upload path, the controls in place and the dependency audit.

## Threat model (STRIDE)

| Threat | Where | Control in Sikka | Residual risk |
| --- | --- | --- | --- |
| **Spoofing** | Anyone who can reach the API can call it | No accounts and no stored personal data; the API binds to 127.0.0.1 by default; CORS allows only the local web app origins | Exposing the API on a network would need authentication, which is out of scope |
| **Tampering** | Uploaded feed content | Uploads are parsed as data only (JSON, CSV, GeoJSON); nothing is executed, imported or evaluated; parsing never calls `eval` or pickle; SQL is built from contract field names, never from upload content | A malformed file can only produce findings or a 4xx error |
| **Tampering** | Report store | Report ids are content hashes of the inputs and the contract version; the store path is built from a validated id pattern (`RPT-` and 20 hex characters), never from user text | Local file system access by other users is outside Sikka |
| **Repudiation** | Who validated what | Reports are idempotent and reproducible from their inputs | No audit log of callers (not needed for synthetic data) |
| **Information disclosure** | Personal data in uploads | Privacy rules quarantine prohibited fields and personal data patterns; quarantined values never appear in reports, examples, maps, lineage or logs; logs never carry record values | Patterns cannot catch every form of personal data, so producers must not send it (see PILOT) |
| **Information disclosure** | File system paths | Uploaded file names are reduced to a safe base name; responses carry file names only; a test asserts that no absolute path appears in API responses | None known |
| **Information disclosure** | Error messages | Errors are returned as `application/problem+json`; unexpected exceptions return a generic message, and only the exception type is logged | None known |
| **Denial of service** | Large or many uploads | Upload limit of 25 MB (checked on `Content-Length` and while reading); only multipart or form encoded requests are accepted; DuckDB runs with a 2 GB memory limit and spills to a temporary folder | A determined caller can still keep a local API busy; there is no rate limit |
| **Elevation of privilege** | Uploaded content reaching code | No plugin loading, no shell calls with request data, no template rendering of user strings without escaping (Jinja2 autoescape is on for HTML reports) | None known |

## Upload rules

- Accepted extensions: `.ndjson`, `.jsonl`, `.csv`, `.geojson`, `.json`.
- Accepted content types: `application/x-ndjson`, `application/jsonl`, `application/json`, `application/geo+json`, `text/csv`, `text/plain`, `application/octet-stream` or none. Anything else returns 415.
- Maximum size: 25 MB, returning 413 when exceeded. Empty files return 400.
- Uploads are disabled entirely in the static demo.

## Network and supply chain

- At run time the web app talks only to its own API (live mode) or reads its own snapshot files (static mode). Fonts are self hosted, maps load no tiles, and there is no analytics or tracking. End to end tests fail if any request goes to another host.
- No paid service, API key or secret is used, and none is stored in the repository.
- Python dependencies are pinned in `requirements.lock`; web dependencies in `web/package-lock.json`.

## Dependency audit

Run on 2026-10-13 with `pip-audit -r requirements.lock` and `npm audit` in `web/`.

| Ecosystem | Result |
| --- | --- |
| Python (`requirements.lock`) | No known vulnerabilities found |
| npm, first run | 7 advisories: one in a runtime dependency (`maplibre-gl` 5.x, an HTML sanitiser bypass, fixed in 6.x) and six in development tooling (`vite` 6, `vitest` 2, `esbuild`, `tinypool`, `vite-node`, `@vitest/mocker`) |
| npm, after upgrading `maplibre-gl` to 6.14, `vite` to 8.3 and `vitest` to 5.0 | 0 vulnerabilities |

Re-run both audits before any release; advisories change over time.
