# Contributing

This repository is a submission to the micro1 Frontier Engineering Challenge
2026, written in a single sprint. While judging is open I am not looking for
feature work — but corrections, failing tests, and counterexamples are very
welcome, and two kinds of contribution are worth more to me than any refactor.

## The two most useful things you could send

**1. A hazard class I did not think of.** The project's stated main failure
mode is that a gate can only veto what somebody enumerated. The holdout split
resamples my own generator, so it demonstrates robustness to different *values*
and proves nothing about robustness to a different *taxonomy*. A receipt shape
that is realistic in a real AP function, that `AP-07.9` does not cover, and
that the gate therefore waves through, is the most valuable thing in this list.

**2. A counterexample to one of the two central properties.** Soundness — the
gate never blocks a posting the proposer had right — and sufficiency — no
unsafe proposal survives it — are asserted in `tests/test_safety.py` against
every proposer, including a deliberately reckless one. If either is false, the
headline finding is wrong, and I would rather know than not.

Both are best expressed as a failing test.

## Getting set up

```bash
make setup
make verify
```

`make verify` is the entire gate: corpus hash audit, the test suite, the
baseline and advanced evaluations, the headline table, and the gate audit. It
runs offline, needs no API key, and takes a few seconds. If it is not green
before you have changed anything, that is itself a bug worth reporting.

## Five invariants

Changes are judged against these before anything else.

**1. Zero runtime dependencies.** Everything, including the HTTP client for the
model API, is Python standard library. `pytest` is the only development
dependency. A reviewer in a clean container must never be blocked waiting for a
wheel to build for their interpreter.

**2. Reproduction is byte-identical.** Committed artifacts must come back
identical on any machine — no timestamps, no wall-clock times, no hostnames, no
absolute paths. This is enforced, not encouraged: trajectories are compared
byte for byte, and `results/` and `traces/` are scanned for machine-dependent
values. Note that wall-clock time is *deliberately* absent from committed
output while still printing on the terminal.

**3. The gate stays monotone, and stays small.** `src/ledgergate/safety.py` may
only turn a `MATCH` into an `ABSTAIN`. It may never choose a different invoice,
alter an allocation, or create a match. Every veto cites the clause it
enforces. Its line count is asserted by a test, because a gate a domain expert
cannot read in one sitting is not a gate anyone can trust — and reviewability
claims that nothing enforces stop being true the first time someone is busy.

**4. Policies never see ground truth.** `truth.json` is reachable only from the
store and the verifier, and this is checked structurally by walking the AST
rather than by grepping. No tool may return a hazard label.

**5. The verifier is frozen and hashes itself.** Every scorecard carries the
verifier's SHA-256. Changing the scoring rules invalidates every published
number by design — see below.

## If you change the verifier

The friction is intentional. `test_committed_deterministic_results_are_reproducible`
fails as soon as the verifier's hash moves, because results scored under one
set of rules and published beside code implementing another are not results.
Regenerate everything and commit it with your change:

```bash
make eval-baseline eval-advanced headline ablation sync-readme
make verify
```

A verifier change whose diff does not also touch `results/` and `traces/` is a
change nobody re-scored under.

## Write the claim as a test

This is the repository's main convention and it was learned the hard way — see
[`docs/CHANGELOG.md`](docs/CHANGELOG.md) §12–§17, which is six consecutive
entries about the same mistake, the last of which is two false claims written
into `SECURITY.md` immediately after concluding that prose is the problem. Every number here is produced by running
something. Every *sentence beside* a number was produced by me. Only the second
could rot silently while the suite stayed green, which made prose the untested
surface of the codebase, and also most of what a reviewer reads.

So:

| If you add | Then |
|---|---|
| a number in prose | add a test that recomputes it |
| a `make` target or CLI subcommand in prose | nothing — existing tests check every documented command exists |
| a `§N` cross-reference | nothing — existing tests check it resolves |
| a property you believe holds | assert the property, not one happy-path example of it |
| a new document | add it to `prose_documents()` in `tests/test_submission.py`, so its claims are checked like every other document's |

Prefer tests that would have caught the bug over tests that describe the fix.
Several tests here passed throughout the failure they were meant to prevent,
because they compared the fields I had thought to check.

## Changelog discipline

[`docs/CHANGELOG.md`](docs/CHANGELOG.md) labels every entry as either a **design
decision** (chose X over Y, and here is the reasoning) or an **iteration**
(measured X, it was wrong, changed it, and here is the evidence). Conflating
the two turns a record of what happened into a record of what would have been
clever, which is the failure mode of most engineering write-ups.

If your change is evidence-driven, include the evidence, and include the number
as it was *before*.

## Style

- Comments explain constraints the code cannot express. They do not narrate
  what the next line does, and they never explain the change to a reviewer.
- Money is integer cents throughout. `safe_compute` rejects a float literal
  outright; do not route around it. A rounding artefact and a real short
  payment must never be confusable.
- Test names are sentences describing the claim —
  `test_the_gate_never_blocks_a_posting_the_proposer_had_right`, not
  `test_gate_5`. The suite doubles as the specification.
- No emoji, in code, docs, or commit messages.

## Before opening a pull request

- [ ] `make verify` is green
- [ ] `make docker-verify` is green — the container must never run a weaker
      suite than your laptop, and a skipped test prints as a pass
- [ ] `git status` is clean afterwards
- [ ] a changelog entry, labelled decision or iteration
- [ ] no credential in any diff, and nothing in
      [`SECURITY.md`](SECURITY.md) that should have been an email instead
