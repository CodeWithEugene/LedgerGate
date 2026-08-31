"""The safety gate: a veto-only reviewer sitting between proposal and ledger.

The gate is **monotone**. It has exactly one power: turning a proposed MATCH
into an ABSTAIN. It can never create a match, change an allocation, or pick a
different invoice. That restriction is what makes it trustworthy to bolt onto
an untrusted proposer, and it is asserted by a test rather than left as a
comment.

Every veto cites the clause of AP-07 it is enforcing, because "the robot said
no" is not an acceptable answer to a supplier asking why their invoice is
still open. The citation ends up in the trajectory and in the analyst queue.

Two properties are the whole argument of this project, and both are tested:

* **Soundness** -- the gate never vetoes a decision that ground truth says was
  correct. If it did, safety would be costing accuracy and the trade would be
  a bad one.
* **Sufficiency** -- no proposal that ground truth calls unsafe survives the
  gate. Even a policy that matches absolutely everything ends up with zero
  unsafe postings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .evidence import ROUNDING_TOLERANCE_CENTS, Evidence
from .tools import ToolSession
from .types import Decision, Payment


@dataclass(frozen=True, slots=True)
class Veto:
    code: str
    citation: str
    detail: str

    def as_text(self) -> str:
        return f"{self.code} ({self.citation}): {self.detail}"


def review(
    payment: Payment,
    proposal: Decision,
    evidence: Evidence,
    session: ToolSession,
) -> tuple[Decision, list[Veto]]:
    """Return ``(decision, vetoes)``. The decision is the proposal or an ABSTAIN."""
    if proposal.action != "MATCH":
        return proposal, []

    vetoes: list[Veto] = []

    if not proposal.allocations:
        vetoes.append(Veto("EMPTY_MATCH", "AP-07.2", "a MATCH must allocate to at least one invoice"))

    if evidence.duplicate_feed:
        vetoes.append(
            Veto(
                "DUPLICATE_FEED",
                "AP-07.6",
                f"bank reference {payment.bank_reference} is already in the journal",
            )
        )

    if payment.amount_cents <= 0:
        vetoes.append(
            Veto(
                "NON_POSITIVE_RECEIPT",
                "AP-07.9(iii)",
                "reversals, returns and recalls are not covered by this revision",
            )
        )

    allocated_total = proposal.total_allocated_cents()
    if allocated_total != payment.amount_cents:
        vetoes.append(
            Veto(
                "TOTAL_MISMATCH",
                "AP-07.3",
                f"allocations total {allocated_total} but the receipt is {payment.amount_cents}; "
                "only cash actually received may be applied",
            )
        )

    views: dict[str, dict[str, Any]] = {}
    for alloc in proposal.allocations:
        view = session.call("get_invoice", {"invoice_id": alloc.invoice_id})
        if "error" in view:
            vetoes.append(
                Veto("UNKNOWN_INVOICE", "AP-07.2", f"{alloc.invoice_id} is not in the invoice book")
            )
            continue
        views[alloc.invoice_id] = view

        if view["currency"] != payment.currency:
            rate = session.call("fx_rate", {"base": payment.currency, "quote": view["currency"]})
            if rate.get("status") != "AVAILABLE":
                vetoes.append(
                    Veto(
                        "CURRENCY_MISMATCH",
                        "AP-07.9(i)",
                        f"receipt is {payment.currency}, {alloc.invoice_id} is "
                        f"{view['currency']}, and no rate source is configured",
                    )
                )

        outstanding = int(view["outstanding_cents"])
        if outstanding <= 0:
            vetoes.append(
                Veto(
                    "ALREADY_SETTLED",
                    "AP-07.2",
                    f"{alloc.invoice_id} has no outstanding balance",
                )
            )
        elif alloc.amount_cents > outstanding:
            vetoes.append(
                Veto(
                    "OVER_APPLICATION",
                    "AP-07.9(ii)",
                    f"{alloc.invoice_id} owes {outstanding} but {alloc.amount_cents} was allocated",
                )
            )
        else:
            shortfall = outstanding - alloc.amount_cents
            if shortfall > 0 and not _shortfall_is_explained(shortfall, alloc.invoice_id, evidence):
                vetoes.append(
                    Veto(
                        "UNEXPLAINED_SHORTFALL",
                        "AP-07.4",
                        f"{alloc.invoice_id} is short by {shortfall} with no declared part "
                        "payment, bank charge, or rounding within tolerance",
                    )
                )

        if payment.value_date < view["issue_date"]:
            vetoes.append(
                Veto(
                    "PREDATED_RECEIPT",
                    "AP-07.9(iv)",
                    f"receipt dated {payment.value_date} precedes {alloc.invoice_id} "
                    f"issued {view['issue_date']}",
                )
            )

        if evidence.vendor_confident and evidence.vendor_id and view["vendor_id"] != evidence.vendor_id:
            vetoes.append(
                Veto(
                    "VENDOR_MISMATCH",
                    "AP-07.2",
                    f"counterparty resolves to {evidence.vendor_id} but "
                    f"{alloc.invoice_id} belongs to {view['vendor_id']}",
                )
            )

    vetoes.extend(_reference_conflict(proposal, evidence))
    vetoes.extend(_amount_ambiguity(proposal, evidence))

    if not vetoes:
        return proposal, []

    reason = vetoes[0].code
    return (
        Decision(
            payment_id=payment.payment_id,
            action="ABSTAIN",
            reason_code=f"GATE_{reason}",
            rationale=(
                "Safety gate withheld a proposed match. "
                + " ".join(v.as_text() for v in vetoes)
            ),
            evidence=tuple(v.as_text() for v in vetoes),
        ),
        vetoes,
    )


def _shortfall_is_explained(shortfall: int, invoice_id: str, evidence: Evidence) -> bool:
    """AP-07.3 and AP-07.4: the only sanctioned reasons to under-apply."""
    if shortfall <= ROUNDING_TOLERANCE_CENTS:
        return True
    if evidence.mentions_fee and invoice_id in evidence.reference_ids():
        return True
    if evidence.mentions_part_payment and invoice_id in evidence.reference_ids():
        return True
    return False


def _reference_conflict(proposal: Decision, evidence: Evidence) -> list[Veto]:
    """AP-07.2: a resolvable reference that disagrees with the allocation."""
    open_reference_ids = {
        str(v["invoice_id"])
        for v in evidence.resolved_references
        if int(v["outstanding_cents"]) > 0
    }
    if not open_reference_ids:
        return []
    allocated = {a.invoice_id for a in proposal.allocations}
    if allocated == open_reference_ids or allocated <= open_reference_ids:
        return []
    return [
        Veto(
            "REFERENCE_CONFLICT",
            "AP-07.2",
            f"remittance names {sorted(open_reference_ids)} but the allocation is "
            f"{sorted(allocated)}; identification requires reference and amount to agree",
        )
    ]


def _amount_ambiguity(proposal: Decision, evidence: Evidence) -> list[Veto]:
    """AP-07.2(b): amount-based identification requires a unique candidate."""
    if evidence.resolved_references:
        return []  # identification came from the reference, not the amount
    candidates = {str(v["invoice_id"]) for v in evidence.vendor_amount_candidates}
    if len(candidates) <= 1:
        return []
    allocated = {a.invoice_id for a in proposal.allocations}
    if allocated <= candidates:
        return [
            Veto(
                "AMBIGUOUS_AMOUNT",
                "AP-07.2",
                f"{len(candidates)} open invoices for this supplier share this amount "
                f"({sorted(candidates)}); the evidence cannot single one out",
            )
        ]
    return []


def review_and_record(
    payment: Payment,
    proposal: Decision,
    evidence: Evidence,
    session: ToolSession,
    stats: dict[str, Any],
) -> Decision:
    """Run the gate, write its verdict into the trajectory, and count vetoes.

    Every policy that uses the gate goes through here. The bookkeeping is
    shared rather than repeated so that a gated run always leaves the same
    evidence behind, whichever proposer produced it -- an analyst reading a
    trajectory should not be able to tell which policy wrote it from whether
    the gate's verdict happens to be recorded.
    """
    final, vetoes = review(payment, proposal, evidence, session)

    if vetoes:
        stats["vetoes"] = stats.get("vetoes", 0) + 1
        codes = stats.setdefault("veto_codes", {})
        for veto in vetoes:
            codes[veto.code] = codes.get(veto.code, 0) + 1
        session.note("gate", {
            "verdict": "WITHHELD",
            "proposed": [
                {"invoice_id": a.invoice_id, "amount_cents": a.amount_cents}
                for a in proposal.allocations
            ],
            "vetoes": [v.as_text() for v in vetoes],
        })
    else:
        session.note("gate", {
            "verdict": "PASSED",
            "proposed_action": proposal.action,
        })

    return final


def gate_is_monotone(before: Decision, after: Decision) -> bool:
    """A gate output is legal only if it kept the proposal or escalated it."""
    if after.action == "MATCH":
        return before.action == "MATCH" and after.normalised().allocations == before.normalised().allocations
    return True
