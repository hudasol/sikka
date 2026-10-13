"""Machine readable JSON report and self contained HTML report for a validation run."""

from __future__ import annotations

import hashlib
from typing import Any

from jinja2 import Environment, select_autoescape

from sikka import __version__
from sikka.conformance.engine import ValidationResult
from sikka.conformance.registry import FAMILY_NAMES
from sikka.conformance.scoring import score_rows
from sikka.conformance.titles_ar import TITLES_AR
from sikka.contract import CURRENT_VERSION
from sikka.core import wilson_interval

SYNTHETIC_NOTICE = "Synthetic data. No real crash, traffic or road records are used."
NOT_DECLARED_NOTICE = (
    "This repository handles synthetic data only. At least one file in this report does not "
    "declare itself synthetic (rule SK-S003); it must not be used here."
)
MAX_EXAMPLES = 5
MAX_LOCATIONS = 500
HEADER_KEYS = (
    "producer_id",
    "feed_type",
    "contract_version",
    "generated_at",
    "licence",
    "synthetic",
    "record_count",
    "period_start",
    "period_end",
)


def report_id(result: ValidationResult, contract_version: str = CURRENT_VERSION) -> str:
    """Idempotent id: the same inputs and contract version give the same id."""
    digest = hashlib.sha256(contract_version.encode())
    for feed in sorted(result.feeds, key=lambda f: (f.is_reference, f.file)):
        digest.update(f"{feed.is_reference}|{feed.file}|{feed.content_hash}".encode())
    return "RPT-" + digest.hexdigest()[:20].upper()


def _safe_header(header: dict[str, Any] | None) -> dict[str, Any] | None:
    if header is None:
        return None
    return {k: header[k] for k in HEADER_KEYS if k in header}


def build_report(result: ValidationResult) -> dict[str, Any]:
    scores, file_checks = score_rows(result.con, result)
    files: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []
    for feed in result.validated():
        quarantined = result.quarantined(feed.file)
        keys = result.record_keys.get(feed.file)
        lookup = {}
        if keys is not None and not keys.empty:
            lookup = {int(r): (rid, lat, lon) for r, rid, lat, lon in keys.itertuples(index=False)}
        files.append(
            {
                "file": feed.file,
                "feed_type": feed.feed_type,
                "producer_id": feed.producer_id,
                "format": feed.fmt,
                "rows": feed.rows,
                "header": _safe_header(feed.header),
                "header_error": feed.header_error,
                "quarantined_rows": len(quarantined),
                "profile": result.profiles.get(feed.file),
            }
        )
        for outcome in result.outcomes:
            if outcome.file != feed.file or outcome.status == "not_applicable":
                continue
            frame = outcome.findings
            rows = sorted({int(r) for r in frame["_row"].dropna()}) if not frame.empty else []
            series = sorted({str(s) for s in frame["series"].dropna()}) if not frame.empty else []
            examples: list[dict[str, Any]] = []
            for r in rows[:MAX_EXAMPLES]:
                rid = lookup.get(r, (None, None, None))[0]
                detail = None
                if r not in quarantined:
                    match = frame.loc[frame["_row"] == r, "detail"]
                    detail = str(match.iloc[0]) if not match.empty else None
                examples.append(
                    {
                        "row": r,
                        "record_id": rid if isinstance(rid, str) and r not in quarantined else None,
                        "detail": detail if detail else "value withheld: record quarantined",
                    }
                )
            if not rows and not frame.empty:
                examples = [
                    {"row": None, "record_id": s, "detail": str(d)}
                    for s, d in zip(frame["series"], frame["detail"], strict=True)
                ][:MAX_EXAMPLES]
            locations: list[list[float]] = []
            if feed.feed_type == "crash_records":
                for r in rows:
                    if r in quarantined or r not in lookup:
                        continue
                    _, lat, lon = lookup[r]
                    if lat is None or lon is None or lat != lat or lon != lon:
                        continue
                    locations.append([r, round(float(lat), 5), round(float(lon), 5)])
                    if len(locations) >= MAX_LOCATIONS:
                        break
            fields = sorted({str(f) for f in frame["field"].dropna()}) if not frame.empty else []
            rules.append(
                {
                    "rule_id": outcome.rule.id,
                    "family": outcome.rule.family,
                    "title": outcome.rule.title,
                    "title_ar": TITLES_AR.get(outcome.rule.id, outcome.rule.title),
                    "severity": outcome.rule.severity,
                    "scope": outcome.rule.scope,
                    "status": outcome.status,
                    "note": outcome.note,
                    "file": feed.file,
                    "producer_id": feed.producer_id,
                    "findings": len(frame),
                    "records": len(rows),
                    "series": len(series),
                    "share": (len(rows) / feed.rows) if feed.rows else 0.0,
                    "share_low": wilson_interval(len(rows), feed.rows).low if feed.rows else 0.0,
                    "share_high": wilson_interval(len(rows), feed.rows).high if feed.rows else 1.0,
                    "fields": fields,
                    "examples": examples,
                    "locations": locations,
                    "fix_hint": outcome.rule.fix_hint,
                }
            )
    failing = [r for r in rules if r["findings"] > 0]
    families = []
    for code, name in FAMILY_NAMES.items():
        fam = [r for r in rules if r["family"] == code]
        families.append(
            {
                "family": code,
                "name": name,
                "rules_evaluated": len({r["rule_id"] for r in fam if r["status"] == "evaluated"}),
                "rules_failing": len({r["rule_id"] for r in fam if r["findings"] > 0}),
                "findings": sum(r["findings"] for r in fam),
            }
        )
    undeclared = [
        f.file for f in result.validated() if (f.header or {}).get("synthetic") is not True
    ]
    notice = SYNTHETIC_NOTICE if not undeclared else NOT_DECLARED_NOTICE
    return {
        "report_id": report_id(result),
        "notice": notice,
        "files_not_declared_synthetic": undeclared,
        "contract_version": CURRENT_VERSION,
        "engine_version": __version__,
        "files": files,
        "references": [f.file for f in result.feeds if f.is_reference],
        "families": families,
        "rules": rules,
        "rules_failing": len({r["rule_id"] for r in failing}),
        "scores": scores,
        "file_checks": file_checks,
        "score_definition": (
            "A record passes a family when no error or warning rule of that family flagged it "
            "directly or through its station series. Informational and file level findings do "
            "not count against records. Intervals are Wilson 95 percent intervals. The overall "
            "index is the share of records that pass every family."
        ),
    }


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sikka conformance report {{ r.report_id }}</title>
<style>
:root { --pearl:#fdf8f5; --sakura:#fbe3ea; --pink:#f7b6c8; --ink:#5b3a4a; --text:#3d2632;
  --link:#8e3553; --muted:#6e4f5d; }
* { box-sizing:border-box; }
body { margin:0; padding:24px; background:var(--pearl); color:var(--text);
  font-family:"IBM Plex Sans", system-ui, sans-serif; line-height:1.5; }
h1, h2, h3 { font-family:"Space Grotesk", "IBM Plex Sans", sans-serif; color:var(--ink); }
.banner { border:2px solid var(--ink); background:var(--sakura); padding:10px 14px;
  box-shadow:4px 4px 0 var(--ink); font-weight:600; margin-bottom:24px; }
.card { border:2px solid var(--ink); background:#fff; padding:16px; margin:16px 0;
  box-shadow:4px 4px 0 var(--ink); }
table { border-collapse:collapse; width:100%; font-size:14px; }
th, td { border:1px solid var(--ink); padding:4px 8px; text-align:start; vertical-align:top; }
th { background:var(--sakura); }
.mono { font-family:"IBM Plex Mono", ui-monospace, monospace; }
.sev-error::before { content:"\\25A0  "; } .sev-warning::before { content:"\\25B2  "; }
.sev-info::before { content:"\\25CB  "; }
.muted { color:var(--muted); }
@media print { body { background:#fff; padding:0; } .card, .banner { box-shadow:none; }
  .card { break-inside:avoid; } a { color:inherit; } }
</style></head><body>
<div class="banner" role="note">{{ r.notice }}</div>
<h1>Conformance report</h1>
<p class="mono">{{ r.report_id }} &middot; contract v{{ r.contract_version }} &middot;
engine {{ r.engine_version }}</p>
<p>This report was produced by Sikka, a proposal seed that checks synthetic feeds against an
open data contract. It is not an official assessment of any entity.</p>
<div class="card"><h2>Files</h2><table><thead><tr><th>File</th><th>Feed</th><th>Producer</th>
<th>Rows</th><th>Quarantined rows</th><th>Header</th></tr></thead><tbody>
{% for f in r.files %}<tr><td class="mono">{{ f.file }}</td><td>{{ f.feed_type }}</td>
<td class="mono">{{ f.producer_id }}</td><td class="mono">{{ f.rows }}</td>
<td class="mono">{{ f.quarantined_rows }}</td><td>{{ f.header_error or "present" }}</td></tr>
{% endfor %}</tbody></table></div>
<div class="card"><h2>Conformance by producer and family</h2>
<p class="muted">{{ r.score_definition }}</p>
<table><thead><tr><th>Producer</th><th>Family</th><th>Passing records</th>
<th>Share passing</th><th>95 percent interval</th></tr></thead><tbody>
{% for s in r.scores %}<tr><td class="mono">{{ s.producer_id }}</td><td>{{ s.family_name }}</td>
<td class="mono">{{ s.passing }} of {{ s.total }}</td>
<td class="mono">{{ "%.1f"|format(100 * s.estimate) }} %</td>
<td class="mono">{{ "%.1f"|format(100 * s.low) }} to {{ "%.1f"|format(100 * s.high) }} %</td></tr>
{% endfor %}</tbody></table></div>
{% for fam in r.families %}<div class="card"><h2>{{ fam.name }} ({{ fam.family }})</h2>
<p>{{ fam.rules_evaluated }} rules evaluated, {{ fam.rules_failing }} with findings.</p>
<table><thead><tr><th>Rule</th><th>File</th><th>Severity</th><th>Records</th><th>Share</th>
<th>Examples</th><th>Fix</th></tr></thead><tbody>
{% for rule in r.rules if rule.family == fam.family
   and (rule.findings > 0 or rule.status != "evaluated") %}
<tr><td><span class="mono">{{ rule.rule_id }}</span> {{ rule.title }}</td>
<td class="mono">{{ rule.file }}</td><td class="sev-{{ rule.severity }}">{{ rule.severity }}</td>
<td class="mono">{% if rule.status == "evaluated" %}{{ rule.records or rule.findings }}{% else %}
not evaluated: {{ rule.note }}{% endif %}</td>
<td class="mono">{{ "%.2f"|format(100 * rule.share) }} %</td>
<td>{% for e in rule.examples %}<div>
<span class="mono">{{ e.record_id or ("row " ~ e.row) }}</span>:
{{ e.detail }}</div>{% endfor %}</td><td>{{ rule.fix_hint }}</td></tr>
{% endfor %}</tbody></table></div>{% endfor %}
<p class="muted">{{ r.notice }}</p>
</body></html>
"""

_ENV = Environment(autoescape=select_autoescape(default=True, default_for_string=True))


def render_html(report: dict[str, Any]) -> str:
    return _ENV.from_string(_TEMPLATE).render(r=report)
