"""Deterministic proposer, and the guarded policy that pairs it with the gate.

The proposer is a faithful implementation of what AP-07 actually *says*:
identification by reference, identification by unique amount, the two-cent
rounding tolerance, declared part payments, enumerated consolidated receipts,
and the once-only rule for bank references.

It deliberately does **not** implement AP-07.9 -- the section listing the
matters the procedure does not yet cover. Those gaps are the safety gate's
job. Splitting the two makes the ablation honest: running the proposer with
the gate switched off shows exactly which failures come from the written rules
being incomplete, rather than from the implementation being wrong.

``use_gate=False`` exists for that ablation and for no other reason. It is not
a supported configuration for anything that touches a real ledger.
"""

from __future__ import annotations

from typing import Any

from .. import evidence as evidence_mod
from .. import safety
from ..evidence import ROUNDING_TOLERANCE_CENTS, Evidence
from ..tools import ToolSession
from ..types import Allocation, Decision, Payment


def _abstain(payment: Payment, code: str, why: str, ev: Evidence | None = None) -> Decision:
    return Decision(
        payment_id=payment.payment_id,
        action="ABSTAIN",
        reason_code=code,
        rationale=why,
        evidence=tuple(ev.reference_ids()) if ev else (),
    )


def propose(payment: Payment, ev: Evidence, session: ToolSession | None = None) -> Decision:
    """Apply AP-07's identification rules to an evidence bundle.

    ``session`` is optional so the rules stay unit-testable in isolation, but
    the shipped policy always passes one. When it is present, the shortfall is
    computed through the ``compute`` tool rather than in Python, so the number
    the decision turns on appears in the trajectory where a reviewer can check
    it. That is a claim this project makes about agents generally, and it would
    be hollow if the shipped policy exempted itself from it.
    """
    if payment.amount_cents <= 0:
        return _abstain(
            payment, "NON_POSITIVE_RECEIPT",
            "AP-07.9(iii): reversals and returns are outside this revision",
        )

    if ev.duplicate_feed:
        return _abstain(
            payment, "DUPLICATE_FEED",
            f"AP-07.6: bank reference {payment.bank_reference} has already been processed",
        )

    open_refs = [v for v in ev.resolved_references if int(v["outstanding_cents"]) > 0]
    settled_refs = [v for v in ev.resolved_references if int(v["outstanding_cents"]) <= 0]

    if ev.resolved_references and not open_refs:
        return _abstain(
            payment, "REFERENCED_INVOICE_SETTLED",
            "AP-07.2: the remittance names "
            f"{[v['invoice_id'] for v in settled_refs]}, which carry no outstanding balance",
            ev,
        )

    if open_refs:
        total = sum(int(v["outstanding_cents"]) for v in open_refs)

        # AP-07.2(a) single invoice, and AP-07.5 enumerated consolidated receipt.
        if total == payment.amount_cents:
            return Decision(
                payment_id=payment.payment_id,
                action="MATCH",
                allocations=tuple(
                    Allocation(str(v["invoice_id"]), int(v["outstanding_cents"]))
                    for v in sorted(open_refs, key=lambda v: str(v["invoice_id"]))
                ),
                reason_code="REFERENCE_EXACT",
                rationale=(
                    "AP-07.2(a): the remittance enumerates "
                    f"{[v['invoice_id'] for v in open_refs]} and their balances sum "
                    "exactly to the receipt"
                ),
                evidence=(f"referenced={ev.reference_ids()}", f"total_outstanding={total}"),
            )

        if len(open_refs) == 1:
            inv = open_refs[0]
            outstanding = int(inv["outstanding_cents"])
            shortfall = _shortfall(outstanding, payment.amount_cents, session)

            if shortfall < 0:
                return _abstain(
                    payment, "OVERPAYMENT",
                    f"AP-07.9(ii): receipt exceeds the {outstanding} outstanding on "
                    f"{inv['invoice_id']} and the treatment of the residual is undefined",
                    ev,
                )
            if shortfall <= ROUNDING_TOLERANCE_CENTS:
                return _match_single(payment, inv, "ROUNDING_TOLERANCE",
                                     f"AP-07.3: {shortfall}c settlement rounding", ev)
            if ev.mentions_fee:
                return _match_single(payment, inv, "BANK_CHARGE",
                                     f"AP-07.3: remittance declares a bank charge; "
                                     f"{shortfall}c shortfall goes to the write-off run", ev)
            if ev.mentions_part_payment:
                return _match_single(payment, inv, "DECLARED_PART_PAYMENT",
                                     f"AP-07.4: remittance declares a part payment; "
                                     f"{shortfall}c remains outstanding", ev)
            return _abstain(
                payment, "UNEXPLAINED_SHORTFALL",
                f"AP-07.4: {shortfall}c short of {inv['invoice_id']} with no declared "
                "part payment or bank charge",
                ev,
            )

        return _abstain(
            payment, "REFERENCE_SUM_MISMATCH",
            f"AP-07.5: referenced balances total {total}, receipt is "
            f"{payment.amount_cents}; the set is not enumerated exactly",
            ev,
        )

    # AP-07.2(b): identification by a unique amount for a resolved supplier.
    if ev.unresolved_references:
        note = (
            f"remittance cites {ev.unresolved_references}, which is not in the ledger; "
            "falling back to amount identification"
        )
    else:
        note = "no invoice number in the remittance"

    if not ev.vendor_confident:
        return _abstain(
            payment, "SUPPLIER_UNRESOLVED",
            f"AP-07.2(b): counterparty {payment.counterparty_raw!r} does not resolve to a "
            f"single supplier ({note})",
            ev,
        )

    candidates = ev.vendor_amount_candidates
    if len(candidates) == 1:
        return _match_single(
            payment, candidates[0], "UNIQUE_AMOUNT",
            f"AP-07.2(b): exactly one open invoice for {ev.vendor_id} carries this "
            f"balance ({note})",
            ev,
        )
    if len(candidates) > 1:
        return _abstain(
            payment, "AMBIGUOUS_AMOUNT",
            f"AP-07.2: {[c['invoice_id'] for c in candidates]} all carry this balance "
            f"for {ev.vendor_id}; the evidence cannot single one out",
            ev,
        )
    return _abstain(
        payment, "NO_CANDIDATE",
        f"AP-07.2: no open invoice for {ev.vendor_id} matches this receipt ({note})",
        ev,
    )


def _shortfall(outstanding: int, received: int, session: ToolSession | None) -> int:
    """The gap the whole part-payment branch turns on, computed in the open.

    ``safe_compute`` works in integer cents and rejects float literals, so the
    answer is identical to doing it in Python -- the point is not accuracy, it
    is that the subtraction is in the record with its operands.
    """
    if session is None:
        return outstanding - received
    result = session.call("compute", {"expression": f"{outstanding} - {received}"})
    return int(result["result"])


def _match_single(
    payment: Payment, view: dict[str, Any], code: str, why: str, ev: Evidence
) -> Decision:
    return Decision(
        payment_id=payment.payment_id,
        action="MATCH",
        allocations=(Allocation(str(view["invoice_id"]), payment.amount_cents),),
        reason_code=code,
        rationale=why,
        evidence=(
            f"invoice={view['invoice_id']}",
            f"outstanding={view['outstanding_cents']}",
            f"supplier={view['vendor_id']}",
        ),
    )


class GuardedPolicy:
    """Deterministic AP-07 proposer, optionally behind the safety gate."""

    def __init__(self, use_gate: bool = True) -> None:
        self.use_gate = use_gate
        self.name = "guarded" if use_gate else "rules-only"
        self.stats: dict[str, Any] = {"vetoes": 0, "veto_codes": {}}

    def instructions(self) -> str:
        gate = (
            "Proposals then pass the AP-07.9 safety gate, which may withhold a match "
            "but may never create or alter one."
            if self.use_gate
            else "The safety gate is DISABLED. This configuration exists only to measure "
            "what the gate contributes and must not be used against a real ledger."
        )
        return (
            "Deterministic cash application following AP-07.\n"
            "Gather evidence: duplicate-feed check, supplier resolution, invoice numbers "
            "named in the remittance, and open invoices matching the receipt amount.\n"
            "Identify by reference (AP-07.2a) or by unique amount (AP-07.2b). Apply the "
            "two-cent rounding tolerance (AP-07.3), declared part payments and bank "
            "charges (AP-07.3/.4), and enumerated consolidated receipts (AP-07.5). "
            "Never reprocess a bank reference (AP-07.6). Escalate whenever the evidence "
            "does not single out one answer.\n" + gate
        )

    def decide(self, payment: Payment, session: ToolSession) -> Decision:
        # Read the procedure through the tool before acting on it. A rules
        # engine does not strictly need to -- the rules are already compiled
        # into this file -- but a trajectory that cites AP-07 without ever
        # fetching it is asking the reader to take the citation on trust, and
        # this project's entire argument is that they should not have to.
        session.call("procedure", {"section": "identification"})

        ev = evidence_mod.gather(payment, session)
        proposal = propose(payment, ev, session)
        if not self.use_gate:
            return proposal
        return safety.review_and_record(payment, proposal, ev, session, self.stats)
