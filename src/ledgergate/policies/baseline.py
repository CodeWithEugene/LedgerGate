"""The baseline: fuzzy name plus amount matching, which is what you get first.

This is written to be a *fair* baseline, not a straw man. It is close to what
a competent engineer produces in an afternoon, and close to what a coding
agent emits when handed "match these payments to these invoices": resolve the
supplier by name similarity, look for an invoice with the same amount, widen
the tolerance if nothing turns up, and give up if nothing is close.

It gets the easy cases right, and it gets several of the hard cases right by
accident, which is exactly why it is dangerous. Its two real defects are
structural rather than cosmetic:

* It reconciles against the **invoice register** (``match_field="net_due"``)
  instead of the **live ledger balance**. That is the single most common bug
  in home-grown cash application, and it is what makes it re-pay invoices that
  are already settled.

* It has no concept of *insufficient evidence*. When two invoices fit equally
  well it takes the first one. A coin flip is not a decision, but it looks
  exactly like one in the output.

Nothing here is deliberately sabotaged. Everything it does can be found in
production somewhere.
"""

from __future__ import annotations

from typing import Any

from ..tools import ToolSession
from ..types import Allocation, Decision, Payment

#: Widen the amount comparison by this fraction before giving up.
FALLBACK_TOLERANCE_PCT = 5


class BaselinePolicy:
    name = "baseline"

    def __init__(self) -> None:
        self.stats: dict[str, Any] = {"fallback_used": 0, "coin_flips": 0}

    def instructions(self) -> str:
        return (
            "Baseline cash-application heuristic.\n"
            "1. Resolve the counterparty to the highest-scoring supplier.\n"
            "2. Look for an invoice for that supplier whose register amount equals "
            "the receipt.\n"
            "3. If none, look across all suppliers for the same amount.\n"
            "4. If none, retry within a 5% tolerance.\n"
            "5. Apply the receipt to the first candidate found; otherwise report "
            "no candidate.\n"
            "No procedure is consulted, no ambiguity is detected, and no "
            "escalation path exists other than finding nothing at all."
        )

    def decide(self, payment: Payment, session: ToolSession) -> Decision:
        if payment.amount_cents <= 0:
            return Decision(
                payment_id=payment.payment_id,
                action="ABSTAIN",
                reason_code="NON_POSITIVE",
                rationale="baseline only handles incoming receipts",
            )

        resolved = session.call("resolve_vendor", {"counterparty": payment.counterparty_raw})
        candidates = resolved.get("candidates") or []
        vendor_id = candidates[0]["vendor_id"] if candidates else None

        found: list[dict[str, Any]] = []
        route = ""

        if vendor_id:
            hit = session.call(
                "search_invoices",
                {
                    "vendor_id": vendor_id,
                    "amount_cents": payment.amount_cents,
                    "tolerance_cents": 0,
                    "include_settled": True,
                    "match_field": "net_due",
                },
            )
            found = list(hit.get("invoices") or [])
            route = "exact amount, resolved supplier"

        if not found:
            hit = session.call(
                "search_invoices",
                {
                    "amount_cents": payment.amount_cents,
                    "tolerance_cents": 0,
                    "include_settled": True,
                    "match_field": "net_due",
                },
            )
            found = list(hit.get("invoices") or [])
            route = "exact amount, any supplier"

        if not found and vendor_id:
            tolerance = payment.amount_cents * FALLBACK_TOLERANCE_PCT // 100
            hit = session.call(
                "search_invoices",
                {
                    "vendor_id": vendor_id,
                    "amount_cents": payment.amount_cents,
                    "tolerance_cents": tolerance,
                    "include_settled": True,
                    "match_field": "net_due",
                },
            )
            found = list(hit.get("invoices") or [])
            route = f"within {FALLBACK_TOLERANCE_PCT}% tolerance, resolved supplier"
            if found:
                self.stats["fallback_used"] += 1

        if not found:
            return Decision(
                payment_id=payment.payment_id,
                action="ABSTAIN",
                reason_code="NO_CANDIDATE",
                rationale="no invoice within tolerance of this amount",
            )

        if len(found) > 1:
            self.stats["coin_flips"] += 1

        chosen = found[0]
        return Decision(
            payment_id=payment.payment_id,
            action="MATCH",
            allocations=(Allocation(chosen["invoice_id"], payment.amount_cents),),
            reason_code="AMOUNT_MATCH",
            rationale=f"matched on {route}; {len(found)} candidate(s), took the first",
            evidence=(
                f"supplier={vendor_id}",
                f"candidates={[c['invoice_id'] for c in found]}",
            ),
        )
