# Reproduction guide

Written for someone starting from a clean machine with nothing installed but
Docker, or nothing installed but Python.

**Every published number in this repository reproduces offline, with no API
key and no network access, in a few seconds.** Nothing in the reproduction path
spends money.

Stronger than that, and worth checking rather than believing: a fresh clone
that runs the whole thing leaves **`git status` empty**. Every committed
scorecard and every committed trajectory comes back byte for byte.

```bash
git clone <this repo> /tmp/check && cd /tmp/check
make setup && make verify && make ablation
git status --short          # prints nothing
```

That is only true because wall-clock timing is deliberately kept out of every
committed artifact — it is a property of your machine, not of the policy. The
headline table reports **tool steps** instead, which reproduce anywhere. Timing
still prints on the terminal when you run a single evaluation.

This is enforced, not remembered: three tests re-run policies and compare
trajectories byte for byte, and a fourth scans `results/` and `traces/` for
machine-dependent values. That fourth test exists because the byte-equality
tests alone passed while the repository was still fragile — the timing column
rounded to `0.0s` on the development laptop and would have rendered `0.1s` on a
host three times slower. See [`CHANGELOG.md` §15](CHANGELOG.md).

**Verified across architectures, not just across runs.** The artifacts hash
identically on an arm64 host and inside an emulated `linux/amd64` container —
a machine slow enough that it does report `wall=0.1s` on the terminal:

```bash
docker build --platform linux/amd64 -t ledgergate:amd64 .
docker run --rm --network none --platform linux/amd64 ledgergate:amd64 sh -c '
  python -m ledgergate.cli compare --corpus holdout --policies \
    reckless reckless+gate baseline baseline+gate rules-only guarded >/dev/null
  sha256sum results/headline.holdout.md traces/guarded.holdout.jsonl'
```

---

## The one command

```bash
docker build -t ledgergate:verify .
docker run --rm --network none ledgergate:verify
```

`--network none` physically disconnects the container. It is there so you do
not have to take "runs offline" on trust. The image is `python:3.11-slim`; the
build is the only step that touches the network, and only to pull that base
image and `pytest`.

Expected: the corpus hash audit, 154 tests (147 run, 7 skipped), the baseline scorecard, the
advanced scorecard, the headline comparison, and the gate audit, ending in

```
  OK  corpus intact, tests green, baseline and advanced scored,
      every gate intervention accounted for against ground truth.
```

Or locally, if you prefer:

```bash
make setup     # creates .venv, installs the single pinned test dependency
make verify    # the whole offline gate
```

---

## Environment

| | |
|---|---|
| Python | **3.11 or newer.** Developed on 3.14.7 (macOS/arm64); container is 3.11.14 (Linux). Verified identical results on both. |
| Runtime dependencies | **none.** Standard library only, including the HTTP client. |
| Test dependency | `pytest==9.1.1`, pinned in `requirements-dev.txt`. Not needed to reproduce the results, only to run the tests. |
| Network | not required for any published result |
| API key | not required for any published result |
| Disk | < 5 MB excluding the Docker base image |
| OS | developed on macOS 15 (arm64); verified in Linux containers |

The zero-dependency design is deliberate rather than minimalist. There is no
wheel that can fail to build on your interpreter, and no transitive package
that can drift underneath a number printed in the README.

---

## What `make verify` does, and what each step proves

| Step | Command | What it proves |
|---|---|---|
| 1 | `ledgergate audit` | The committed corpus matches its SHA-256 manifest, and all 9 ground-truth invariants re-derive from the data. If this fails, stop — everything downstream is meaningless. |
| 2 | `pytest` | 154 tests (7 of them skip without cassettes), including the gate's soundness and sufficiency properties, the adversarial probes, and the submission-integrity checks. |
| 3 | `ledgergate run --policy baseline --corpus holdout` | The baseline scorecard. |
| 4 | `ledgergate run --policy guarded --corpus holdout` | The advanced scorecard. |
| 5 | `ledgergate compare --corpus holdout --policies ...` | The comparison table published in the README, plus the cost-model sensitivity sweep. |
| 6 | `ledgergate gate-audit --proposer rules-only` | Every decision the gate changed, the clause each veto cites, and a check against ground truth that the set is exactly the set of would-be wrong payments. Re-asserts monotonicity on that run. |

Individual targets:

```bash
make corpus         # regenerate both splits from their seeds
make audit          # hash + invariant check only
make test           # test suite only
make eval-baseline  # the baseline solution on holdout
make eval-advanced  # the advanced solution on holdout
make headline       # the full comparison table
make gate-audit     # every decision the gate changed, checked against ground truth
make sync-readme    # paste that table back into the README
make ablation       # the same curve on the development split
make approve        # the human approval queue the advanced solution produced
make trace-sample   # one full agent trajectory, rendered as prose
make docker-verify  # the identical gate in a clean container, no network
```

---

## Which data is required

None from you. Both corpus splits are committed under `data/`, with a SHA-256
manifest:

| Path | Contents |
|---|---|
| `data/dev/` | development split, seed `20260828`, 60 receipts |
| `data/holdout/` | holdout split, seed `20260831`, 60 receipts — **all published numbers use this one** |

Each split holds `invoices.json`, `payments.json`, `opening_ledger.json`,
`truth.json` and `manifest.json`. The data is fully synthetic and generated by
`src/ledgergate/corpus.py`; no real supplier, invoice or bank data is involved,
and `tests/test_corpus.py` asserts it.

To regenerate from scratch:

```bash
make corpus && make audit
```

That rewrites both splits from their seeds and re-derives the hash manifest. A
test asserts the committed files are byte-identical to a fresh generation, so a
change to the generator that was not re-committed fails the suite rather than
quietly changing the benchmark.

---

## Expected output

The exact figures live in `results/*.json` and are reproduced in the README.
The properties that must hold on any machine:

- the corpus audit reports `OK` for both splits, with no hash mismatch;
- every test passes (some are skipped — see below — and that is expected);
- the baseline records a **negative** net business value and a double-digit
  false-pay count;
- every `+gate` policy records a **positive** net business value and **zero**
  false pays;
- correct postings needlessly escalated fall monotonically as the proposer
  improves (12, 7, 0);
- `gate-audit` reports 6 interventions against the `rules-only` proposer, all
  of them wrong payments prevented, none of them collateral, and confirms the
  gate created no match and altered no allocation;
- the comparison ordering is unchanged across every false-pay penalty in the
  sensitivity sweep.

**About the skipped tests.** Seven tests in `tests/test_cassette_integrity.py`
skip when `cassettes/` is empty, which it is in this submission. They cover the
optional model-driven arm; see below. Nothing in the headline depends on them.

The container and a local run report **the same** `147 passed, 7 skipped`. That
is checked rather than assumed: a skip prints as success, so an image missing a
directory the suite reads would silently verify less than the author does.
`test_the_container_sees_everything_the_test_suite_reads` compares the
Dockerfile's `COPY` directives against what the tests actually open. If your
container reports a different tally from the one above, something is missing
from the image and the run should not be trusted.

---

## Runtime and cost

Measured on an M-series MacBook Air; the container is comparable.

| Command | Wall time | Cost |
|---|---|---|
| `make setup` | ~8 s (one `pip install`) | free |
| `make test` | ~1.5 s | free |
| `make eval-baseline` | < 0.2 s | free |
| `make eval-advanced` | < 0.2 s | free |
| `make headline` | < 0.3 s | free |
| `make gate-audit` | < 0.2 s | free |
| **`make verify`** | **~4 s** | **free** |
| `docker build` | ~40 s cold, mostly the base-image pull | free |
| `docker run --network none` | ~5 s | free |

There is no paid step in the reproduction path.

---

## The optional model-driven arm

`src/ledgergate/policies/llm.py` implements a full tool-using agent against the
Anthropic Messages API, with content-addressed record/replay cassettes so a
model run can be replayed offline and reproduce a scorecard exactly.

**It is not part of the published results, and `make verify` does not touch
it.** The reason is a service-terms problem rather than a technical one, and it
is documented in full in [`CHANGELOG.md` §9](CHANGELOG.md) and
[`PROBLEM.md`](PROBLEM.md). In short: the only endpoint available to me rejects
any client that does not misrepresent itself as a first-party tool, so the arm
was removed rather than shipped on data obtained that way. The user-agent
override that made that possible has been deleted from the client.

The loop is nonetheless first-class, tested code — 19 tests in
`tests/test_llm_policy.py` exercise it against a scripted model, with no
network and no credential.

If you hold a legitimate credential and want the model rows back:

```bash
export ANTHROPIC_API_KEY=...     # must be valid for ANTHROPIC_BASE_URL
make record-llm                  # ~20 min, ~370 requests, a few USD on a frontier model
make headline-llm                # the same table, with llm and llm-gated rows added
```

`LEDGERGATE_LLM_MODE` selects behaviour:

- `replay` (default) — read the committed cassette, never touch the network. A
  missing entry is a **hard error**, never a silent fallback: if the prompt
  changed, the tape no longer describes the system being measured.
- `record` — call the live model and append to the cassette.
- `live` — call the live model and record nothing.

Cassettes store only responses, keyed by a SHA-256 of the exact request.
Credentials are never written to disk, never logged, and never recorded;
`tests/test_cassette_integrity.py` asserts a committed tape contains no
credential and no ground truth.

---

## Repository map

| Path | Contents |
|---|---|
| `src/ledgergate/` | The system. See [`ARCHITECTURE.md`](ARCHITECTURE.md). |
| `tests/` | Test suite, including the adversarial probes and submission-integrity checks. |
| `data/dev/`, `data/holdout/` | The committed corpora and their hash manifests. |
| `traces/` | Agent trajectories, one JSONL file per policy per split. |
| `results/` | Scorecards, the comparison, and the generated headline block. |
| `docs/agent-sessions/` | Redacted transcripts of the coding agent that built this. |
| `scripts/` | Trace viewer, README sync, cassette recorder, session exporter, `verify.sh`. |

## If something fails

| Symptom | Meaning |
|---|---|
| `HASH MISMATCH` in step 1 | `data/` was edited without regenerating the manifest. Run `make corpus`. |
| `CassetteMiss` | You asked for an `llm` policy with no cassettes. That arm is optional; use `make verify`. |
| README headline test fails | `results/headline.holdout.md` and the README disagree. Run `make sync-readme`. |
| `the verifier changed after these results were published` | Working as designed: every scorecard carries the verifier's SHA-256, and someone edited `verifier.py` without regenerating. As a reviewer, this means the committed numbers were not produced by the code in front of you — treat them as void. As the author, note that `make verify` cannot recover on its own, because it runs the tests *before* the evaluations that would refresh the results. Regenerate first: `make eval-baseline eval-advanced headline ablation sync-readme && make verify`. |
| `make: command not found` in a container | Use `./scripts/verify.sh`, which is what the image runs. |
