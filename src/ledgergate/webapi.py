"""A JSON API over the LedgerGate engine, for the operator interface in `web/`.

Dana is a cash application analyst. She is not going to run `make`. This module
is the seam between the evaluation harness -- which is a research artifact and
reads like one -- and something an accounts payable team could actually sit in
front of.

Three design rules, in descending order of how much trouble ignoring them would
cause:

1. **Standard library only.** The rest of this project has zero runtime
   dependencies, and a web server is exactly the place where that discipline
   normally dies. `http.server` is unglamorous and entirely adequate for a
   single-analyst tool serving a 60-receipt file.

2. **The operator endpoints never return ground truth.** `truth.json` exists to
   grade policies, not to help Dana. If the queue could see it, the interface
   would be a demo of a system that cannot exist. Everything under `/api/ops/`
   is restricted to what a real deployment would know; the answer key is
   confined to `/api/eval/`, which is the reviewer's view and is labelled as
   such in the UI.

3. **Actions go through the real ledger.** Approving a posting here calls
   `SandboxLedger.approve`, which raises unless the caller declares a human.
   The web layer gets no privileged path -- if the UI could post something the
   CLI could not, the controls would be theatre.

Run it with `make web-api`, or:

    PYTHONPATH=src python3 -m ledgergate.webapi --port 8787
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .cli import _make_policy
from .evaluation.verifier import score
from .ledger import DEFAULT_APPROVAL_THRESHOLD_CENTS, QUEUED_FOR_APPROVAL
from .runtime import run_policy
from .store import load_corpus
from .tools import PROCEDURE, TOOL_SPECS

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data"
TRACES = REPO_ROOT / "traces"

#: Policies the interface will run. `reckless` is included deliberately: the
#: comparison view is worth nothing if you cannot select the bad proposer and
#: watch the gate hold anyway.
POLICIES = ("guarded", "rules-only", "baseline", "baseline+gate", "reckless", "reckless+gate")

DEFAULT_POLICY = "guarded"
DEFAULT_SPLIT = "holdout"

#: `AP-07.9(iv)` in a veto string. The UI turns these into links into the
#: procedure, so a queued item arrives with its justification one click away
#: rather than as an opaque code.
CITATION = re.compile(r"AP-07(?:\.\d+)?(?:\([ivx]+\))?")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


@dataclass
class Session:
    """One policy run against one split, plus whatever the analyst did next.

    Held in memory. This is a single-user tool over a synthetic corpus, and
    persistence would mean a database, which would mean a dependency. Restart
    the server to get a clean file back -- which is also how you demo it twice.
    """

    split: str
    policy: str
    corpus: Any
    result: Any
    episodes: dict[str, dict]
    resolutions: dict[str, dict]

    @property
    def ledger(self):
        return self.result.ledger

    def entries_for(self, payment_id: str) -> list:
        """Journal lines for one receipt.

        The ledger indexes by idempotency key rather than payment, because that
        is what idempotency means. The queue is organised by receipt, so the
        lookup happens here rather than by widening the ledger's interface for
        a UI's convenience.
        """
        return [e for e in self.ledger.journal if e.payment_id == payment_id]

    def pending_for(self, payment_id: str) -> list:
        return [e for e in self.ledger.pending_approvals if e.payment_id == payment_id]


_sessions: dict[tuple[str, str], Session] = {}
_lock = threading.Lock()


def get_session(split: str, policy: str, *, reset: bool = False) -> Session:
    key = (split, policy)
    with _lock:
        if reset:
            _sessions.pop(key, None)
        if key not in _sessions:
            corpus = load_corpus(DATA_ROOT, split)
            result = run_policy(_make_policy(policy), corpus, max_steps_per_payment=40)
            _sessions[key] = Session(
                split=split,
                policy=policy,
                corpus=corpus,
                result=result,
                episodes=_load_episodes(policy, split),
                resolutions={},
            )
        return _sessions[key]


def _load_episodes(policy: str, split: str) -> dict[str, dict]:
    """Committed trajectories, keyed by payment.

    Read from `traces/` rather than regenerated, so what the UI shows is the
    same artifact a reviewer can open in a text editor and diff. Absent for
    policy/split pairs that were never published, in which case the detail view
    degrades to the decision without the investigation behind it.
    """
    path = TRACES / f"{policy}.{split}.jsonl"
    if not path.exists():
        return {}
    episodes: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("record") == "episode":
            episodes[record["payment_id"]] = record
    return episodes


# ---------------------------------------------------------------------------
# Shaping
# ---------------------------------------------------------------------------


def _citations(text: str) -> list[str]:
    return sorted(set(CITATION.findall(text or "")))


def _status(session: Session, payment_id: str) -> str:
    """What the analyst sees in the queue column.

    Deliberately not the verifier's vocabulary. `CORRECT_ABSTAIN` is a grading
    outcome and requires the answer key; `ESCALATED` is an operational state
    and does not.
    """
    if payment_id in session.resolutions:
        return session.resolutions[payment_id]["status"]

    decision = session.result.decisions.get(payment_id)
    if decision is None:
        return "UNPROCESSED"
    if decision.action != "MATCH":
        return "ESCALATED"

    if session.pending_for(payment_id):
        return "AWAITING_APPROVAL"
    states = {e.state for e in session.entries_for(payment_id)}
    if any(s.startswith("REJECTED") for s in states):
        return "LEDGER_REJECTED"
    if states:
        return "POSTED"
    return "ESCALATED"


def _receipt_row(session: Session, payment) -> dict:
    decision = session.result.decisions.get(payment.payment_id)
    episode = session.episodes.get(payment.payment_id, {})
    gate = next(
        (s for s in episode.get("steps", []) if s.get("event") == "gate"),
        None,
    )
    return {
        "payment_id": payment.payment_id,
        "bank_reference": payment.bank_reference,
        "counterparty": payment.counterparty_raw,
        "amount_cents": payment.amount_cents,
        "currency": payment.currency,
        "value_date": payment.value_date,
        "memo": payment.memo,
        "status": _status(session, payment.payment_id),
        "action": getattr(decision, "action", None),
        "reason_code": getattr(decision, "reason_code", None),
        "rationale": getattr(decision, "rationale", None),
        "allocations": [
            {"invoice_id": a.invoice_id, "amount_cents": a.amount_cents}
            for a in getattr(decision, "allocations", []) or []
        ],
        "gate_withheld": bool(gate and gate.get("verdict") == "WITHHELD"),
        "vetoes": (gate or {}).get("vetoes", []),
        "steps_used": episode.get("steps_used"),
        "resolution": session.resolutions.get(payment.payment_id),
    }


def _invoice_row(invoice) -> dict:
    return {
        "invoice_id": invoice.invoice_id,
        "invoice_number": invoice.invoice_number,
        "vendor_id": invoice.vendor_id,
        "vendor_name": invoice.vendor_name,
        "currency": invoice.currency,
        "face_amount_cents": invoice.face_amount_cents,
        "net_due_cents": invoice.net_due_cents,
        "outstanding_cents": invoice.outstanding_cents,
        "credit_note_cents": invoice.credit_note_cents,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "settled": invoice.settled,
    }


def _episode_detail(session: Session, payment_id: str) -> dict:
    episode = session.episodes.get(payment_id, {})
    payment = next(
        (p for p in _payments(session) if p.payment_id == payment_id), None
    )
    if payment is None:
        raise KeyError(payment_id)

    steps = []
    for index, step in enumerate(episode.get("steps", []), start=1):
        if "tool" in step:
            steps.append({
                "index": index,
                "kind": "tool",
                "tool": step["tool"],
                "arguments": step.get("arguments"),
                "observation": step.get("observation"),
            })
        elif step.get("event") == "gate":
            steps.append({
                "index": index,
                "kind": "gate",
                "verdict": step.get("verdict"),
                "proposed": step.get("proposed", []),
                "vetoes": [
                    {"text": v, "citations": _citations(v)}
                    for v in step.get("vetoes", [])
                ],
            })
        else:
            steps.append({"index": index, "kind": "event", "payload": step})

    row = _receipt_row(session, payment)
    row.update({
        "steps": steps,
        "human_checkpoint": episode.get("human_checkpoint", {"required": False}),
        "ledger_feedback": episode.get("ledger_feedback", []),
        "policy_error": episode.get("policy_error"),
        "evidence": list(getattr(session.result.decisions.get(payment_id), "evidence", []) or []),
        "citations": _citations(row.get("rationale") or ""),
        "referenced_invoices": _referenced_invoices(session, episode),
    })
    return row


def _referenced_invoices(session: Session, episode: dict) -> list[dict]:
    """Every invoice the investigation actually touched.

    Lets the detail view show the candidates the agent weighed instead of only
    the one it landed on, which is the difference between "here is a decision"
    and "here is why this decision and not the other one".
    """
    seen: dict[str, dict] = {}
    for step in episode.get("steps", []):
        observation = step.get("observation")
        if not isinstance(observation, dict):
            continue
        for bucket in ("matches", "invoices"):
            for candidate in observation.get(bucket, []) or []:
                if isinstance(candidate, dict) and candidate.get("invoice_id"):
                    seen.setdefault(candidate["invoice_id"], candidate)
        if observation.get("invoice_id"):
            seen.setdefault(observation["invoice_id"], observation)
    return list(seen.values())


def _payments(session: Session):
    return session.corpus.payments


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

Handler = Callable[[dict, dict], Any]
ROUTES: list[tuple[str, re.Pattern, Handler]] = []


def route(method: str, pattern: str):
    def register(fn: Handler):
        ROUTES.append((method, re.compile(f"^{pattern}$"), fn))
        return fn
    return register


def _params(query: dict) -> tuple[str, str]:
    split = (query.get("split") or [DEFAULT_SPLIT])[0]
    policy = (query.get("policy") or [DEFAULT_POLICY])[0]
    if split not in {"dev", "holdout"}:
        raise ValueError(f"unknown split {split!r}")
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    return split, policy


@route("GET", "/api/health")
def health(_match, _query):
    return {
        "ok": True,
        "policies": list(POLICIES),
        "splits": ["holdout", "dev"],
        "approval_threshold_cents": DEFAULT_APPROVAL_THRESHOLD_CENTS,
    }


@route("GET", "/api/ops/overview")
def overview(_match, query):
    split, policy = _params(query)
    session = get_session(split, policy)
    rows = [_receipt_row(session, p) for p in _payments(session)]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    posted = [r for r in rows if r["status"] == "POSTED"]
    return {
        "split": split,
        "policy": policy,
        "receipts": len(rows),
        "value_cents": sum(r["amount_cents"] for r in rows),
        "counts": counts,
        "posted_value_cents": sum(r["amount_cents"] for r in posted),
        "gate_interventions": sum(1 for r in rows if r["gate_withheld"]),
        "veto_codes": _veto_codes(rows),
        "approval_threshold_cents": DEFAULT_APPROVAL_THRESHOLD_CENTS,
        "steps_used": getattr(session.result, "steps_used", None),
    }


def _veto_codes(rows: list[dict]) -> dict[str, int]:
    codes: dict[str, int] = {}
    for row in rows:
        for veto in row["vetoes"]:
            code = veto.split(" ", 1)[0]
            codes[code] = codes.get(code, 0) + 1
    return codes


@route("GET", "/api/ops/receipts")
def receipts(_match, query):
    split, policy = _params(query)
    session = get_session(split, policy)
    rows = [_receipt_row(session, p) for p in _payments(session)]

    status = (query.get("status") or [None])[0]
    if status and status != "ALL":
        rows = [r for r in rows if r["status"] == status]

    search = (query.get("q") or [""])[0].strip().lower()
    if search:
        rows = [
            r for r in rows
            if search in r["payment_id"].lower()
            or search in r["counterparty"].lower()
            or search in (r["memo"] or "").lower()
            or search in r["bank_reference"].lower()
        ]
    return {"receipts": rows, "total": len(rows)}


@route("GET", r"/api/ops/receipts/([A-Za-z0-9\-]+)")
def receipt_detail(match, query):
    split, policy = _params(query)
    session = get_session(split, policy)
    return _episode_detail(session, match.group(1))


@route("GET", "/api/ops/invoices")
def invoices(_match, query):
    split, _policy = _params(query)
    corpus = load_corpus(DATA_ROOT, split)
    rows = [_invoice_row(i) for i in corpus.invoices]

    search = (query.get("q") or [""])[0].strip().lower()
    if search:
        rows = [
            r for r in rows
            if search in r["invoice_number"].lower()
            or search in r["vendor_name"].lower()
            or search in r["invoice_id"].lower()
        ]
    if (query.get("open_only") or ["false"])[0] == "true":
        rows = [r for r in rows if not r["settled"]]
    return {"invoices": rows, "total": len(rows)}


@route("GET", "/api/ops/procedure")
def procedure(_match, _query):
    return {
        "sections": [{"key": k, "text": v} for k, v in PROCEDURE.items()],
        "tools": [
            {"name": s.name, "description": s.description, "input_schema": s.input_schema}
            for s in TOOL_SPECS
        ],
    }


@route("POST", r"/api/ops/receipts/([A-Za-z0-9\-]+)/approve")
def approve(match, query, body=None):
    """Release a queued posting. Goes through the real ledger, which refuses
    unless a human is named -- the same call `make approve` makes."""
    split, policy = _params(query)
    session = get_session(split, policy)
    payment_id = match.group(1)
    body = body or {}

    approver = (body.get("approver") or "").strip()
    if not approver:
        raise ValueError("an approver name is required")
    if not body.get("approver_is_human"):
        raise PermissionError(
            "approval requires a human reviewer; the system cannot release its own queue"
        )

    pending = session.pending_for(payment_id)
    if not pending:
        raise ValueError(f"{payment_id} is not awaiting approval")

    for entry in pending:
        session.ledger.approve(
            entry.idempotency_key, approver=approver, approver_is_human=True
        )
    session.resolutions[payment_id] = {
        "status": "POSTED",
        "by": approver,
        "note": body.get("note") or "",
        "kind": "APPROVED",
    }
    return _episode_detail(session, payment_id)


@route("POST", r"/api/ops/receipts/([A-Za-z0-9\-]+)/resolve")
def resolve(match, query, body=None):
    """An analyst's disposition of an escalated item.

    Recorded rather than posted. Applying it would mean letting the interface
    write allocations the gate never saw, and the whole argument of this
    project is that nothing reaches the ledger without passing the same
    control. Deciding what a real deployment should do here -- re-run the
    proposal through the gate with the analyst's invoice pinned, most likely --
    is genuine design work and is called out in the limitations.
    """
    split, policy = _params(query)
    session = get_session(split, policy)
    payment_id = match.group(1)
    body = body or {}

    analyst = (body.get("analyst") or "").strip()
    if not analyst:
        raise ValueError("an analyst name is required")

    disposition = body.get("disposition")
    if disposition not in {"MATCHED", "HELD", "RETURNED"}:
        raise ValueError("disposition must be MATCHED, HELD or RETURNED")
    if disposition == "MATCHED" and not body.get("invoice_id"):
        raise ValueError("matching requires an invoice")

    session.resolutions[payment_id] = {
        "status": "RESOLVED" if disposition != "HELD" else "ESCALATED",
        "by": analyst,
        "kind": disposition,
        "invoice_id": body.get("invoice_id"),
        "note": body.get("note") or "",
    }
    return _episode_detail(session, payment_id)


@route("POST", "/api/ops/reset")
def reset(_match, query, body=None):
    split, policy = _params(query)
    get_session(split, policy, reset=True)
    return {"ok": True, "split": split, "policy": policy}


# --- evaluation: the reviewer's view, and the only place truth appears -------


@route("GET", "/api/eval/scorecard")
def scorecard(_match, query):
    split, policy = _params(query)
    session = get_session(split, policy)
    card = score(policy, session.corpus, session.result.decisions)
    return card.to_dict()


@route("GET", "/api/eval/comparison")
def comparison(_match, query):
    split = (query.get("split") or [DEFAULT_SPLIT])[0]
    rows = []
    for policy in POLICIES:
        session = get_session(split, policy)
        card = score(policy, session.corpus, session.result.decisions)
        data = card.to_dict()
        rows.append({
            "policy": policy,
            "gated": policy.endswith("+gate") or policy == "guarded",
            **data["headline"],
            "over_escalation": data["counts"].get("OVER_ESCALATION", 0),
            "steps_used": data["cost"]["steps_used"],
        })
    return {"split": split, "rows": rows}


@route("GET", "/api/eval/gate-audit")
def gate_audit(_match, query):
    """Every decision the gate changed, classified against ground truth."""
    split = (query.get("split") or [DEFAULT_SPLIT])[0]
    proposer = (query.get("proposer") or ["rules-only"])[0]
    gated = {"rules-only": "guarded"}.get(proposer, f"{proposer}+gate")
    if proposer not in POLICIES or gated not in POLICIES:
        raise ValueError(f"no gated counterpart for {proposer!r}")

    before = get_session(split, proposer)
    after = get_session(split, gated)
    truth = before.corpus.truth_by_payment()

    interventions = []
    for payment_id, original in before.result.decisions.items():
        changed = after.result.decisions.get(payment_id)
        if changed is None or original.action != "MATCH" or changed.action == "MATCH":
            continue
        # The same three buckets `make gate-audit` prints, and for the same
        # reason: "ground truth says MATCH and the gate escalated" is not the
        # same as "the gate blocked a correct posting". The proposer may have
        # been about to pay the right receipt against the wrong invoice, where
        # the veto prevented a loss even though the ideal outcome was an
        # automatic posting. Collapsing the two understates the gate.
        expected = truth[payment_id]
        proposal_was_right = (
            expected.expected_action == "MATCH"
            and original.allocations == expected.expected_allocations
        )
        interventions.append({
            "payment_id": payment_id,
            "hazard": expected.hazard,
            "expected_action": expected.expected_action,
            "proposed": [
                {"invoice_id": a.invoice_id, "amount_cents": a.amount_cents}
                for a in original.allocations
            ],
            "vetoes": [
                {"text": v, "citations": _citations(v)}
                for v in _vetoes_for(after, payment_id)
            ],
            "classification": (
                "CORRECT_POSTING_BLOCKED" if proposal_was_right
                else "WRONG_PAYMENT_PREVENTED_MATCH_WAS_POSSIBLE"
                if expected.expected_action == "MATCH"
                else "WRONG_PAYMENT_PREVENTED"
            ),
        })

    buckets: dict[str, int] = {}
    for item in interventions:
        buckets[item["classification"]] = buckets.get(item["classification"], 0) + 1
    return {
        "split": split,
        "proposer": proposer,
        "gated": gated,
        "receipts": len(before.result.decisions),
        "interventions": interventions,
        "counts": buckets,
        "correct_postings_blocked": buckets.get("CORRECT_POSTING_BLOCKED", 0),
    }


def _vetoes_for(session: Session, payment_id: str) -> list[str]:
    episode = session.episodes.get(payment_id, {})
    for step in episode.get("steps", []):
        if step.get("event") == "gate":
            return step.get("vetoes", [])
    decision = session.result.decisions.get(payment_id)
    return list(getattr(decision, "evidence", []) or [])


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


class APIHandler(BaseHTTPRequestHandler):
    server_version = "ledgergate-api/0.1"

    def _send(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # The UI is served by Next.js on another port in development. This is a
        # localhost-only tool over synthetic data; it is not an auth boundary.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        self._send({})

    def do_GET(self):  # noqa: N802
        self._dispatch("GET")

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._send({"error": "request body was not valid JSON"}, 400)
            return
        self._dispatch("POST", body)

    def _dispatch(self, method: str, body: dict | None = None) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        for verb, pattern, handler in ROUTES:
            if verb != method:
                continue
            match = pattern.match(parsed.path)
            if not match:
                continue
            try:
                payload = (
                    handler(match, query, body) if method == "POST"
                    else handler(match, query)
                )
                self._send(payload)
            except PermissionError as exc:
                self._send({"error": str(exc)}, 403)
            except KeyError as exc:
                self._send({"error": f"not found: {exc}"}, 404)
            except (ValueError, LookupError) as exc:
                self._send({"error": str(exc)}, 400)
            except Exception as exc:  # noqa: BLE001
                self._send({"error": f"{type(exc).__name__}: {exc}"}, 500)
            return
        self._send({"error": f"no route for {method} {parsed.path}"}, 404)

    def log_message(self, fmt, *args):
        print(f"  {self.command:4s} {self.path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--warm", action="store_true",
                        help="run every policy at startup instead of on first request")
    args = parser.parse_args()

    if args.warm:
        for policy in POLICIES:
            get_session(DEFAULT_SPLIT, policy)

    server = ThreadingHTTPServer((args.host, args.port), APIHandler)
    print(f"LedgerGate API on http://{args.host}:{args.port}")
    print("  operator endpoints under /api/ops/   (no ground truth)")
    print("  evaluation endpoints under /api/eval/ (ground truth, reviewer view)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
