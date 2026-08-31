"""Frozen data contracts shared by the corpus, the policies and the verifier.

Every monetary value in LedgerGate is an integer number of minor units
(cents). Floats never touch money: a 0.01 rounding artefact in a
reconciliation system is indistinguishable from a real short-payment, and
that ambiguity is exactly what this project exists to eliminate.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Iterable, Literal, Mapping, Sequence

Action = Literal["MATCH", "ABSTAIN"]

#: Every planted hazard class in the corpus. The verifier reports per-hazard
#: results against this list, so a policy cannot quietly ignore a whole class.
HAZARDS: tuple[str, ...] = (
    "CLEAN_EXACT",
    "NAME_NOISE",
    "BANK_FEE",
    "ROUNDING_FX",
    "TRANSPOSED_REF",
    "CREDIT_NOTE",
    "CONSOLIDATED_REF",
    "CROSS_VENDOR_TRAP",
    "PARTIAL_DECLARED",
    "PARTIAL_SILENT",
    "CONSOLIDATED_AMBIGUOUS",
    "AMBIGUOUS_TWIN",
    "WRONG_REF_CONFLICT",
    "CURRENCY_MISMATCH",
    "DUPLICATE_PAYMENT",
    "ALREADY_SETTLED",
    "REVERSAL",
    "OVERPAYMENT",
    "PREDATED",
    "NO_CANDIDATE",
)


@dataclass(frozen=True, slots=True)
class Invoice:
    """A payable invoice as it exists in the accounting system."""

    invoice_id: str
    invoice_number: str
    vendor_id: str
    vendor_name: str
    amount_cents: int
    currency: str
    issue_date: str
    due_date: str
    credit_note_cents: int = 0

    @property
    def net_due_cents(self) -> int:
        """Invoice face value less any credit note already granted."""
        return self.amount_cents - self.credit_note_cents


@dataclass(frozen=True, slots=True)
class Payment:
    """One row from the bank statement feed.

    ``bank_reference`` is the bank's own identifier for the movement. Two rows
    sharing a ``bank_reference`` are the *same* real-world movement delivered
    twice, which is the duplicate-ingest hazard.
    """

    payment_id: str
    bank_reference: str
    counterparty_raw: str
    amount_cents: int
    currency: str
    value_date: str
    memo: str = ""


@dataclass(frozen=True, slots=True)
class Allocation:
    """Application of ``amount_cents`` from a payment onto one invoice."""

    invoice_id: str
    amount_cents: int


@dataclass(frozen=True, slots=True)
class Decision:
    """A policy's answer for a single payment.

    ``MATCH`` means "post these allocations to the ledger". ``ABSTAIN`` means
    "route to a human"; it is a legitimate, sometimes optimal answer, and the
    verifier scores it as such.
    """

    payment_id: str
    action: Action
    allocations: tuple[Allocation, ...] = ()
    reason_code: str = ""
    rationale: str = ""
    evidence: tuple[str, ...] = ()

    def total_allocated_cents(self) -> int:
        return sum(a.amount_cents for a in self.allocations)

    def normalised(self) -> "Decision":
        """Canonical form: allocations sorted, ABSTAIN carries no allocations."""
        if self.action == "ABSTAIN":
            return replace(self, allocations=())
        ordered = tuple(sorted(self.allocations, key=lambda a: a.invoice_id))
        return replace(self, allocations=ordered)


@dataclass(frozen=True, slots=True)
class Truth:
    """Ground truth for one payment. Read by the verifier and by nothing else."""

    payment_id: str
    hazard: str
    expected_action: Action
    expected_allocations: tuple[Allocation, ...] = ()
    note: str = ""


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """An immutable line in the sandbox journal."""

    sequence: int
    payment_id: str
    invoice_id: str
    amount_cents: int
    state: str
    idempotency_key: str


# --------------------------------------------------------------------------
# Serialisation helpers. Kept explicit rather than pickling dataclasses so the
# on-disk corpus is a stable, human-reviewable contract across versions.
# --------------------------------------------------------------------------


def _dump(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, (list, tuple)):
        return [_dump(x) for x in obj]
    return obj


def to_json(obj: Any, *, indent: int = 2) -> str:
    """Deterministic JSON: sorted keys, trailing newline, no float drift."""
    return json.dumps(_dump(obj), indent=indent, sort_keys=True, ensure_ascii=False) + "\n"


def invoice_from_dict(d: Mapping[str, Any]) -> Invoice:
    return Invoice(
        invoice_id=d["invoice_id"],
        invoice_number=d["invoice_number"],
        vendor_id=d["vendor_id"],
        vendor_name=d["vendor_name"],
        amount_cents=int(d["amount_cents"]),
        currency=d["currency"],
        issue_date=d["issue_date"],
        due_date=d["due_date"],
        credit_note_cents=int(d.get("credit_note_cents", 0)),
    )


def payment_from_dict(d: Mapping[str, Any]) -> Payment:
    return Payment(
        payment_id=d["payment_id"],
        bank_reference=d["bank_reference"],
        counterparty_raw=d["counterparty_raw"],
        amount_cents=int(d["amount_cents"]),
        currency=d["currency"],
        value_date=d["value_date"],
        memo=d.get("memo", ""),
    )


def allocations_from_list(items: Iterable[Mapping[str, Any]]) -> tuple[Allocation, ...]:
    return tuple(
        Allocation(invoice_id=i["invoice_id"], amount_cents=int(i["amount_cents"]))
        for i in items
    )


def truth_from_dict(d: Mapping[str, Any]) -> Truth:
    return Truth(
        payment_id=d["payment_id"],
        hazard=d["hazard"],
        expected_action=d["expected_action"],
        expected_allocations=allocations_from_list(d.get("expected_allocations", ())),
        note=d.get("note", ""),
    )


def decision_from_dict(d: Mapping[str, Any]) -> Decision:
    return Decision(
        payment_id=d["payment_id"],
        action=d["action"],
        allocations=allocations_from_list(d.get("allocations", ())),
        reason_code=d.get("reason_code", ""),
        rationale=d.get("rationale", ""),
        evidence=tuple(d.get("evidence", ())),
    )


def format_cents(cents: int, currency: str = "") -> str:
    """Render minor units for humans without ever going through a float."""
    sign = "-" if cents < 0 else ""
    whole, minor = divmod(abs(cents), 100)
    body = f"{sign}{whole:,}.{minor:02d}"
    return f"{body} {currency}".strip()


def parse_sequence(items: Sequence[Any]) -> tuple[Any, ...]:
    return tuple(items)
