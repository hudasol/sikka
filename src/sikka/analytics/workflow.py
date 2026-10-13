"""From a harmonised dataset to the published ranking (EB and EB with quality propagation)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

from sikka.analytics.inputs import AnalyticsConfig, group_capture_counts, segment_table
from sikka.analytics.quality import Chapman, chapman_by_group
from sikka.analytics.ranking import Ranking, rank_segments, ranking_summary
from sikka.harmonise import HarmonisedDataset


@dataclass
class RankingBundle:
    table: pd.DataFrame
    eb: Ranking
    eb_qp: Ranking
    chapman: dict[str, Chapman]
    config: AnalyticsConfig

    def segment_rows(self) -> list[dict[str, Any]]:
        """Per segment record for the API: EB+QP is the published ranking, EB beside it."""
        qp = self.eb_qp.table.set_index("segment_id")
        eb = self.eb.table.set_index("segment_id")
        rows = []
        for sid in sorted(qp.index):
            q, e = qp.loc[sid], eb.loc[sid]

            def num(value: Any) -> float | None:
                return (
                    None
                    if value is None or (isinstance(value, float) and math.isnan(value))
                    else float(value)
                )

            rows.append(
                {
                    "segment_id": sid,
                    "corridor": q["corridor"],
                    "road_name_en": q["road_name_en"],
                    "road_name_ar": q["road_name_ar"],
                    "road_class": q["road_class"],
                    "lane_count": int(q["lane_count"]),
                    "length_km": float(q["length_km"]),
                    "owner": q["owner"],
                    "aadt": num(q["aadt"]),
                    "window_years": float(q["window_years"]),
                    "observed": int(q["observed"]),
                    "observed_by_year": {str(y): int(q[f"y{y}"]) for y in self.config.years},
                    "unresolved_pairs": int(q["unresolved_pairs"]),
                    "coverage": float(q["coverage"]),
                    "abstained": q["abstained"] or None,
                    "predicted_per_year": num(q["predicted_per_year"]),
                    "eb_weight": num(q["eb_weight"]),
                    "eb_per_year": None
                    if num(q["eb"]) is None
                    else float(q["eb"]) / float(q["window_years"]),
                    "psi_per_year": num(q["psi_per_year"]),
                    "rank": num(q["rank"]),
                    "rank_median": num(q["rank_median"]),
                    "rank_low": num(q["rank_low"]),
                    "rank_high": num(q["rank_high"]),
                    "p_top_k": num(q["p_top_k"]),
                    "quality_factor": num(q["quality_factor"]),
                    "eb_only": {
                        "rank": num(e["rank"]),
                        "rank_low": num(e["rank_low"]),
                        "rank_high": num(e["rank_high"]),
                        "p_top_k": num(e["p_top_k"]),
                    },
                    "raw_rank": num(q["raw_rank"]),
                    "rate_rank": num(q["rate_rank"]),
                    "rate_per_mvkm": num(q["rate_per_mvkm"]),
                }
            )
        return rows

    def summary(self) -> dict[str, Any]:
        return {
            "published": ranking_summary(self.eb_qp),
            "eb_only": ranking_summary(self.eb),
            "spf": self.eb_qp.spf.as_dict() if self.eb_qp.spf else None,
            "capture_recapture": [c.as_dict() for c in self.chapman.values()],
            "window": {"first_year": self.config.first_year, "last_year": self.config.last_year},
            "abstention_rules": {
                "no_exposure": "no daily traffic estimate for the segment",
                "short_window": f"observation window under {self.config.min_window_years:g} years",
                "low_coverage": "mean monthly delivery coverage of the producers expected on the "
                f"corridor below {self.config.coverage_floor:g}",
            },
        }


def rank_dataset(
    ds: HarmonisedDataset, cfg: AnalyticsConfig | None = None, seed: int = 0
) -> RankingBundle:
    cfg = cfg or AnalyticsConfig()
    table = segment_table(ds, cfg)
    chapman = chapman_by_group(group_capture_counts(ds, cfg))
    eb = rank_segments(table, cfg, seed=seed, quality=False)
    eb_qp = rank_segments(table, cfg, seed=seed, chapman=chapman, quality=True)
    return RankingBundle(table, eb, eb_qp, chapman, cfg)
