"""The preregistered predictions, in machine checkable form.

Each prediction repeats the wording of docs/PREREGISTRATION.md exactly (a test
checks this), and states how the observed value is read from results/*.json and
how HIT or MISS is decided. Nothing here may be changed after results exist,
except through a dated amendment in the preregistration.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Results = dict[str, dict[str, Any]]


@dataclass(frozen=True)
class Prediction:
    id: str
    experiment: str
    text: str
    observe: Callable[[Results], tuple[str, bool]]


def _est(node: dict[str, Any] | None) -> float | None:
    if not node:
        return None
    value = node.get("estimate")
    return None if value is None else float(value)


def _fmt(value: float | None, digits: int = 3) -> str:
    return "undefined" if value is None else f"{value:.{digits}f}"


def _in(value: float | None, low: float, high: float) -> bool:
    return value is not None and low <= value <= high


# E1 -----------------------------------------------------------------------------


def _e1(r: Results) -> dict[str, Any]:
    faults: dict[str, Any] = r["e1_fault_detection"]["faults"]
    return faults


def p1_1(r: Results) -> tuple[str, bool]:
    good = 0
    for fault in _e1(r).values():
        recalls = [_est(b["recall"]) for b in fault["by_rate"].values()]
        if all(v is not None and v >= 0.95 for v in recalls):
            good += 1
    return f"{good} of 25 faults", good >= 22


def p1_2(r: Results) -> tuple[str, bool]:
    worst = None
    bad = []
    for fid, fault in _e1(r).items():
        for rate, b in fault["by_rate"].items():
            v = _est(b["precision"])
            if v is None:
                continue
            worst = v if worst is None else min(worst, v)
            if v < 0.95:
                bad.append(f"{fid} at {rate}")
    text = f"lowest mean precision {_fmt(worst)}"
    if bad:
        text += f"; below 0.95: {', '.join(bad)}"
    return text, not bad


def p1_3(r: Results) -> tuple[str, bool]:
    v = _est(_e1(r)["F03"]["by_rate"]["0.05"]["recall"])
    return f"recall {_fmt(v)}", _in(v, 0.85, 0.99)


def p1_4(r: Results) -> tuple[str, bool]:
    values = [_est(f["combined"]["recall"]) for f in _e1(r).values()]
    finite = [v for v in values if v is not None]
    mean = sum(finite) / len(finite) if finite else None
    return f"mean recall {_fmt(mean)}", _in(mean, 0.85, 1.0)


def p1_5(r: Results) -> tuple[str, bool]:
    values = [_est(f["combined"]["precision_any"]) for f in _e1(r).values()]
    finite = [v for v in values if v is not None]
    mean = sum(finite) / len(finite) if finite else None
    return f"mean precision against any fault {_fmt(mean)}", mean is not None and mean >= 0.95


def p1_6(r: Results) -> tuple[str, bool]:
    n = sum(1 for f in _e1(r).values() if (_est(f.get("schema_baseline_recall")) or 0.0) >= 0.5)
    return f"{n} of 25 faults", n < 13


# E2 -----------------------------------------------------------------------------


def _e2(r: Results, scenario: str, metric: str) -> float | None:
    return _est(r["e2_entity_resolution"]["summary"][scenario][metric])


def p2_range(
    scenario: str, metric: str, low: float, high: float
) -> Callable[[Results], tuple[str, bool]]:
    def check(r: Results) -> tuple[str, bool]:
        v = _e2(r, scenario, metric)
        return f"{metric} {_fmt(v)}", _in(v, low, high)

    return check


def p2_at_least(scenario: str, metric: str, floor: float) -> Callable[[Results], tuple[str, bool]]:
    def check(r: Results) -> tuple[str, bool]:
        v = _e2(r, scenario, metric)
        return f"{metric} {_fmt(v)}", v is not None and v >= floor

    return check


def p2_7(r: Results) -> tuple[str, bool]:
    naive = _est(r["e2_entity_resolution"]["naive_baseline"]["clean"]["precision"])
    ours = _e2(r, "clean", "precision")
    ok = naive is not None and ours is not None and naive < ours
    return f"naive {_fmt(naive)} against matcher {_fmt(ours)}", ok


# E3 -----------------------------------------------------------------------------


def _e3(r: Results, key: str) -> float | None:
    return _est(r["e3_blackspot_ranking"]["summary"].get(key))


def p3_1(r: Results) -> tuple[str, bool]:
    v = _e3(r, "eb_recall_rankable")
    return f"EB recall_rankable {_fmt(v)}", _in(v, 0.45, 0.80)


def p3_greater(other: str, label: str) -> Callable[[Results], tuple[str, bool]]:
    def check(r: Results) -> tuple[str, bool]:
        eb, o = _e3(r, "eb_recall_rankable"), _e3(r, f"{other}_recall_rankable")
        ok = eb is not None and o is not None and eb > o
        return f"EB {_fmt(eb)} against {label} {_fmt(o)}", ok

    return check


def p3_4(r: Results) -> tuple[str, bool]:
    v = _e3(r, "raw_count_recall_all")
    return f"raw count recall_all {_fmt(v)}", _in(v, 0.20, 0.50)


def p3_5(r: Results) -> tuple[str, bool]:
    v = _e3(r, "eb_coverage")
    return f"EB coverage {_fmt(v)}", _in(v, 0.80, 0.95)


def p3_6(r: Results) -> tuple[str, bool]:
    c_eb, c_qp = _e3(r, "eb_coverage"), _e3(r, "eb_qp_coverage")
    w_eb, w_qp = _e3(r, "eb_width"), _e3(r, "eb_qp_width")
    ok = None not in (c_eb, c_qp, w_eb, w_qp) and c_qp >= c_eb and w_qp > w_eb  # type: ignore[operator]
    return (
        f"coverage {_fmt(c_qp)} against {_fmt(c_eb)}; "
        f"width {_fmt(w_qp, 1)} against {_fmt(w_eb, 1)}",
        bool(ok),
    )


def p3_7(r: Results) -> tuple[str, bool]:
    eb, qp = _e3(r, "eb_recall_rankable"), _e3(r, "eb_qp_recall_rankable")
    ok = eb is not None and qp is not None and abs(qp - eb) <= 0.05
    return f"EB+QP {_fmt(qp)} against EB {_fmt(eb)}", ok


# E4 -----------------------------------------------------------------------------


def _e4(r: Results, scenario: str, metric: str = "kendall_tau") -> float | None:
    return _est(r["e4_robustness"]["summary"][scenario]["eb"][metric])


def p4_1(r: Results) -> tuple[str, bool]:
    v = _e4(r, "drop_D")
    return f"Kendall tau {_fmt(v)}", v is not None and v >= 0.90


def p4_2(r: Results) -> tuple[str, bool]:
    taus = {s: _e4(r, s) for s in ("drop_A", "drop_B", "drop_C", "drop_D")}
    finite = {k: v for k, v in taus.items() if v is not None}
    lowest = min(finite, key=lambda k: finite[k]) if finite else None
    text = ", ".join(f"{k} {_fmt(v)}" for k, v in taus.items())
    return text, lowest == "drop_B"


def p4_3(r: Results) -> tuple[str, bool]:
    v = _e4(r, "faults_5pct")
    return f"Kendall tau {_fmt(v)}", _in(v, 0.75, 0.95)


def p4_4(r: Results) -> tuple[str, bool]:
    a, b = _e4(r, "faults_5pct"), _e4(r, "faults_20pct")
    ok = a is not None and b is not None and b < a
    return f"20 percent {_fmt(b)} against 5 percent {_fmt(a)}", ok


def p4_5(r: Results) -> tuple[str, bool]:
    v = _e4(r, "faults_20pct", "top_k_overlap")
    return f"top 12 overlap {_fmt(v)}", _in(v, 0.40, 0.80)


# E5 -----------------------------------------------------------------------------


def _e5(r: Results) -> dict[str, Any]:
    summary: dict[str, Any] = r["e5_tasking"]["summary"]
    return summary


def p5_1(r: Results) -> tuple[str, bool]:
    n = int(_e5(r)["seeds_voi_beats_random"])
    total = len(r["e5_tasking"]["seeds"])
    return f"{n} of {total} seeds", n >= 18


def p5_2(r: Results) -> tuple[str, bool]:
    n = int(_e5(r)["seeds_voi_beats_greedy"])
    total = len(r["e5_tasking"]["seeds"])
    return f"{n} of {total} seeds", n >= 15


def p5_3(r: Results) -> tuple[str, bool]:
    v = _est(_e5(r)["value_of_information_reduction"])
    return f"mean reduction {_fmt(v)}", _in(v, 0.10, 0.40)


PREDICTIONS: tuple[Prediction, ...] = (
    Prediction(
        "P1.1",
        "E1",
        "in isolation, at least 22 of the 25 faults have mean recall of "
        "at least 0.95 at every rate.",
        p1_1,
    ),
    Prediction(
        "P1.2",
        "E1",
        "in isolation, every fault has mean precision of at least 0.95 at "
        "every rate where at least one unit is flagged.",
        p1_2,
    ),
    Prediction(
        "P1.3",
        "E1",
        "F03 (local time labelled as UTC) has mean recall between 0.85 and "
        "0.99 at 5 percent, because crash records that no other producer reported cannot "
        "be compared.",
        p1_3,
    ),
    Prediction(
        "P1.4",
        "E1",
        "in the combined scenario, mean recall over the 25 faults is between 0.85 and 1.00.",
        p1_4,
    ),
    Prediction(
        "P1.5",
        "E1",
        "in the combined scenario, mean precision against any fault over the "
        "25 faults is at least 0.95.",
        p1_5,
    ),
    Prediction(
        "P1.6",
        "E1",
        "the schema only baseline detects fewer than 13 of the 25 faults "
        "with recall of at least 0.5, because many faults (swapped axes, wrong units, stuck "
        "sensors, duplicates, offsets, gaps, partial periods) produce records that are "
        "each individually valid.",
        p1_6,
    ),
    Prediction("P2.1", "E2", "clean F1 between 0.97 and 1.00.", p2_range("clean", "f1", 0.97, 1.0)),
    Prediction(
        "P2.2", "E2", "clean precision of at least 0.99.", p2_at_least("clean", "precision", 0.99)
    ),
    Prediction(
        "P2.3",
        "E2",
        "clean abstention rate between 0.01 and 0.06.",
        p2_range("clean", "abstention_rate", 0.01, 0.06),
    ),
    Prediction(
        "P2.4",
        "E2",
        "faults_5pct recall between 0.55 and 0.80.",
        p2_range("faults_5pct", "recall", 0.55, 0.80),
    ),
    Prediction(
        "P2.5",
        "E2",
        "faults_5pct precision of at least 0.98.",
        p2_at_least("faults_5pct", "precision", 0.98),
    ),
    Prediction(
        "P2.6",
        "E2",
        "faults_5pct abstention rate between 0.05 and 0.15.",
        p2_range("faults_5pct", "abstention_rate", 0.05, 0.15),
    ),
    Prediction(
        "P2.7", "E2", "the naive baseline has lower clean precision than the matcher.", p2_7
    ),
    Prediction("P3.1", "E3", "EB `recall_rankable` between 0.45 and 0.80.", p3_1),
    Prediction(
        "P3.2",
        "E3",
        "EB `recall_rankable` is higher than rate `recall_rankable`.",
        p3_greater("rate", "rate"),
    ),
    Prediction(
        "P3.3",
        "E3",
        "EB `recall_rankable` is higher than raw count `recall_rankable`.",
        p3_greater("raw_count", "raw count"),
    ),
    Prediction("P3.4", "E3", "raw count `recall_all` is between 0.20 and 0.50.", p3_4),
    Prediction("P3.5", "E3", "EB 90 percent rank interval coverage between 0.80 and 0.95.", p3_5),
    Prediction(
        "P3.6",
        "E3",
        "EB+QP coverage is at least EB coverage, and EB+QP mean interval "
        "width is larger than EB mean width.",
        p3_6,
    ),
    Prediction(
        "P3.7", "E3", "EB+QP `recall_rankable` is within 0.05 of EB `recall_rankable`.", p3_7
    ),
    Prediction(
        "P4.1",
        "E4",
        "dropping D (fatal and serious crashes only, mostly duplicates of B) "
        "leaves Kendall tau of at least 0.90.",
        p4_1,
    ),
    Prediction(
        "P4.2", "E4", "dropping B gives the lowest Kendall tau of the four producer drops.", p4_2
    ),
    Prediction("P4.3", "E4", "Kendall tau at 5 percent faults is between 0.75 and 0.95.", p4_3),
    Prediction(
        "P4.4", "E4", "Kendall tau at 20 percent faults is lower than at 5 percent faults.", p4_4
    ),
    Prediction("P4.5", "E4", "top 12 overlap at 20 percent faults is between 0.40 and 0.80.", p4_5),
    Prediction(
        "P5.1",
        "E5",
        "value of information reduces the uncertainty mass by more than random in at least "
        "18 of 20 seeds.",
        p5_1,
    ),
    Prediction(
        "P5.2",
        "E5",
        "value of information reduces it by more than greedy by crash count in at least 15 of "
        "20 seeds.",
        p5_2,
    ),
    Prediction(
        "P5.3",
        "E5",
        "the mean relative reduction with value of information is between 0.10 and 0.40.",
        p5_3,
    ),
)

RESULT_FILES = {
    "E1": "e1_fault_detection",
    "E2": "e2_entity_resolution",
    "E3": "e3_blackspot_ranking",
    "E4": "e4_robustness",
    "E5": "e5_tasking",
}


def judge(results: Results) -> list[dict[str, Any]]:
    """HIT or MISS for every prediction whose experiment has results."""
    out = []
    for p in PREDICTIONS:
        if RESULT_FILES[p.experiment] not in results:
            out.append(
                {
                    "id": p.id,
                    "experiment": p.experiment,
                    "text": p.text,
                    "observed": "not run yet",
                    "verdict": "PENDING",
                }
            )
            continue
        observed, hit = p.observe(results)
        out.append(
            {
                "id": p.id,
                "experiment": p.experiment,
                "text": p.text,
                "observed": observed,
                "verdict": "HIT" if hit else "MISS",
            }
        )
    return out
