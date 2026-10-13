"""L4 Harmonisation: producer adapters, entity resolution and lineage."""

from sikka.harmonise.adapters import adapt_count, adapt_crash, normalise_segment_ref
from sikka.harmonise.model import (
    SEVERITY_RANK,
    CanonicalCrash,
    Exposure,
    Lineage,
    PairDecision,
    ProducerCrash,
    SourceRef,
    Transformation,
)
from sikka.harmonise.pipeline import HarmonisedDataset, Segment, harmonise
from sikka.harmonise.resolution import MATCH_AT, NON_MATCH_BELOW, resolve, score_pair
from sikka.harmonise.snapping import SegmentIndex
from sikka.harmonise.tables import ADAPTER_VERSION, ADAPTERS, AdapterTable, table_for

__all__ = [
    "ADAPTERS",
    "ADAPTER_VERSION",
    "MATCH_AT",
    "NON_MATCH_BELOW",
    "SEVERITY_RANK",
    "AdapterTable",
    "CanonicalCrash",
    "Exposure",
    "HarmonisedDataset",
    "Lineage",
    "PairDecision",
    "ProducerCrash",
    "Segment",
    "SegmentIndex",
    "SourceRef",
    "Transformation",
    "adapt_count",
    "adapt_crash",
    "harmonise",
    "normalise_segment_ref",
    "resolve",
    "score_pair",
    "table_for",
]
