"""The tool surface exposed to a policy, and the written procedure it reads.

Three properties of this module matter more than the individual tools:

* **No route to ground truth.** ``ToolSession`` is constructed from the invoice
  book and the ledger only. It never receives ``truth.json``. A test walks the
  object graph to assert that a policy cannot reach the labels.

* **Arithmetic is a tool, not a habit.** ``compute`` exists so a language model
  is never asked to do money maths in its head. Mental arithmetic on cents is
  a known failure mode; making it a tool call makes it auditable.

* **The written procedure is deliberately incomplete.** ``procedure`` returns
  the real standard operating procedure this workflow would ship with, and
  that document simply does not say what to do about reversals, overpayments
  or cross-currency receipts. Those gaps are the point of the exercise. A
  policy that notices the gap and escalates is behaving correctly; one that
  invents a rule is not.
"""

from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .ledger import SandboxLedger
from .types import Invoice, Payment

MAX_SEARCH_RESULTS = 12

_LEGAL_SUFFIXES = {
    "LTD", "LIMITED", "INC", "INCORPORATED", "LLC", "PLC", "CO", "COMPANY",
    "CORP", "CORPORATION", "GMBH", "BV", "SA", "AG", "NV", "SARL", "PTY",
}
_NOISE_TOKENS = {"PAYMENT", "ACH", "CREDIT", "WIRE", "SEPA", "REF", "INV", "INVOICE"}


# --------------------------------------------------------------------------
# The written procedure. Incomplete on purpose.
# --------------------------------------------------------------------------

PROCEDURE: dict[str, str] = {
    "overview": (
        "AP-07 Cash Application Procedure (rev. 2026-03).\n"
        "Apply incoming bank receipts against open supplier invoices. Post only "
        "when the supporting evidence identifies exactly one invoice, or an "
        "explicitly enumerated set of invoices. Where evidence is incomplete or "
        "conflicting, route the item to the AP analyst queue. Cash applied to the "
        "wrong invoice is treated as a reportable control failure; an item parked "
        "for review is not."
    ),
    "identification": (
        "AP-07.2 An invoice is identified when EITHER (a) the remittance reference "
        "contains an invoice number present in the ledger AND the counterparty "
        "resolves to that invoice's supplier, OR (b) the receipt amount equals the "
        "outstanding balance of exactly one open invoice for the resolved supplier. "
        "If (a) and (b) point at different invoices, the item is NOT identified."
    ),
    "tolerances": (
        "AP-07.3 A receipt may be applied where it falls short of the outstanding "
        "balance by no more than 2 cents (settlement rounding), or where the "
        "remittance states a correspondent bank charge. Apply the cash actually "
        "received; the residual is handled by the write-off run, not by this "
        "procedure."
    ),
    "part_payments": (
        "AP-07.4 A part payment may be applied where the remittance explicitly "
        "declares it as such and names the invoice. Unexplained short payments are "
        "NOT part payments for the purposes of this procedure."
    ),
    "consolidated": (
        "AP-07.5 A single receipt may settle several invoices where the remittance "
        "enumerates them and the enumerated balances sum exactly to the receipt."
    ),
    "duplicates": (
        "AP-07.6 Each bank reference is processed once. A bank reference already "
        "present in the journal must not be applied again under any circumstances."
    ),
    "gaps": (
        "AP-07.9 Matters not covered by this revision, pending Controller sign-off: "
        "(i) receipts denominated in a currency other than the invoice; "
        "(ii) receipts exceeding the outstanding balance; "
        "(iii) reversals, returns and recalls; "
        "(iv) receipts dated before the invoice was raised. "
        "Until this section is issued, items of these kinds are routed to the AP "
        "analyst queue. Do not infer a rule."
    ),
}


# --------------------------------------------------------------------------
# Name normalisation
# --------------------------------------------------------------------------


def normalise_name(raw: str) -> str:
    upper = re.sub(r"[^A-Z0-9 ]+", " ", raw.upper())
    tokens = [t for t in upper.split() if t and t not in _LEGAL_SUFFIXES and t not in _NOISE_TOKENS]
    return " ".join(tokens)


def name_similarity(a: str, b: str) -> float:
    """0..1 similarity that rewards shared leading tokens.

    Pure ``SequenceMatcher`` treats "GRANITE" and "GRANITE FASTENERS" as only
    moderately similar, but on a bank statement a truncated supplier name is
    the norm. Token containment is therefore blended in.
    """
    na, nb = normalise_name(a), normalise_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return max(ratio, 0.5 * ratio + 0.5 * overlap)


_INVOICE_NUMBER_RE = re.compile(r"\bINV[-\s]?\d{4}[-\s]?\d{3,6}\b", re.IGNORECASE)


def extract_invoice_numbers(text: str) -> list[str]:
    """Pull invoice-number-shaped tokens out of free-text remittance data."""
    found = []
    for raw in _INVOICE_NUMBER_RE.findall(text or ""):
        cleaned = re.sub(r"[\s]+", "-", raw.strip().upper())
        cleaned = re.sub(r"-+", "-", cleaned)
        if cleaned not in found:
            found.append(cleaned)
    return found


# --------------------------------------------------------------------------
# Safe integer arithmetic
# --------------------------------------------------------------------------

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod, ast.USub, ast.UAdd,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Tuple, ast.List,
)


class ComputeError(ValueError):
    pass


def safe_compute(expression: str) -> int | bool | list:
    """Evaluate integer-only arithmetic. No names, no calls, no floats."""
    if len(expression) > 200:
        raise ComputeError("expression too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ComputeError(f"could not parse: {exc.msg}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ComputeError(f"{type(node).__name__} is not permitted")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, bool)):
            raise ComputeError("only integers are permitted; money is counted in cents")

    result = eval(compile(tree, "<compute>", "eval"), {"__builtins__": {}}, {})  # noqa: S307
    if isinstance(result, float):
        raise ComputeError("floating point is not permitted")
    return result


# --------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "procedure",
        "Read a section of the AP-07 cash application procedure. Sections: "
        "overview, identification, tolerances, part_payments, consolidated, "
        "duplicates, gaps. Read 'gaps' before deciding anything unusual.",
        {"type": "object", "properties": {"section": {"type": "string"}}, "required": ["section"]},
    ),
    ToolSpec(
        "resolve_vendor",
        "Resolve a raw bank counterparty string to ranked supplier candidates "
        "with similarity scores in 0..1.",
        {
            "type": "object",
            "properties": {"counterparty": {"type": "string"}},
            "required": ["counterparty"],
        },
    ),
    ToolSpec(
        "find_invoice_by_number",
        "Look up an invoice by its printed invoice number. Returns an empty list "
        "if no such invoice exists, which is itself informative.",
        {
            "type": "object",
            "properties": {"invoice_number": {"type": "string"}},
            "required": ["invoice_number"],
        },
    ),
    ToolSpec(
        "search_invoices",
        "Search the invoice book. Any combination of filters may be supplied. "
        "match_field selects what amount_cents is compared against: 'outstanding' "
        "(the live ledger balance, the correct choice for cash application) or "
        "'net_due' (the invoice register value, which ignores payments already "
        "made). tolerance_cents widens the comparison.",
        {
            "type": "object",
            "properties": {
                "vendor_id": {"type": "string"},
                "amount_cents": {"type": "integer"},
                "tolerance_cents": {"type": "integer"},
                "include_settled": {"type": "boolean"},
                "match_field": {"type": "string", "enum": ["outstanding", "net_due"]},
            },
        },
    ),
    ToolSpec(
        "get_invoice",
        "Full detail for one invoice, including credit notes, currency, dates "
        "and the live outstanding balance.",
        {
            "type": "object",
            "properties": {"invoice_id": {"type": "string"}},
            "required": ["invoice_id"],
        },
    ),
    ToolSpec(
        "check_duplicate_feed",
        "Ask whether this bank reference has already been processed in this run. "
        "AP-07.6 forbids applying the same bank reference twice.",
        {
            "type": "object",
            "properties": {"bank_reference": {"type": "string"}},
            "required": ["bank_reference"],
        },
    ),
    ToolSpec(
        "fx_rate",
        "Request a conversion rate between two currencies.",
        {
            "type": "object",
            "properties": {"base": {"type": "string"}, "quote": {"type": "string"}},
            "required": ["base", "quote"],
        },
    ),
    ToolSpec(
        "compute",
        "Evaluate integer arithmetic over cents, e.g. '145000 - 143750'. Use this "
        "for every calculation instead of doing arithmetic yourself.",
        {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    ),
)

TOOL_NAMES: frozenset[str] = frozenset(spec.name for spec in TOOL_SPECS)


class ToolError(RuntimeError):
    pass


class BudgetExhausted(RuntimeError):
    pass


@dataclass
class ToolSession:
    """Per-payment tool access, with a step budget and a recorded transcript."""

    invoices: Mapping[str, Invoice]
    ledger: SandboxLedger
    payment: Payment
    max_steps: int = 24
    steps: list[dict[str, Any]] = field(default_factory=list)

    @property
    def steps_used(self) -> int:
        return sum(1 for step in self.steps if "tool" in step)

    @property
    def budget_remaining(self) -> int:
        return self.max_steps - self.steps_used

    def note(self, kind: str, payload: Mapping[str, Any]) -> None:
        """Record a non-tool event (a model turn, a retry, a gate verdict).

        These land in the trajectory so a reader can follow the reasoning, but
        they do not consume the tool budget: the budget exists to bound
        *actions against the ledger*, not narration.
        """
        self.steps.append({"event": kind, **dict(payload)})

    def call(self, name: str, arguments: Mapping[str, Any] | None = None) -> Any:
        """Dispatch a tool by name, recording the call and its observation."""
        args = dict(arguments or {})
        if self.steps_used >= self.max_steps:
            raise BudgetExhausted(f"step budget of {self.max_steps} exhausted")
        handler: Callable[..., Any] | None = getattr(self, f"_tool_{name}", None)
        if handler is None or name not in TOOL_NAMES:
            observation: Any = {"error": f"unknown tool {name!r}", "available": sorted(TOOL_NAMES)}
        else:
            try:
                observation = handler(**args)
            except TypeError as exc:
                observation = {"error": f"bad arguments for {name}: {exc}"}
            except (ToolError, ComputeError) as exc:
                observation = {"error": str(exc)}
        self.steps.append({"tool": name, "arguments": args, "observation": observation})
        return observation

    # -- tool implementations ---------------------------------------------

    def _tool_procedure(self, section: str) -> dict[str, Any]:
        key = str(section).strip().lower()
        if key not in PROCEDURE:
            return {"error": f"no section {section!r}", "sections": sorted(PROCEDURE)}
        return {"section": key, "text": PROCEDURE[key]}

    def _tool_resolve_vendor(self, counterparty: str) -> dict[str, Any]:
        seen: dict[str, str] = {}
        for inv in self.invoices.values():
            seen[inv.vendor_id] = inv.vendor_name
        scored = [
            {"vendor_id": vid, "vendor_name": vname,
             "similarity": round(name_similarity(counterparty, vname), 4)}
            for vid, vname in seen.items()
        ]
        scored.sort(key=lambda r: (-r["similarity"], r["vendor_id"]))
        top = scored[:5]
        best = top[0]["similarity"] if top else 0.0
        runner_up = top[1]["similarity"] if len(top) > 1 else 0.0
        return {
            "query": counterparty,
            "candidates": top,
            "confident": bool(best >= 0.72 and best - runner_up >= 0.12),
        }

    def _tool_find_invoice_by_number(self, invoice_number: str) -> dict[str, Any]:
        wanted = str(invoice_number).strip().upper()
        hits = [self._invoice_view(i) for i in self.invoices.values()
                if i.invoice_number.upper() == wanted]
        return {"invoice_number": wanted, "matches": hits, "found": bool(hits)}

    def _tool_search_invoices(
        self,
        vendor_id: str | None = None,
        amount_cents: int | None = None,
        tolerance_cents: int = 0,
        include_settled: bool = False,
        match_field: str = "outstanding",
    ) -> dict[str, Any]:
        if match_field not in ("outstanding", "net_due"):
            raise ToolError("match_field must be 'outstanding' or 'net_due'")
        tolerance = max(0, int(tolerance_cents or 0))
        results = []
        for inv in self.invoices.values():
            outstanding = self.ledger.outstanding_cents(inv.invoice_id)
            if not include_settled and outstanding <= 0:
                continue
            if vendor_id and inv.vendor_id != vendor_id:
                continue
            comparand = outstanding if match_field == "outstanding" else inv.net_due_cents
            if amount_cents is not None and abs(comparand - int(amount_cents)) > tolerance:
                continue
            results.append(self._invoice_view(inv))
        results.sort(key=lambda r: r["invoice_id"])
        return {
            "count": len(results),
            "truncated": len(results) > MAX_SEARCH_RESULTS,
            "invoices": results[:MAX_SEARCH_RESULTS],
        }

    def _tool_get_invoice(self, invoice_id: str) -> dict[str, Any]:
        inv = self.invoices.get(str(invoice_id))
        if inv is None:
            return {"error": f"no invoice {invoice_id!r}"}
        return self._invoice_view(inv)

    def _tool_check_duplicate_feed(self, bank_reference: str) -> dict[str, Any]:
        seen = self.ledger.bank_reference_seen(str(bank_reference))
        return {
            "bank_reference": bank_reference,
            "already_processed": seen,
            "guidance": (
                "AP-07.6 forbids applying this reference again"
                if seen
                else "not seen in the journal for this run"
            ),
        }

    def _tool_fx_rate(self, base: str, quote: str) -> dict[str, Any]:
        # There is no rate source. This is a real gap in the workflow, not a bug.
        return {
            "base": base,
            "quote": quote,
            "status": "UNAVAILABLE",
            "detail": (
                "No FX rate source is configured for this workflow. AP-07.9(i) "
                "routes cross-currency receipts to the analyst queue."
            ),
        }

    def _tool_compute(self, expression: str) -> dict[str, Any]:
        return {"expression": expression, "result": safe_compute(str(expression))}

    # -- shared view ------------------------------------------------------

    def _invoice_view(self, inv: Invoice) -> dict[str, Any]:
        outstanding = self.ledger.outstanding_cents(inv.invoice_id)
        return {
            "invoice_id": inv.invoice_id,
            "invoice_number": inv.invoice_number,
            "vendor_id": inv.vendor_id,
            "vendor_name": inv.vendor_name,
            "currency": inv.currency,
            "face_amount_cents": inv.amount_cents,
            "credit_note_cents": inv.credit_note_cents,
            "net_due_cents": inv.net_due_cents,
            "outstanding_cents": outstanding,
            "settled": outstanding <= 0,
            "issue_date": inv.issue_date,
            "due_date": inv.due_date,
        }
