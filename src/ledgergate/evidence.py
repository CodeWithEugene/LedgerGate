"""Gather, through the tool surface, everything a decision could rest on.

This is factored out of the policies on purpose. The safety gate must be able
to re-derive the facts for itself rather than believing whatever a language
model asserted in its rationale: a model that hallucinates an invoice number
is precisely the failure the gate exists to catch, and a gate that reads the
model's own summary would inherit the hallucination.

Every lookup here goes through ``ToolSession``, so it lands in the trajectory
and counts against the step budget like any other tool use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .tools import ToolSession, extract_invoice_numbers
from .types import Payment

#: Cents of shortfall accepted as settlement rounding (AP-07.3).
ROUNDING_TOLERANCE_CENTS = 2

_FEE_RE = re.compile(r"\b(FEE|FEES|CHARGE|CHARGES|CHG|CORRESPONDENT)\b", re.IGNORECASE)
_PART_RE = re.compile(
    r"\b(PART|PARTIAL|DEPOSIT|INSTALMENT|INSTALLMENT|PCT|\d+\s*OF\s*\d+)\b", re.IGNORECASE
)
_REVERSAL_RE = re.compile(r"\b(REVERSAL|REVERSE|RETURN|RECALL|CHARGEBACK|REFUND)\b", re.IGNORECASE)


@dataclass(slots=True)
class Evidence:
    payment: Payment
    vendor_id: str | None = None
    vendor_name: str | None = None
    vendor_confident: bool = False
    vendor_candidates: list[dict[str, Any]] = field(default_factory=list)
    duplicate_feed: bool = False
    referenced_numbers: list[str] = field(default_factory=list)
    resolved_references: list[dict[str, Any]] = field(default_factory=list)
    unresolved_references: list[str] = field(default_factory=list)
    vendor_amount_candidates: list[dict[str, Any]] = field(default_factory=list)
    global_amount_candidates: list[dict[str, Any]] = field(default_factory=list)
    mentions_fee: bool = False
    mentions_part_payment: bool = False
    mentions_reversal: bool = False

    # -- convenience ------------------------------------------------------

    @property
    def reference_total_outstanding(self) -> int:
        return sum(int(v["outstanding_cents"]) for v in self.resolved_references)

    def reference_ids(self) -> list[str]:
        return [str(v["invoice_id"]) for v in self.resolved_references]

    def summary(self) -> dict[str, Any]:
        """Compact form suitable for embedding in a model prompt."""
        return {
            "vendor": {
                "vendor_id": self.vendor_id,
                "vendor_name": self.vendor_name,
                "confident": self.vendor_confident,
                "candidates": self.vendor_candidates[:3],
            },
            "bank_reference_already_processed": self.duplicate_feed,
            "invoice_numbers_in_memo": self.referenced_numbers,
            "references_that_resolved": self.resolved_references,
            "references_that_did_not_resolve": self.unresolved_references,
            "same_amount_open_invoices_for_this_vendor": self.vendor_amount_candidates,
            "same_amount_open_invoices_any_vendor": self.global_amount_candidates,
            "memo_signals": {
                "mentions_bank_fee": self.mentions_fee,
                "mentions_part_payment": self.mentions_part_payment,
                "mentions_reversal": self.mentions_reversal,
            },
        }


def gather(payment: Payment, session: ToolSession) -> Evidence:
    """Collect the standard evidence bundle for one payment."""
    ev = Evidence(payment=payment)

    memo = payment.memo or ""
    ev.mentions_fee = bool(_FEE_RE.search(memo))
    ev.mentions_part_payment = bool(_PART_RE.search(memo))
    ev.mentions_reversal = bool(_REVERSAL_RE.search(memo))

    dup = session.call("check_duplicate_feed", {"bank_reference": payment.bank_reference})
    ev.duplicate_feed = bool(dup.get("already_processed"))

    resolved = session.call("resolve_vendor", {"counterparty": payment.counterparty_raw})
    ev.vendor_candidates = list(resolved.get("candidates", []))
    ev.vendor_confident = bool(resolved.get("confident"))
    if ev.vendor_candidates:
        ev.vendor_id = ev.vendor_candidates[0].get("vendor_id")
        ev.vendor_name = ev.vendor_candidates[0].get("vendor_name")

    ev.referenced_numbers = extract_invoice_numbers(memo)
    for number in ev.referenced_numbers:
        hit = session.call("find_invoice_by_number", {"invoice_number": number})
        matches = hit.get("matches") or []
        if matches:
            ev.resolved_references.extend(matches)
        else:
            ev.unresolved_references.append(number)

    # Amount-based candidates are only meaningful for positive receipts.
    if payment.amount_cents > 0:
        if ev.vendor_id:
            found = session.call(
                "search_invoices",
                {
                    "vendor_id": ev.vendor_id,
                    "amount_cents": payment.amount_cents,
                    "tolerance_cents": ROUNDING_TOLERANCE_CENTS,
                },
            )
            ev.vendor_amount_candidates = list(found.get("invoices", []))
        found_any = session.call(
            "search_invoices",
            {
                "amount_cents": payment.amount_cents,
                "tolerance_cents": ROUNDING_TOLERANCE_CENTS,
            },
        )
        ev.global_amount_candidates = list(found_any.get("invoices", []))

    return ev
