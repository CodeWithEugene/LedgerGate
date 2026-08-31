"""The verifier must be hard to game and must rank policies the way a CFO would."""

from __future__ import annotations

import pytest
from conftest import AlwaysAbstainPolicy, AlwaysMatchPolicy, OraclePolicy

from ledgergate.evaluation.verifier import (
    CORRECT_ABSTAIN,
    CORRECT_MATCH,
    OVER_ESCALATION,
    UNSAFE_MATCH,
    WRONG_AMOUNT,
    WRONG_INVOICE,
    CostModel,
    classify,
    score,
    sweep_cost_models,
    verifier_fingerprint,
)
from ledgergate.policies.baseline import BaselinePolicy
from ledgergate.policies.guarded import GuardedPolicy
from ledgergate.runtime import run_policy
from ledgergate.types import Allocation, Decision, Truth


def truth(action="MATCH", allocations=(("INV1", 100),)):
    return Truth("P1", "CLEAN_EXACT", action, tuple(Allocation(*a) for a in allocations))


def decision(action="MATCH", allocations=(("INV1", 100),)):
    return Decision("P1", action, tuple(Allocation(*a) for a in allocations))


def test_classification_covers_every_outcome():
    assert classify(decision(), truth()).outcome == CORRECT_MATCH
    assert classify(decision("ABSTAIN", ()), truth("ABSTAIN", ())).outcome == CORRECT_ABSTAIN
    assert classify(decision("ABSTAIN", ()), truth()).outcome == OVER_ESCALATION
    assert classify(decision(), truth("ABSTAIN", ())).outcome == UNSAFE_MATCH
    assert classify(decision(allocations=(("INV2", 100),)), truth()).outcome == WRONG_INVOICE
    assert classify(decision(allocations=(("INV1", 99),)), truth()).outcome == WRONG_AMOUNT


def test_allocation_order_does_not_change_the_grade():
    t = truth(allocations=(("INV1", 60), ("INV2", 40)))
    forward = decision(allocations=(("INV1", 60), ("INV2", 40)))
    reversed_ = decision(allocations=(("INV2", 40), ("INV1", 60)))
    assert classify(forward, t).outcome == classify(reversed_, t).outcome == CORRECT_MATCH


def test_a_missing_decision_is_graded_not_skipped(dev_corpus):
    """Otherwise a policy could raise its average by emitting fewer rows."""
    card = score("silent", dev_corpus, {})
    assert card.total_payments == len(dev_corpus.payments)
    assert card.counts[CORRECT_MATCH] == 0
    assert card.counts[OVER_ESCALATION] > 0
    assert card.counts[CORRECT_ABSTAIN] + card.counts[OVER_ESCALATION] == card.total_payments


def test_confidence_claimed_by_the_policy_cannot_influence_the_score():
    high = Decision("P1", "MATCH", (Allocation("INV2", 100),), rationale="absolutely certain")
    low = Decision("P1", "MATCH", (Allocation("INV2", 100),), rationale="a wild guess")
    assert classify(high, truth()).outcome == classify(low, truth()).outcome == WRONG_INVOICE


@pytest.mark.parametrize("corpus_name", ["dev", "holdout"])
def test_constant_policies_lose_to_a_policy_that_discriminates(request, corpus_name):
    """The central anti-gaming property of the cost model."""
    corpus = request.getfixturevalue(f"{corpus_name}_corpus")

    abstain = score("abstain", corpus, run_policy(AlwaysAbstainPolicy(), corpus).decisions)
    match_all = score("match", corpus, run_policy(AlwaysMatchPolicy(), corpus).decisions)
    guarded = score("guarded", corpus, run_policy(GuardedPolicy(), corpus, max_steps_per_payment=60).decisions)

    assert guarded.net_value > abstain.net_value
    assert guarded.net_value > match_all.net_value
    assert match_all.net_value < 0, "reckless automation must be worse than doing nothing"
    # Escalating everything is safe but close to worthless, not a winning strategy.
    assert abstain.false_pay_count == 0
    assert abstain.net_value < guarded.net_value


def test_the_ranking_survives_any_reasonable_false_pay_penalty(dev_corpus):
    """If the ordering only holds at one weight, it is an artefact of the weight."""
    baseline = score("baseline", dev_corpus, run_policy(BaselinePolicy(), dev_corpus).decisions)
    guarded = score(
        "guarded", dev_corpus, run_policy(GuardedPolicy(), dev_corpus, max_steps_per_payment=60).decisions
    )

    for cheap, good in zip(sweep_cost_models(baseline), sweep_cost_models(guarded)):
        assert cheap["false_pay_penalty"] == good["false_pay_penalty"]
        assert good["net_value"] > cheap["net_value"], (
            f"ranking flips at penalty {good['false_pay_penalty']}"
        )


def test_a_false_pay_always_costs_more_than_an_unnecessary_escalation():
    model = CostModel()
    assert model.value(UNSAFE_MATCH) < model.value(OVER_ESCALATION)
    assert model.value(WRONG_INVOICE) < model.value(OVER_ESCALATION)
    assert model.value(CORRECT_MATCH) > model.value(CORRECT_ABSTAIN) > 0
    assert model.value(OVER_ESCALATION) < 0


def test_metrics_are_consistent_with_each_other(dev_corpus):
    card = score("guarded", dev_corpus, run_policy(GuardedPolicy(), dev_corpus, max_steps_per_payment=60).decisions)
    assert sum(card.counts.values()) == card.total_payments
    assert 0.0 <= card.exact_accuracy <= 1.0
    assert 0.0 <= card.coverage <= 1.0
    assert 0.0 <= card.automation_precision <= 1.0
    assert card.false_pay_count == card.counts[WRONG_INVOICE] + card.counts[UNSAFE_MATCH]
    assert sum(sum(b.values()) for b in card.per_hazard.values()) == card.total_payments


def test_the_verifier_records_its_own_fingerprint(dev_corpus):
    """So a reviewer can confirm scoring did not change between two runs."""
    card = score("x", dev_corpus, {})
    assert card.verifier_sha256 == verifier_fingerprint()
    assert len(card.verifier_sha256) == 64


def test_the_oracle_is_the_ceiling_and_nothing_beats_it(dev_corpus):
    oracle = score("oracle", dev_corpus, run_policy(OraclePolicy(dev_corpus), dev_corpus).decisions)
    guarded = score(
        "guarded", dev_corpus, run_policy(GuardedPolicy(), dev_corpus, max_steps_per_payment=60).decisions
    )
    assert oracle.exact_accuracy == 1.0
    assert guarded.net_value <= oracle.net_value
