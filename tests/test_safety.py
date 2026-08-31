"""The two claims the whole project rests on, stated as tests.

If either of these fails, the headline result is void:

* **Soundness** -- the gate never withholds a decision that ground truth says
  was correct. Safety bought by rejecting good answers is not safety, it is
  just a slower manual process.
* **Sufficiency** -- nothing ground truth calls unsafe gets past the gate, even
  when the proposer is maximally reckless.
"""

from __future__ import annotations

import pytest
from conftest import AlwaysMatchPolicy, GatedProbe, OraclePolicy

from ledgergate import safety
from ledgergate.evaluation.verifier import (
    CORRECT_MATCH,
    UNSAFE_MATCH,
    WRONG_INVOICE,
    score,
)
from ledgergate.runtime import run_policy
from ledgergate.types import Allocation, Decision


@pytest.mark.parametrize("corpus_name", ["dev", "holdout"])
def test_gate_is_sound_it_never_blocks_a_correct_decision(request, corpus_name):
    corpus = request.getfixturevalue(f"{corpus_name}_corpus")

    ungated = run_policy(OraclePolicy(corpus), corpus, max_steps_per_payment=60)
    gated = run_policy(GatedProbe(OraclePolicy(corpus)), corpus, max_steps_per_payment=60)

    ungated_card = score("oracle", corpus, ungated.decisions)
    gated_card = score("oracle+gate", corpus, gated.decisions)

    assert ungated_card.exact_accuracy == 1.0, "the oracle must define the ceiling"
    assert gated_card.exact_accuracy == 1.0, (
        "the safety gate withheld a correct decision: "
        f"{[o.payment_id for o in gated_card.outcomes if o.outcome != CORRECT_MATCH and o.expected_action == 'MATCH']}"
    )


@pytest.mark.parametrize("corpus_name", ["dev", "holdout"])
def test_gate_is_sufficient_no_unsafe_posting_survives_it(request, corpus_name):
    corpus = request.getfixturevalue(f"{corpus_name}_corpus")

    reckless = run_policy(AlwaysMatchPolicy(), corpus, max_steps_per_payment=60)
    reckless_card = score("always-match", corpus, reckless.decisions)
    assert reckless_card.false_pay_count > 0, (
        "the adversarial probe must actually be dangerous, otherwise the next "
        "assertion proves nothing"
    )

    gated = run_policy(GatedProbe(AlwaysMatchPolicy()), corpus, max_steps_per_payment=60)
    gated_card = score("always-match+gate", corpus, gated.decisions)

    assert gated_card.counts[UNSAFE_MATCH] == 0
    assert gated_card.counts[WRONG_INVOICE] == 0
    assert gated_card.false_pay_count == 0


@pytest.mark.parametrize("corpus_name", ["dev", "holdout"])
@pytest.mark.parametrize("proposer", ["reckless", "baseline", "rules-only"])
def test_the_guarantee_holds_for_every_proposer_not_just_a_convenient_one(
    request, corpus_name, proposer
):
    """Sufficiency is a property of the gate, so it must not depend on the input.

    A control that only works against opponents you chose is a tie-breaker.
    This runs the gate against the whole spread of proposer quality shipped in
    the repository and demands the same answer from all of them.
    """
    corpus = request.getfixturevalue(f"{corpus_name}_corpus")
    from ledgergate.cli import _make_policy

    ungated = score(
        proposer, corpus,
        run_policy(_make_policy(proposer), corpus, max_steps_per_payment=60).decisions,
    )
    gated = score(
        f"{proposer}+gate", corpus,
        run_policy(_make_policy(f"{proposer}+gate"), corpus, max_steps_per_payment=60).decisions,
    )

    assert ungated.false_pay_count > 0, (
        f"{proposer} posts nothing wrong on its own, so the next assertion is vacuous"
    )
    assert gated.false_pay_count == 0, (
        f"the gate let {gated.false_pay_count} unsafe postings through from {proposer}"
    )
    assert gated.net_value > ungated.net_value


@pytest.mark.parametrize("corpus_name", ["dev", "holdout"])
def test_containment_gets_cheaper_as_the_proposer_gets_better(request, corpus_name):
    """The claim the README makes about the shape of the curve.

    The safety guarantee is flat across proposer quality; the price paid for it
    is not. A better proposer triggers fewer vetoes, so fewer correct postings
    are escalated unnecessarily. If this ever inverts, the README is wrong.
    """
    corpus = request.getfixturevalue(f"{corpus_name}_corpus")
    from ledgergate.cli import _make_policy
    from ledgergate.evaluation.verifier import OVER_ESCALATION

    costs = []
    for proposer in ("reckless", "baseline", "rules-only"):
        card = score(
            proposer, corpus,
            run_policy(_make_policy(f"{proposer}+gate"), corpus,
                       max_steps_per_payment=60).decisions,
        )
        assert card.false_pay_count == 0
        costs.append(card.counts[OVER_ESCALATION])

    assert costs == sorted(costs, reverse=True), (
        f"containment cost did not fall monotonically with proposer quality: {costs}"
    )


@pytest.mark.parametrize("corpus_name", ["dev", "holdout"])
@pytest.mark.parametrize("proposer", ["reckless", "baseline", "rules-only"])
def test_the_gate_never_blocks_a_posting_the_proposer_had_right(request, corpus_name, proposer):
    """Soundness, measured on real proposers rather than argued for.

    `test_gate_is_sound_...` proves this against an oracle, which is the clean
    statement but also the easy one -- an oracle only ever hands the gate
    correct proposals. This checks the same property where it is actually load
    bearing: across proposers that are frequently wrong, no intervention may
    ever land on a proposal that was already exactly right.

    Without this, the README's "the gate's true cost is zero" is an observation
    about one run. With it, the cost column in `make gate-audit` cannot go
    non-zero without a test failing first.
    """
    corpus = request.getfixturevalue(f"{corpus_name}_corpus")
    from ledgergate.cli import _make_policy

    truth = {t.payment_id: t for t in corpus.truths}
    before = run_policy(_make_policy(proposer), corpus, max_steps_per_payment=60).decisions
    after = run_policy(
        _make_policy(f"{proposer}+gate"), corpus, max_steps_per_payment=60
    ).decisions

    blocked_correct = [
        pid
        for pid, post in after.items()
        if post.action != before[pid].action
        and truth[pid].expected_action == "MATCH"
        and before[pid].allocations == truth[pid].expected_allocations
    ]
    assert not blocked_correct, (
        f"the gate withheld {len(blocked_correct)} posting(s) the proposer had exactly "
        f"right: {sorted(blocked_correct)}"
    )


@pytest.mark.parametrize("corpus_name", ["dev", "holdout"])
def test_against_the_best_proposer_the_gate_fires_only_where_it_must(request, corpus_name):
    """The sharpest form of the claim, and the one worth failing loudly.

    Soundness and sufficiency are each one-sided. Together, against the
    faithful AP-07 proposer, they say something stronger: the set of receipts
    the gate intervenes on should be *exactly* the set the written procedure
    would have paid wrongly -- no misses, and no collateral. Anything the gate
    touches beyond that set is a correct posting it needlessly sent to a human,
    and anything it fails to touch is a wrong payment it let through.

    This is what ``ledgergate gate-audit`` prints; asserting it here means the
    printed result cannot quietly stop being true.
    """
    corpus = request.getfixturevalue(f"{corpus_name}_corpus")
    from ledgergate.cli import _make_policy

    truth = {t.payment_id: t for t in corpus.truths}
    before = run_policy(_make_policy("rules-only"), corpus, max_steps_per_payment=60).decisions
    after = run_policy(_make_policy("rules-only+gate"), corpus, max_steps_per_payment=60).decisions

    would_be_wrong = {
        pid for pid, d in before.items()
        if d.action == "MATCH" and truth[pid].expected_action != "MATCH"
    }
    intervened = {pid for pid, d in after.items() if d.action != before[pid].action}

    assert would_be_wrong, "the ungated proposer must be wrong somewhere for this to mean anything"
    assert intervened == would_be_wrong, (
        "the gate did not fire exactly where it had to.\n"
        f"  let through: {sorted(would_be_wrong - intervened)}\n"
        f"  collateral : {sorted(intervened - would_be_wrong)}"
    )


def test_the_gate_stays_small_enough_to_read():
    """The README claims the gate is reviewable by a non-programmer. Enforce it.

    "Small enough that a domain expert reads the whole thing" is load-bearing
    here -- it is most of the argument for why a veto-only gate is more
    trustworthy than a better model. Unenforced, it is exactly the kind of
    claim that stays in a README long after it stopped being true, so the
    budget is asserted and the README quotes this number.

    Raise the ceiling deliberately if the gate genuinely needs to grow, and
    update the README in the same commit. Do not raise it to make a red test
    green.
    """
    import ast
    from pathlib import Path

    source_path = Path(safety.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        if node.body and isinstance(node.body[0], ast.Expr) and ast.get_docstring(node):
            first = node.body[0]
            docstring_lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))

    effective = sum(
        1
        for number, line in enumerate(source.splitlines(), start=1)
        if line.strip() and not line.strip().startswith("#") and number not in docstring_lines
    )

    assert effective == 209, (
        f"safety.py is now {effective} effective lines, and the README says 209. "
        "Update both together, or reconsider whether the gate should be growing."
    )


def test_gate_is_monotone_it_can_only_escalate(dev_corpus):
    """A gate that could alter an allocation would be a second, unaudited policy."""
    from ledgergate import evidence as evidence_mod
    from ledgergate.ledger import SandboxLedger
    from ledgergate.tools import ToolSession

    ledger = SandboxLedger.from_invoices(dev_corpus.invoices, dev_corpus.opening_allocations)
    invoices = dev_corpus.invoice_by_id()
    every_invoice = sorted(invoices)

    checked = 0
    for index, payment in enumerate(dev_corpus.payments):
        session = ToolSession(invoices, ledger, payment, max_steps=200)
        ev = evidence_mod.gather(payment, session)
        # Deliberately silly proposals, cycled so every payment meets a
        # different invoice than the one it plausibly belongs to.
        target = every_invoice[index % len(every_invoice)]
        proposal = Decision(
            payment_id=payment.payment_id,
            action="MATCH",
            allocations=(Allocation(target, payment.amount_cents),),
            reason_code="FUZZ",
        )
        final, vetoes = safety.review(payment, proposal, ev, session)
        assert safety.gate_is_monotone(proposal, final)
        if final.action == "MATCH":
            assert final.allocations == proposal.allocations
            assert not vetoes
        else:
            assert final.action == "ABSTAIN"
        checked += 1

    assert checked == len(dev_corpus.payments)


def test_every_veto_cites_the_clause_it_enforces(dev_corpus):
    """An unexplained refusal is not an auditable control."""
    from ledgergate import evidence as evidence_mod
    from ledgergate.ledger import SandboxLedger
    from ledgergate.tools import ToolSession

    ledger = SandboxLedger.from_invoices(dev_corpus.invoices, dev_corpus.opening_allocations)
    invoices = dev_corpus.invoice_by_id()
    first_invoice = sorted(invoices)[0]

    seen = 0
    for payment in dev_corpus.payments:
        session = ToolSession(invoices, ledger, payment, max_steps=200)
        ev = evidence_mod.gather(payment, session)
        proposal = Decision(
            payment_id=payment.payment_id,
            action="MATCH",
            allocations=(Allocation(first_invoice, payment.amount_cents),),
            reason_code="FUZZ",
        )
        _, vetoes = safety.review(payment, proposal, ev, session)
        for veto in vetoes:
            assert veto.code and veto.code.isupper()
            assert veto.citation.startswith("AP-07")
            assert len(veto.detail) > 10
            seen += 1

    assert seen > 0


def test_gate_passes_through_an_abstain_untouched(dev_corpus):
    from ledgergate import evidence as evidence_mod
    from ledgergate.ledger import SandboxLedger
    from ledgergate.tools import ToolSession

    ledger = SandboxLedger.from_invoices(dev_corpus.invoices, dev_corpus.opening_allocations)
    payment = dev_corpus.payments[0]
    session = ToolSession(dev_corpus.invoice_by_id(), ledger, payment, max_steps=50)
    ev = evidence_mod.gather(payment, session)

    proposal = Decision(payment.payment_id, "ABSTAIN", reason_code="ALREADY_ESCALATED")
    final, vetoes = safety.review(payment, proposal, ev, session)

    assert final is proposal
    assert vetoes == []
