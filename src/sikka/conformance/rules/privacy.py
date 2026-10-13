"""P family: personal data. Records with a finding here are quarantined.

Quarantined values are never copied into reports, examples, maps or logs; only
the row number and the field name are kept.
"""

from __future__ import annotations

import pandas as pd

from sikka.conformance.context import RuleContext
from sikka.conformance.registry import Example, Rule, register
from sikka.conformance.rules.structural import ALL, sql_list, union
from sikka.contract import PROHIBITED_PATTERNS
from sikka.contract.conventions import PROHIBITED_NORMALISED

NORMALISE_SQL = "lower(regexp_replace(k, '[^A-Za-z0-9]', '', 'g'))"


def p001(ctx: RuleContext) -> pd.DataFrame:
    return union(
        ctx,
        [
            f"SELECT _row, NULL AS series, k AS field, 'prohibited personal field; record "
            f"quarantined' AS detail FROM (SELECT _row, unnest(_keys) AS k FROM {ctx.table}) "
            f"WHERE {NORMALISE_SQL} IN {sql_list(sorted(PROHIBITED_NORMALISED))}"
        ],
    )


register(
    Rule(
        "SK-P001",
        "P",
        "No prohibited personal fields",
        "error",
        "Records carry none of the prohibited field names (names, identity numbers, phone, "
        "plate numbers, free text narratives). Matching ignores case and separators.",
        "Crash analysis does not need personal data, and holding it creates legal and ethical "
        "duties that this tool is not designed for.",
        "Remove the field at the source before sharing. The record is quarantined until then.",
        ALL,
        ("*",),
        "record",
        p001,
        Example("crash_records", {"plate_number": "SYN 00000"}, {}),
    )
)


def p002(ctx: RuleContext, *, prefilter: bool = True) -> pd.DataFrame:
    """Scan every value of every field, contract or not, nested objects and lists included.

    The patterns are first run once over the raw line. A raw line without a backslash
    and without a number in exponent form holds every decoded value verbatim, between
    characters that are not word characters, so a value can only match when its line
    matches. Lines with escapes or exponents always get the field by field scan.
    """
    combined = "|".join(f"(?:{p})" for _, p in sorted(PROHIBITED_PATTERNS.items()))
    combined = combined.replace("'", "''")
    candidates = (
        f"SELECT _row, _raw, _keys FROM {ctx.table} WHERE strpos(_raw, chr(92)) > 0 OR "
        f"regexp_matches(_raw, '[0-9][eE][-+]?[0-9]') OR regexp_matches(_raw, '{combined}')"
        if prefilter
        else f"SELECT _row, _raw, _keys FROM {ctx.table}"
    )
    value_sources = (
        f"SELECT _row, k, json_extract_string(_raw, '$.\"' || replace(k, '\"', '') || '\"') AS v "
        f"FROM (SELECT _row, _raw, unnest(_keys) AS k FROM ({candidates}))"
    )
    selects = []
    for label, pattern in sorted(PROHIBITED_PATTERNS.items()):
        safe = pattern.replace("'", "''")
        selects.append(
            f"SELECT _row, NULL AS series, k AS field, 'value matches the {label} pattern; "
            f"record quarantined' AS detail FROM ({value_sources}) WHERE v IS NOT NULL AND "
            f"regexp_matches(v, '{safe}')"
        )
    frame = union(ctx, selects)
    return frame.drop_duplicates(subset=["_row", "field"]).reset_index(drop=True)


register(
    Rule(
        "SK-P002",
        "P",
        "No personal data patterns in values",
        "error",
        "No value in any field, including identifiers, enumerations and lists, looks like a "
        "UAE phone number, an identity card number or an email address.",
        "Personal data can arrive under an innocent field name such as contact or reference.",
        "Remove the value at the source. The record is quarantined until then.",
        ALL,
        ("*",),
        "record",
        p002,
        Example("crash_records", {"contact": "+971500000123"}, {}),
    )
)
