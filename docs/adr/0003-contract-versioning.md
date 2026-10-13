# ADR 0003: Contract first, with semantic versioning

Status: accepted

## Context

Feeds come from several producers with different conventions. Consumers need a stable promise about field names, types, units and meanings, and producers need to know when a change will break consumers.

## Decision

1. The contract lives in code, in `sikka.contract` (layer L0), as pydantic models. Every other representation is generated from it: JSON Schema per feed and version (`contract/vX.Y.Z/*.schema.json`), a bundle per version (`contract.json`), the field dictionary (`docs/CONTRACT.md`) and TypeScript types for the web app (`web/src/generated/contract.ts`). A test fails if any generated file differs from what the generator would write.
2. Versions follow `MAJOR.MINOR.PATCH`. Adding an optional field is minor; removing a field, adding a required field or changing type, unit, allowed values or meaning is major; rewording is patch. The rule is written in `contract/CHANGELOG.md` and enforced by `sikka contract diff`, which exits non zero when the declared bump is too small.
3. Version 1.0.0 is released. Version 1.1.0 is a draft that adds the optional `crash_records.work_zone` flag, to prove that the diff tooling works.
4. Optional fields are absent when missing. The models reject explicit `null`, and the generated schemas do not allow `null`.

## Consequences

- Changes to the contract are reviewed in one place and propagate automatically.
- The schema dialect is JSON Schema 2020 12 as emitted by pydantic, with `x-` extensions for the Arabic description and the unit.
- Field level rule references in the dictionary are supplied by the conformance layer at generation time, so the contract does not import a higher layer.
