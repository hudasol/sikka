# Contract changelog

The Sikka data contract uses semantic versioning (`MAJOR.MINOR.PATCH`).

## Compatibility rule

- **Major**: removing a field, adding a required field, or changing the type, unit, allowed values or meaning of an existing field. Consumers must change.
- **Minor**: adding an optional field. Existing producers and consumers keep working.
- **Patch**: rewording a description or example without changing meaning.

`sikka contract diff OLD NEW` classifies every change by this rule and exits with a non zero code when the declared version bump is smaller than the bump the changes require.

## 1.1.0 (draft)

- Added the optional boolean field `crash_records.work_zone`: true when the crash occurred inside a marked road works zone, absent when unknown. Minor change.
- Status: draft. It exists to exercise the diff tooling and is not the version the product validates against.

## 1.0.0 (released)

- First version: provenance header, road segment registry, crash records and traffic station counts.
- Conventions: WGS84 coordinates, UTC timestamps with `Z`, metres, km/h, percentages 0 to 100, opaque identifiers, missing values absent.
- Prohibited personal fields and value patterns, with quarantine.

All data that follows this contract in this repository is synthetic.
