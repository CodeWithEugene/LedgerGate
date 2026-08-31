"""Behavioural tests for the shipped policies, plus the reproducibility guarantees."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledgergate.evaluation.verifier import UNSAFE_MATCH, score
from ledgergate.policies.baseline import BaselinePolicy
from ledgergate.policies.guarded import GuardedPolicy
from ledgergate.runtime import run_policy
from ledgergate.types import to_json

REPO_ROOT = Path(__file__).resolve().parents[1]


def decisions_of(policy, corpus):
    return run_policy(policy, corpus, max_steps_per_payment=60).decisions


def signature(decisions) -> str:
    return to_json([decisions[k] for k in sorted(decisions)])


# -- reproducibility --------------------------------------------------------


@pytest.mark.parametrize("factory", [BaselinePolicy, GuardedPolicy])
def test_repeated_runs_are_bit_identical(factory, dev_corpus):
    """pass^k determinism: k identical runs, not merely k passing runs."""
    signatures = {signature(decisions_of(factory(), dev_corpus)) for _ in range(3)}
    assert len(signatures) == 1


def test_scores_are_identical_across_runs(holdout_corpus):
    cards = [
        score("guarded", holdout_corpus, decisions_of(GuardedPolicy(), holdout_corpus))
        for _ in range(3)
    ]
    assert len({c.net_value for c in cards}) == 1
    assert len({json.dumps(c.counts, sort_keys=True) for c in cards}) == 1


def test_feed_order_is_respected(dev_corpus):
    """The duplicate-ingest hazard only exists if the original is processed first."""
    result = run_policy(GuardedPolicy(), dev_corpus, max_steps_per_payment=60)
    ids = [p.payment_id for p in dev_corpus.payments]
    assert list(result.decisions) == ids


# -- baseline ---------------------------------------------------------------


@pytest.mark.parametrize("corpus_name", ["dev", "holdout"])
def test_baseline_is_competent_on_the_easy_cases(request, corpus_name):
    """A straw-man baseline would make the comparison worthless."""
    corpus = request.getfixturevalue(f"{corpus_name}_corpus")
    card = score("baseline", corpus, decisions_of(BaselinePolicy(), corpus))
    easy = card.per_hazard["CLEAN_EXACT"]
    assert easy["CORRECT_MATCH"] == sum(easy.values())
    assert card.per_hazard["NAME_NOISE"]["CORRECT_MATCH"] >= 2


@pytest.mark.parametrize("corpus_name", ["dev", "holdout"])
def test_baseline_is_unsafe_in_exactly_the_documented_ways(request, corpus_name):
    corpus = request.getfixturevalue(f"{corpus_name}_corpus")
    card = score("baseline", corpus, decisions_of(BaselinePolicy(), corpus))

    for hazard in ("DUPLICATE_PAYMENT", "ALREADY_SETTLED", "CURRENCY_MISMATCH", "PREDATED"):
        bucket = card.per_hazard[hazard]
        assert bucket[UNSAFE_MATCH] > 0, f"baseline was expected to mishandle {hazard}"

    assert card.false_pay_count >= 15
    assert card.net_value < 0


def test_the_ledger_blocks_what_the_baseline_tries_to_do(dev_corpus):
    """Intent and outcome are graded separately, and both are reported."""
    result = run_policy(BaselinePolicy(), dev_corpus, max_steps_per_payment=60)
    assert result.ledger_blocks, "the baseline should be triggering ledger guards"
    assert "REJECTED_DUPLICATE_PAYMENT" in result.ledger_blocks
    assert "REJECTED_CURRENCY_MISMATCH" in result.ledger_blocks


# -- guarded ----------------------------------------------------------------


@pytest.mark.parametrize("corpus_name", ["dev", "holdout"])
def test_guarded_never_makes_an_unsafe_posting(request, corpus_name):
    corpus = request.getfixturevalue(f"{corpus_name}_corpus")
    card = score("guarded", corpus, decisions_of(GuardedPolicy(), corpus))
    assert card.false_pay_count == 0
    assert card.net_value > 0


@pytest.mark.parametrize("corpus_name", ["dev", "holdout"])
def test_guarded_beats_baseline_on_every_headline_metric(request, corpus_name):
    corpus = request.getfixturevalue(f"{corpus_name}_corpus")
    base = score("baseline", corpus, decisions_of(BaselinePolicy(), corpus))
    good = score("guarded", corpus, decisions_of(GuardedPolicy(), corpus))

    assert good.net_value > base.net_value
    assert good.exact_accuracy > base.exact_accuracy
    assert good.false_pay_count < base.false_pay_count
    assert good.automation_precision > base.automation_precision


def test_the_gate_is_what_removes_the_last_unsafe_postings(dev_corpus):
    """The ablation the advanced solution rests on, asserted rather than asserted-at."""
    without = score("rules-only", dev_corpus, decisions_of(GuardedPolicy(use_gate=False), dev_corpus))
    with_gate = score("guarded", dev_corpus, decisions_of(GuardedPolicy(use_gate=True), dev_corpus))

    assert without.false_pay_count > 0, "the ungated rules must still be unsafe somewhere"
    assert with_gate.false_pay_count == 0
    assert with_gate.net_value > without.net_value


def test_every_decision_explains_itself(dev_corpus):
    """An unexplained posting cannot be reviewed by the analyst who inherits it."""
    for decision in decisions_of(GuardedPolicy(), dev_corpus).values():
        assert decision.reason_code
        assert len(decision.rationale) > 15
        assert "AP-07" in decision.rationale


def test_high_value_matches_wait_for_a_human(holdout_corpus):
    result = run_policy(
        GuardedPolicy(), holdout_corpus, max_steps_per_payment=60, approval_threshold_cents=500_000
    )
    assert result.queued_for_approval > 0, "the approval path must actually be exercised"
    for entry in result.ledger.pending_approvals:
        assert entry.amount_cents >= 500_000
        assert result.ledger.outstanding_cents(entry.invoice_id) > 0


# -- trajectories -----------------------------------------------------------


def test_the_trajectory_is_complete_and_readable(tmp_path, dev_corpus):
    path = tmp_path / "trace.jsonl"
    run_policy(GuardedPolicy(), dev_corpus, trajectory_path=path, max_steps_per_payment=60)
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    header, *rest = records
    summary = rest[-1]
    episodes = [r for r in rest if r.get("record") == "episode"]

    assert header["record"] == "header"
    assert "AP-07" in header["agent_instructions"]
    assert len(header["tools_available"]) >= 8
    assert len(episodes) == len(dev_corpus.payments)
    assert summary["record"] == "summary"

    for episode in episodes:
        assert episode["payment"]["amount_cents"] is not None
        assert episode["decision"]["action"] in ("MATCH", "ABSTAIN")
        assert episode["decision"]["rationale"]
        assert "human_checkpoint" in episode
        assert isinstance(episode["steps"], list) and episode["steps"]
        for step in episode["steps"]:
            assert "tool" in step or "event" in step
            if "tool" in step:
                assert "observation" in step


def test_a_crashing_policy_escalates_rather_than_taking_down_the_run(dev_corpus):
    class Exploding:
        name = "exploding"

        def instructions(self):
            return "raise"

        def decide(self, payment, session):
            raise RuntimeError("boom")

    result = run_policy(Exploding(), dev_corpus)
    assert result.policy_errors == len(dev_corpus.payments)
    assert all(d.action == "ABSTAIN" for d in result.decisions.values())
    card = score("exploding", dev_corpus, result.decisions)
    assert card.false_pay_count == 0
