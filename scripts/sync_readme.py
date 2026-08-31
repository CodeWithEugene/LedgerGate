#!/usr/bin/env python3
"""Paste the generated headline table into the README, between its markers.

A number that a human transcribed into a README is a claim. A number a script
copied out of the run that produced it is a result. This is the script, and
``tests/test_submission.py`` fails if the README and the generated table ever
disagree -- so the only way to publish a figure here is to have generated it.

    python3 scripts/sync_readme.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
GENERATED = REPO_ROOT / "results" / "headline.holdout.md"

BEGIN = "<!-- BEGIN HEADLINE -->"
END = "<!-- END HEADLINE -->"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if the README is stale, and change nothing")
    args = parser.parse_args()

    if not GENERATED.exists():
        print(f"{GENERATED.relative_to(REPO_ROOT)} is missing; run 'make headline' first",
              file=sys.stderr)
        return 2

    table = GENERATED.read_text(encoding="utf-8").strip()
    readme = README.read_text(encoding="utf-8")

    if BEGIN not in readme or END not in readme:
        print(f"README is missing the {BEGIN} / {END} markers", file=sys.stderr)
        return 2

    head, rest = readme.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    updated = f"{head}{BEGIN}\n```\n{table}\n```\n{END}{tail}"

    if updated == readme:
        print("README headline is current")
        return 0

    if args.check:
        print("README headline is stale; run 'make sync-readme'", file=sys.stderr)
        return 1

    README.write_text(updated, encoding="utf-8")
    print(f"README headline updated from {GENERATED.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
