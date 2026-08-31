"""Shared fixtures and the probe policies used to attack the evaluation.

The probes here are not realistic solutions. They exist to answer a question a
reviewer should always ask of a benchmark: *what is the best score you can get
without solving the problem?* If a constant policy or a lucky heuristic can
score well, the benchmark is measuring the wrong thing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ledgergate.corpus import Corpus, build_corpus  # noqa: E402
from ledgergate.tools import ToolSession  # noqa: E402
from ledgergate.types import Allocation, Decision, Payment  # noqa: E402

DATA_ROOT = REPO_ROOT / "data"


@pytest.fixture(scope="session")
def dev_corpus() -> Corpus:
    return build_corpus("dev", 20260828, instances=3)


@pytest.fixture(scope="session")
def holdout_corpus() -> Corpus:
    return build_corpus("holdout", 20260831, instances=3)


class AlwaysAbstainPolicy:
    """Never touches the ledger. Should be safe and nearly worthless."""

    name = "probe-always-abstain"

    def instructions(self) -> str:
        return "Escalate everything."

    def decide(self, payment: Payment, session: ToolSession) -> Decision:
        return Decision(payment.payment_id, "ABSTAIN", reason_code="PROBE")


class AlwaysMatchPolicy:
    """Posts the receipt against whatever invoice it sees first.

    This is the adversary the safety gate is claimed to defeat. Behind the gate
    it must produce zero unsafe postings, no matter how reckless it is.
    """

    name = "probe-always-match"

    def instructions(self) -> str:
        return "Post everything against the first invoice found."

    def decide(self, payment: Payment, session: ToolSession) -> Decision:
        found = session.call(
            "search_invoices", {"include_settled": True, "match_field": "net_due"}
        )
        invoices = found.get("invoices") or []
        if not invoices:
            return Decision(payment.payment_id, "ABSTAIN", reason_code="PROBE_EMPTY")
        return Decision(
            payment_id=payment.payment_id,
            action="MATCH",
            allocations=(Allocation(invoices[0]["invoice_id"], payment.amount_cents),),
            reason_code="PROBE",
        )


class GatedProbe:
    """Wraps any probe in the production safety gate."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.name = f"{inner.name}+gate"

    def instructions(self) -> str:
        return self.inner.instructions() + " Then the safety gate reviews it."

    def decide(self, payment: Payment, session: ToolSession) -> Decision:
        from ledgergate import evidence as evidence_mod
        from ledgergate import safety

        proposal = self.inner.decide(payment, session)
        ev = evidence_mod.gather(payment, session)
        final, _ = safety.review(payment, proposal, ev, session)
        return final


class OraclePolicy:
    """Reads ground truth directly. Only a test may do this.

    Used to establish the ceiling, and to prove the safety gate is *sound*:
    a gate that blocks correct answers would be buying safety with accuracy.
    """

    name = "probe-oracle"

    def __init__(self, corpus: Corpus) -> None:
        self.truths = corpus.truth_by_payment()

    def instructions(self) -> str:
        return "Return ground truth."

    def decide(self, payment: Payment, session: ToolSession) -> Decision:
        truth = self.truths[payment.payment_id]
        return Decision(
            payment_id=payment.payment_id,
            action=truth.expected_action,
            allocations=truth.expected_allocations,
            reason_code="ORACLE",
        )
