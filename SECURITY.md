# Security policy

## What this repository is, and what "security" means for it

LedgerGate is a research artifact: a study of whether a small veto-only gate
can make an untrusted agent safe enough to let near a payment workflow. It is
not deployed software. The ledger in `src/ledgergate/ledger.py` is in-memory
and simulated, nothing here touches a payment rail, the corpus is synthetic and
generated from seeds in this repository, and the whole verification path runs
under `--network none`.

So the usual attack surface — untrusted input, network services, stored data —
is mostly absent. What is *not* absent is the thing the project is actually
about: this repository ships a safety control and makes two falsifiable claims
about it. A way to break either of those claims is the most interesting
security report I could receive, and it is treated as a vulnerability rather
than a feature request.

## Reporting

Email **eugenegabriel.ke@gmail.com**, subject line starting `LedgerGate
security`. Please do not open a public issue for anything in the first table
below.

Useful reports include what you did, what happened, what you expected, and —
ideally — a failing test. This repository's convention is that a claim worth
making is worth asserting, and that applies to claims about its own defects
(see [`CONTRIBUTING.md`](CONTRIBUTING.md)).

I will acknowledge within three working days. There is no bug bounty; this is
a personal project.

## What counts as a vulnerability here

| Class | Why it matters |
|---|---|
| A proposal that `AP-07.9` should veto but the gate passes | **Sufficiency break.** The central claim is that no unsafe proposal survives the gate, for any proposer. |
| The gate altering a decision instead of only vetoing it — changing an allocation, choosing a different invoice, creating a match where the proposer abstained | **Monotonicity break.** The gate's trustworthiness rests entirely on it having exactly one power. |
| Posting at or above the approval threshold without a recorded human | **Control bypass.** `approve()` must raise unless the caller names a human; the system must not be able to release its own queue. |
| A policy reaching `truth.json`, the verifier, or a hazard label through any tool | **Evaluation integrity.** If a policy can see the answer key, every number in the README is meaningless. |
| A committed credential, or a key recoverable from a trace, cassette or exported transcript | Straightforwardly a leak, and one a test is supposed to prevent. |
| Anything that touches the network during `make verify` | The offline guarantee is what makes the results checkable by a stranger. |
| `safe_compute` evaluating anything other than integer arithmetic | The one place an untrusted model's output reaches an evaluator. See the note below — it *does* call `eval`, under an allowlist, and I would rather you knew that from this document than from `grep`. |

## What is deliberately unsafe, and is not a vulnerability

- **The `reckless` policy posts against the first invoice it sees.** It exists
  to be terrible. It is the lower anchor of the proposer-quality curve, and its
  job is to be the worst input the gate must survive.
- **The proposer is untrusted by design.** A proposer that is *wrong* is not a
  bug. A wrong *posting* is. The distinction is the whole architecture.
- **The gate's hazard taxonomy is finite, and it is mine.** A realistic hazard
  that `AP-07.9` does not enumerate will pass the gate. This is the project's
  stated main failure mode, documented in the README, not a defect I am unaware
  of. Please still report new hazard classes — see below, they are the single
  most valuable thing you could send.
- **The corpus models error, not fraud.** See the last section.

## The one evaluator, described honestly

`safe_compute` in `src/ledgergate/tools.py` backs the `compute` tool, which is
the only path from a model's output to anything evaluator-shaped. It is worth
being precise about, because "arithmetic is a tool call" is a claim the README
leans on.

It parses the expression to an AST and walks every node against an allowlist
that contains arithmetic, comparison and literal nodes and nothing else —
notably no `Name`, `Call`, `Attribute` or `Subscript`, so an expression has no
way to *refer* to anything. Constants must be `int` or `bool`; a float literal
is refused outright, because a rounding artefact and a real short payment must
never be confusable. Input is capped at 200 characters.

**It then calls `eval`** on the compiled tree with `__builtins__` stripped:

```python
result = eval(compile(tree, "<compute>", "eval"), {"__builtins__": {}}, {})
```

The allowlist runs first and is what the safety rests on, not the empty
globals. I am flagging it here rather than describing the function as
"sandboxed" and letting you discover the call yourself, which is the sort of
thing that reasonably destroys confidence in every other claim in a document
like this. If you can reach a `Name`, a call, a float, or any object at all
through it, that is a genuine vulnerability and I would like to hear about it
quickly.

## Credentials and secrets

- **No credential is committed**, and `test_no_credentials_anywhere_in_the_repository`
  scans every tracked file on every run. If you find one, that is a genuine
  finding and I would want to know quickly.
- `src/ledgergate/llm/client.py` reads exactly three environment variables and
  no others: `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY` for the credential,
  and `ANTHROPIC_BASE_URL` for the endpoint. Credentials are never written to
  disk and never logged. That list is asserted by
  `test_the_api_client_cannot_be_made_to_misrepresent_itself`, so a new
  environment hook cannot appear unnoticed.
- All three are used solely by `make record-llm`, which is **not** on the
  reproduction path. Reproducing every published number requires no key and no
  network.
- **No cassettes are committed.** If you record your own, they hold model
  responses rather than request headers, but treat them as untrusted output and
  read before committing.
- Exported coding-agent transcripts in `docs/agent-sessions/` are redacted, and
  `scripts/export_agent_sessions.py --check` re-verifies the redaction as part
  of the suite.

## The API client identifies itself honestly, on purpose

Stated here because it was a deliberate decision rather than an accident of
implementation. The Messages API client sends a fixed `User-Agent` of
`ledgergate/0.1 (frontier-engineering-challenge)`, and there is intentionally
**no way to override it**.

An earlier version allowed an override, and I used it to get past a third-party
gateway that rejects any client not presenting itself as first-party tooling.
It worked because it was misrepresenting what it was. I discarded the resulting
data, deleted the override, and dropped the model arm from the published
results. The full account is in [`docs/CHANGELOG.md`](docs/CHANGELOG.md) §9.

If you add a transport, preserve that property. A result obtained by lying
about your client is not evidence.

## If you are deploying anything shaped like this

Not advice so much as the gaps I already know about, offered because the
failure modes are not obvious from the code:

- **The ledger is a simulation.** Its idempotency is an in-memory set. A real
  one needs durable idempotency keys that survive a restart and a replay.
- **Approval is a recorded string.** A real one needs authenticated identity
  and an append-only audit log that the approving system cannot rewrite.
- **The gate enforces a procedure I wrote.** Ported to another AP function,
  `AP-07` is the first thing that must be replaced — not the code around it.
  A gate citing clauses that do not govern your process is worse than none,
  because it reads as though someone checked.
- **Nothing here is hardened against an adversarial supplier.** The corpus
  models mistakes: truncated names, correspondent-bank fees, re-ingested feeds.
  It does not model an attacker. Invoice-redirection fraud — a real supplier's
  bank details replaced by someone else's — is the obvious threat in this
  workflow, it looks exactly like a legitimate first payment to a new account,
  and **it is entirely out of scope here.** A gate tuned to catch reconciliation
  error should not be mistaken for one that catches deception.

## Supported versions

This is a single submission with no release branches. `main` is the only
supported state. Python 3.11 or newer; verified on 3.11 and 3.14.
