"""L3 Conformance: rule registry, rule engine, reports and scores."""

from sikka.conformance.catalogue import (
    example_header,
    example_records,
    render_rules_md,
    rules_by_field,
)
from sikka.conformance.context import RuleConfig, RuleContext
from sikka.conformance.engine import RuleOutcome, Source, ValidationResult, run_validation
from sikka.conformance.fields import BASE_HEADER, BASE_RECORDS, RECORD_KEY
from sikka.conformance.registry import FAMILY_NAMES, REGISTRY, Example, Rule, rules_for
from sikka.conformance.report import SYNTHETIC_NOTICE, build_report, render_html, report_id
from sikka.conformance.scoring import score_rows

__all__ = [
    "BASE_HEADER",
    "BASE_RECORDS",
    "FAMILY_NAMES",
    "RECORD_KEY",
    "REGISTRY",
    "SYNTHETIC_NOTICE",
    "Example",
    "Rule",
    "RuleConfig",
    "RuleContext",
    "RuleOutcome",
    "Source",
    "ValidationResult",
    "build_report",
    "example_header",
    "example_records",
    "render_html",
    "render_rules_md",
    "report_id",
    "rules_by_field",
    "rules_for",
    "run_validation",
    "score_rows",
]
