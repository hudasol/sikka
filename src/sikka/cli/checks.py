"""The fast check: lint, format, types, import contracts and unit tests.

Every tool runs through the current interpreter (``python -m ...``) so the
check behaves the same on Windows, macOS and Linux.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

COVERAGE_FLOOR = 85


@dataclass(frozen=True)
class Step:
    name: str
    argv: list[str]


def fast_check_steps(*, with_coverage: bool = True) -> list[Step]:
    py = sys.executable
    workers = str(max(1, min(4, os.cpu_count() or 1)))
    pytest_argv = [py, "-m", "pytest", "-q", "-n", workers, "-m", "not slow and not perf"]
    if with_coverage:
        pytest_argv += [
            "--cov=sikka",
            "--cov-report=term",
            f"--cov-fail-under={COVERAGE_FLOOR}",
        ]
    return [
        Step("ruff lint", [py, "-m", "ruff", "check", "src", "tests"]),
        Step("ruff format", [py, "-m", "ruff", "format", "--check", "src", "tests"]),
        Step("mypy strict", [py, "-m", "mypy"]),
        Step(
            "import contracts",
            [
                py,
                "-c",
                "import sys; from importlinter.cli import lint_imports; sys.exit(lint_imports())",
            ],
        ),
        Step("pytest", pytest_argv),
    ]


def run_steps(steps: list[Step], root: Path) -> list[tuple[str, int, float]]:
    """Run each step from ``root`` and return (name, exit code, seconds)."""
    outcomes: list[tuple[str, int, float]] = []
    for step in steps:
        print(f"==> {step.name}", flush=True)
        started = time.perf_counter()
        code = subprocess.call(step.argv, cwd=root)
        outcomes.append((step.name, code, time.perf_counter() - started))
    return outcomes
