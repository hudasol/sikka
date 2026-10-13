"""L2 Ingestion: parsers, DuckDB staging and profiling."""

from sikka.ingest.parsers import (
    FEED_KEYS,
    ParsedFeed,
    contract_types,
    csv_row_to_record,
    detect_format,
    infer_feed_type,
    open_feed,
    open_text,
)
from sikka.ingest.profile import profile_feed
from sikka.ingest.staging import BATCH_ROWS, StagedFeed, json_path, stage, typed_columns

__all__ = [
    "BATCH_ROWS",
    "FEED_KEYS",
    "ParsedFeed",
    "StagedFeed",
    "contract_types",
    "csv_row_to_record",
    "detect_format",
    "infer_feed_type",
    "json_path",
    "open_feed",
    "open_text",
    "profile_feed",
    "stage",
    "typed_columns",
]
