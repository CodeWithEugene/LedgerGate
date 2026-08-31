"""Rendering for scorecards and policy comparisons.

Plain text on purpose. A reviewer should be able to read the result of a run
in a terminal, paste it into a pull request, and diff two runs against each
other without a viewer.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from .verifier import (
    CORRECT_ABSTAIN,
    CORRECT_MATCH,
    OUTCOMES,
    OVER_ESCALATION,
    UNSAFE_MATCH,
    WRONG_AMOUNT,
    WRONG_INVOICE,
    Scorecard,
    sweep_cost_models,
)

_SHORT = {
    CORRECT_MATCH: "ok-match",
    CORRECT_ABSTAIN: "ok-hold",
    OVER_ESCALATION: "over-esc",
    WRONG_AMOUNT: "wrong-amt",
    WRONG_INVOICE: "wrong-inv",
    UNSAFE_MATCH: "unsafe",
}


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)).rstrip()
    rule = "  ".join("-" * widths[i] for i in range(len(headers)))
    body = [
        "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)).rstrip() for row in rows
    ]
    return "\n".join([line, rule, *body])


def render_scorecard(card: Scorecard, queued_for_approval: int | None = None) -> str:
    h = card.to_dict()["headline"]
    out: list[str] = []
    out.append(f"policy={card.policy}  corpus={card.corpus}  seed={card.corpus_seed}  "
               f"payments={card.total_payments}")
    out.append(f"verifier={card.verifier_sha256[:16]}")
    out.append("")

    rows = [
        ["net business value", f"{h['net_value']:+d}"],
        ["exact accuracy", f"{h['exact_accuracy']:.1%}"],
        ["false pays", f"{h['false_pay_count']} ({h['false_pay_rate']:.1%})"],
        ["coverage (decided, not escalated)", f"{h['coverage']:.1%}"],
    ]

    # The two human touchpoints are different things and are reported as such:
    # escalation means an analyst had to decide, approval means a decided
    # posting was large enough to need a second signature. Showing coverage
    # alone would overstate how hands-off the system actually is.
    if queued_for_approval is not None:
        decided = round(h["coverage"] * card.total_payments)
        hands_off = decided - queued_for_approval
        rows.append([
            "  of which queued for approval",
            f"{queued_for_approval} (a second signature, not a decision)",
        ])
        rows.append([
            "posted with no human at all",
            f"{hands_off / card.total_payments:.1%}" if card.total_payments else "n/a",
        ])

    rows.extend([
        ["automation precision", f"{h['automation_precision']:.1%}"],
        ["escalation precision", f"{h['abstain_precision']:.1%}"],
        ["escalation recall", f"{h['abstain_recall']:.1%}"],
    ])
    out.append(_table(["metric", "value"], rows))
    out.append("")
    out.append(_table(
        ["outcome", "count"],
        [[_SHORT[o], str(card.counts.get(o, 0))] for o in OUTCOMES],
    ))

    failing = sorted(
        (hz, b) for hz, b in card.per_hazard.items()
        if b.get(CORRECT_MATCH, 0) + b.get(CORRECT_ABSTAIN, 0) != sum(b.values())
    )
    if failing:
        out.append("")
        out.append("hazards with at least one failure:")
        out.append(_table(
            ["hazard", "n", "unsafe", "wrong-inv", "wrong-amt", "over-esc"],
            [
                [
                    hz,
                    str(sum(b.values())),
                    str(b.get(UNSAFE_MATCH, 0)),
                    str(b.get(WRONG_INVOICE, 0)),
                    str(b.get(WRONG_AMOUNT, 0)),
                    str(b.get(OVER_ESCALATION, 0)),
                ]
                for hz, b in failing
            ],
        ))

    if card.ledger_blocks:
        out.append("")
        out.append("postings the sandbox ledger refused (policy intent was unsafe):")
        out.append(_table(
            ["rejection", "count"],
            [[k, str(v)] for k, v in sorted(card.ledger_blocks.items())],
        ))

    out.append("")
    out.append(f"cost: steps={card.steps_used} wall={card.wall_seconds:.1f}s "
               f"llm_calls={card.llm_calls} "
               f"tokens_in={card.llm_input_tokens} tokens_out={card.llm_output_tokens}")
    return "\n".join(out)


def render_comparison(cards: Iterable[Scorecard]) -> str:
    """The headline table. Committed to `results/` and synced into the README.

    Cost is reported as tool steps rather than wall-clock seconds. Steps are a
    property of the policy and reproduce anywhere; seconds are a property of
    whichever machine happened to run it. This table is a committed artifact,
    so a machine-dependent column in it would mean a reviewer reproducing the
    results gets a dirty tree through no fault of their own -- and on a host
    only three times slower than the development laptop, `0.0s` starts
    rendering as `0.1s`. Wall time is still printed by `render_scorecard`,
    which goes to the terminal and is not committed.
    """
    cards = list(cards)
    rows = []
    for c in cards:
        h = c.to_dict()["headline"]
        rows.append([
            c.policy,
            f"{h['net_value']:+d}",
            f"{h['exact_accuracy']:.1%}",
            str(h["false_pay_count"]),
            f"{h['coverage']:.1%}",
            f"{h['automation_precision']:.1%}",
            str(c.counts.get(OVER_ESCALATION, 0)),
            str(c.steps_used),
        ])
    return _table(
        ["policy", "net value", "exact acc", "false pays", "coverage",
         "auto precision", "over-esc", "steps"],
        rows,
    )


def render_sensitivity(cards: Iterable[Scorecard]) -> str:
    """Net value for each policy across a range of false-pay penalties."""
    cards = list(cards)
    penalties = [row["false_pay_penalty"] for row in sweep_cost_models(cards[0])]
    headers = ["policy"] + [f"pen={p}" for p in penalties]
    rows = []
    for card in cards:
        sweep = sweep_cost_models(card)
        rows.append([card.policy] + [f"{row['net_value']:+d}" for row in sweep])
    return _table(headers, rows)
