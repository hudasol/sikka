"""L6 Tasking: value of information and drone survey mission plans.

Every plan states that it is for simulation and review only.
"""

from typing import Any

from sikka.tasking.exports import to_geojson, to_kml, to_plan, validate_plan
from sikka.tasking.planner import (
    DISCLAIMER,
    Candidate,
    DroneProfile,
    Mission,
    TaskingConfig,
    build_mission,
    candidates_from_rows,
    greedy_count_order,
    plan_missions,
    random_order,
    value_density,
)


def compare_strategies(
    rows: list[dict[str, Any]],
    geometry: dict[str, list[list[float]]],
    cfg: TaskingConfig | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    """Plan with value of information, random order and greedy by crash count."""
    cfg = cfg or TaskingConfig()
    candidates = candidates_from_rows(rows, geometry)
    observed = {str(r["segment_id"]): int(r["observed"]) for r in rows}
    orders = {
        "value_of_information": None,
        "random": random_order(candidates, seed),
        "greedy_crash_count": greedy_count_order(candidates, observed),
    }
    out: dict[str, Any] = {}
    for name, order in orders.items():
        planned, refused = plan_missions(candidates, cfg, order)
        out[name] = {
            "missions": planned,
            "refused": refused,
            "segments": sorted({s for m in planned for s in m.segments}),
            "value": round(sum(m.value for m in planned), 6),
            "flight_s": round(sum(m.flight_s for m in planned), 1),
        }
    return out


__all__ = [
    "DISCLAIMER",
    "Candidate",
    "DroneProfile",
    "Mission",
    "TaskingConfig",
    "build_mission",
    "candidates_from_rows",
    "compare_strategies",
    "greedy_count_order",
    "plan_missions",
    "random_order",
    "to_geojson",
    "to_kml",
    "to_plan",
    "validate_plan",
    "value_density",
]
