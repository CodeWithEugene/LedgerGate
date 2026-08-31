# Agents: disclosure and trajectories

Two distinct kinds of agent are involved in this submission, and both are
disclosed with their trajectories.

---

## 1. The runtime agent — the thing being measured

This is the product. It is a tool-using agent that reads incoming bank
receipts, investigates them through a fixed tool surface, and either proposes a
posting or escalates to a human.

**Trajectories:** `traces/<policy>.<split>.jsonl`, written by
`src/ledgergate/runtime.py`. These are a product artifact, not a debug log —
the same record an AP analyst needs when a queued item lands on their desk.

Each file is JSONL with three record types:

| Record | Contents |
|---|---|
| `header` | The policy name, the **full agent instructions** it operated under, every tool it was given with descriptions, the step budget, the human-approval threshold, and the corpus and seed. |
| `episode` | One per receipt: the receipt as the bank delivered it, every tool call with its arguments and the observation that came back, every model turn with its text and requested tool calls, any retry, any rejected malformed submission and the corrective feedback sent back, the safety gate's verdict with each veto and the clause it cites, the final decision, what the ledger did with it, and whether a human checkpoint was triggered. |
| `summary` | Decision count, steps used, wall time, ledger rejections by reason, items queued for human approval, policy errors, and model/token counters. |

Read one as prose:

```bash
make trace-sample
python3 scripts/show_trace.py traces/llm-gated.holdout.jsonl HLD-PAY0012
```

Every policy produces its own trajectory, so the ablation is inspectable rather
than merely tabulated. Comparing `baseline.holdout.jsonl` against
`baseline+gate.holdout.jsonl` for the same receipt shows the proposer making
the identical proposal and the gate withholding it, with the clause cited.

`make trace-sample` selects, by default, an episode in which the gate overruled
the proposer — that is the one worth reading.

**On the model-driven runtime agent.** `src/ledgergate/policies/llm.py`
implements the same agent loop driven by a language model, and it is fully
tested (`tests/test_llm_policy.py`, 19 tests against a scripted model, no
network). **It produced no published trajectory and no published number**, for
the service-terms reason recorded in [`CHANGELOG.md` §9](CHANGELOG.md) and
[`PROBLEM.md` §6](PROBLEM.md). `cassettes/` is therefore empty in this
submission. Anyone with a legitimate credential can populate it with
`make record-llm`, after which `traces/llm.holdout.jsonl` and
`traces/llm-gated.holdout.jsonl` appear alongside the rest.

---

## 2. The coding agent — the thing that built the repository

This repository was written in **Cursor**, driven by **Claude Opus 5**, working
from my direction. That is disclosed here rather than implied.

**Trajectories:** `docs/agent-sessions/*.jsonl`, exported by
`scripts/export_agent_sessions.py`. Every line passes through a redaction pass
before it is written, and `--check` re-verifies that nothing secret-shaped
survived. `tests/test_submission.py` runs that check.

**What these files do and do not contain — stated plainly, because the
difference matters.** Cursor's exported transcript records the *conversation*:
my instructions, the agent's reasoning, and its reported results, turn by turn.
It does **not** record individual tool calls and their raw responses; the IDE
does not expose those in an exportable form, and the local tool cache holds
unstructured fetched content rather than a call/response log. So for the coding
agent you get instructions → reasoning → outcome, and not a per-tool trace.

Where a per-tool trace exists, it is the runtime agent's, in `traces/` — and
those are complete: every call, every argument, every observation. The
distinction is worth being explicit about rather than letting two very
different artifacts sit under one heading.

### How the work was actually split

I set the direction and made the design calls: the choice of problem, the
insight that the interesting artifact is the *gate* rather than the matcher,
the decision to make the gate monotone, the hazard taxonomy, the cost model's
shape, and the decision to treat escalation as a positive outcome. The agent
did the great majority of the typing, and did it well — the corpus generator
and the test suite in particular would have taken far longer by hand.

### Where the agent was wrong, and how it was caught

Recording this matters more than the successes, because it is the part that
tells you what supervision this workflow actually needs.

**A mislabelled benchmark, caught by the system's own safety gate.** The first
full run of the advanced policy scored below 100%, with two `CONSOLIDATED_REF`
receipts escalated. Reading the trajectory showed the gate firing
`PREDATED_RECEIPT`: the generator derived a consolidated receipt's value date
from the *first* invoice in the group, but invoices carry independent issue
dates, so a sibling in the same group could be issued after the receipt
arrived. My ground truth said MATCH while my own written procedure said
escalate. The gate was right and the benchmark was wrong. Fixed in
`_Builder.settle_date` (now `max(issue_date)` over the group), and
`audit_corpus` re-asserts the property directly so the same class of error
cannot come back silently. This is the single most useful thing that happened
during the build.

**Colliding identifiers across splits.** The first corpus gave both splits the
same invoice numbers and payment IDs. Nothing was measurably broken, but it
made trajectories ambiguous and left a latent collision hazard in the
prompt-keyed response cache. Caught by a test I wrote to assert the splits were
genuinely different. Fixed by giving each split its own identifier prefix and
invoice-number block — which cost a full re-record of the cassettes.

**An isolation test that matched its own prose.** A test asserting that only
the store module names `truth.json` failed because other modules *mention* the
file in their docstrings while explaining that they never read it. The test was
wrong, not the code; it now parses the AST and ignores docstrings.

**A fabricated decision log.** Drafting `CHANGELOG.md`, the agent produced
entries describing experiments that read plausibly and had never happened — a
float-arithmetic bug with a specific numeric example, and an LLM-as-judge
scorer "killed after one afternoon." Both were inventions in the shape of the
surrounding true entries, and both would have been indistinguishable from the
real ones to a reader. Caught by going back through the session history and the
code to check each claim, then rewriting the file so every entry is labelled as
either a *design decision* (reasoned up front) or an *iteration* (driven by
named evidence). This is the most dangerous failure in the list: the others
produce wrong code, which tests catch, and this one produces a convincing
document, which nothing catches automatically.

**A control that was technically correct and practically useless.** The agent
set the human-approval threshold below the median receipt, queueing 26 of 27
postings. Every test passed. See [`CHANGELOG.md` §10](CHANGELOG.md).

**Scope pressure.** The agent was willing to keep adding capability — subset-sum
matching, richer reporting, a second corpus generator. Each was cut
deliberately; see "What I deliberately did not build" in
[`PROBLEM.md`](PROBLEM.md).

### What this says about supervising coding agents

The agent was reliably good at code with a clear contract, reliably weak at
noticing when a *specification* was self-contradictory, and — most importantly
— **weakest exactly where verification is hardest.** Every code failure above
was caught by something automatic. The one failure that automation could not
catch was the fabricated changelog, because prose has no test suite: a
plausible sentence and a true sentence are the same object to every check in
this repository.

That maps directly onto the product's own argument. The predated-receipt bug
was found by an independent component that re-derived the facts rather than
trusting the narration, which is precisely what `safety.py` does to a proposer's
rationale. The lesson generalises in an uncomfortable direction: the artifacts
most worth supervising are the ones a reviewer is least able to check, and for
a coding agent that is the documentation, not the code.

---

## Tool and licence compliance

- **A model run was discarded over a service-terms problem.** The only endpoint
  available to me refuses clients that do not identify as first-party tools,
  and the recording in progress was getting through by declaring itself
  `claude-cli/1.0.0`. That run was killed, its ~230 recorded responses were
  discarded, and the user-agent override was deleted from the client so the
  header is now a module constant. No data obtained that way appears in this
  submission. Full account in [`CHANGELOG.md` §9](CHANGELOG.md).
- **The coding agent** ran in Cursor under my own subscription, within its
  terms.
- No credential appears in this repository, and a test scans every tracked file
  to confirm it.
- No third-party runtime code is vendored. The package has zero runtime
  dependencies; the only test dependency is `pytest` (MIT), pinned.
- All data is synthetic and generated by `src/ledgergate/corpus.py`. No real
  company, supplier, bank, invoice or payment data was used, and a test asserts
  the corpus contains no email addresses, IBANs, routing numbers or URLs.
- No consequential action is taken against any real system. The ledger is an
  in-memory simulation, and it refuses to release a queued posting unless the
  caller declares itself human.
