"""L1 Synthetic world: network, exposure, crashes, producers and fault injection.

Everything in this layer is invented. The product layers (L2 to L7) are not
allowed to import it; only the evaluation harness and the CLI may, which keeps
the hidden truth away from the product.
"""

from sikka.synth.config import CORRIDORS, PRODUCERS, Corridor, ProducerProfile, WorldConfig
from sikka.synth.faults import CATALOGUE, FAULTS, Fault, inject
from sikka.synth.network import SegmentTruth, build_network, to_lonlat, to_xy
from sikka.synth.samples import SAMPLE_BROKEN_RATE, SAMPLE_SEED, sample_files
from sikka.synth.world import Feed, World, build_world, finalise_feed, truth_documents, write_world

__all__ = [
    "CATALOGUE",
    "CORRIDORS",
    "FAULTS",
    "PRODUCERS",
    "SAMPLE_BROKEN_RATE",
    "SAMPLE_SEED",
    "Corridor",
    "Fault",
    "Feed",
    "ProducerProfile",
    "SegmentTruth",
    "World",
    "WorldConfig",
    "build_network",
    "build_world",
    "finalise_feed",
    "inject",
    "sample_files",
    "to_lonlat",
    "to_xy",
    "truth_documents",
    "write_world",
]
