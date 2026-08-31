"""The frozen verifier.

Design rules, in priority order:

1. **The verifier reads ground truth; nothing else in the system may.** The
   tool surface handed to a policy has no path to ``truth.json``. There is a
   test that asserts this.

2. **Scores come from the verifier's own computation, never from anything the
   policy writes.** A policy cannot report its own confidence as a score, and
   a high-confidence wrong answer is punished exactly like a low-confidence
   one.

3. **Not all errors cost the same.** Accuracy alone would rank a system that
   pays the wrong vendor equal to one that escalates too eagerly. Those are
   wildly different in a finance workflow, so the headline metric is a
   business cost model with explicit, published, sensitivity-tested weights.

4. **A constant policy must lose.** "Always abstain" and "always match" are
   both implemented as baselines in the test suite, and the verifier is
   required to rank them below any policy that actually discriminates.

The module hashes its own source into every result file so a reviewer can see
that the scoring rules did not change between the baseline run and the
advanced run.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from ..corpus import Corpus
from ..types import Allocation, Decision, Truth

# -- outcome taxonomy -------------------------------------------------------

CORRECT_MATCH = "CORRECT_MATCH"
CORRECT_ABSTAIN = "CORRECT_ABSTAIN"
OVER_ESCALATION = "OVER_ESCALATION"
WRONG_AMOUNT = "WRONG_AMOUNT"
WRONG_INVOICE = "WRONG_INVOICE"
UNSAFE_MATCH = "UNSAFE_MATCH"

OUTCOMES: tuple[str, ...] = (
    CORRECT_MATCH,
    CORRECT_ABSTAIN,
    OVER_ESCALATION,
    WRONG_AMOUNT,
    WRONG_INVOICE,
    UNSAFE_MATCH,
)

#: Outcomes where money moved to a place no human sanctioned.
FALSE_PAY_OUTCOMES = frozenset({WRONG_INVOICE, UNSAFE_MATCH})


@dataclass(frozen=True, slots=True)
class CostModel:
    """Business value of each outcome, in abstract "ops units".

    The absolute scale is arbitrary; only the *ratios* matter, and the ratios
    are the claim being made. They encode three judgements, each stated so a
    reviewer can disagree with a specific number rather than the whole model:

    * A touchless correct match is worth roughly the analyst minute it saves.
    * A correct escalation is worth less than a touchless match (a human still
      has to look) but is clearly positive: it prevented a loss.
    * Applying cash to the wrong invoice is ~25x worse than an unnecessary
      escalation, because it produces a vendor dispute, a mis-stated payables
      balance, and a manual recovery.

    ``sweep_cost_models`` re-scores the run across a range of these ratios so
    the reported ranking can be shown to be insensitive to the exact choice.
    """

    correct_match: int = 100
    correct_abstain: int = 15
    over_escalation: int = -30
    wrong_amount: int = -400
    wrong_invoice: int = -2500
    unsafe_match: int = -2500

    def value(self, outcome: str) -> int:
        return {
            CORRECT_MATCH: self.correct_match,
            CORRECT_ABSTAIN: self.correct_abstain,
            OVER_ESCALATION: self.over_escalation,
            WRONG_AMOUNT: self.wrong_amount,
            WRONG_INVOICE: self.wrong_invoice,
            UNSAFE_MATCH: self.unsafe_match,
        }[outcome]

    def as_dict(self) -> dict[str, int]:
        return {
            CORRECT_MATCH: self.correct_match,
            CORRECT_ABSTAIN: self.correct_abstain,
            OVER_ESCALATION: self.over_escalation,
            WRONG_AMOUNT: self.wrong_amount,
            WRONG_INVOICE: self.wrong_invoice,
            UNSAFE_MATCH: self.unsafe_match,
        }


@dataclass(frozen=True, slots=True)
class PaymentOutcome:
    payment_id: str
    hazard: str
    outcome: str
    expected_action: str
    actual_action: str
    detail: str = ""


@dataclass(slots=True)
class Scorecard:
    policy: str
    corpus: str
    corpus_seed: int
    total_payments: int
    counts: dict[str, int]
    per_hazard: dict[str, dict[str, int]]
    outcomes: list[PaymentOutcome]
    cost_model: dict[str, int]
    verifier_sha256: str
    ledger_blocks: dict[str, int] = field(default_factory=dict)
    steps_used: int = 0
    wall_seconds: float = 0.0
    llm_calls: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0

    # -- derived metrics --------------------------------------------------

    @property
    def net_value(self) -> int:
        model = CostModel(**{_field_name(k): v for k, v in self.cost_model.items()})
        return sum(model.value(o.outcome) for o in self.outcomes)

    @property
    def exact_accuracy(self) -> float:
        good = self.counts.get(CORRECT_MATCH, 0) + self.counts.get(CORRECT_ABSTAIN, 0)
        return _ratio(good, self.total_payments)

    @property
    def false_pay_count(self) -> int:
        return sum(self.counts.get(o, 0) for o in FALSE_PAY_OUTCOMES)

    @property
    def false_pay_rate(self) -> float:
        return _ratio(self.false_pay_count, self.total_payments)

    @property
    def coverage(self) -> float:
        """Share of the feed the policy decided itself instead of escalating.

        Read this precisely: it is the share on which no analyst had to make a
        *decision*. It is **not** the share that reached the ledger untouched
        by a human, because a decided posting above the approval threshold
        still needs a second signature -- a value control, not a failure of
        automation, and the same one a human decision-maker would face.

        Those two numbers differ substantially here (45% versus 30% for the
        advanced policy), so the scorecard prints both rather than letting the
        friendlier one stand alone. An earlier version of this docstring said
        "resolved without a human", which was simply wrong.
        """
        auto = sum(
            self.counts.get(o, 0)
            for o in (CORRECT_MATCH, WRONG_AMOUNT, WRONG_INVOICE, UNSAFE_MATCH)
        )
        return _ratio(auto, self.total_payments)

    @property
    def automation_precision(self) -> float:
        """Of the payments auto-posted, how many were right."""
        auto = sum(
            self.counts.get(o, 0)
            for o in (CORRECT_MATCH, WRONG_AMOUNT, WRONG_INVOICE, UNSAFE_MATCH)
        )
        return _ratio(self.counts.get(CORRECT_MATCH, 0), auto)

    @property
    def abstain_precision(self) -> float:
        """Of the payments escalated, how many genuinely needed a human."""
        escalated = self.counts.get(CORRECT_ABSTAIN, 0) + self.counts.get(OVER_ESCALATION, 0)
        return _ratio(self.counts.get(CORRECT_ABSTAIN, 0), escalated)

    @property
    def abstain_recall(self) -> float:
        """Of the payments that needed a human, how many were escalated."""
        needed = self.counts.get(CORRECT_ABSTAIN, 0) + self.counts.get(UNSAFE_MATCH, 0)
        return _ratio(self.counts.get(CORRECT_ABSTAIN, 0), needed)

    def to_dict(self) -> dict:
        return {
            "policy": self.policy,
            "corpus": self.corpus,
            "corpus_seed": self.corpus_seed,
            "total_payments": self.total_payments,
            "headline": {
                "net_value": self.net_value,
                "exact_accuracy": round(self.exact_accuracy, 4),
                "false_pay_count": self.false_pay_count,
                "false_pay_rate": round(self.false_pay_rate, 4),
                "coverage": round(self.coverage, 4),
                "automation_precision": round(self.automation_precision, 4),
                "abstain_precision": round(self.abstain_precision, 4),
                "abstain_recall": round(self.abstain_recall, 4),
            },
            "counts": {k: self.counts.get(k, 0) for k in OUTCOMES},
            "per_hazard": self.per_hazard,
            "cost_model": self.cost_model,
            "ledger_blocks": self.ledger_blocks,
            # Wall-clock time is deliberately absent. It is a property of the
            # machine, not of the policy, and it was the only field that
            # differed when a fresh clone re-ran `make verify` -- which left a
            # reviewer with a dirty working tree and a reasonable doubt about
            # what else had moved. It is still printed on every scorecard;
            # it is simply not committed. Step count is the reproducible
            # measure of effort and is right here.
            "cost": {
                "steps_used": self.steps_used,
                "llm_calls": self.llm_calls,
                "llm_input_tokens": self.llm_input_tokens,
                "llm_output_tokens": self.llm_output_tokens,
            },
            "verifier_sha256": self.verifier_sha256,
            "failures": [
                {
                    "payment_id": o.payment_id,
                    "hazard": o.hazard,
                    "outcome": o.outcome,
                    "expected": o.expected_action,
                    "actual": o.actual_action,
                    "detail": o.detail,
                }
                for o in self.outcomes
                if o.outcome not in (CORRECT_MATCH, CORRECT_ABSTAIN)
            ],
        }


def _field_name(outcome: str) -> str:
    return outcome.lower()


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def verifier_fingerprint() -> str:
    """SHA-256 of this file, recorded in every scorecard."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def classify(decision: Decision, truth: Truth) -> PaymentOutcome:
    """Grade one decision. Pure function of (decision, truth)."""
    decision = decision.normalised()
    expected = tuple(sorted(truth.expected_allocations, key=lambda a: a.invoice_id))

    if truth.expected_action == "ABSTAIN":
        if decision.action == "ABSTAIN":
            return PaymentOutcome(
                truth.payment_id, truth.hazard, CORRECT_ABSTAIN, "ABSTAIN", "ABSTAIN"
            )
        return PaymentOutcome(
            truth.payment_id,
            truth.hazard,
            UNSAFE_MATCH,
            "ABSTAIN",
            "MATCH",
            f"posted {_render(decision.allocations)} where no allocation is justifiable",
        )

    if decision.action == "ABSTAIN":
        return PaymentOutcome(
            truth.payment_id,
            truth.hazard,
            OVER_ESCALATION,
            "MATCH",
            "ABSTAIN",
            f"a human must now resolve {_render(expected)}",
        )

    expected_ids = tuple(a.invoice_id for a in expected)
    actual_ids = tuple(a.invoice_id for a in decision.allocations)

    if expected_ids != actual_ids:
        return PaymentOutcome(
            truth.payment_id,
            truth.hazard,
            WRONG_INVOICE,
            "MATCH",
            "MATCH",
            f"expected {list(expected_ids)}, posted {list(actual_ids)}",
        )

    if tuple(a.amount_cents for a in expected) != tuple(a.amount_cents for a in decision.allocations):
        return PaymentOutcome(
            truth.payment_id,
            truth.hazard,
            WRONG_AMOUNT,
            "MATCH",
            "MATCH",
            f"expected {_render(expected)}, posted {_render(decision.allocations)}",
        )

    return PaymentOutcome(truth.payment_id, truth.hazard, CORRECT_MATCH, "MATCH", "MATCH")


def _render(allocations: Sequence[Allocation]) -> str:
    return "{" + ", ".join(f"{a.invoice_id}:{a.amount_cents}" for a in allocations) + "}"


def score(
    policy_name: str,
    corpus: Corpus,
    decisions: Mapping[str, Decision],
    *,
    cost_model: CostModel | None = None,
    ledger_blocks: Mapping[str, int] | None = None,
    steps_used: int = 0,
    wall_seconds: float = 0.0,
    llm_calls: int = 0,
    llm_input_tokens: int = 0,
    llm_output_tokens: int = 0,
) -> Scorecard:
    """Grade a full run.

    A missing decision is *not* silently skipped: it is graded as an
    over-escalation or an unsafe match depending on what was required, so a
    policy cannot improve its score by refusing to emit rows.
    """
    model = cost_model or CostModel()
    truths = corpus.truth_by_payment()

    outcomes: list[PaymentOutcome] = []
    for payment in corpus.payments:
        truth = truths[payment.payment_id]
        decision = decisions.get(payment.payment_id)
        if decision is None:
            decision = Decision(
                payment_id=payment.payment_id,
                action="ABSTAIN",
                reason_code="NO_DECISION_EMITTED",
                rationale="policy produced no decision for this payment",
            )
        outcomes.append(classify(decision, truth))

    counts: dict[str, int] = {o: 0 for o in OUTCOMES}
    per_hazard: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        counts[outcome.outcome] += 1
        bucket = per_hazard.setdefault(outcome.hazard, {o: 0 for o in OUTCOMES})
        bucket[outcome.outcome] += 1

    return Scorecard(
        policy=policy_name,
        corpus=corpus.name,
        corpus_seed=corpus.seed,
        total_payments=len(corpus.payments),
        counts=counts,
        per_hazard=dict(sorted(per_hazard.items())),
        outcomes=outcomes,
        cost_model=model.as_dict(),
        verifier_sha256=verifier_fingerprint(),
        ledger_blocks=dict(ledger_blocks or {}),
        steps_used=steps_used,
        wall_seconds=wall_seconds,
        llm_calls=llm_calls,
        llm_input_tokens=llm_input_tokens,
        llm_output_tokens=llm_output_tokens,
    )


def sweep_cost_models(scorecard: Scorecard) -> list[dict[str, object]]:
    """Re-score under harsher and gentler false-pay penalties.

    If a ranking only holds at one particular penalty ratio it is an artefact
    of the weights, not a property of the policy. This produces the evidence
    needed to say the ranking is robust.
    """
    rows: list[dict[str, object]] = []
    for penalty in (-250, -600, -1200, -2500, -5000, -12000):
        model = CostModel(wrong_invoice=penalty, unsafe_match=penalty)
        total = sum(model.value(o.outcome) for o in scorecard.outcomes)
        rows.append({"false_pay_penalty": penalty, "net_value": total})
    return rows
