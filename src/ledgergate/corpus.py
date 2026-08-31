"""Deterministic synthetic corpus with planted reconciliation hazards.

No real company, vendor or bank data is used anywhere in this project. Every
record below is generated from a seeded PRNG, so the corpus is reproducible
byte-for-byte on any machine and can be regenerated from scratch by a judge.

The generator is written hazard-first. Each hazard is a *named failure mode a
real accounts-payable team hits*, and each one is emitted with a ground truth
that is defensible from the visible evidence alone. ``audit_corpus`` then
mechanically re-checks that claim; if the generator ever produces a payment
whose "correct" answer is not actually determinable, the audit fails loudly
rather than silently rewarding a lucky guess.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

from .types import HAZARDS, Allocation, Invoice, Payment, Truth

BASE_DATE = date(2026, 5, 1)

#: (vendor_id, canonical name, bank-statement aliases)
VENDORS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("V01", "Acme Manufacturing", ("ACME MANUFACTURING", "Acme Mfg Ltd", "ACME MANUFACTURING LTD", "ACME MFG")),
    ("V02", "Borealis Logistics", ("BOREALIS LOGISTICS", "Borealis Log.", "BOREALIS LOGISTICS BV", "BOREALIS")),
    ("V03", "Cedar Print Works", ("CEDAR PRINT WORKS", "Cedar PrintWorks", "CEDAR PRINT WKS", "CEDARPRINT")),
    ("V04", "Delta Instruments", ("DELTA INSTRUMENTS", "Delta Instr Inc", "DELTA INSTRUMENT CO", "DELTA INST")),
    ("V05", "Everline Textiles", ("EVERLINE TEXTILES", "Everline Textile Co", "EVERLINE TEX", "EVERLINE")),
    ("V06", "Foxbridge Chemicals", ("FOXBRIDGE CHEMICALS", "Foxbridge Chem", "FOXBRIDGE CHEMICAL LTD", "FOXBRIDGE")),
    ("V07", "Granite Fasteners", ("GRANITE FASTENERS", "Granite Fastener Co", "GRANITE FSTNRS", "GRANITE")),
    ("V08", "Harborview Packaging", ("HARBORVIEW PACKAGING", "Harborview Pkg", "HARBORVIEW PACK LTD", "HARBORVIEW")),
    ("V09", "Ionvale Electronics", ("IONVALE ELECTRONICS", "Ionvale Elec", "IONVALE ELECTRONIC SA", "IONVALE")),
    ("V10", "Juniper Analytics", ("JUNIPER ANALYTICS", "Juniper Analytic", "JUNIPER ANALYTICS LLC", "JUNIPER")),
    ("V11", "Kestrel Machining", ("KESTREL MACHINING", "Kestrel Mach", "KESTREL MACHINING GMBH", "KESTREL")),
    ("V12", "Larkspur Supplies", ("LARKSPUR SUPPLIES", "Larkspur Supply", "LARKSPUR SUPPLIES LTD", "LARKSPUR")),
)

UNKNOWN_COUNTERPARTIES = (
    "NORTHWIND TRADING CO",
    "PELICAN BAY HOLDINGS",
    "QUARRY LANE SERVICES",
    "RIVERSTONE PARTNERS",
)


@dataclass(frozen=True, slots=True)
class Corpus:
    name: str
    seed: int
    invoices: tuple[Invoice, ...]
    payments: tuple[Payment, ...]
    opening_allocations: tuple[Allocation, ...]
    truths: tuple[Truth, ...]

    def truth_by_payment(self) -> dict[str, Truth]:
        return {t.payment_id: t for t in self.truths}

    def invoice_by_id(self) -> dict[str, Invoice]:
        return {i.invoice_id: i for i in self.invoices}


#: Each split gets its own identifier prefix and invoice-number block. Sharing
#: them across splits made traces ambiguous ("which PAY0007?") and left a
#: latent collision hazard in the response cache, which is keyed by prompt
#: content. Disjoint namespaces remove both problems outright.
SPLITS: dict[str, tuple[str, int]] = {
    "dev": ("DEV", 4_000),
    "holdout": ("HLD", 60_000),
}


class _Builder:
    """Stateful helper that keeps identifiers and amounts collision-free."""

    def __init__(self, seed: int, tag: str = "DEV", number_base: int = 4_000) -> None:
        self.rng = random.Random(seed)
        self.tag = tag
        self.number_base = number_base
        self.invoices: list[Invoice] = []
        self.payments: list[Payment] = []
        self.truths: list[Truth] = []
        self.opening: list[Allocation] = []
        self._used_amounts: set[int] = set()
        self._invoice_seq = 0
        self._payment_seq = 0
        self._bank_seq = 0

    # -- primitives -------------------------------------------------------

    def fresh_amount(self, lo: int = 15_000, hi: int = 4_800_000, credit: int = 0) -> int:
        """An invoice face value whose face *and* net-due are both unseen."""
        for _ in range(10_000):
            amount = self.rng.randrange(lo, hi, 13)
            if amount in self._used_amounts or (amount - credit) in self._used_amounts:
                continue
            self._used_amounts.add(amount)
            if credit:
                self._used_amounts.add(amount - credit)
            return amount
        raise RuntimeError("exhausted amount space")

    def reserve(self, amount: int) -> None:
        self._used_amounts.add(amount)

    def amount_is_free(self, amount: int) -> bool:
        return amount not in self._used_amounts

    def distinct_amount_near(self, target: int) -> int:
        """Nudge ``target`` until it collides with no invoice value."""
        candidate = target
        step = 7
        while candidate in self._used_amounts:
            candidate += step
        self._used_amounts.add(candidate)
        return candidate

    def add_invoice(
        self,
        vendor: tuple[str, str, tuple[str, ...]],
        amount_cents: int,
        *,
        credit_note_cents: int = 0,
        issue_offset: int | None = None,
        currency: str = "USD",
    ) -> Invoice:
        self._invoice_seq += 1
        offset = self.rng.randrange(0, 55) if issue_offset is None else issue_offset
        issue = BASE_DATE + timedelta(days=offset)
        invoice = Invoice(
            invoice_id=f"{self.tag}-INV{self._invoice_seq:04d}",
            invoice_number=f"INV-2026-{self.number_base + self._invoice_seq * 7:05d}",
            vendor_id=vendor[0],
            vendor_name=vendor[1],
            amount_cents=amount_cents,
            currency=currency,
            issue_date=issue.isoformat(),
            due_date=(issue + timedelta(days=30)).isoformat(),
            credit_note_cents=credit_note_cents,
        )
        self.invoices.append(invoice)
        return invoice

    def alias(self, vendor: tuple[str, str, tuple[str, ...]]) -> str:
        return self.rng.choice(vendor[2])

    def next_bank_reference(self) -> str:
        self._bank_seq += 1
        return f"{self.tag}-BNK-{self._bank_seq:06d}"

    def add_payment(
        self,
        *,
        counterparty: str,
        amount_cents: int,
        value_date: str,
        memo: str,
        currency: str = "USD",
        bank_reference: str | None = None,
    ) -> Payment:
        self._payment_seq += 1
        payment = Payment(
            payment_id=f"{self.tag}-PAY{self._payment_seq:04d}",
            bank_reference=bank_reference or self.next_bank_reference(),
            counterparty_raw=counterparty,
            amount_cents=amount_cents,
            currency=currency,
            value_date=value_date,
            memo=memo,
        )
        self.payments.append(payment)
        return payment

    def add_truth(
        self,
        payment: Payment,
        hazard: str,
        action: str,
        allocations: Sequence[Allocation] = (),
        note: str = "",
    ) -> None:
        self.truths.append(
            Truth(
                payment_id=payment.payment_id,
                hazard=hazard,
                expected_action=action,  # type: ignore[arg-type]
                expected_allocations=tuple(allocations),
                note=note,
            )
        )

    def settle_date(self, *invoices: Invoice, jitter: tuple[int, int] = (-4, 18)) -> str:
        """A plausible value date that never precedes any invoice's issue date.

        Getting this wrong once already produced a mislabelled consolidated
        receipt: the value date was taken from the last invoice in the group
        while a sibling had been issued later, which made the "correct" answer
        a receipt that arrived before the invoice existed. The clamp below is
        re-asserted by ``audit_corpus`` so the same class of labelling error
        cannot come back silently.
        """
        latest_due = max(date.fromisoformat(i.due_date) for i in invoices)
        latest_issue = max(date.fromisoformat(i.issue_date) for i in invoices)
        candidate = latest_due + timedelta(days=self.rng.randrange(*jitter))
        return max(candidate, latest_issue + timedelta(days=1)).isoformat()


def _transpose_digits(invoice_number: str, taken: set[str]) -> str:
    """Swap an adjacent digit pair so the reference points at nothing real."""
    prefix, _, digits = invoice_number.rpartition("-")
    chars = list(digits)
    for i in range(len(chars) - 1):
        if chars[i] != chars[i + 1]:
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
            candidate = f"{prefix}-{''.join(chars)}"
            if candidate not in taken:
                return candidate
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return f"{prefix}-{digits[:-1]}9"


def build_corpus(name: str, seed: int, instances: int = 3) -> Corpus:
    """Generate a corpus containing ``instances`` payments per hazard class."""
    tag, number_base = SPLITS.get(name, ("DEV", 4_000))
    b = _Builder(seed, tag=tag, number_base=number_base)
    vendors = list(VENDORS)

    # Filler invoices give the search tools a realistic haystack.
    for vendor in vendors:
        for _ in range(2):
            b.add_invoice(vendor, b.fresh_amount())

    def pick_vendor(offset: int) -> tuple[str, str, tuple[str, ...]]:
        return vendors[offset % len(vendors)]

    for n in range(instances):
        # 1. CLEAN_EXACT -- and the first leg of the duplicate-ingest pair.
        v = pick_vendor(n)
        inv = b.add_invoice(v, b.fresh_amount())
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=inv.net_due_cents,
            value_date=b.settle_date(inv),
            memo=f"PAYMENT {inv.invoice_number}",
        )
        b.add_truth(pay, "CLEAN_EXACT", "MATCH", [Allocation(inv.invoice_id, inv.net_due_cents)],
                    "reference, vendor and amount all agree")

        # 15. DUPLICATE_PAYMENT -- same bank movement delivered twice.
        dup = b.add_payment(
            counterparty=pay.counterparty_raw,
            amount_cents=pay.amount_cents,
            value_date=pay.value_date,
            memo=pay.memo,
            bank_reference=pay.bank_reference,
        )
        b.add_truth(dup, "DUPLICATE_PAYMENT", "ABSTAIN", [],
                    "bank_reference already ingested; re-applying would double-pay")

        # 2. NAME_NOISE -- no reference, messy counterparty, unique amount.
        v = pick_vendor(n + 1)
        inv = b.add_invoice(v, b.fresh_amount())
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=inv.net_due_cents,
            value_date=b.settle_date(inv),
            memo="ACH CREDIT",
        )
        b.add_truth(pay, "NAME_NOISE", "MATCH", [Allocation(inv.invoice_id, inv.net_due_cents)],
                    "amount is unique to one open invoice for this vendor")

        # 3. BANK_FEE -- intermediary bank deducted its cut.
        v = pick_vendor(n + 2)
        inv = b.add_invoice(v, b.fresh_amount())
        fee = b.rng.randrange(1_200, 3_500)
        amount = b.distinct_amount_near(inv.net_due_cents - fee)
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=amount,
            value_date=b.settle_date(inv),
            memo=f"{inv.invoice_number} LESS CORRESPONDENT BANK FEE",
        )
        b.add_truth(pay, "BANK_FEE", "MATCH", [Allocation(inv.invoice_id, amount)],
                    "memo names the invoice and explains the shortfall; apply cash received")

        # 4. ROUNDING_FX -- one or two cents short, reference present.
        v = pick_vendor(n + 3)
        inv = b.add_invoice(v, b.fresh_amount())
        amount = b.distinct_amount_near(inv.net_due_cents - b.rng.randrange(1, 3))
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=amount,
            value_date=b.settle_date(inv),
            memo=f"REF {inv.invoice_number}",
        )
        b.add_truth(pay, "ROUNDING_FX", "MATCH", [Allocation(inv.invoice_id, amount)],
                    "sub-cent rounding on the sending side; within tolerance")

        # 5. TRANSPOSED_REF -- reference is wrong, amount and vendor are right.
        v = pick_vendor(n + 4)
        inv = b.add_invoice(v, b.fresh_amount())
        taken = {i.invoice_number for i in b.invoices}
        bad_ref = _transpose_digits(inv.invoice_number, taken)
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=inv.net_due_cents,
            value_date=b.settle_date(inv),
            memo=f"INVOICE {bad_ref}",
        )
        b.add_truth(pay, "TRANSPOSED_REF", "MATCH", [Allocation(inv.invoice_id, inv.net_due_cents)],
                    "cited reference does not exist; amount and vendor identify one invoice")

        # 6. CREDIT_NOTE -- payer nets off an agreed credit.
        v = pick_vendor(n + 5)
        credit = b.rng.randrange(5_000, 40_000)
        inv = b.add_invoice(v, b.fresh_amount(credit=credit), credit_note_cents=credit)
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=inv.net_due_cents,
            value_date=b.settle_date(inv),
            memo=f"{inv.invoice_number} NET OF CREDIT NOTE",
        )
        b.add_truth(pay, "CREDIT_NOTE", "MATCH", [Allocation(inv.invoice_id, inv.net_due_cents)],
                    "payment equals invoice less the recorded credit note")

        # 7. CONSOLIDATED_REF -- one wire, several invoices, all referenced.
        v = pick_vendor(n + 6)
        group = [b.add_invoice(v, b.fresh_amount(20_000, 900_000)) for _ in range(3)]
        total = sum(i.net_due_cents for i in group)
        b.reserve(total)
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=total,
            value_date=b.settle_date(*group),
            memo="SETTLEMENT " + " ".join(i.invoice_number for i in group),
        )
        b.add_truth(pay, "CONSOLIDATED_REF", "MATCH",
                    [Allocation(i.invoice_id, i.net_due_cents) for i in group],
                    "memo enumerates every invoice and the total reconciles exactly")

        # 8. CROSS_VENDOR_TRAP -- an identical amount sits under another vendor.
        v = pick_vendor(n + 7)
        other = pick_vendor(n + 8)
        shared = b.fresh_amount(30_000, 1_500_000)
        inv = b.add_invoice(v, shared)
        decoy = b.add_invoice(other, shared)
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=shared,
            value_date=b.settle_date(inv),
            memo="ACH CREDIT",
        )
        b.add_truth(pay, "CROSS_VENDOR_TRAP", "MATCH", [Allocation(inv.invoice_id, shared)],
                    f"amount also matches {decoy.invoice_id}; counterparty resolves the tie")

        # 9. PARTIAL_DECLARED -- the memo says it is a part payment.
        v = pick_vendor(n + 9)
        inv = b.add_invoice(v, b.fresh_amount(200_000, 2_000_000))
        amount = b.distinct_amount_near(inv.net_due_cents * 40 // 100)
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=amount,
            value_date=b.settle_date(inv),
            memo=f"DEPOSIT 40PCT {inv.invoice_number} PART 1 OF 2",
        )
        b.add_truth(pay, "PARTIAL_DECLARED", "MATCH", [Allocation(inv.invoice_id, amount)],
                    "explicit part payment against a named invoice")

        # 10. PARTIAL_SILENT -- short payment with no explanation.
        v = pick_vendor(n + 10)
        inv = b.add_invoice(v, b.fresh_amount(200_000, 2_000_000))
        amount = b.distinct_amount_near(inv.net_due_cents * 62 // 100)
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=amount,
            value_date=b.settle_date(inv),
            memo="ACH CREDIT",
        )
        b.add_truth(pay, "PARTIAL_SILENT", "ABSTAIN", [],
                    "indistinguishable from a payment for work not yet invoiced")

        # 11. CONSOLIDATED_AMBIGUOUS -- two disjoint subsets share a total.
        v = pick_vendor(n + 11)
        a1 = b.add_invoice(v, b.fresh_amount(100_000, 400_000))
        a2 = b.add_invoice(v, b.fresh_amount(100_000, 400_000))
        delta = b.rng.randrange(5_000, 30_000)
        c1 = b.add_invoice(v, a1.net_due_cents + delta)
        c2 = b.add_invoice(v, a2.net_due_cents - delta)
        b.reserve(c1.amount_cents)
        b.reserve(c2.amount_cents)
        total = a1.net_due_cents + a2.net_due_cents
        b.reserve(total)
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=total,
            value_date=b.settle_date(a2),
            memo="BULK SETTLEMENT",
        )
        b.add_truth(pay, "CONSOLIDATED_AMBIGUOUS", "ABSTAIN", [],
                    f"{a1.invoice_id}+{a2.invoice_id} and {c1.invoice_id}+{c2.invoice_id} both total exactly this")

        # 12. AMBIGUOUS_TWIN -- two open invoices, identical amounts.
        v = pick_vendor(n + 2)
        twin_amount = b.fresh_amount(40_000, 900_000)
        t1 = b.add_invoice(v, twin_amount)
        t2 = b.add_invoice(v, twin_amount)
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=twin_amount,
            value_date=b.settle_date(t1),
            memo="ACH CREDIT",
        )
        b.add_truth(pay, "AMBIGUOUS_TWIN", "ABSTAIN", [],
                    f"{t1.invoice_id} and {t2.invoice_id} are indistinguishable on this evidence")

        # 13. WRONG_REF_CONFLICT -- reference and amount name different invoices.
        v = pick_vendor(n + 3)
        cited = b.add_invoice(v, b.fresh_amount(50_000, 800_000))
        actual = b.add_invoice(v, b.fresh_amount(50_000, 800_000))
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=actual.net_due_cents,
            value_date=b.settle_date(actual),
            memo=f"PAYMENT FOR {cited.invoice_number}",
        )
        b.add_truth(pay, "WRONG_REF_CONFLICT", "ABSTAIN", [],
                    f"memo cites {cited.invoice_id} but the amount is {actual.invoice_id}'s; evidence conflicts")

        # 14. CURRENCY_MISMATCH -- no conversion rate is available anywhere.
        v = pick_vendor(n + 4)
        inv = b.add_invoice(v, b.fresh_amount(80_000, 1_200_000))
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=inv.net_due_cents,
            value_date=b.settle_date(inv),
            memo=f"SEPA {inv.invoice_number}",
            currency="EUR",
        )
        b.add_truth(pay, "CURRENCY_MISMATCH", "ABSTAIN", [],
                    "invoice is USD, payment is EUR, and no FX rate source is configured")

        # 16. ALREADY_SETTLED -- invoice was closed before this feed arrived.
        v = pick_vendor(n + 5)
        inv = b.add_invoice(v, b.fresh_amount(40_000, 700_000))
        b.opening.append(Allocation(inv.invoice_id, inv.net_due_cents))
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=inv.net_due_cents,
            value_date=b.settle_date(inv),
            memo=f"REMITTANCE {inv.invoice_number}",
        )
        b.add_truth(pay, "ALREADY_SETTLED", "ABSTAIN", [],
                    "invoice carries no outstanding balance; paying again is a loss")

        # 17. REVERSAL -- money coming back out.
        v = pick_vendor(n + 6)
        inv = b.add_invoice(v, b.fresh_amount(60_000, 900_000))
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=-inv.net_due_cents,
            value_date=b.settle_date(inv),
            memo=f"RETURN OF FUNDS REVERSAL {inv.invoice_number}",
        )
        b.add_truth(pay, "REVERSAL", "ABSTAIN", [],
                    "the written procedure does not define reversal handling")

        # 18. OVERPAYMENT -- more cash than the invoice is worth.
        v = pick_vendor(n + 7)
        inv = b.add_invoice(v, b.fresh_amount(60_000, 900_000))
        amount = b.distinct_amount_near(inv.net_due_cents * 104 // 100)
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=amount,
            value_date=b.settle_date(inv),
            memo=f"PAYMENT {inv.invoice_number}",
        )
        b.add_truth(pay, "OVERPAYMENT", "ABSTAIN", [],
                    "the procedure does not define what happens to the residual credit")

        # 19. PREDATED -- cash arrived before the invoice existed.
        v = pick_vendor(n + 8)
        inv = b.add_invoice(v, b.fresh_amount(60_000, 900_000), issue_offset=40)
        issue = date.fromisoformat(inv.issue_date)
        pay = b.add_payment(
            counterparty=b.alias(v),
            amount_cents=inv.net_due_cents,
            value_date=(issue - timedelta(days=b.rng.randrange(4, 16))).isoformat(),
            memo=f"PAYMENT {inv.invoice_number}",
        )
        b.add_truth(pay, "PREDATED", "ABSTAIN", [],
                    "value date precedes the invoice issue date; the reference cannot be trusted")

        # 20. NO_CANDIDATE -- nothing in the book explains this money.
        stranger = UNKNOWN_COUNTERPARTIES[n % len(UNKNOWN_COUNTERPARTIES)]
        amount = b.distinct_amount_near(b.rng.randrange(25_000, 1_400_000))
        pay = b.add_payment(
            counterparty=stranger,
            amount_cents=amount,
            value_date=(BASE_DATE + timedelta(days=b.rng.randrange(20, 80))).isoformat(),
            memo="INCOMING WIRE",
        )
        b.add_truth(pay, "NO_CANDIDATE", "ABSTAIN", [],
                    "counterparty is not a known vendor and no invoice fits")

    return Corpus(
        name=name,
        seed=seed,
        invoices=tuple(b.invoices),
        payments=tuple(b.payments),
        opening_allocations=tuple(b.opening),
        truths=tuple(b.truths),
    )


# --------------------------------------------------------------------------
# Ground-truth audit
# --------------------------------------------------------------------------


class CorpusAuditError(AssertionError):
    """The generated corpus contains a payment whose truth is not well posed."""


def audit_corpus(corpus: Corpus) -> list[str]:
    """Re-derive the corpus invariants. Returns the list of checks performed.

    This exists because a synthetic benchmark is only as trustworthy as its
    labels. Every assertion here is a property the *label* must satisfy; if
    one fails, the score would be measuring luck instead of judgment.
    """
    checks: list[str] = []
    invoices = corpus.invoice_by_id()
    truths = corpus.truth_by_payment()
    payments = {p.payment_id: p for p in corpus.payments}

    # Opening balances, replayed so "outstanding" means what it says.
    outstanding = {i.invoice_id: i.net_due_cents for i in corpus.invoices}
    for alloc in corpus.opening_allocations:
        outstanding[alloc.invoice_id] -= alloc.amount_cents

    if len(payments) != len(corpus.payments):
        raise CorpusAuditError("duplicate payment_id in corpus")
    checks.append("payment ids unique")

    if set(truths) != set(payments):
        raise CorpusAuditError("every payment must carry exactly one truth row")
    checks.append("one truth row per payment")

    missing = set(HAZARDS) - {t.hazard for t in corpus.truths}
    if missing:
        raise CorpusAuditError(f"hazards never exercised: {sorted(missing)}")
    checks.append(f"all {len(HAZARDS)} hazard classes present")

    for inv in corpus.invoices:
        if inv.credit_note_cents < 0 or inv.credit_note_cents >= inv.amount_cents:
            raise CorpusAuditError(f"{inv.invoice_id}: nonsensical credit note")
    checks.append("credit notes within bounds")

    seen_refs: set[str] = set()
    duplicate_refs: set[str] = set()
    for pay in corpus.payments:
        if pay.bank_reference in seen_refs:
            duplicate_refs.add(pay.bank_reference)
        seen_refs.add(pay.bank_reference)
        if pay.amount_cents == 0:
            raise CorpusAuditError(f"{pay.payment_id}: zero-value payment")

    for ref in duplicate_refs:
        rows = [p for p in corpus.payments if p.bank_reference == ref]
        hazards = [truths[p.payment_id].hazard for p in rows]
        if hazards[0] == "DUPLICATE_PAYMENT":
            raise CorpusAuditError(f"{ref}: duplicate leg precedes its original")
        if not all(h == "DUPLICATE_PAYMENT" for h in hazards[1:]):
            raise CorpusAuditError(f"{ref}: repeated bank reference outside the duplicate hazard")
    checks.append("repeated bank references occur only as the duplicate hazard, original first")

    replay_outstanding = dict(outstanding)
    for pay in corpus.payments:
        truth = truths[pay.payment_id]

        if truth.expected_action == "ABSTAIN":
            if truth.expected_allocations:
                raise CorpusAuditError(f"{pay.payment_id}: ABSTAIN must carry no allocations")
            continue

        if not truth.expected_allocations:
            raise CorpusAuditError(f"{pay.payment_id}: MATCH must carry allocations")

        total = sum(a.amount_cents for a in truth.expected_allocations)
        if total != pay.amount_cents:
            raise CorpusAuditError(
                f"{pay.payment_id}: allocations total {total} but payment is {pay.amount_cents}"
            )

        for alloc in truth.expected_allocations:
            inv = invoices.get(alloc.invoice_id)
            if inv is None:
                raise CorpusAuditError(f"{pay.payment_id}: allocation to unknown invoice")
            if inv.currency != pay.currency:
                raise CorpusAuditError(f"{pay.payment_id}: cross-currency allocation in truth")
            if alloc.amount_cents <= 0:
                raise CorpusAuditError(f"{pay.payment_id}: non-positive allocation in truth")
            if alloc.amount_cents > replay_outstanding.get(alloc.invoice_id, 0):
                raise CorpusAuditError(
                    f"{pay.payment_id}: truth over-applies {alloc.invoice_id}"
                )
            replay_outstanding[alloc.invoice_id] -= alloc.amount_cents

    checks.append("every MATCH truth is payable: positive, in-currency, within outstanding balance")

    # A receipt cannot legitimately settle an invoice that did not yet exist.
    # AP-07.9(iv) escalates those, so a MATCH label here would contradict the
    # very procedure the policies are graded against.
    for pay in corpus.payments:
        truth = truths[pay.payment_id]
        if truth.expected_action != "MATCH":
            continue
        for alloc in truth.expected_allocations:
            issued = invoices[alloc.invoice_id].issue_date
            if pay.value_date < issued:
                raise CorpusAuditError(
                    f"{pay.payment_id}: labelled MATCH but dated {pay.value_date}, before "
                    f"{alloc.invoice_id} was issued on {issued}"
                )
    checks.append("no MATCH truth asks for a receipt that predates its own invoice")

    # Uniqueness claim for the hazards that rest on it.
    for pay in corpus.payments:
        truth = truths[pay.payment_id]
        if truth.hazard not in {"NAME_NOISE", "CROSS_VENDOR_TRAP"}:
            continue
        target = truth.expected_allocations[0]
        vendor_id = invoices[target.invoice_id].vendor_id
        rivals = [
            i
            for i in corpus.invoices
            if i.vendor_id == vendor_id
            and i.invoice_id != target.invoice_id
            and i.net_due_cents == pay.amount_cents
            and outstanding.get(i.invoice_id, 0) > 0
        ]
        if rivals:
            raise CorpusAuditError(
                f"{pay.payment_id}: {truth.hazard} is not uniquely resolvable; rivals {rivals}"
            )
    checks.append("amount-resolved MATCH hazards have exactly one candidate per vendor")

    for pay in corpus.payments:
        truth = truths[pay.payment_id]
        if truth.hazard != "AMBIGUOUS_TWIN":
            continue
        twins = [
            i
            for i in corpus.invoices
            if i.net_due_cents == pay.amount_cents and outstanding.get(i.invoice_id, 0) > 0
        ]
        if len({t.vendor_id for t in twins}) != 1 or len(twins) < 2:
            raise CorpusAuditError(f"{pay.payment_id}: twin hazard lacks two same-vendor twins")
    checks.append("twin hazards really do have two indistinguishable candidates")

    return checks
