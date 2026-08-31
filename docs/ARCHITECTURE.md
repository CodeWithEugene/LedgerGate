# Architecture

## The shape of the idea

Cash application is a decision followed by an irreversible action. Almost
every agent design puts intelligence in the same place as authority: the model
decides, and the decision executes. That is fine when a mistake is a bad
sentence and unacceptable when a mistake is a payment.

LedgerGate separates them into four parts with different trust levels:

```
                    untrusted                trusted
  receipt ──▶ ┌───────────────┐   proposal  ┌──────────┐   decision  ┌────────┐
              │   proposer    │────────────▶│   gate   │────────────▶│ ledger │
              │ rules | model │             │ veto-only│             │ sandbox│
              └───────┬───────┘             └────┬─────┘             └───┬────┘
                      │                          │                       │
                      │  tool calls              │ re-derives            │ idempotency
                      ▼                          ▼ evidence              ▼ approval queue
              ┌──────────────────────────────────────────┐
              │  tool surface: procedure, invoices,      │
              │  ledger reads, duplicate check, compute  │
              └──────────────────────────────────────────┘
                                   │
                    (no path to ground truth — asserted by test)

                        ground truth ──▶ verifier ──▶ scorecard
```

Each boundary carries a property that is tested, not assumed.

**The proposer is untrusted and swappable.** A rules engine, a language model,
or a deliberately reckless probe all implement the same interface and produce
the same trajectory format. Swapping it is the ablation.

**The gate is monotone.** It has exactly one power: turning a proposed MATCH
into an ABSTAIN. It cannot create a match, change an allocation, or choose a
different invoice. That single restriction is why it is safe to bolt onto a
proposer you do not trust — the worst it can do is escalate too much, and that
cost is measured. `test_gate_is_monotone_it_can_only_escalate` fuzzes it with
absurd proposals and asserts the property holds for every one.

**The gate re-derives the facts.** It never reads the proposer's rationale.
A model that hallucinates an invoice number must not have that hallucination
promoted to a fact by the component whose job is to catch it. The gate calls
the tools itself.

**The ledger assumes everything upstream failed.** Idempotency by bank
reference and by allocation, over-application checks that survive being split
across lines, currency enforcement, and an approval queue that the system
cannot release on its own. `SandboxLedger.approve` raises unless the caller
declares a human.

---

## Why the gate is not just "more rules"

The proposer also contains rules. The distinction is what each is allowed to
be wrong about.

The proposer implements what AP-07 **says**: identification by reference,
identification by unique amount, rounding tolerance, declared part payments,
enumerated consolidated receipts, once-only bank references. If it is wrong,
you get a bad match.

The gate implements what AP-07 **does not say** — section AP-07.9, the list of
matters the procedure has not yet ruled on: cross-currency receipts,
overpayments, reversals, receipts predating their invoice. Plus the structural
ambiguity checks: conflicting evidence, and amounts that fit more than one
invoice.

Running the proposer with the gate disabled (`--policy rules-only`) isolates
exactly the failures that come from the procedure being incomplete rather than
from the implementation being wrong. That is why `use_gate=False` exists at
all.

---

## Why the gate is measured against a range of proposers, not one

`Gated` (`policies/gated.py`) wraps *any* proposer, and `--policy X+gate` works
for every `X` the CLI knows. That generality is not tidiness; it is what makes
the central claim falsifiable.

A single ablation shows the gate helping one proposer. It cannot distinguish
"the gate is a safety control" from "the gate happens to patch this particular
proposer's weaknesses" — and it has no answer at all to the natural objection
that a sufficiently good model would not need it.

Proposers spanning the quality range turn the claim into a shape:

| | proposer | role in the argument | in the published table? |
|---|---|---|---|
| lower anchor | `reckless` | The worst plausible input. Posts against the first row it sees, including settled invoices. If the guarantee survives this, it is a property of the gate. | yes |
| naive | `baseline` | What the workflow looks like built in an afternoon. | yes |
| competent | `rules-only` | A faithful implementation of the written procedure. | yes |
| untrusted-but-strong | `llm` | A frontier model with the same tools and the same procedure. | **no — removed over a service-terms problem, see [`CHANGELOG.md` §9](CHANGELOG.md)** |

The measured result is that **false pays go to zero for all three published
proposers**, while the number of correct postings needlessly escalated falls as
the proposer improves: 12, 7, 0. Safety is flat; its price is not. Both halves
are asserted in `tests/test_safety.py`, including the ordering claim, so the
prose in the README cannot quietly stop being true.

**Across all three, the gate blocked zero postings a proposer had right.**
`ledgergate gate-audit` classifies every changed decision against ground truth
and separates "the proposer named the wrong invoice, so the veto prevented a
loss even though a correct posting was theoretically available" from "the
proposer was right and the gate refused anyway". The second category is empty
for every proposer, which means the `over-esc` column measures proposer error
rather than gate over-caution.
`test_the_gate_never_blocks_a_posting_the_proposer_had_right` asserts it on
both splits.

At the competent end the gate is also exact: it intervenes on six of sixty
receipts, and those six are precisely the six `rules-only` would have paid
wrongly — no misses, no collateral.
`test_against_the_best_proposer_the_gate_fires_only_where_it_must` asserts the
two sets are identical, and `gate-audit` prints each veto with its citation.

**The missing fourth row is the weakest point in this argument, and it is a
gap rather than an omission.** The curve is established over three proposers,
the strongest of which is a rules engine rather than a model. Whether the shape
continues to hold at frontier-model quality is untested here. The code and its
tests are in the repository; only the measurement is absent.

---

## Layout

| Path | Role |
|---|---|
| `src/ledgergate/types.py` | Frozen contracts. Money is integer cents everywhere; floats never touch it. |
| `src/ledgergate/corpus.py` | Seeded synthetic generator, 20 hazard classes, plus `audit_corpus`. |
| `src/ledgergate/store.py` | Persistence and the SHA-256 manifest over the committed corpus. |
| `src/ledgergate/ledger.py` | Sandbox ledger: idempotency, over-application, currency, approval queue. |
| `src/ledgergate/tools.py` | The tool surface, and the AP-07 procedure text with its gaps. |
| `src/ledgergate/evidence.py` | Shared evidence gathering, used by both the proposer and the gate. |
| `src/ledgergate/safety.py` | The veto-only gate. Every veto cites a clause. |
| `src/ledgergate/runtime.py` | Drives a policy over the feed; writes trajectories. |
| `src/ledgergate/policies/` | `reckless`, `baseline`, `guarded` (rules ± gate), `llm` (model ± gate), and `gated.Gated`, which puts the gate in front of any of them. |
| `src/ledgergate/llm/` | Stdlib HTTP client and the record/replay cassette. |
| `src/ledgergate/evaluation/` | The frozen verifier, the cost model, and reporting. |

## Design decisions worth defending

**Zero runtime dependencies.** The whole system, including the HTTP client for
the model provider, is standard library. There is no wheel that can fail to
build on a reviewer's interpreter and no transitive package that can drift
underneath a published number. The only third-party package anywhere is
`pytest`, pinned, and it is not needed to reproduce the results.

**Integer cents, enforced.** `safe_compute` rejects float literals outright.
A rounding artefact and a real short payment must never be confusable.

**Arithmetic is a tool call.** Models do arithmetic badly and confidently.
Routing every calculation through `compute` makes each one appear in the
trajectory where it can be checked.

**Trajectories are a product feature, not a debug log.** The analyst who
inherits a queued item needs the same record a reviewer of this project needs:
what was checked, what came back, what was decided, and why. One artifact,
both audiences. `scripts/show_trace.py` renders it as prose.

**Model narration does not consume the action budget.** `ToolSession.note`
records model turns, retries and gate verdicts into the trajectory without
counting against `max_steps`. The budget exists to bound *actions against the
ledger*, not thinking.

**Every gated policy logs the gate identically.** `safety.review_and_record` is
the single path through which the gate is applied, so a trajectory carries the
same evidence whichever proposer produced it. This was not true at first — the
advanced policy was the one policy whose vetoes left no audit trail, which is
the worst possible place for that gap ([`CHANGELOG.md` §11](CHANGELOG.md)).

**Cassettes make a model run reproducible — in principle here, since none are
shipped.** Every live response is recorded, keyed by a SHA-256 of the exact
request, so a tape replays offline with no API key and reproduces its scorecard
exactly. A replay miss is a hard error rather than a fallback: if the prompt
changed, the recording no longer describes the system being measured, and
quietly substituting an answer would be the most misleading thing this code
could do. `cassettes/` is empty in this submission for the reason in
[`CHANGELOG.md` §9](CHANGELOG.md), and nothing in the published results depends
on it.
