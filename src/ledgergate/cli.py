"""Command line entry point.

Every published number in this repository comes from one of these commands,
and the exact invocation is printed in docs/REPRODUCTION.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Sequence

from .corpus import audit_corpus, build_corpus
from .evaluation import report
from .evaluation.verifier import Scorecard, score, sweep_cost_models
from .runtime import run_policy
from .store import load_corpus, save_corpus, verify_manifest
from .types import to_json

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data"
RESULTS_ROOT = REPO_ROOT / "results"
TRACE_ROOT = REPO_ROOT / "traces"

CORPORA = {"dev": 20260828, "holdout": 20260831}


def _make_policy(spec: str):
    """Build a policy from its command-line name.

    Any proposer may be suffixed with ``+gate`` to run it behind the safety
    gate, which is how the gate is measured across the full range of proposer
    quality rather than against one opponent.
    """
    from .policies.baseline import BaselinePolicy
    from .policies.gated import Gated
    from .policies.guarded import GuardedPolicy

    if spec.endswith("+gate"):
        return Gated(_make_policy(spec[: -len("+gate")]))

    if spec == "baseline":
        return BaselinePolicy()
    if spec == "guarded":
        return GuardedPolicy(use_gate=True)
    if spec == "rules-only":
        return GuardedPolicy(use_gate=False)
    if spec == "reckless":
        from .policies.reckless import RecklessPolicy

        return RecklessPolicy()
    if spec.startswith("llm"):
        from .policies.llm import build_llm_policy

        return build_llm_policy(spec)
    raise SystemExit(
        f"unknown policy {spec!r}; expected one of: baseline, reckless, rules-only, "
        "guarded, llm, llm-gated, optionally suffixed with '+gate'"
    )


POLICY_HELP = (
    "baseline | reckless | rules-only | guarded | llm | llm-gated; "
    "suffix any of them with '+gate' to add the safety gate "
    "(llm variants accept a :model suffix, e.g. llm-gated:claude-opus-5)"
)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_corpus(args: argparse.Namespace) -> int:
    for name, seed in CORPORA.items():
        corpus = build_corpus(name, seed, instances=args.instances)
        checks = audit_corpus(corpus)
        hashes = save_corpus(corpus, DATA_ROOT)
        print(f"{name}: {len(corpus.invoices)} invoices, {len(corpus.payments)} payments, "
              f"{len(checks)} audit checks passed")
        for filename, digest in sorted(hashes.items()):
            print(f"    {filename:24s} {digest[:16]}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    failures = 0
    for name in CORPORA:
        problems = verify_manifest(DATA_ROOT, name)
        corpus = load_corpus(DATA_ROOT, name)
        checks = audit_corpus(corpus)
        status = "OK" if not problems else "HASH MISMATCH"
        print(f"{name}: {status}; {len(checks)} ground-truth invariants re-derived")
        for check in checks:
            print(f"    - {check}")
        for problem in problems:
            failures += 1
            print(f"    !! {problem}")
    return 1 if failures else 0


def _run_one(
    policy_spec: str, corpus_name: str, *, max_steps: int, limit: int | None = None
) -> tuple[Scorecard, int]:
    corpus = load_corpus(DATA_ROOT, corpus_name)
    policy = _make_policy(policy_spec)
    safe_name = policy_spec.replace(":", "-")
    trace_path = TRACE_ROOT / f"{safe_name}.{corpus_name}.jsonl"

    result = run_policy(
        policy,
        corpus,
        trajectory_path=trace_path,
        max_steps_per_payment=max_steps,
        limit=limit,
    )
    stats = result.stats
    card = score(
        policy.name,
        corpus,
        result.decisions,
        ledger_blocks=result.ledger_blocks,
        steps_used=result.steps_used,
        wall_seconds=result.wall_seconds,
        llm_calls=int(stats.get("llm_calls", 0)),
        llm_input_tokens=int(stats.get("input_tokens", 0)),
        llm_output_tokens=int(stats.get("output_tokens", 0)),
    )

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    payload = card.to_dict()
    payload["policy_stats"] = stats
    payload["queued_for_approval"] = result.queued_for_approval
    payload["policy_errors"] = result.policy_errors
    payload["trajectory"] = str(trace_path.relative_to(REPO_ROOT))
    payload["sensitivity"] = sweep_cost_models(card)
    (RESULTS_ROOT / f"{safe_name}.{corpus_name}.json").write_text(
        to_json(payload), encoding="utf-8"
    )
    return card, result.queued_for_approval


def cmd_run(args: argparse.Namespace) -> int:
    card, queued = _run_one(
        args.policy, args.corpus, max_steps=args.max_steps, limit=args.limit
    )
    print(report.render_scorecard(card, queued_for_approval=queued))
    return 0


def render_comparison_block(cards: list[Scorecard], corpus_name: str) -> str:
    """The exact text embedded in the README between the headline markers.

    Generating it rather than transcribing it is the point: a test asserts the
    README block equals this string, so a published number cannot drift away
    from the run that produced it.
    """
    return "\n".join([
        f"corpus: {corpus_name}",
        "",
        report.render_comparison(cards),
        "",
        "net value under different false-pay penalties "
        "(the ranking should not depend on the exact weight):",
        "",
        report.render_sensitivity(cards),
    ])


def cmd_compare(args: argparse.Namespace) -> int:
    cards = [
        _run_one(spec, args.corpus, max_steps=args.max_steps, limit=args.limit)[0]
        for spec in args.policies
    ]
    block = render_comparison_block(cards, args.corpus)
    print(block)

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    (RESULTS_ROOT / f"comparison.{args.corpus}.json").write_text(
        to_json([c.to_dict() for c in cards]), encoding="utf-8"
    )
    if args.limit is None:
        (RESULTS_ROOT / f"headline.{args.corpus}.md").write_text(block + "\n", encoding="utf-8")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    """Simulate the human checkpoint on high-value allocations."""
    corpus = load_corpus(DATA_ROOT, args.corpus)
    policy = _make_policy(args.policy)
    result = run_policy(policy, corpus, trajectory_path=None, max_steps_per_payment=args.max_steps)

    queued = result.ledger.pending_approvals
    print(f"{len(queued)} allocation(s) awaiting human approval "
          f"(threshold {result.ledger.approval_threshold_cents} cents)\n")
    for entry in queued:
        invoice = result.ledger.invoices[entry.invoice_id]
        print(f"  {entry.payment_id} -> {entry.invoice_id} ({invoice.vendor_name}) "
              f"{entry.amount_cents} cents  key={entry.idempotency_key[:12]}")

    if not args.approver:
        print("\nNo --approver supplied, so nothing was released. This is the default: "
              "the system never approves its own postings.")
        return 0

    print(f"\nreleasing as human reviewer {args.approver!r}")
    for entry in queued:
        posted = result.ledger.approve(
            entry.idempotency_key, approver=args.approver, approver_is_human=True
        )
        print(f"  {posted.state} {posted.invoice_id} {posted.amount_cents} :: {posted.detail}")
    return 0


def cmd_gate_audit(args: argparse.Namespace) -> int:
    """Show, receipt by receipt, what the gate withheld and what it cost.

    The headline table says the gate turns six false payments into six
    escalations. This command shows *which* six, on what clause, and confirms
    against ground truth that nothing else was touched. It is the difference
    between a number a reviewer has to trust and one they can read.
    """
    corpus = load_corpus(DATA_ROOT, args.corpus)
    truth = {t.payment_id: t for t in corpus.truths}

    ungated = run_policy(
        _make_policy(args.proposer), corpus,
        trajectory_path=None, max_steps_per_payment=args.max_steps,
    )
    gated = run_policy(
        _make_policy(args.proposer + "+gate"), corpus,
        trajectory_path=None, max_steps_per_payment=args.max_steps,
    )
    before, after = ungated.decisions, gated.decisions

    # Three buckets, not two. "The gate escalated something ground truth calls
    # a MATCH" is not the same as "the gate blocked a correct posting": the
    # proposer may have been about to pay the *right receipt against the wrong
    # invoice*, in which case the veto prevented a loss even though the ideal
    # outcome was an automatic posting. Collapsing those two cases understates
    # the gate's value and, worse, prints a line that contradicts the clause
    # cited directly beneath it.
    prevented_loss: list[tuple[str, str, list[str]]] = []
    lost_automation: list[tuple[str, str, list[str]]] = []
    blocked_correct: list[tuple[str, str, list[str]]] = []

    for pid, post in sorted(after.items()):
        pre = before[pid]
        if pre.action == post.action:
            continue

        # A gate veto records one clause per evidence entry; anything else
        # reaching here changed action for its own reasons, so show those.
        clauses = list(post.evidence) if post.reason_code.startswith("GATE_") else [post.rationale]
        row = (pid, truth[pid].hazard, clauses)

        expected = truth[pid].expected_action
        proposal_was_right = (
            expected == "MATCH" and pre.allocations == truth[pid].expected_allocations
        )
        if proposal_was_right:
            blocked_correct.append(row)
        elif expected == "MATCH":
            lost_automation.append(row)
        else:
            prevented_loss.append(row)

    def show(title: str, rows: list[tuple[str, str, list[str]]], gloss: str = "") -> None:
        print(f"\n{title}: {len(rows)}")
        if gloss and rows:
            print(f"  ({gloss})")
        for pid, hazard, clauses in rows:
            print(f"  {pid}  [{hazard}]")
            for clause in clauses:
                print(f"      {clause}")

    print(f"gate audit: proposer={args.proposer!r} corpus={args.corpus}")
    interventions = len(prevented_loss) + len(lost_automation) + len(blocked_correct)
    print(f"receipts={len(after)}  gate interventions={interventions}")

    show(
        "Wrong payments prevented (ground truth says escalate; the proposer would have paid)",
        prevented_loss,
    )
    show(
        "Wrong payments prevented, but a correct posting was possible",
        lost_automation,
        "the proposer picked the wrong invoice, so the veto still avoided a loss; "
        "a better proposer would have cleared these automatically",
    )
    show(
        "Correct postings blocked (the gate's true cost)",
        blocked_correct,
        "the proposer had the right answer and the gate withheld it anyway",
    )

    # The gate is veto-only: assert it here as well as in the test suite, so a
    # reviewer running this by hand gets the guarantee checked in front of them.
    for pid, post in after.items():
        pre = before[pid]
        if pre.action == "ABSTAIN" and post.action == "MATCH":
            print(f"\n!! MONOTONICITY VIOLATED at {pid}: gate created a match")
            return 1
        if pre.action == "MATCH" and post.action == "MATCH" and pre.allocations != post.allocations:
            print(f"\n!! MONOTONICITY VIOLATED at {pid}: gate altered an allocation")
            return 1
    print("\nmonotonicity re-checked on this run: the gate withheld only; "
          "it created no match and altered no allocation.")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    """Print the committed comparison files without recomputing anything."""
    for path in sorted(RESULTS_ROOT.glob("comparison.*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        print(f"== {path.name} ==")
        for card in payload:
            h = card["headline"]
            print(f"  {card['policy']:>12s}  net={h['net_value']:+7d}  "
                  f"acc={h['exact_accuracy']:.1%}  false_pays={h['false_pay_count']}")
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledgergate", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("corpus", help="regenerate the synthetic corpora from their seeds")
    p.add_argument("--instances", type=int, default=3, help="payments per hazard class")
    p.set_defaults(func=cmd_corpus)

    p = sub.add_parser("audit", help="verify corpus hashes and re-derive ground-truth invariants")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("run", help="run one policy and score it")
    p.add_argument("--policy", required=True, help=POLICY_HELP)
    p.add_argument("--corpus", default="holdout", choices=sorted(CORPORA))
    p.add_argument("--max-steps", type=int, default=40)
    p.add_argument("--limit", type=int, default=None,
                   help="process only the first N receipts (smoke test; not a headline result)")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("compare", help="run several policies and tabulate them")
    p.add_argument("--policies", nargs="+", default=["baseline", "rules-only", "guarded"])
    p.add_argument("--corpus", default="holdout", choices=sorted(CORPORA))
    p.add_argument("--max-steps", type=int, default=40)
    p.add_argument("--limit", type=int, default=None,
                   help="process only the first N receipts (smoke test; not a headline result)")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("approve", help="inspect and release the human approval queue")
    p.add_argument("--policy", default="guarded", help=POLICY_HELP)
    p.add_argument("--corpus", default="holdout", choices=sorted(CORPORA))
    p.add_argument("--approver", default="", help="name of the human releasing the queue")
    p.add_argument("--max-steps", type=int, default=40)
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser(
        "gate-audit",
        help="show every decision the gate changed, on what clause, against ground truth",
    )
    p.add_argument("--proposer", default="rules-only",
                   help="the ungated proposer to audit; the gated form is derived from it")
    p.add_argument("--corpus", default="holdout", choices=sorted(CORPORA))
    p.add_argument("--max-steps", type=int, default=40)
    p.set_defaults(func=cmd_gate_audit)

    p = sub.add_parser("summary", help="print committed results without recomputing")
    p.set_defaults(func=cmd_summary)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    func: Callable[[argparse.Namespace], int] = args.func
    return func(args)


if __name__ == "__main__":
    sys.exit(main())
