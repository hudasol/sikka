# Decisions

This log records choices made where the build brief was silent or open to more than one reading. Larger architectural choices also have an ADR in `docs/adr/`.

| Id | Decision | Reason |
| --- | --- | --- |
| D01 | The Python environment is a standard `venv` created with `py -3.13 -m venv .venv` on Windows (`python3.13 -m venv .venv` elsewhere). Dependencies are pinned in `requirements.lock`, compiled with `uv pip compile --universal`, and can be installed with either `pip` or `uv`. | Works with plain `pip` on every platform while still giving a reproducible lock file. |
| D02 | The local reporting zone Asia/Dubai is represented as a fixed UTC+04:00 offset. | The zone has no daylight saving, and a fixed offset avoids a dependency on the tz database, which is not bundled with Python on Windows. |
| D03 | `.gitattributes` forces LF line endings. | Generated artefacts are compared byte for byte; per user line ending settings would otherwise change them. |
| D04 | The evaluation harness is its own package, `sikka.evaluation`, placed above the service layer. An extra import contract forbids the product layers (L2 to L7) from importing `sikka.synth`. | The brief requires that the hidden truth file is used only by evaluation. Making it an import rule turns that promise into a checked property. |
| D05 | `sikka check` enforces the 85 percent coverage floor and skips tests marked `slow` or `perf`. Those run in `sikka all` and in CI. | Keeps the fast check fast while the quality gate still holds. |
