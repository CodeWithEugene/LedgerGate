# LedgerGate — operator interface

The evaluation harness in the parent directory answers "does the safety gate
work". This answers a different question: **what does it look like to work
next to one?**

Nobody doing cash application is going to run `make`. Dana opens a queue,
reads why the agent stopped, and either signs it off or picks up the phone.
This is that queue.

## Running it

Two processes. The engine is Python and has no dependencies; the interface is
Next.js and has plenty.

```bash
make web-install     # once — needs Node 20+
make web-api         # terminal 1 — the engine, on :8787
make web             # terminal 2 — the interface, on :3400
```

Then open <http://localhost:3400>. If the interface loads but every page says
the engine is not responding, `make web-api` is not running.

## The two namespaces, and why they are separate

The engine exposes `/api/ops/` and `/api/eval/`, and the split is a design
constraint rather than a filing convention.

`data/*/truth.json` labels every receipt in the corpus. It exists so the
verifier can grade a policy. **A real deployment has no such file** — if it
did, there would be nothing to automate. So every screen an analyst touches is
built strictly from what the system could know without it: the bank file, the
invoice register, the agent's own trajectory, and the ledger's state.

Ground truth appears in exactly one place, the Evaluation section, which is
labelled as the reviewer's view. `tests/test_webapi.py` enforces the boundary
by stripping the labels out of the corpus and requiring every operator payload
to come back byte-identical.

## User flows

| Flow | Where | What it demonstrates |
| --- | --- | --- |
| Triage the morning file | `/` | 60 receipts split into posted, awaiting approval, and needs review. |
| Understand a decision | `/receipts/[id]` | The agent's investigation as a readable timeline, each tool call in plain English with the raw record one click away. |
| Work the escalations | `/review` | Withheld items lead with the veto and the clause, so the analyst starts from a position rather than from nothing. |
| Sign off a large posting | `/approvals` | Dual authorisation. The ledger refuses any approval that does not name a human. |
| Look up the rule | `/procedure` | AP-07, addressable by clause. Every citation in the system links here. |
| Audit the gate | `/evaluation` | The proposer quality curve, the scorecard, and every intervention checked against the label. |

The proposer selector in the header changes which agent processed the file.
Switch it from `guarded` to `reckless` and the wrong-payment count in the
Evaluation tab goes from 0 to 45; switch to `reckless+gate` and it returns to
0 while the queue fills up instead. That is the project's central claim, made
operable rather than tabulated.

## What this interface deliberately cannot do

Resolving an escalation **records** the analyst's disposition; it does not post
it. Letting the UI write an allocation would create a path to the ledger that
the safety gate never reviewed, which is the exact failure the rest of the
project is built to prevent. The honest version re-runs the proposal through
the gate with the analyst's invoice pinned — real work, written up as a
limitation rather than faked here.

Approvals do go through, because they go through `SandboxLedger.approve`,
which raises unless the caller declares a human. The web layer has no
privileged path.

## Stack

Next.js (App Router) with TypeScript, Tailwind, and
[shadcn/ui](https://ui.shadcn.com/). Components are vendored into
`src/components/ui/`, so they are readable and editable rather than a black
box. `src/hooks/use-mobile.ts` is rewritten from the shadcn default, which set
state inside an effect and failed lint.

State is deliberately plain: `useEngine` is thirty lines around `fetch`. The
whole surface is a handful of endpoints against a local server holding sixty
receipts, and a cache layer would be complexity borrowed against no benefit.
