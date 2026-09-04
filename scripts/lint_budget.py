#!/usr/bin/env python3
"""Ratchet for `ruff check`: fail only when lint findings *increase*.

The codebase carries ~900 pre-existing findings. Gating CI on zero would mean
either a huge unrelated cleanup commit or a permanently red build, so this
enforces the useful invariant instead: a change may fix findings, and may not
add them. When the count drops, the budget is rewritten so the gain is locked
in and cannot be spent later.

    python scripts/lint_budget.py          # check against the budget
    python scripts/lint_budget.py --update # adopt the current count
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUDGET_FILE = REPO / ".lint-budget"
TARGETS = ["src", "tests"]


def current_count() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", *TARGETS, "--output-format=concise"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    # ruff exits 1 when it finds anything; only a crash (2) is an error here.
    if proc.returncode not in (0, 1):
        sys.exit(f"ruff failed to run:\n{proc.stderr}")
    return sum(1 for line in proc.stdout.splitlines() if ":" in line)


def read_budget() -> int | None:
    if not BUDGET_FILE.exists():
        return None
    text = BUDGET_FILE.read_text().strip()
    return int(text) if text else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="adopt the current count")
    args = parser.parse_args()

    count = current_count()
    budget = read_budget()

    if args.update or budget is None:
        BUDGET_FILE.write_text(f"{count}\n")
        print(f"lint budget set to {count}")
        return 0

    if count > budget:
        print(
            f"FAIL: ruff findings rose from {budget} to {count} (+{count - budget}).\n"
            f"Fix the new findings, or run `python scripts/lint_budget.py --update` "
            f"only if the increase is genuinely intended.",
            file=sys.stderr,
        )
        return 1

    if count < budget:
        BUDGET_FILE.write_text(f"{count}\n")
        print(f"lint budget improved: {budget} -> {count}. Commit .lint-budget.")
        return 0

    print(f"lint findings unchanged at {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
