# ADR 0001: Licence is Apache 2.0

Status: accepted

## Context

Sikka is a proposal seed. Any entity that later wants to evaluate it on real data should be able to read, run, adapt and redistribute the code without negotiating terms, and contributors should grant an explicit patent licence so that adoption carries less legal risk.

## Decision

The repository is released under the Apache License, Version 2.0. The full text is in `LICENSE`, and `pyproject.toml` declares `Apache-2.0`.

## Consequences

- Reuse, modification and redistribution are permitted, including inside closed systems, provided the licence and notices are kept.
- Contributors grant a patent licence for their contributions.
- Synthetic sample data and generated results in this repository are covered by the same licence. Each feed header also carries a `licence` field so the terms travel with the data.
- Third party dependencies keep their own licences; the dependency audit in `docs/SECURITY.md` lists them.
