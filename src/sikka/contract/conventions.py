"""Conventions that apply to every feed in the contract."""

from __future__ import annotations

from typing import Final

from sikka.core import ID_PATTERN, LOCAL_TZ_NAME

UTC_TIMESTAMP_PATTERN: Final = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$"
SEMVER_PATTERN: Final = r"^\d+\.\d+\.\d+$"
IDENTIFIER_PATTERN: Final = ID_PATTERN

# Generous box around the UAE. Coordinates outside it cannot be on the network.
UAE_BBOX: Final = {"lat_min": 22.5, "lat_max": 26.5, "lon_min": 51.0, "lon_max": 56.5}

HEADER_KEY: Final = "sikka_header"
FEED_TYPES: Final = ("road_segments", "crash_records", "traffic_counts")

# Field names that must never appear in a feed. Matching is case insensitive
# and ignores separators, so "Plate_Number" and "platenumber" both match.
PROHIBITED_FIELDS: Final = (
    "name",
    "full_name",
    "first_name",
    "last_name",
    "driver_name",
    "person_name",
    "emirates_id",
    "national_id",
    "id_number",
    "passport_number",
    "phone",
    "phone_number",
    "mobile",
    "email",
    "plate",
    "plate_number",
    "licence_plate",
    "license_plate",
    "narrative",
    "description",
    "notes",
    "comments",
    "free_text",
)

# Value patterns that indicate personal data even under an innocent field name.
PROHIBITED_PATTERNS: Final = {
    "emirates_id": r"\b784-?\d{4}-?\d{7}-?\d\b",
    "uae_phone": r"(?:\+971|00971|\b0)5\d[\s-]?\d{3}[\s-]?\d{4}\b",
    "email": r"\b[\w.+-]+@[\w-]+\.[\w.]+\b",
}

# Values that some producers use to mean "missing". The contract says missing
# values are absent, so these are suspicious in numeric and text fields.
SENTINEL_VALUES: Final = (-1, -9, -99, -999, 9999, 99999, "N/A", "NA", "n/a", "null", "NULL", "-")

CONVENTIONS: Final = {
    "coordinates": "WGS84 (EPSG:4326), lat and lon in decimal degrees",
    "timestamps": "ISO 8601 in UTC with a trailing Z",
    "local_time_zone": f"{LOCAL_TZ_NAME} (UTC+04:00); never assumed for timestamps",
    "distance_unit": "metres",
    "speed_unit": "km/h",
    "percentages": "0 to 100",
    "identifiers": f"opaque strings matching {ID_PATTERN}",
    "missing_values": "absent from the record; never null, -1, 0 or N/A",
    "header": f"every feed file starts with a provenance header under the key {HEADER_KEY}",
}


def normalise_field_name(name: str) -> str:
    """Lower case and drop separators, for prohibited field matching."""
    return "".join(ch for ch in name.lower() if ch.isalnum())


PROHIBITED_NORMALISED: Final = frozenset(normalise_field_name(n) for n in PROHIBITED_FIELDS)


def is_prohibited_field(name: str) -> bool:
    return normalise_field_name(name) in PROHIBITED_NORMALISED
