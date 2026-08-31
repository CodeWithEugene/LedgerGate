"""The model-driven agent loop, tested against a scripted fake model.

None of this needs a network or a credential. The point is to pin down the
behaviour that matters when a model misbehaves: a malformed submission must
become corrective feedback rather than a crash, an unreachable provider must
become an escalation rather than a posting, and a model that never commits must
not silently default to acting.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledgergate.evidence import gather
from ledgergate.ledger import SandboxLedger
from ledgergate.llm.cassette import CassetteClient, request_key
from ledgergate.llm.client import CassetteMiss, LLMError, LLMResponse
from ledgergate.policies.llm import LLMPolicy, build_llm_policy
from ledgergate.tools import ToolSession


class ScriptedModel:
    """Returns a fixed sequence of responses, recording what it was asked."""

    model = "fake-model"

    def __init__(self, script: list[LLMResponse | Exception]) -> None:
        self.script = list(script)
        self.requests: list[dict] = []

    def complete(self, *, system, messages, tools, max_tokens=1024, temperature=0.0):
        self.requests.append({"system": system, "messages": list(messages)})
        if not self.script:
            raise AssertionError("the loop asked for more turns than the script provides")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def response(*blocks, stop_reason="tool_use") -> LLMResponse:
    return LLMResponse(content=list(blocks), stop_reason=stop_reason, model="fake-model",
                       input_tokens=10, output_tokens=5)


def tool_use(name, payload, use_id="tu1"):
    return {"type": "tool_use", "id": use_id, "name": name, "input": payload}


def text(body):
    return {"type": "text", "text": body}


def make_policy(script, *, use_gate=False) -> LLMPolicy:
    policy = LLMPolicy.__new__(LLMPolicy)
    policy.model = "fake-model"
    policy.use_gate = use_gate
    policy.max_model_turns = 6
    policy.name = "llm-gated" if use_gate else "llm"
    policy.mode = "live"
    policy.cassette_path = Path("/nonexistent")
    policy.client = ScriptedModel(script)
    policy.stats = {
        "llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "http_attempts": 0,
        "malformed_submissions": 0, "no_submission": 0, "vetoes": 0, "veto_codes": {},
        "cassette_hits": 0, "cassette_misses": 0, "mode": "live", "model": "fake-model",
    }
    return policy


@pytest.fixture()
def session(dev_corpus):
    ledger = SandboxLedger.from_invoices(dev_corpus.invoices, dev_corpus.opening_allocations)
    payment = dev_corpus.payments[0]
    return payment, ToolSession(dev_corpus.invoice_by_id(), ledger, payment, max_steps=40)


# -- the loop ---------------------------------------------------------------


def test_the_loop_runs_tools_then_records_the_submission(session):
    payment, tool_session = session
    target = "DEV-INV0025"
    policy = make_policy([
        response(text("Let me read the procedure."),
                 tool_use("procedure", {"section": "identification"})),
        response(tool_use("submit_decision", {
            "action": "MATCH",
            "allocations": [{"invoice_id": target, "amount_cents": payment.amount_cents}],
            "reason_code": "REFERENCE_EXACT",
            "rationale": "AP-07.2(a) reference and amount agree.",
        }, use_id="tu2")),
    ])

    decision = policy.decide(payment, tool_session)

    assert decision.action == "MATCH"
    assert decision.allocations[0].invoice_id == target
    assert policy.stats["llm_calls"] == 2
    assert any(step.get("tool") == "procedure" for step in tool_session.steps)
    assert any(step.get("event") == "model_turn" for step in tool_session.steps)


def test_a_malformed_submission_is_returned_as_feedback_not_a_crash(session):
    payment, tool_session = session
    policy = make_policy([
        response(tool_use("submit_decision", {
            "action": "MATCH", "allocations": [], "reason_code": "X", "rationale": "y",
        })),
        response(tool_use("submit_decision", {
            "action": "ABSTAIN", "reason_code": "AMBIGUOUS", "rationale": "cannot tell",
        }, use_id="tu2")),
    ])

    decision = policy.decide(payment, tool_session)

    assert decision.action == "ABSTAIN"
    assert policy.stats["malformed_submissions"] == 1
    rejected = [s for s in tool_session.steps if s.get("event") == "submission_rejected"]
    assert len(rejected) == 1
    # The correction must actually reach the model on the following turn.
    follow_up = json.dumps(policy.client.requests[-1]["messages"])
    assert "rejected" in follow_up


@pytest.mark.parametrize("bad", [
    {"action": "MAYBE", "reason_code": "X", "rationale": "y"},
    {"action": "MATCH", "allocations": [{"invoice_id": "I", "amount_cents": "100"}],
     "reason_code": "X", "rationale": "y"},
    {"action": "MATCH", "allocations": [{"amount_cents": 100}], "reason_code": "X",
     "rationale": "y"},
    {"action": "MATCH", "allocations": "everything", "reason_code": "X", "rationale": "y"},
])
def test_submission_validation_rejects_malformed_payloads(session, bad):
    payment, _ = session
    policy = make_policy([])
    decision, error = policy._parse_submission(payment, bad)
    assert decision is None
    assert error


def test_a_string_amount_is_never_coerced_into_money(session):
    """Silently accepting "100" would put a string through the money path."""
    payment, _ = session
    policy = make_policy([])
    _, error = policy._parse_submission(
        payment,
        {"action": "MATCH", "reason_code": "X", "rationale": "y",
         "allocations": [{"invoice_id": "I1", "amount_cents": "100"}]},
    )
    assert "integer" in error


def test_a_provider_failure_escalates_and_never_posts(session):
    payment, tool_session = session
    policy = make_policy([LLMError("HTTP 503: upstream unavailable")])

    decision = policy.decide(payment, tool_session)

    assert decision.action == "ABSTAIN"
    assert decision.reason_code == "LLM_UNAVAILABLE"
    assert any(s.get("event") == "llm_error" for s in tool_session.steps)


def test_a_model_that_never_commits_does_not_default_to_acting(session):
    payment, tool_session = session
    policy = make_policy([response(text("thinking...")) for _ in range(6)])
    policy.max_model_turns = 3

    decision = policy.decide(payment, tool_session)

    assert decision.action == "ABSTAIN"
    assert decision.reason_code == "NO_SUBMISSION"
    assert policy.stats["no_submission"] == 1


def test_an_unknown_tool_name_becomes_an_observation(session):
    payment, tool_session = session
    policy = make_policy([
        response(tool_use("wire_money", {"to": "me"})),
        response(tool_use("submit_decision", {
            "action": "ABSTAIN", "reason_code": "NO", "rationale": "no",
        }, use_id="tu2")),
    ])

    decision = policy.decide(payment, tool_session)

    assert decision.action == "ABSTAIN"
    step = next(s for s in tool_session.steps if s.get("tool") == "wire_money")
    assert "error" in step["observation"]


def test_the_gate_overrides_a_model_that_wants_to_post_a_duplicate(dev_corpus):
    """End to end: model proposes, gate independently refuses."""
    ledger = SandboxLedger.from_invoices(dev_corpus.invoices, dev_corpus.opening_allocations)
    invoices = dev_corpus.invoice_by_id()

    original = dev_corpus.payments[0]
    duplicate = next(
        p for p in dev_corpus.payments[1:] if p.bank_reference == original.bank_reference
    )
    truth = dev_corpus.truth_by_payment()[original.payment_id]
    target = truth.expected_allocations[0].invoice_id

    # Settle the original first so the duplicate really is a replay.
    first_session = ToolSession(invoices, ledger, original, max_steps=40)
    gather(original, first_session)
    from ledgergate.types import Allocation, Decision
    ledger.apply(original, Decision(original.payment_id, "MATCH",
                                    (Allocation(target, original.amount_cents),)))

    session = ToolSession(invoices, ledger, duplicate, max_steps=60)
    policy = make_policy([
        response(tool_use("submit_decision", {
            "action": "MATCH",
            "allocations": [{"invoice_id": target, "amount_cents": duplicate.amount_cents}],
            "reason_code": "LOOKS_FINE",
            "rationale": "the reference matches",
        })),
    ], use_gate=True)

    decision = policy.decide(duplicate, session)

    assert decision.action == "ABSTAIN"
    assert decision.reason_code.startswith("GATE_")
    assert policy.stats["vetoes"] == 1
    assert any(s.get("event") == "gate" and s.get("verdict") == "WITHHELD"
               for s in session.steps)


# -- cassettes --------------------------------------------------------------


def test_the_request_key_is_stable_and_content_addressed():
    args = dict(model="m", system="s", messages=[{"role": "user", "content": "hi"}],
                tools=[], max_tokens=10, temperature=0.0)
    assert request_key(**args) == request_key(**args)

    changed = dict(args)
    changed["messages"] = [{"role": "user", "content": "hello"}]
    assert request_key(**args) != request_key(**changed)


def test_record_then_replay_reproduces_the_response_exactly(tmp_path):
    path = tmp_path / "tape.json"
    live = ScriptedModel([response(text("recorded answer"), stop_reason="end_turn")])

    recorder = CassetteClient(path=path, model="fake-model", inner=live, mode="record")
    first = recorder.complete(system="s", messages=[{"role": "user", "content": "q"}], tools=[])
    recorder.save()

    player = CassetteClient(path=path, model="fake-model", mode="replay")
    second = player.complete(system="s", messages=[{"role": "user", "content": "q"}], tools=[])

    assert second.text() == first.text() == "recorded answer"
    assert second.replayed is True
    assert player.hits == 1 and player.misses == 0


def test_a_replay_miss_is_a_hard_error(tmp_path):
    """Silently substituting an answer would misrepresent what was measured."""
    path = tmp_path / "tape.json"
    live = ScriptedModel([response(text("a"))])
    recorder = CassetteClient(path=path, model="fake-model", inner=live, mode="record")
    recorder.complete(system="s", messages=[{"role": "user", "content": "q"}], tools=[])
    recorder.save()

    player = CassetteClient(path=path, model="fake-model", mode="replay")
    with pytest.raises(CassetteMiss):
        player.complete(system="s", messages=[{"role": "user", "content": "DIFFERENT"}], tools=[])


def test_replay_without_a_cassette_explains_what_to_do(tmp_path):
    with pytest.raises(CassetteMiss) as excinfo:
        CassetteClient(path=tmp_path / "missing.json", model="m", mode="replay")
    assert "record" in str(excinfo.value)


def test_the_cassette_never_stores_a_credential(tmp_path):
    path = tmp_path / "tape.json"
    live = ScriptedModel([response(text("ok"))])
    recorder = CassetteClient(path=path, model="fake-model", inner=live, mode="record")
    recorder.complete(
        system="you are an agent",
        messages=[{"role": "user", "content": "q"}],
        tools=[],
    )
    recorder.save()

    blob = path.read_text().lower()
    for forbidden in ("authorization", "x-api-key", "bearer", "sk-"):
        assert forbidden not in blob


# -- wiring -----------------------------------------------------------------


def test_the_policy_spec_parser_selects_the_gate_and_the_model(monkeypatch):
    monkeypatch.setenv("LEDGERGATE_LLM_MODE", "live")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-used-because-nothing-is-called")

    gated = build_llm_policy("llm-gated:some-model")
    plain = build_llm_policy("llm")

    assert gated.use_gate is True and gated.model == "some-model"
    assert plain.use_gate is False and plain.name == "llm"


def test_an_unknown_llm_spec_is_rejected(monkeypatch):
    monkeypatch.setenv("LEDGERGATE_LLM_MODE", "live")
    with pytest.raises(SystemExit):
        build_llm_policy("llm-turbo")


def test_a_missing_credential_is_a_clear_error_not_a_stack_trace(monkeypatch):
    from ledgergate.llm.client import AnthropicClient

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    client = AnthropicClient(model="m", token="")

    with pytest.raises(LLMError) as excinfo:
        client.complete(system="s", messages=[], tools=[])
    assert "replay" in str(excinfo.value)
