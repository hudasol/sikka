"""Time conventions.

All contract timestamps are ISO 8601 in UTC with a trailing ``Z``. The local
reporting zone is Asia/Dubai, which has a fixed offset of UTC+04:00 and no
daylight saving, so a fixed offset is used instead of a tz database lookup.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone

LOCAL_TZ = timezone(timedelta(hours=4), name="Asia/Dubai")
LOCAL_TZ_NAME = "Asia/Dubai"

_UTC_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")


def is_utc_z(text: str) -> bool:
    """True when ``text`` is an ISO 8601 UTC timestamp ending in ``Z``."""
    return bool(_UTC_Z.match(text))


def parse_utc(text: str) -> datetime:
    """Parse a contract timestamp. Raises ``ValueError`` when it is not UTC ``Z``."""
    if not is_utc_z(text):
        raise ValueError(f"not an ISO 8601 UTC timestamp with Z: {text!r}")
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def format_utc(moment: datetime) -> str:
    """Format an aware datetime as ISO 8601 UTC with ``Z`` and second precision."""
    if moment.tzinfo is None:
        raise ValueError("naive datetimes are not allowed; attach a time zone")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_local(moment: datetime) -> datetime:
    """Convert an aware datetime to the local reporting zone."""
    if moment.tzinfo is None:
        raise ValueError("naive datetimes are not allowed; attach a time zone")
    return moment.astimezone(LOCAL_TZ)
