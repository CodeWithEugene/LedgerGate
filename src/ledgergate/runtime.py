"""Drives a policy across a payment feed and records what happened.

The trajectory this module writes is not a debug log bolted on afterwards; it
is the artifact the workflow exists to produce. An AP analyst reviewing a
queued item needs to see which invoices were considered, what the tools said,
and why the system stopped. The same record is what a reviewer of this project
needs in order to believe the numbers. One artifact, both audiences.

Payments are processed **in feed order against a shared ledger**, because
order is load-bearing: the duplicate-ingest hazard only exists if the second
copy of a bank reference arrives after the first has been journalled.
"""

from __future__ import annotations

import json
import time
import traceback
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from .corpus import Corpus
from .ledger import (
    DEFAULT_APPROVAL_THRESHOLD_CENTS,
    QUEUED_FOR_APPROVAL,
    SandboxLedger,
)
from .tools import TOOL_SPECS, BudgetExhausted, ToolSession
from .types import Decision, Payment


@runtime_checkable
class Policy(Protocol):
    """Anything that can turn a payment plus tool access into a decision."""

    name: str

    def instructions(self) -> str:
        """The contract the policy operates under, recorded in the trajectory."""

    def decide(self, payment: Payment, session: ToolSession) -> Decision:
        ...


@dataclass(slots=True)
class RunResult:
    policy: str
    corpus: str
    decisions: dict[str, Decision]
    ledger: SandboxLedger
    ledger_blocks: dict[str, int]
    steps_used: int
    wall_seconds: float
    queued_for_approval: int
    trajectory_path: Path | None
    policy_errors: int
    stats: dict[str, Any] = field(default_factory=dict)


def run_policy(
    policy: Policy,
    corpus: Corpus,
    *,
    trajectory_path: Path | None = None,
    max_steps_per_payment: int = 24,
    approval_threshold_cents: int = DEFAULT_APPROVAL_THRESHOLD_CENTS,
    limit: int | None = None,
) -> RunResult:
    """Execute ``policy`` over ``corpus`` and return decisions plus telemetry.

    ``limit`` truncates the feed for smoke tests. A truncated run is still
    scored against the whole corpus, so the score will be poor by design and
    cannot be mistaken for a headline result.
    """
    ledger = SandboxLedger.from_invoices(
        corpus.invoices,
        corpus.opening_allocations,
        approval_threshold_cents=approval_threshold_cents,
    )
    invoices = corpus.invoice_by_id()

    decisions: dict[str, Decision] = {}
    blocks: Counter[str] = Counter()
    total_steps = 0
    policy_errors = 0
    queued = 0
    started = time.monotonic()

    handle = None
    if trajectory_path is not None:
        trajectory_path.parent.mkdir(parents=True, exist_ok=True)
        handle = trajectory_path.open("w", encoding="utf-8")
        _write(handle, {
            "record": "header",
            "policy": policy.name,
            "corpus": corpus.name,
            "corpus_seed": corpus.seed,
            "payments": len(corpus.payments),
            "max_steps_per_payment": max_steps_per_payment,
            "approval_threshold_cents": approval_threshold_cents,
            "agent_instructions": policy.instructions(),
            "tools_available": [
                {"name": s.name, "description": s.description} for s in TOOL_SPECS
            ],
        })

    feed = corpus.payments if limit is None else corpus.payments[:limit]

    try:
        for payment in feed:
            session = ToolSession(
                invoices=invoices,
                ledger=ledger,
                payment=payment,
                max_steps=max_steps_per_payment,
            )
            error_detail = ""
            try:
                decision = policy.decide(payment, session)
            except BudgetExhausted as exc:
                policy_errors += 1
                error_detail = f"budget exhausted: {exc}"
                decision = Decision(
                    payment_id=payment.payment_id,
                    action="ABSTAIN",
                    reason_code="BUDGET_EXHAUSTED",
                    rationale=str(exc),
                )
            except Exception as exc:  # noqa: BLE001 - a crashing policy must not
                policy_errors += 1  # take down the run; it must score as an escalation.
                error_detail = "".join(
                    traceback.format_exception_only(type(exc), exc)
                ).strip()
                decision = Decision(
                    payment_id=payment.payment_id,
                    action="ABSTAIN",
                    reason_code="POLICY_ERROR",
                    rationale=error_detail,
                )

            decision = decision.normalised()
            decisions[payment.payment_id] = decision
            total_steps += session.steps_used

            posts = ledger.apply(payment, decision)
            for post in posts:
                if post.blocked:
                    blocks[post.state] += 1
                elif post.state == QUEUED_FOR_APPROVAL:
                    queued += 1

            if handle is not None:
                _write(handle, {
                    "record": "episode",
                    "payment_id": payment.payment_id,
                    "payment": {
                        "bank_reference": payment.bank_reference,
                        "counterparty_raw": payment.counterparty_raw,
                        "amount_cents": payment.amount_cents,
                        "currency": payment.currency,
                        "value_date": payment.value_date,
                        "memo": payment.memo,
                    },
                    "steps": session.steps,
                    "steps_used": session.steps_used,
                    "decision": {
                        "action": decision.action,
                        "allocations": [
                            {"invoice_id": a.invoice_id, "amount_cents": a.amount_cents}
                            for a in decision.allocations
                        ],
                        "reason_code": decision.reason_code,
                        "rationale": decision.rationale,
                        "evidence": list(decision.evidence),
                    },
                    "policy_error": error_detail or None,
                    "ledger_feedback": [
                        {
                            "invoice_id": p.invoice_id,
                            "amount_cents": p.amount_cents,
                            "state": p.state,
                            "detail": p.detail,
                        }
                        for p in posts
                    ],
                    "human_checkpoint": (
                        {
                            "required": True,
                            "reason": f"allocation at or above {approval_threshold_cents} cents",
                            "status": "AWAITING_HUMAN_APPROVAL",
                        }
                        if any(p.state == QUEUED_FOR_APPROVAL for p in posts)
                        else {"required": False}
                    ),
                })

        wall = time.monotonic() - started
        finalise = getattr(policy, "finalise", None)
        if callable(finalise):
            finalise()
        stats = dict(getattr(policy, "stats", {}) or {})

        if handle is not None:
            _write(handle, {
                "record": "summary",
                "decisions": len(decisions),
                "steps_used": total_steps,
                "wall_seconds": round(wall, 3),
                "ledger_blocks": dict(sorted(blocks.items())),
                "queued_for_approval": queued,
                "policy_errors": policy_errors,
                "policy_stats": stats,
            })
    finally:
        if handle is not None:
            handle.close()

    return RunResult(
        policy=policy.name,
        corpus=corpus.name,
        decisions=decisions,
        ledger=ledger,
        ledger_blocks=dict(sorted(blocks.items())),
        steps_used=total_steps,
        wall_seconds=time.monotonic() - started,
        queued_for_approval=queued,
        trajectory_path=trajectory_path,
        policy_errors=policy_errors,
        stats=dict(getattr(policy, "stats", {}) or {}),
    )


def _write(handle: Any, payload: Mapping[str, Any]) -> None:
    handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
