# Decisions

This log records choices made where the build brief was silent or open to more than one reading. Larger architectural choices also have an ADR in `docs/adr/`.

| Id | Decision | Reason |
| --- | --- | --- |
| D01 | The Python environment is a standard `venv` created with `py -3.13 -m venv .venv` on Windows (`python3.13 -m venv .venv` elsewhere). Dependencies are pinned in `requirements.lock`, compiled with `uv pip compile --universal`, and can be installed with either `pip` or `uv`. | Works with plain `pip` on every platform while still giving a reproducible lock file. |
| D02 | The local reporting zone Asia/Dubai is represented as a fixed UTC+04:00 offset. | The zone has no daylight saving, and a fixed offset avoids a dependency on the tz database, which is not bundled with Python on Windows. |
| D03 | `.gitattributes` forces LF line endings. | Generated artefacts are compared byte for byte; per user line ending settings would otherwise change them. |
| D04 | The evaluation harness is its own package, `sikka.evaluation`, placed above the service layer. An extra import contract forbids the product layers (L2 to L7) from importing `sikka.synth`. | The brief requires that the hidden truth file is used only by evaluation. Making it an import rule turns that promise into a checked property. |
| D05 | `sikka check` enforces the 85 percent coverage floor and skips tests marked `slow` or `perf`. Those run in `sikka all` and in CI. | Keeps the fast check fast while the quality gate still holds. |
| D06 | `sikka contract diff` accepts exact versions (`1.0.0`), `v` prefixed versions (`v1.1.0`) and the aliases `v1` (1.0.0), `v1.1` (1.1.0) and `latest`. The brief's example `sikka contract diff v1 v2` is served as `v1 v1.1`, since no 2.0.0 exists. | Only one released and one draft version exist; aliases keep the command short without guessing. |
| D07 | The enumerations the brief leaves open are fixed as follows. Collision type: rear_end, side_impact, head_on, rollover, run_off_road, pedestrian, fixed_object, other. Weather: clear, rain, fog, dust_sand, strong_wind, other. Light: daylight, dark_lit, dark_unlit, dawn_dusk. Surface: dry, wet, sand_covered, damaged, other. Vehicle classes: car, light_goods, heavy_goods, bus, motorcycle. | Small, mutually exclusive sets that cover common coding schemes, including dust and sand conditions. |
| D08 | Range limits used by the models: lanes 1 to 12, speed limit 20 to 160 km/h, mean speed 0 to 250 km/h, contributing factors at most 8 per crash. | Wide enough not to reject plausible values; tighter plausibility checks are conformance rules with their own ids. |
