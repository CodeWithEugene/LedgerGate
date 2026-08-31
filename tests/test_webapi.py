"""The operator interface must not be able to weaken the engine.

A user interface is where safety properties quietly die. It is the layer under
the most pressure to be helpful, it is written last, and it is the natural home
for a convenience endpoint that turns out to be a way around the control the
rest of the system exists to enforce.

So the web layer gets the same treatment as everything else here: the claims it
makes are written as tests. There are three, and each one corresponds to a way
this feature could have quietly made the project worse.

1. **The operator views cannot see ground truth.** The corpus ships with a
   label for every receipt. A real deployment has no such file. If any endpoint
   an analyst uses could read it, every screenshot would be a demonstration of
   a system that cannot exist.

2. **The interface has no privileged path to the ledger.** Approving through
   the API must go through `SandboxLedger.approve` and inherit its refusals. A
   web layer that could post something the CLI could not would make the
   controls theatre.

3. **Nothing reaches the ledger without passing the gate.** An analyst
   disposition is recorded, not applied. The moment the UI can write an
   allocation the gate never reviewed, the headline claim is false.
"""

from __future__ import annotations

import ast
import json
import threading
import urllib.error
import urllib.request
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from ledgergate import webapi
from ledgergate.cli import _make_policy
from ledgergate.ledger import ApprovalError
from ledgergate.runtime import run_policy

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def session():
    """A fresh guarded run, and the same object the endpoints will resolve to.

    Function-scoped on purpose. Several of these tests approve or resolve, and
    a shared session would let one test's write decide another test's result --
    which is precisely the class of bug this file exists to catch.
    """
    webapi._sessions.clear()
    live = webapi.get_session("holdout", "guarded")
    yield live
    webapi._sessions.clear()


# -- 1. the answer key stays out of the analyst's hands ---------------------


def test_no_operator_endpoint_can_reach_ground_truth():
    """Statically: no `/api/ops/` handler mentions the truth labels.

    Checked by reading the source rather than by calling the endpoints,
    because an endpoint that leaks truth only on some inputs would pass a
    sampled test and fail in the demo.
    """
    source = Path(webapi.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    truth_names = {"truth_by_payment", "truths", "hazard", "expected_action",
                   "expected_allocations"}

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        routes = [
            d.args[1].value
            for d in node.decorator_list
            if isinstance(d, ast.Call)
            and getattr(d.func, "id", None) == "route"
            and len(d.args) > 1
            and isinstance(d.args[1], ast.Constant)
        ]
        if not any(str(r).startswith("/api/ops/") for r in routes):
            continue
        for inner in ast.walk(node):
            name = getattr(inner, "attr", None) or getattr(inner, "id", None)
            if name in truth_names:
                offenders.append(f"{node.name} touches {name}")

    assert not offenders, (
        "an operator endpoint can see the answer key, so the interface would "
        f"be demonstrating a system that cannot be deployed: {offenders}"
    )


def test_the_operator_view_is_byte_identical_without_the_answer_key(session):
    """Delete ground truth entirely and the analyst's screens do not change.

    Scanning payloads for hazard names is the obvious test and it is a bad
    one, because the vocabulary legitimately overlaps: a receipt labelled
    `CURRENCY_MISMATCH` is vetoed by a rule *called* `CURRENCY_MISMATCH`, and
    a policy that finds nothing abstains with `NO_CANDIDATE`. Both strings are
    derived from tool observations that exist in any real deployment. A
    substring scan cannot tell those apart from a leak, and tuning it until it
    passes is just fitting the test to the code.

    Independence is the property actually worth having, and it can be checked
    directly: run the identical corpus with the truth labels stripped out, and
    require the operator payloads to be unchanged down to the byte. If any of
    them consulted the answer key, this fails.
    """
    stripped = replace(session.corpus, truths=())
    blind = webapi.Session(
        split="holdout",
        policy="guarded",
        corpus=stripped,
        result=run_policy(
            _make_policy("guarded"), stripped, max_steps_per_payment=40
        ),
        episodes=webapi._load_episodes("guarded", "holdout"),
        resolutions={},
    )

    def render(target: webapi.Session) -> str:
        webapi._sessions[("holdout", "guarded")] = target
        return json.dumps(
            [
                webapi.overview(None, _q()),
                webapi.receipts(None, _q()),
                webapi.invoices(None, _q()),
                webapi.receipt_detail(_Match("HLD-PAY0015"), _q()),
                webapi.procedure(None, _q()),
            ],
            default=str,
            sort_keys=True,
        )

    with_truth = render(session)
    without_truth = render(blind)

    assert with_truth == without_truth, (
        "an operator endpoint changed when ground truth was removed, so the "
        "interface depends on a file no real deployment has"
    )


def test_removing_the_answer_key_does_break_the_reviewer_view(session):
    """The control for the test above.

    If grading kept working without labels, the comparison would prove nothing
    -- it would just mean neither view was reading truth in the first place.
    """
    stripped = replace(session.corpus, truths=())
    webapi._sessions[("holdout", "guarded")] = webapi.Session(
        split="holdout",
        policy="guarded",
        corpus=stripped,
        result=session.result,
        episodes={},
        resolutions={},
    )
    with pytest.raises(KeyError):
        webapi.scorecard(None, _q())


def test_the_evaluation_endpoints_do_use_truth_and_say_so():
    """The converse. A reviewer's view that could not grade would be useless."""
    audit = webapi.gate_audit(None, _q(proposer="rules-only"))
    assert audit["interventions"], "the gate audit graded nothing"
    assert all("hazard" in item for item in audit["interventions"])


# -- 2. approval is the ledger's decision, not the interface's --------------


def test_the_interface_cannot_approve_without_a_human(session):
    queued = next(
        r["payment_id"]
        for r in webapi.receipts(None, _q())["receipts"]
        if r["status"] == "AWAITING_APPROVAL"
    )
    with pytest.raises(PermissionError):
        webapi.approve(
            _Match(queued), _q(), {"approver": "the agent", "approver_is_human": False}
        )
    with pytest.raises(ValueError):
        webapi.approve(_Match(queued), _q(), {"approver": "  ", "approver_is_human": True})

    assert _status(queued) == "AWAITING_APPROVAL", (
        "a refused approval still changed the queue"
    )


def test_approving_goes_through_the_real_ledger(session):
    queued = next(
        r["payment_id"]
        for r in webapi.receipts(None, _q())["receipts"]
        if r["status"] == "AWAITING_APPROVAL"
    )
    before = len(session.ledger.pending_approvals)

    webapi.approve(
        _Match(queued), _q(), {"approver": "D. Okoro", "approver_is_human": True}
    )

    assert _status(queued) == "POSTED"
    assert len(session.ledger.pending_approvals) == before - 1
    with pytest.raises(ValueError):
        webapi.approve(
            _Match(queued), _q(), {"approver": "D. Okoro", "approver_is_human": True}
        )


def test_the_ledger_still_refuses_a_non_human_even_if_the_api_is_bypassed(session):
    """The guarantee lives in the ledger, not in the route's argument check."""
    pending = session.ledger.pending_approvals
    if not pending:
        pytest.skip("nothing queued on this run")
    with pytest.raises(ApprovalError):
        session.ledger.approve(
            pending[0].idempotency_key, approver="bot", approver_is_human=False
        )


# -- 3. the gate stays on the only path to the ledger -----------------------


def test_an_analyst_disposition_never_writes_to_the_ledger(session):
    """Resolving an escalation records a decision; it does not post one.

    If this ever changes, the interface has become a way to apply an
    allocation the safety gate never reviewed -- which is the exact failure
    the rest of this project is built to prevent.
    """
    withheld = next(
        r["payment_id"]
        for r in webapi.receipts(None, _q())["receipts"]
        if r["gate_withheld"]
    )
    before = len(session.ledger.journal)

    webapi.resolve(
        _Match(withheld),
        _q(),
        {
            "analyst": "D. Okoro",
            "disposition": "MATCHED",
            "invoice_id": "HLD-INV0046",
        },
    )

    assert len(session.ledger.journal) == before, (
        "resolving an escalation wrote to the ledger, bypassing the gate"
    )
    assert webapi.receipt_detail(_Match(withheld), _q())["resolution"]["by"] == "D. Okoro"


def test_resolution_requires_a_named_analyst_and_a_real_disposition(session):
    withheld = next(
        r["payment_id"]
        for r in webapi.receipts(None, _q())["receipts"]
        if r["gate_withheld"]
    )
    for body in (
        {"analyst": "", "disposition": "MATCHED", "invoice_id": "X"},
        {"analyst": "D. Okoro", "disposition": "POST_IT_ANYWAY"},
        {"analyst": "D. Okoro", "disposition": "MATCHED"},
    ):
        with pytest.raises(ValueError):
            webapi.resolve(_Match(withheld), _q(), body)


# -- the interface must agree with the command line -------------------------


def test_the_api_reports_the_same_numbers_as_the_committed_results():
    """`make eval-advanced` and the Evaluation tab must not disagree.

    Two code paths that grade the same run will drift apart eventually. The
    scorecard endpoint takes keyword arguments with harmless-looking defaults,
    and silently publishing zeros for them is exactly how a dashboard ends up
    contradicting the README it was built to illustrate.
    """
    committed = json.loads(
        (REPO_ROOT / "results" / "guarded.holdout.json").read_text(encoding="utf-8")
    )
    live = webapi.scorecard(None, _q())

    assert live["headline"] == committed["headline"]
    assert live["counts"] == committed["counts"]
    assert live["cost"]["steps_used"] == committed["cost"]["steps_used"]


def test_the_gate_audit_matches_the_cli_classification():
    """Three buckets, and the third one is the claim."""
    for proposer, expected_total in (("rules-only", 6), ("baseline", 24), ("reckless", 45)):
        audit = webapi.gate_audit(None, _q(proposer=proposer))
        assert len(audit["interventions"]) == expected_total, proposer
        assert audit["correct_postings_blocked"] == 0, (
            f"the gate blocked a correct posting behind {proposer}; "
            "soundness is broken"
        )


def test_every_veto_the_interface_shows_carries_a_clause():
    """The UI links each citation into the procedure. A veto without one
    would render as 'the computer said no', which is not an answer an analyst
    can give a supplier."""
    for row in webapi.receipts(None, _q())["receipts"]:
        for veto in row["vetoes"]:
            assert webapi.CITATION.search(veto), f"veto with no clause: {veto}"


# -- the shape of a failure is part of the contract -------------------------


@pytest.fixture
def server():
    """The real HTTP server on an ephemeral port."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), webapi.APIHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_every_failure_is_json_with_an_error_key(server):
    """Errors must be JSON, because the browser distinguishes two failures by it.

    Next serves the interface and rewrites `/api/*` to this server. When this
    server is not running, that rewrite fails on its own and returns a bare 500
    reading `Internal Server Error` -- no JSON, no `error`. That is the single
    likeliest thing to go wrong for anyone following the README, because it is
    what you get from `make web` without `make web-api`.

    The client tells the two apart by exactly this: a 5xx carrying no JSON
    `error` did not come from here, so it says "start the engine" instead of
    "something went wrong". That inference is only sound while this holds, so
    it is pinned here rather than left as a comment in the TypeScript.
    """
    cases = [
        ("GET", "/api/ops/nonexistent", None, 404),
        ("GET", "/api/ops/receipts/NOPE-0001?split=holdout&policy=guarded", None, 404),
        ("GET", "/api/ops/overview?split=holdout&policy=no-such-policy", None, 400),
        ("POST", "/api/ops/receipts/HLD-PAY0001/approve?split=holdout&policy=guarded",
         {"approver": "D. Okoro", "approver_is_human": False}, 403),
        ("POST", "/api/ops/reset?split=holdout&policy=guarded", b"{not json", 400),
    ]

    for method, path, body, expected_status in cases:
        if body is None:
            request = urllib.request.Request(server + path, method=method)
        else:
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            request = urllib.request.Request(
                server + path, data=raw, method=method,
                headers={"Content-Type": "application/json"},
            )

        try:
            with urllib.request.urlopen(request) as response:
                pytest.fail(f"{method} {path} unexpectedly succeeded "
                            f"({response.status})")
        except urllib.error.HTTPError as exc:
            assert exc.code == expected_status, f"{method} {path}"
            assert exc.headers.get("Content-Type") == "application/json", (
                f"{method} {path} did not answer in JSON; the interface would "
                "read this as the engine being down"
            )
            payload = json.loads(exc.read())
            assert payload.get("error"), (
                f"{method} {path} returned {exc.code} with no `error` key, "
                "which the interface reads as 'the engine is not running'"
            )


def _status(payment_id: str) -> str:
    return webapi.receipt_detail(_Match(payment_id), _q())["status"]


def _q(**kwargs: str) -> dict[str, list[str]]:
    """A query dict in the shape `parse_qs` produces, which is what routes read."""
    return {key: [value] for key, value in kwargs.items()}


class _Match:
    """Stands in for the regex match a route would receive from the server."""

    def __init__(self, value: str) -> None:
        self._value = value

    def group(self, _index: int) -> str:
        return self._value
