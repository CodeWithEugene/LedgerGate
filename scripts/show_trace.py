#!/usr/bin/env python3
"""Print one agent trajectory as prose.

The JSONL trajectories are the machine-readable record. This renders a single
episode the way an AP analyst would need to read it when a queued item lands on
their desk: what arrived, what the agent checked, what each tool said back, what
it decided, and whether a human still has to sign off.

    python3 scripts/show_trace.py                       # first interesting episode
    python3 scripts/show_trace.py traces/llm-gated.holdout.jsonl HLD-PAY0012
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = REPO_ROOT / "traces"

#: Searched in order when no file is named. A trajectory in which the gate
#: overruled the proposer teaches more than one in which it had nothing to do,
#: so a run with a fallible proposer is preferred over the tidy one.
DEFAULT_TRACE_ORDER = (
    "baseline+gate.holdout.jsonl",
    "llm-gated.holdout.jsonl",
    "reckless+gate.holdout.jsonl",
    "guarded.holdout.jsonl",
)

WIDTH = 78


def rule(title: str = "") -> str:
    if not title:
        return "-" * WIDTH
    return f"-- {title} " + "-" * max(0, WIDTH - len(title) - 4)


def render_observation(observation: object) -> str:
    text = json.dumps(observation, sort_keys=True)
    if len(text) <= 300:
        return text
    return text[:297] + "..."


def _default_trace() -> Path | None:
    for name in DEFAULT_TRACE_ORDER:
        candidate = TRACE_ROOT / name
        if candidate.exists():
            return candidate
    remaining = sorted(TRACE_ROOT.glob("*.jsonl"))
    return remaining[0] if remaining else None


def _gate_withheld(episode: dict) -> bool:
    return any(
        step.get("event") == "gate" and step.get("verdict") == "WITHHELD"
        for step in episode["steps"]
    )


def _most_instructive(episodes: list[dict]) -> dict:
    """Pick the episode a sceptical reader learns the most from.

    In preference order: one where the gate overruled a proposed posting (the
    control doing its job, with a citation); then one that needed a human
    signature; then any escalation that actually did some work; then whatever
    is first. Reading order matters here -- the default view of a trajectory is
    the one most people will ever see.
    """
    for predicate in (
        _gate_withheld,
        lambda e: e["human_checkpoint"]["required"],
        lambda e: e["decision"]["action"] == "ABSTAIN" and len(e["steps"]) > 4,
    ):
        found = next((e for e in episodes if predicate(e)), None)
        if found is not None:
            return found
    return episodes[0]


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else _default_trace()
    wanted = argv[2] if len(argv) > 2 else None

    if path is None:
        print("no trajectories yet. Run 'make verify' first.", file=sys.stderr)
        return 1
    if not path.exists():
        print(f"no trajectory at {path}. Run 'make verify' first.", file=sys.stderr)
        return 1

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    header = records[0]
    episodes = [r for r in records if r.get("record") == "episode"]

    if wanted:
        chosen = next((e for e in episodes if e["payment_id"] == wanted), None)
        if chosen is None:
            print(f"{wanted} is not in {path.name}", file=sys.stderr)
            return 1
    else:
        chosen = _most_instructive(episodes)

    print(rule("policy"))
    print(f"{header['policy']} over corpus {header['corpus']} (seed {header['corpus_seed']})")
    print(f"step budget {header['max_steps_per_payment']} per receipt, "
          f"human approval above {header['approval_threshold_cents']} cents")
    print()
    print(rule("agent instructions"))
    print(header["agent_instructions"])
    print()

    payment = chosen["payment"]
    print(rule(f"receipt {chosen['payment_id']}"))
    for key in ("bank_reference", "counterparty_raw", "amount_cents", "currency",
                "value_date", "memo"):
        print(f"  {key:20s} {payment[key]}")
    print()

    print(rule("what the agent did"))
    for index, step in enumerate(chosen["steps"], 1):
        if "tool" in step:
            args = json.dumps(step["arguments"], sort_keys=True)
            print(f"  {index:2d}. call {step['tool']}({args})")
            print(f"      -> {render_observation(step['observation'])}")
        else:
            event = step.get("event")
            if event == "model_turn":
                if step.get("text"):
                    print(f"  {index:2d}. model: {step['text'][:400]}")
                for call in step.get("tool_calls") or []:
                    print(f"      wants {call['name']}({json.dumps(call['input'], sort_keys=True)})")
            elif event == "gate":
                print(f"  {index:2d}. SAFETY GATE: {step.get('verdict')}")
                for veto in step.get("vetoes") or []:
                    print(f"      veto {veto}")
            else:
                print(f"  {index:2d}. {event}: {json.dumps({k: v for k, v in step.items() if k != 'event'})[:300]}")
    print()

    decision = chosen["decision"]
    print(rule("decision"))
    print(f"  action     {decision['action']}")
    print(f"  reason     {decision['reason_code']}")
    print(f"  rationale  {decision['rationale']}")
    for allocation in decision["allocations"]:
        print(f"  allocate   {allocation['invoice_id']} <- {allocation['amount_cents']} cents")
    print()

    print(rule("ledger"))
    if not chosen["ledger_feedback"]:
        print("  nothing posted; the item is in the analyst queue")
    for feedback in chosen["ledger_feedback"]:
        print(f"  {feedback['state']:28s} {feedback['invoice_id']} "
              f"{feedback['amount_cents']} {feedback['detail']}")
    checkpoint = chosen["human_checkpoint"]
    print(f"  human checkpoint required: {checkpoint['required']}"
          + (f" ({checkpoint.get('status')})" if checkpoint["required"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
