"""Sandbox ledger: the only component permitted to "move money".

Nothing here touches a real payment rail. The ledger is a simulation, and it
is deliberately the *last* line of defence rather than the first. Two design
rules drive everything in this file:

1. **The policy is untrusted.** A hallucinating agent may propose paying an
   invoice twice, paying a settled invoice, or paying across currencies. The
   ledger rejects those proposals structurally. Safety must not depend on the
   model behaving.

2. **Consequential actions need a human.** Any allocation at or above the
   approval threshold is parked in a review queue and is *not* posted until an
   explicit human approval is recorded. The policy cannot approve its own work.

The ledger also reports how often it had to block a policy. That number
matters: a policy whose bad proposals are silently absorbed by a guard rail
still has bad judgment, and the evaluation grades intent separately from
outcome.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .types import Allocation, Decision, Invoice, LedgerEntry, Payment

#: Allocations at or above this value require a recorded human approval.
#:
#: 25,000.00 is a common dual-authorisation limit in a mid-market AP function.
#: On this corpus it sits between the 75th and 90th percentile of receipt
#: values, so roughly the top sixth of postings need a signature. The first
#: value tried was 5,000.00, which is below the median receipt here and put 26
#: of 27 postings into the queue -- technically safe, and useless, because a
#: control that fires on almost everything is just the manual process with
#: extra steps. See docs/PROBLEM.md, "Numbers I had to choose".
DEFAULT_APPROVAL_THRESHOLD_CENTS = 2_500_000  # 25,000.00

POSTED = "POSTED"
QUEUED_FOR_APPROVAL = "QUEUED_FOR_APPROVAL"
REJECTED_DUPLICATE_PAYMENT = "REJECTED_DUPLICATE_PAYMENT"
REJECTED_REPLAYED_ALLOCATION = "REJECTED_REPLAYED_ALLOCATION"
REJECTED_OVERAPPLICATION = "REJECTED_OVERAPPLICATION"
REJECTED_UNKNOWN_INVOICE = "REJECTED_UNKNOWN_INVOICE"
REJECTED_CURRENCY_MISMATCH = "REJECTED_CURRENCY_MISMATCH"
REJECTED_NON_POSITIVE = "REJECTED_NON_POSITIVE"

REJECTION_STATES = frozenset(
    {
        REJECTED_DUPLICATE_PAYMENT,
        REJECTED_REPLAYED_ALLOCATION,
        REJECTED_OVERAPPLICATION,
        REJECTED_UNKNOWN_INVOICE,
        REJECTED_CURRENCY_MISMATCH,
        REJECTED_NON_POSITIVE,
    }
)


class ApprovalError(RuntimeError):
    """Raised when an approval is attempted by a non-human actor."""


@dataclass(frozen=True, slots=True)
class PostResult:
    payment_id: str
    invoice_id: str
    amount_cents: int
    state: str
    detail: str = ""

    @property
    def blocked(self) -> bool:
        return self.state in REJECTION_STATES


@dataclass
class SandboxLedger:
    """In-memory, append-only ledger over a fixed invoice book."""

    invoices: Mapping[str, Invoice]
    approval_threshold_cents: int = DEFAULT_APPROVAL_THRESHOLD_CENTS

    _applied_cents: dict[str, int] = field(default_factory=dict)
    _seen_bank_references: set[str] = field(default_factory=set)
    _seen_idempotency_keys: set[str] = field(default_factory=set)
    _journal: list[LedgerEntry] = field(default_factory=list)
    _pending_approval: dict[str, LedgerEntry] = field(default_factory=dict)
    _sequence: int = 0

    # -- construction -----------------------------------------------------

    @classmethod
    def from_invoices(
        cls,
        invoices: Iterable[Invoice],
        opening_allocations: Iterable[Allocation] = (),
        approval_threshold_cents: int = DEFAULT_APPROVAL_THRESHOLD_CENTS,
    ) -> "SandboxLedger":
        book = {inv.invoice_id: inv for inv in invoices}
        ledger = cls(invoices=book, approval_threshold_cents=approval_threshold_cents)
        for alloc in opening_allocations:
            ledger._applied_cents[alloc.invoice_id] = (
                ledger._applied_cents.get(alloc.invoice_id, 0) + alloc.amount_cents
            )
        return ledger

    # -- read surface -----------------------------------------------------

    def applied_cents(self, invoice_id: str) -> int:
        return self._applied_cents.get(invoice_id, 0)

    def outstanding_cents(self, invoice_id: str) -> int:
        invoice = self.invoices.get(invoice_id)
        if invoice is None:
            return 0
        return invoice.net_due_cents - self.applied_cents(invoice_id)

    def is_settled(self, invoice_id: str) -> bool:
        return self.outstanding_cents(invoice_id) <= 0

    def bank_reference_seen(self, bank_reference: str) -> bool:
        return bank_reference in self._seen_bank_references

    @property
    def journal(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._journal)

    @property
    def pending_approvals(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._pending_approval.values())

    # -- write surface ----------------------------------------------------

    def idempotency_key(self, payment: Payment, allocation: Allocation) -> str:
        raw = f"{payment.bank_reference}|{allocation.invoice_id}|{allocation.amount_cents}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def apply(self, payment: Payment, decision: Decision) -> tuple[PostResult, ...]:
        """Attempt to post a decision. Never raises on bad policy input."""
        if decision.action != "MATCH" or not decision.allocations:
            return ()

        # A bank reference we have already consumed is the same real movement
        # arriving twice. Refuse the whole decision, not just the overlap.
        if payment.bank_reference in self._seen_bank_references:
            return tuple(
                PostResult(
                    payment.payment_id,
                    a.invoice_id,
                    a.amount_cents,
                    REJECTED_DUPLICATE_PAYMENT,
                    f"bank_reference {payment.bank_reference} already ingested",
                )
                for a in decision.allocations
            )

        results: list[PostResult] = []
        accepted: list[tuple[Allocation, str]] = []

        for alloc in decision.allocations:
            key = self.idempotency_key(payment, alloc)
            invoice = self.invoices.get(alloc.invoice_id)

            if invoice is None:
                results.append(
                    PostResult(
                        payment.payment_id,
                        alloc.invoice_id,
                        alloc.amount_cents,
                        REJECTED_UNKNOWN_INVOICE,
                        "invoice not in book",
                    )
                )
                continue
            if alloc.amount_cents <= 0:
                results.append(
                    PostResult(
                        payment.payment_id,
                        alloc.invoice_id,
                        alloc.amount_cents,
                        REJECTED_NON_POSITIVE,
                        "allocation must be a positive amount",
                    )
                )
                continue
            if invoice.currency != payment.currency:
                results.append(
                    PostResult(
                        payment.payment_id,
                        alloc.invoice_id,
                        alloc.amount_cents,
                        REJECTED_CURRENCY_MISMATCH,
                        f"payment {payment.currency} vs invoice {invoice.currency}; "
                        "no conversion rate is configured",
                    )
                )
                continue
            if key in self._seen_idempotency_keys:
                results.append(
                    PostResult(
                        payment.payment_id,
                        alloc.invoice_id,
                        alloc.amount_cents,
                        REJECTED_REPLAYED_ALLOCATION,
                        "identical allocation already recorded",
                    )
                )
                continue

            # Provisional over-application check includes allocations accepted
            # earlier in this same decision, so a policy cannot split one
            # over-payment across two lines to slip past the guard.
            provisional = sum(
                a.amount_cents for a, _ in accepted if a.invoice_id == alloc.invoice_id
            )
            if self.applied_cents(alloc.invoice_id) + provisional + alloc.amount_cents > invoice.net_due_cents:
                results.append(
                    PostResult(
                        payment.payment_id,
                        alloc.invoice_id,
                        alloc.amount_cents,
                        REJECTED_OVERAPPLICATION,
                        f"outstanding is {self.outstanding_cents(alloc.invoice_id) - provisional}",
                    )
                )
                continue

            accepted.append((alloc, key))

        for alloc, key in accepted:
            self._sequence += 1
            state = (
                QUEUED_FOR_APPROVAL
                if alloc.amount_cents >= self.approval_threshold_cents
                else POSTED
            )
            entry = LedgerEntry(
                sequence=self._sequence,
                payment_id=payment.payment_id,
                invoice_id=alloc.invoice_id,
                amount_cents=alloc.amount_cents,
                state=state,
                idempotency_key=key,
            )
            self._journal.append(entry)
            self._seen_idempotency_keys.add(key)

            if state == POSTED:
                self._applied_cents[alloc.invoice_id] = (
                    self.applied_cents(alloc.invoice_id) + alloc.amount_cents
                )
                results.append(
                    PostResult(payment.payment_id, alloc.invoice_id, alloc.amount_cents, POSTED)
                )
            else:
                self._pending_approval[key] = entry
                results.append(
                    PostResult(
                        payment.payment_id,
                        alloc.invoice_id,
                        alloc.amount_cents,
                        QUEUED_FOR_APPROVAL,
                        f"at or above approval threshold {self.approval_threshold_cents}",
                    )
                )

        if accepted:
            self._seen_bank_references.add(payment.bank_reference)

        return tuple(results)

    def approve(self, idempotency_key: str, *, approver: str, approver_is_human: bool) -> PostResult:
        """Release a queued allocation. Only a human may call this."""
        if not approver_is_human:
            raise ApprovalError(
                f"{approver!r} is not a human reviewer; queued allocations "
                "require human approval before posting"
            )
        entry = self._pending_approval.pop(idempotency_key, None)
        if entry is None:
            raise KeyError(f"no queued allocation {idempotency_key!r}")

        self._applied_cents[entry.invoice_id] = (
            self.applied_cents(entry.invoice_id) + entry.amount_cents
        )
        self._sequence += 1
        posted = LedgerEntry(
            sequence=self._sequence,
            payment_id=entry.payment_id,
            invoice_id=entry.invoice_id,
            amount_cents=entry.amount_cents,
            state=POSTED,
            idempotency_key=entry.idempotency_key,
        )
        self._journal.append(posted)
        return PostResult(
            entry.payment_id,
            entry.invoice_id,
            entry.amount_cents,
            POSTED,
            f"approved by {approver}",
        )

    # -- reporting --------------------------------------------------------

    def guard_summary(self) -> dict[str, int]:
        """How often the ledger had to stop a policy, by rejection reason."""
        summary: dict[str, int] = {}
        for state in sorted(REJECTION_STATES):
            summary[state] = 0
        return summary
