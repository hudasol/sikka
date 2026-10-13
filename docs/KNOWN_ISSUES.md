# Known issues

Open gaps, limitations of the implementation and any `TODO` or `FIXME` markers in the code are listed here. A gap listed here is a known and accepted gap; anything not listed is a bug.

| Id | Area | Issue | Status |
| --- | --- | --- | --- |
| K01 | Conformance | `SK-V013` compares each station's daily profile with the median of all stations. When half or more of the stations share the same clock offset, the median moves with them and the offset is not detected. A unit test pins this behaviour. | Accepted; documented in the rule text. |
| K02 | Ingestion | GeoJSON files are parsed as one document rather than streamed. Registries are small, but a very large GeoJSON point file would be held in memory. NDJSON and CSV stream. | Accepted for v1. |
| K03 | Ingestion | CSV parsing converts each row in Python and is slower per row than NDJSON staging, which passes lines through unchanged. The one million row budget is measured on NDJSON. | Accepted; measured figures go to `docs/EVALUATION.md`. |
| K04 | Evaluation | The faults and the rules were written by the same author. High detection rates in E1 show that the rules catch the anticipated faults; they say nothing about faults outside the catalogue. | Stated in PREREGISTRATION, EVALUATION and LIMITATIONS. |
