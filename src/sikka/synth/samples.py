"""Committed sample feeds: one clean world and the same world with every fault injected.

The samples contain feeds only. Their ground truth is regenerated on demand by
``sikka generate`` and is not committed, so the product never sees it.
"""

from __future__ import annotations

from sikka.core import stable_json_dumps
from sikka.synth.config import WorldConfig
from sikka.synth.faults import CATALOGUE, inject
from sikka.synth.world import World, build_world, finalise_feed

SAMPLE_SEED = 20260422
SAMPLE_BROKEN_RATE = 0.03
SAMPLE_FAULT_SEED = 7


def sample_worlds() -> tuple[World, World]:
    clean = build_world(WorldConfig(seed=SAMPLE_SEED))
    broken = inject(clean, {f.id: SAMPLE_BROKEN_RATE for f in CATALOGUE}, SAMPLE_FAULT_SEED)
    return clean, broken


def sample_files() -> dict[str, str]:
    """Every committed sample file, keyed by path relative to the repository root."""
    clean, broken = sample_worlds()
    files: dict[str, str] = {}
    for label, world in (("clean", clean), ("broken", broken)):
        for feed in world.feeds:
            text, _ = finalise_feed(feed)
            files[f"data/samples/{label}/{feed.filename}"] = text
    catalogue = {
        "note": "Public description of the fault catalogue. Locations of injected faults are "
        "hidden ground truth and are not part of the samples.",
        "broken_rate": SAMPLE_BROKEN_RATE,
        "seed": SAMPLE_SEED,
        "faults": [f.as_dict() for f in CATALOGUE],
    }
    files["data/samples/fault_catalogue.json"] = stable_json_dumps(catalogue, indent=2) + "\n"
    return files
