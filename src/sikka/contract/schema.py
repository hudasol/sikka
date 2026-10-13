"""JSON Schema generation and field specifications derived from the models."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any

from sikka.contract.conventions import (
    CONVENTIONS,
    HEADER_KEY,
    PROHIBITED_FIELDS,
    PROHIBITED_PATTERNS,
    UAE_BBOX,
)
from sikka.contract.models import ContractModel
from sikka.contract.versions import ContractVersion

SCHEMA_BASE = "https://github.com/hudasol/sikka/blob/main/contract"
FEED_TITLES = {
    "road_segments": ("Road segment registry", "سجل مقاطع الطرق"),
    "crash_records": ("Crash records", "سجلات الحوادث"),
    "traffic_counts": ("Traffic station counts", "أعداد محطات العد المروري"),
    "provenance_header": ("Provenance header", "ترويسة المصدر"),
}


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            target = defs[node["$ref"].rsplit("/", 1)[-1]]
            merged = {**_inline_refs(copy.deepcopy(target), defs)}
            merged.update({k: v for k, v in node.items() if k != "$ref"})
            return merged
        return {k: _inline_refs(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def _strip_nullable(node: Any) -> Any:
    """Turn pydantic's ``anyOf [X, null]`` into ``X``: missing means absent."""
    if isinstance(node, dict):
        out = {k: _strip_nullable(v) for k, v in node.items()}
        any_of = out.get("anyOf")
        if isinstance(any_of, list):
            rest = [s for s in any_of if s != {"type": "null"}]
            if len(rest) == 1 and len(rest) < len(any_of):
                out.pop("anyOf")
                out = {**rest[0], **out}
        if out.get("default", ...) is None:
            out.pop("default")
        out.pop("title", None)
        return out
    if isinstance(node, list):
        return [_strip_nullable(v) for v in node]
    return node


def model_schema(model: type[ContractModel], *, version: str, name: str) -> dict[str, Any]:
    raw = model.model_json_schema(mode="validation")
    defs = raw.pop("$defs", {})
    body = _strip_nullable(_inline_refs(raw, defs))
    title_en, title_ar = FEED_TITLES[name]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_BASE}/v{version}/{name}.schema.json",
        "title": title_en,
        "x-title-ar": title_ar,
        "x-contract-version": version,
        **{k: v for k, v in body.items() if k not in {"title"}},
    }


@dataclass(frozen=True)
class FieldSpec:
    """One row of the field dictionary."""

    feed: str
    name: str
    type: str
    required: bool
    unit: str | None
    allowed: str | None
    description_en: str
    description_ar: str
    example: Any
    enum: list[str] = field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    pattern: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _type_label(prop: dict[str, Any]) -> str:
    if "enum" in prop:
        return "enum"
    if "const" in prop:
        return "constant"
    kind = prop.get("type", "any")
    if kind == "array":
        items = prop.get("items", {})
        if "enum" in items:
            return "list of enum"
        if "prefixItems" in items or items.get("type") == "array":
            return "list of positions"
        return f"list of {items.get('type', 'any')}"
    if kind == "string" and prop.get("pattern", "").endswith("Z$"):
        return "timestamp"
    if kind == "string" and "pattern" in prop:
        return "identifier" if "A-Z0-9" in prop["pattern"] else "string"
    return str(kind)


def _allowed(prop: dict[str, Any]) -> str | None:
    if "enum" in prop:
        return ", ".join(str(v) for v in prop["enum"])
    if "const" in prop:
        return str(prop["const"])
    items = prop.get("items", {})
    if "enum" in items:
        return ", ".join(str(v) for v in items["enum"])
    if "exclusiveMinimum" in prop and "maximum" not in prop:
        return f"greater than {prop['exclusiveMinimum']:g}"
    low = prop.get("minimum")
    high = prop.get("maximum")
    if low is not None and high is not None:
        return f"{low:g} to {high:g}"
    if low is not None:
        return f"at least {low:g}"
    if high is not None:
        return f"at most {high:g}"
    return None


def field_specs(schema: dict[str, Any], feed: str, prefix: str = "") -> list[FieldSpec]:
    """Flatten a feed schema into field dictionary rows, nested objects included."""
    required = set(schema.get("required", []))
    specs: list[FieldSpec] = []
    for name, prop in schema.get("properties", {}).items():
        full = f"{prefix}{name}"
        examples = prop.get("examples") or [None]
        items = prop.get("items", {})
        specs.append(
            FieldSpec(
                feed=feed,
                name=full,
                type=_type_label(prop),
                required=name in required,
                unit=prop.get("x-unit"),
                allowed=_allowed(prop),
                description_en=prop.get("description", ""),
                description_ar=prop.get("x-description-ar", ""),
                example=examples[0],
                enum=[str(v) for v in prop.get("enum", items.get("enum", []))],
                minimum=prop.get("minimum", prop.get("exclusiveMinimum")),
                maximum=prop.get("maximum"),
                pattern=prop.get("pattern"),
            )
        )
        if prop.get("type") == "object" and "properties" in prop:
            specs.extend(field_specs(prop, feed, prefix=f"{full}."))
    return specs


def version_schemas(version: ContractVersion) -> dict[str, dict[str, Any]]:
    """All schemas of a version keyed by name, header included."""
    schemas = {
        "provenance_header": model_schema(
            version.header, version=version.version, name="provenance_header"
        )
    }
    for feed, model in version.feeds.items():
        schemas[feed] = model_schema(model, version=version.version, name=feed)
    return schemas


def contract_bundle(version: ContractVersion) -> dict[str, Any]:
    """Everything a client needs to know about one contract version."""
    schemas = version_schemas(version)
    return {
        "version": version.version,
        "status": version.status,
        "summary": version.summary,
        "synthetic_only_repository": True,
        "conventions": dict(CONVENTIONS),
        "header_key": HEADER_KEY,
        "uae_bbox": dict(UAE_BBOX),
        "prohibited_fields": list(PROHIBITED_FIELDS),
        "prohibited_patterns": sorted(PROHIBITED_PATTERNS),
        "feeds": {
            name: {
                "title_en": FEED_TITLES[name][0],
                "title_ar": FEED_TITLES[name][1],
                "schema": f"v{version.version}/{name}.schema.json",
                "fields": [s.as_dict() for s in field_specs(schema, name)],
            }
            for name, schema in schemas.items()
        },
    }
