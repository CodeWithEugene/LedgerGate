"""Structural guarantees that a policy cannot cheat.

A benchmark where the candidate can reach the answer key measures nothing.
These tests assert the separation structurally, by walking the object graph and
the import graph, rather than trusting that nobody wired it up by accident.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from ledgergate import evidence, tools
from ledgergate.ledger import SandboxLedger
from ledgergate.tools import TOOL_NAMES, TOOL_SPECS, ComputeError, ToolSession, safe_compute
from ledgergate.types import Truth

POLICY_DIR = Path(inspect.getfile(tools)).parent / "policies"


def _reachable_objects(root, limit=40_000):
    """Bounded traversal of everything a policy could get to from its session."""
    seen: set[int] = set()
    stack = [root]
    while stack and len(seen) < limit:
        obj = stack.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        yield obj
        if isinstance(obj, dict):
            stack.extend(list(obj.keys())[:500])
            stack.extend(list(obj.values())[:500])
        elif isinstance(obj, (list, tuple, set, frozenset)):
            stack.extend(list(obj)[:500])
        elif hasattr(obj, "__dict__"):
            stack.extend(vars(obj).values())
        elif hasattr(obj, "__slots__"):
            for slot in obj.__slots__:
                if hasattr(obj, slot):
                    stack.append(getattr(obj, slot))


def test_ground_truth_is_unreachable_from_the_tool_session(dev_corpus):
    ledger = SandboxLedger.from_invoices(dev_corpus.invoices, dev_corpus.opening_allocations)
    session = ToolSession(dev_corpus.invoice_by_id(), ledger, dev_corpus.payments[0])

    for obj in _reachable_objects(session):
        assert not isinstance(obj, Truth), "a policy can reach ground truth from its session"


def test_no_tool_returns_a_hazard_label(dev_corpus):
    """Even the hazard *name* would give the answer away."""
    from ledgergate.corpus import HAZARDS

    ledger = SandboxLedger.from_invoices(dev_corpus.invoices, dev_corpus.opening_allocations)
    hazard_names = set(HAZARDS)

    for payment in dev_corpus.payments[:12]:
        session = ToolSession(dev_corpus.invoice_by_id(), ledger, payment, max_steps=500)
        evidence.gather(payment, session)
        for step in session.steps:
            blob = repr(step.get("observation", ""))
            for hazard in hazard_names:
                assert hazard not in blob


@pytest.mark.parametrize("module_path", sorted(POLICY_DIR.glob("*.py")))
def test_policies_never_import_the_verifier_or_the_corpus_labels(module_path):
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            imported.append(base)
            imported.extend(f"{base}.{alias.name}" for alias in node.names)

    for name in imported:
        assert "verifier" not in name, f"{module_path.name} imports the verifier"
        assert not name.endswith(".Truth"), f"{module_path.name} imports Truth"
        assert "corpus" not in name, f"{module_path.name} imports the corpus generator"


def _non_docstring_constants(tree: ast.Module) -> list[str]:
    """String literals that are actual code, not prose.

    Naively grepping the source counts the sentence "never receives truth.json"
    in a docstring as an access, which is the opposite of what it means.
    """
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_only_the_store_actually_opens_truth_json():
    """Prose may mention the answer key. Code may not name it."""
    src = Path(inspect.getfile(tools)).parent
    offenders = []
    for path in src.rglob("*.py"):
        if path.name == "store.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any("truth.json" in value for value in _non_docstring_constants(tree)):
            offenders.append(path.name)
    assert offenders == []


def test_tool_specs_and_implementations_stay_in_sync():
    """A documented tool that does not exist is a prompt that wastes a turn."""
    session_methods = {
        name[len("_tool_"):] for name in dir(ToolSession) if name.startswith("_tool_")
    }
    assert session_methods == set(TOOL_NAMES) == {s.name for s in TOOL_SPECS}

    for spec in TOOL_SPECS:
        assert spec.description.strip()
        assert spec.input_schema.get("type") == "object"


def test_an_unknown_tool_is_an_observation_not_a_crash(dev_corpus):
    ledger = SandboxLedger.from_invoices(dev_corpus.invoices)
    session = ToolSession(dev_corpus.invoice_by_id(), ledger, dev_corpus.payments[0])
    result = session.call("delete_everything", {})
    assert "error" in result
    assert session.steps_used == 1


def test_the_step_budget_is_enforced(dev_corpus):
    from ledgergate.tools import BudgetExhausted

    ledger = SandboxLedger.from_invoices(dev_corpus.invoices)
    session = ToolSession(dev_corpus.invoice_by_id(), ledger, dev_corpus.payments[0], max_steps=3)
    for _ in range(3):
        session.call("procedure", {"section": "overview"})
    with pytest.raises(BudgetExhausted):
        session.call("procedure", {"section": "overview"})


def test_notes_do_not_consume_the_action_budget(dev_corpus):
    ledger = SandboxLedger.from_invoices(dev_corpus.invoices)
    session = ToolSession(dev_corpus.invoice_by_id(), ledger, dev_corpus.payments[0], max_steps=2)
    for _ in range(50):
        session.note("model_turn", {"text": "thinking"})
    assert session.steps_used == 0
    session.call("procedure", {"section": "gaps"})
    assert session.steps_used == 1


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "open('/etc/passwd').read()",
        "1.5 + 2",
        "[x for x in range(10)]",
        "globals()",
        "(1).__class__",
        "a + 1",
    ],
)
def test_compute_refuses_anything_that_is_not_integer_arithmetic(expression):
    with pytest.raises(ComputeError):
        safe_compute(expression)


def test_compute_does_the_arithmetic_it_is_for():
    assert safe_compute("145000 - 143750") == 1250
    assert safe_compute("269574 + 517172 + 471451") == 1258197
    assert safe_compute("100000 * 104 // 100") == 104000
    assert safe_compute("500 > 400") is True


def test_the_fx_tool_never_invents_a_rate(dev_corpus):
    ledger = SandboxLedger.from_invoices(dev_corpus.invoices)
    session = ToolSession(dev_corpus.invoice_by_id(), ledger, dev_corpus.payments[0])
    for pair in (("EUR", "USD"), ("USD", "EUR"), ("GBP", "USD")):
        result = session.call("fx_rate", {"base": pair[0], "quote": pair[1]})
        assert result["status"] == "UNAVAILABLE"
        assert "rate" not in result


def test_the_written_procedure_admits_its_own_gaps():
    gaps = tools.PROCEDURE["gaps"].lower()
    for topic in ("currency", "exceeding", "reversal", "before the invoice"):
        assert topic in gaps
    assert "do not infer a rule" in gaps
