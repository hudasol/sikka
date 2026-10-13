"""Performance budget measurements, written to results/performance.json.

Budgets (from the build brief): validate 1,000,000 crash rows in under 60 seconds;
rank 240 segments with 4,000 posterior draws in under 10 seconds; static web first
load under 3 seconds (measured by Playwright into results/web_performance.json);
bundle size reported.
"""

from __future__ import annotations

import json
import platform
import time
from pathlib import Path
from typing import Any

from sikka.analytics import AnalyticsConfig, rank_dataset
from sikka.conformance import Source, run_validation
from sikka.core import Paths
from sikka.harmonise import harmonise

ROWS = 1_000_000


def big_crash_feed(samples: Path, path: Path, rows: int = ROWS) -> None:
    """Repeat the clean producer B records with unique ids until ``rows`` lines."""
    source = (samples / "clean" / "crash_records_producer_b.ndjson").read_text("utf-8")
    lines = source.splitlines()
    header = json.loads(lines[0])
    header["sikka_header"]["record_count"] = rows
    records = [json.loads(line) for line in lines[1:]]
    with path.open("w", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(header) + "\n")
        for i in range(rows):
            record = dict(records[i % len(records)])
            record["crash_id"] = f"PB-{i + 1:09d}"
            out.write(json.dumps(record, ensure_ascii=False) + "\n")


def measure(paths: Paths | None = None) -> dict[str, Any]:
    paths = paths or Paths()
    work = paths.build / "perf"
    work.mkdir(parents=True, exist_ok=True)
    big = work / "crash_records_1m.ndjson"
    if not big.is_file():
        big_crash_feed(paths.samples, big)
    refs = [
        Source.from_path(p)
        for p in sorted((paths.samples / "clean").iterdir())
        if p.name.startswith("road_segments")
    ]
    started = time.perf_counter()
    result = run_validation([Source.from_path(big)], refs)
    validate_s = time.perf_counter() - started
    rows = result.feeds[0].rows
    result.close()

    clean = [Source.from_path(p) for p in sorted((paths.samples / "clean").iterdir())]
    ds = harmonise(clean)
    started = time.perf_counter()
    bundle = rank_dataset(ds, AnalyticsConfig(draws=4000), seed=1)
    rank_s = time.perf_counter() - started
    segments = len(bundle.table)

    dist = paths.web / "dist"
    js = css = fonts = 0
    for f in dist.rglob("*") if dist.is_dir() else []:
        if f.suffix == ".js":
            js += f.stat().st_size
        elif f.suffix == ".css":
            css += f.stat().st_size
        elif f.suffix in {".woff", ".woff2"}:
            fonts += f.stat().st_size

    measures = [
        {
            "name": f"Validate {rows:,} crash rows (NDJSON, every rule, registry as context)",
            "value": f"{validate_s:.1f} s",
            "budget": "under 60 s",
            "ok": validate_s < 60,
        },
        {
            "name": f"Rank {segments} segments with 4,000 posterior draws (EB and EB+QP)",
            "value": f"{rank_s:.1f} s",
            "budget": "under 10 s",
            "ok": rank_s < 10,
        },
    ]
    if js or css:
        measures.append(
            {
                "name": "Web bundle: JavaScript, CSS, fonts (uncompressed)",
                "value": f"{js / 1024:.0f} KB, {css / 1024:.0f} KB, {fonts / 1024:.0f} KB",
                "budget": "reported",
                "ok": True,
            }
        )
    web = paths.results / "web_performance.json"
    if web.is_file():
        data = json.loads(web.read_text("utf-8"))
        measures.append(
            {
                "name": f"Static web first load ({data['profile']})",
                "value": f"{data['load_s']:.2f} s",
                "budget": "under 3 s",
                "ok": data["load_s"] < 3,
            }
        )
    return {
        "note": (
            "Measured by `sikka perf` on the machine that ran it "
            f"({platform.system()} {platform.release()}, {platform.machine()}, "
            f"Python {platform.python_version()}). Timings vary between machines and runs."
        ),
        "measures": measures,
        "validate_seconds": validate_s,
        "rank_seconds": rank_s,
        "rows": rows,
        "segments": segments,
        "bundle_bytes": {"js": js, "css": css, "fonts": fonts},
    }
