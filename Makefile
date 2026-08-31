# LedgerGate. Every published number comes from a target in this file.
#
#   make setup           create .venv and install the pinned test dependency
#   make verify          the full offline gate: corpus audit + tests + both evals
#   make eval-baseline   score the baseline on the holdout split
#   make eval-advanced   score the advanced solution on the holdout split
#   make headline        the comparison table that appears in the README
#
# Nothing in `make verify` needs network access or an API key. The optional
# model-driven arm is behind `make record-llm`; see docs/PROBLEM.md.

PY ?= python3
VENV := .venv
VPY := $(VENV)/bin/python
export PYTHONPATH := src

HOLDOUT := --corpus holdout
DEV := --corpus dev

.DEFAULT_GOAL := help
.PHONY: help setup corpus audit test eval-baseline eval-advanced headline \
        gate-audit sync-readme ablation approve verify clean docker-verify \
        trace-sample record-llm headline-llm demo

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t22

setup: ## create the virtualenv and install pinned dev dependencies
	$(PY) -m venv $(VENV)
	$(VPY) -m pip install --quiet --upgrade pip
	$(VPY) -m pip install --quiet -r requirements-dev.txt
	@echo "ready: run 'make verify'"

corpus: ## regenerate both synthetic splits from their seeds
	$(PY) -m ledgergate.cli corpus

audit: ## verify corpus hashes and re-derive every ground-truth invariant
	$(PY) -m ledgergate.cli audit

test: ## run the test suite
	$(VPY) -m pytest

eval-baseline: ## the baseline solution on the holdout split
	$(PY) -m ledgergate.cli run --policy baseline $(HOLDOUT)

eval-advanced: ## the advanced solution on the holdout split
	$(PY) -m ledgergate.cli run --policy guarded $(HOLDOUT)

headline: ## the gate measured across the full range of proposer quality
	$(PY) -m ledgergate.cli compare $(HOLDOUT) --policies \
		reckless reckless+gate \
		baseline baseline+gate \
		rules-only guarded

gate-audit: ## show every decision the gate changed, on what clause, vs ground truth
	$(PY) -m ledgergate.cli gate-audit --proposer rules-only $(HOLDOUT)

sync-readme: ## paste the generated headline table back into the README
	$(PY) scripts/sync_readme.py

ablation: ## the same curve on the development split
	$(PY) -m ledgergate.cli compare $(DEV) --policies \
		reckless reckless+gate \
		baseline baseline+gate \
		rules-only guarded

# -- optional: the model-driven arm ----------------------------------------
# Needs an API credential to record, and committed cassettes to replay. It is
# deliberately outside `make verify` so that the published result never depends
# on a credential a reviewer does not have. See docs/PROBLEM.md.

record-llm: ## record live model responses into cassettes (needs ANTHROPIC_API_KEY)
	./scripts/record_llm.sh

headline-llm: ## the curve with the model rows added (needs cassettes)
	$(PY) -m ledgergate.cli compare $(HOLDOUT) --policies \
		reckless reckless+gate \
		baseline baseline+gate \
		rules-only guarded \
		llm llm-gated

approve: ## show the human approval queue the advanced solution produced
	$(PY) -m ledgergate.cli approve --policy guarded $(HOLDOUT)

demo: ## walk the video beats in order, one keypress apart (see docs/VIDEO_SCRIPT.md)
	PYTHON=$(VPY) sh scripts/demo.sh

trace-sample: ## print one full agent trajectory, readable end to end
	$(PY) scripts/show_trace.py

verify: ## everything, offline: audit + tests + baseline + advanced + headline
	PYTHON=$(VPY) ./scripts/verify.sh

docker-verify: ## the identical gate inside a clean container, with no network
	docker build -t ledgergate:verify .
	docker run --rm --network none ledgergate:verify

clean:
	rm -rf $(VENV) .pytest_cache results/*.json traces/*.jsonl
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
