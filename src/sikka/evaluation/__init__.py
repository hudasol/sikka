"""Evaluation harness: preregistered experiments E1 to E5 over the synthetic world.

Only this layer and the CLI may read the hidden ground truth. Results are written
to ``results/*.json`` and every document number is rendered from those files.
"""

from sikka.evaluation.runner import EXPERIMENT_SEED_BASE, SMOKE_SEED, run_experiments, seed_list

__all__ = ["EXPERIMENT_SEED_BASE", "SMOKE_SEED", "run_experiments", "seed_list"]
