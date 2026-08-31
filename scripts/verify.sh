#!/usr/bin/env sh
# The full offline verification gate.
#
# This is the single definition of "does this repository check out". Both
# `make verify` and the Docker image run this exact script, so the container
# cannot drift away from the local run.
#
# Needs no network access and no API credential. Every policy exercised here is
# deterministic; the optional model-driven arm is not part of this gate.
#
#   PYTHON=.venv/bin/python ./scripts/verify.sh
set -eu

cd "$(dirname "$0")/.."

PYTHON=${PYTHON:-python3}
PYTHONPATH=src
export PYTHONPATH

step() {
    echo
    echo "=============================================================="
    echo "  $1"
    echo "=============================================================="
}

step "1/6  corpus integrity: hashes and ground-truth invariants"
$PYTHON -m ledgergate.cli audit

step "2/6  test suite"
$PYTHON -m pytest

step "3/6  baseline solution (holdout)"
$PYTHON -m ledgergate.cli run --policy baseline --corpus holdout

step "4/6  advanced solution (holdout)"
$PYTHON -m ledgergate.cli run --policy guarded --corpus holdout

step "5/6  headline: the gate across the full range of proposer quality"
$PYTHON -m ledgergate.cli compare --corpus holdout --policies \
    reckless reckless+gate \
    baseline baseline+gate \
    rules-only guarded

step "6/6  gate audit: every decision the gate changed, and why"
$PYTHON -m ledgergate.cli gate-audit --proposer rules-only --corpus holdout

# The model-driven arm is optional and is NOT part of this gate. It needs a
# credential to record and committed cassettes to replay; see docs/PROBLEM.md
# ("The model arm, and why it is not the headline"). When cassettes are
# present, `make headline-llm` adds those rows to the same table.

echo
echo "=============================================================="
echo "  OK  corpus intact, tests green, baseline and advanced scored,"
echo "      every gate intervention accounted for against ground truth."
echo "=============================================================="
