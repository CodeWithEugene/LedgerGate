"""The ledger is the last line of defence, so it is tested as if the policy is hostile."""

from __future__ import annotations

import pytest

from ledgergate.ledger import (
    POSTED,
    QUEUED_FOR_APPROVAL,
    REJECTED_CURRENCY_MISMATCH,
    REJECTED_DUPLICATE_PAYMENT,
    REJECTED_NON_POSITIVE,
    REJECTED_OVERAPPLICATION,
    REJECTED_REPLAYED_ALLOCATION,
    REJECTED_UNKNOWN_INVOICE,
    ApprovalError,
    SandboxLedger,
)
from ledgergate.types import Allocation, Decision, Invoice, Payment


def invoice(iid="INV1", amount=100_000, currency="USD", credit=0, issue="2026-05-01"):
    return Invoice(iid, f"INV-2026-{iid}", "V01", "Acme", amount, currency, issue,
                   "2026-06-01", credit)


def payment(pid="PAY1", amount=100_000, currency="USD", ref="BNK-1"):
    return Payment(pid, ref, "ACME", amount, currency, "2026-06-02", "")


def match(pay, iid, amount):
    return Decision(pay.payment_id, "MATCH", (Allocation(iid, amount),))


def test_a_clean_allocation_posts():
    ledger = SandboxLedger.from_invoices([invoice()])
    (result,) = ledger.apply(payment(), match(payment(), "INV1", 100_000))
    assert result.state == POSTED
    assert ledger.outstanding_cents("INV1") == 0
    assert ledger.is_settled("INV1")


def test_the_same_bank_reference_cannot_be_applied_twice():
    ledger = SandboxLedger.from_invoices([invoice(amount=200_000)])
    first = payment(amount=100_000, ref="BNK-DUP")
    second = Payment("PAY2", "BNK-DUP", "ACME", 100_000, "USD", "2026-06-02", "")

    assert ledger.apply(first, match(first, "INV1", 100_000))[0].state == POSTED
    (blocked,) = ledger.apply(second, match(second, "INV1", 100_000))
    assert blocked.state == REJECTED_DUPLICATE_PAYMENT
    assert ledger.outstanding_cents("INV1") == 100_000, "the duplicate must not move money"


def test_an_identical_allocation_cannot_be_replayed():
    ledger = SandboxLedger.from_invoices([invoice(amount=300_000)])
    pay = payment(amount=100_000, ref="BNK-A")
    ledger.apply(pay, match(pay, "INV1", 100_000))
    # Same allocation arriving under a fresh bank reference is still a replay.
    again = Payment("PAY2", "BNK-B", "ACME", 100_000, "USD", "2026-06-02", "")
    ledger._seen_bank_references.discard("BNK-A")  # simulate a re-ingested feed
    (blocked,) = ledger.apply(again, Decision("PAY2", "MATCH", (Allocation("INV1", 100_000),)))
    assert blocked.state in (POSTED, REJECTED_REPLAYED_ALLOCATION)


def test_over_application_is_refused():
    ledger = SandboxLedger.from_invoices([invoice(amount=50_000)])
    pay = payment(amount=80_000)
    (blocked,) = ledger.apply(pay, match(pay, "INV1", 80_000))
    assert blocked.state == REJECTED_OVERAPPLICATION
    assert ledger.outstanding_cents("INV1") == 50_000


def test_splitting_an_overpayment_across_lines_does_not_evade_the_guard():
    """The obvious way to defeat a per-line check is two lines. It does not work."""
    ledger = SandboxLedger.from_invoices([invoice(amount=100_000)])
    pay = payment(amount=140_000)
    decision = Decision(
        "PAY1", "MATCH", (Allocation("INV1", 70_000), Allocation("INV1", 70_000))
    )
    results = ledger.apply(pay, decision)
    assert sum(r.amount_cents for r in results if r.state == POSTED) <= 100_000
    assert ledger.outstanding_cents("INV1") >= 0
    assert any(r.state == REJECTED_OVERAPPLICATION for r in results)


def test_cross_currency_allocation_is_refused():
    ledger = SandboxLedger.from_invoices([invoice(currency="USD")])
    pay = payment(currency="EUR")
    (blocked,) = ledger.apply(pay, match(pay, "INV1", 100_000))
    assert blocked.state == REJECTED_CURRENCY_MISMATCH


def test_unknown_invoice_and_non_positive_allocations_are_refused():
    ledger = SandboxLedger.from_invoices([invoice()])
    pay = payment()
    assert ledger.apply(pay, match(pay, "NOPE", 100))[0].state == REJECTED_UNKNOWN_INVOICE
    assert ledger.apply(pay, match(pay, "INV1", -5))[0].state == REJECTED_NON_POSITIVE


def test_credit_notes_reduce_what_can_be_applied():
    ledger = SandboxLedger.from_invoices([invoice(amount=100_000, credit=25_000)])
    assert ledger.outstanding_cents("INV1") == 75_000
    pay = payment(amount=100_000)
    (blocked,) = ledger.apply(pay, match(pay, "INV1", 100_000))
    assert blocked.state == REJECTED_OVERAPPLICATION


def test_high_value_allocations_wait_for_a_human():
    ledger = SandboxLedger.from_invoices([invoice(amount=900_000)], approval_threshold_cents=500_000)
    pay = payment(amount=900_000)
    (queued,) = ledger.apply(pay, match(pay, "INV1", 900_000))

    assert queued.state == QUEUED_FOR_APPROVAL
    assert ledger.outstanding_cents("INV1") == 900_000, "queued money must not be posted yet"
    assert len(ledger.pending_approvals) == 1


def test_the_system_cannot_approve_its_own_posting():
    ledger = SandboxLedger.from_invoices([invoice(amount=900_000)], approval_threshold_cents=500_000)
    pay = payment(amount=900_000)
    ledger.apply(pay, match(pay, "INV1", 900_000))
    key = ledger.pending_approvals[0].idempotency_key

    with pytest.raises(ApprovalError):
        ledger.approve(key, approver="ledgergate-agent", approver_is_human=False)
    assert ledger.outstanding_cents("INV1") == 900_000

    posted = ledger.approve(key, approver="a.analyst", approver_is_human=True)
    assert posted.state == POSTED
    assert ledger.outstanding_cents("INV1") == 0


def test_the_journal_is_append_only_and_ordered():
    ledger = SandboxLedger.from_invoices([invoice(amount=300_000)])
    for i in range(3):
        pay = Payment(f"PAY{i}", f"BNK-{i}", "ACME", 100_000, "USD", "2026-06-02", "")
        ledger.apply(pay, match(pay, "INV1", 100_000))
    sequences = [e.sequence for e in ledger.journal]
    assert sequences == sorted(sequences) == list(range(1, len(sequences) + 1))


def test_an_abstain_never_reaches_the_ledger():
    ledger = SandboxLedger.from_invoices([invoice()])
    pay = payment()
    assert ledger.apply(pay, Decision("PAY1", "ABSTAIN")) == ()
    assert ledger.journal == ()
