# Cassettes

This directory is intentionally empty.

It is where `src/ledgergate/llm/cassette.py` writes recorded model responses,
keyed by a SHA-256 of the exact request, so that a language-model run can be
replayed offline and reproduce a scorecard byte for byte.

**No recordings are shipped with this submission.** The only model endpoint
available to me rejects any client that does not misrepresent itself as a
first-party tool, and a recording obtained that way is not evidence. The run
was killed and its output discarded. The reasoning is in
[`../docs/CHANGELOG.md` §9](../docs/CHANGELOG.md) and
[`../docs/PROBLEM.md` §6](../docs/PROBLEM.md).

Nothing in the published results depends on this directory. `make verify` is
entirely deterministic and offline, and the seven tests in
`tests/test_cassette_integrity.py` skip when it is empty.

To populate it with your own credential:

```bash
export ANTHROPIC_API_KEY=...   # valid for whatever ANTHROPIC_BASE_URL points at
make record-llm                # ~20 min, ~370 requests, a few USD
make headline-llm              # the published table, with the model rows added
```

The client identifies itself honestly as `ledgergate/<version>` and that is not
configurable. If an endpoint refuses an honest client, this project does not
record against it.
