"""Integrity checks on the submission itself.

Two things a reviewer should not have to take on trust: that the repository
contains no credentials, and that the numbers printed in the README are the
numbers the code actually produces. Both are asserted here.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS = REPO_ROOT / "results"

HEADLINE_BEGIN = "<!-- BEGIN HEADLINE -->"
HEADLINE_END = "<!-- END HEADLINE -->"

SECRET_PATTERNS = [
    re.compile(r"sk-(?!REDACTED)[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(api[_-]?key|auth[_-]?token|client[_-]?secret)\s*[=:]\s*"
               r"[\"']?[A-Za-z0-9_\-]{20,}"),
]

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache"}


def tracked_files() -> list[Path]:
    """Prefer git's view; fall back to a walk where git is unavailable.

    The verification container has no git binary, and the scan must still run
    there -- that is precisely the environment a reviewer sees.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        )
        if out.returncode == 0 and out.stdout.strip():
            return [
                REPO_ROOT / line
                for line in out.stdout.splitlines()
                if (REPO_ROOT / line).is_file()
            ]
    except (FileNotFoundError, OSError):
        pass
    return [
        p for p in REPO_ROOT.rglob("*")
        if p.is_file() and not any(part in SKIP_DIRS for part in p.parts)
    ]


def test_no_credentials_anywhere_in_the_repository():
    offenders: list[str] = []
    for path in tracked_files():
        if path.suffix in (".png", ".jpg", ".gif", ".pdf", ".mp4", ".zip"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern.pattern[:36]}")
    assert offenders == [], offenders


def test_exported_agent_sessions_are_redacted():
    script = REPO_ROOT / "scripts" / "export_agent_sessions.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "relative",
    [
        "README.md",
        "Makefile",
        "Dockerfile",
        "pyproject.toml",
        "requirements-dev.txt",
        "docs/PROBLEM.md",
        "docs/ARCHITECTURE.md",
        "docs/REPRODUCTION.md",
        "docs/CHANGELOG.md",
        "docs/AGENTS.md",
        "docs/VIDEO_SCRIPT.md",
    ],
)
def test_the_submission_package_is_complete(relative):
    path = REPO_ROOT / relative
    assert path.exists(), f"{relative} is missing"
    assert path.stat().st_size > 120, f"{relative} is a stub"


def _documented_commands(doc: Path, pattern: str) -> set[str]:
    """Extract command invocations from inline code and fenced blocks only.

    Markdown prose and shell commands share a vocabulary, so scanning the raw
    text finds "make proposers smarter" and reports it as a missing target.
    """
    text = doc.read_text(encoding="utf-8")
    fragments: list[str] = re.findall(r"`([^`\n]+)`", text)

    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            fragments.append(line)

    found: set[str] = set()
    for fragment in fragments:
        # Strip a leading shell prompt or comment marker, then require the
        # command to start the fragment.
        candidate = fragment.strip().lstrip("$ ").strip()
        match = re.match(pattern, candidate)
        if match:
            found.add(match.group(1))
    return found


def test_every_make_target_the_docs_promise_actually_exists():
    """Documentation drift, caught mechanically.

    Prose has no test suite, which is the one place this project's own agent
    disclosure admits automation cannot help. It can help a little: a command
    printed in a document is a checkable claim, and a reviewer who types
    `make something` from the README and gets `No rule to make target` has
    already stopped believing the rest of it.
    """
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    defined = set(re.findall(r"^([a-z][a-z0-9-]*):", makefile, re.MULTILINE))
    assert "verify" in defined, "sanity: the Makefile did not parse as expected"

    # Only invocations the reader would actually type: inside inline code, or
    # on their own line in a fenced block. Prose like "make proposers smarter"
    # is not a promise.
    promised: dict[str, set[str]] = {}
    for doc in [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").glob("*.md"))]:
        for target in _documented_commands(doc, r"make ([a-z][a-z0-9-]*)"):
            promised.setdefault(target, set()).add(doc.name)

    assert promised, "sanity: no make invocations found in the docs at all"
    missing = {t: sorted(v) for t, v in promised.items() if t not in defined}
    assert not missing, f"documented make targets that do not exist: {missing}"


def test_every_cli_subcommand_the_docs_promise_actually_exists():
    """Same argument, for the CLI a reviewer might drive directly."""
    from ledgergate.cli import build_parser

    actions = [
        a for a in build_parser()._subparsers._group_actions  # noqa: SLF001
        if hasattr(a, "choices")
    ]
    defined = set(actions[0].choices)

    promised: dict[str, set[str]] = {}
    for doc in [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").glob("*.md"))]:
        for cmd in _documented_commands(
            doc, r"(?:\S*python\S*\s+-m\s+)?ledgergate(?:\.cli)?\s+([a-z][a-z0-9-]*)"
        ):
            promised.setdefault(cmd, set()).add(doc.name)

    assert promised, "sanity: no ledgergate invocations found in the docs at all"
    missing = {c: sorted(v) for c, v in promised.items() if c not in defined}
    assert not missing, f"documented CLI subcommands that do not exist: {missing}"


def test_the_committed_corpus_is_present_and_hashed():
    for split in ("dev", "holdout"):
        directory = REPO_ROOT / "data" / split
        manifest = json.loads((directory / "manifest.json").read_text())
        assert set(manifest["sha256"]) == {
            "invoices.json", "payments.json", "opening_ledger.json", "truth.json"
        }
        for name in manifest["sha256"]:
            assert (directory / name).exists()


@pytest.mark.skipif(
    not (RESULTS / "headline.holdout.md").exists(),
    reason="headline not generated yet; run 'make headline'",
)
def test_the_readme_headline_matches_the_generated_results():
    """A published number that nobody regenerated is a claim, not a result."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert HEADLINE_BEGIN in readme and HEADLINE_END in readme

    embedded = readme.split(HEADLINE_BEGIN, 1)[1].split(HEADLINE_END, 1)[0]
    embedded = embedded.replace("```", "").strip()

    generated = (RESULTS / "headline.holdout.md").read_text(encoding="utf-8").strip()
    assert embedded == generated, (
        "the README headline block has drifted from results/headline.holdout.md; "
        "re-run 'make headline' and paste the output back in"
    )


@pytest.mark.skipif(
    not (RESULTS / "guarded.holdout.json").exists(),
    reason="results not generated yet; run 'make verify'",
)
@pytest.mark.parametrize("policy", ["baseline", "guarded", "rules-only"])
def test_committed_deterministic_results_are_reproducible(policy):
    """Re-run the policy now and confirm the committed scorecard still holds."""
    from ledgergate.evaluation.verifier import score
    from ledgergate.runtime import run_policy
    from ledgergate.store import load_corpus

    from conftest import DATA_ROOT

    committed = json.loads((RESULTS / f"{policy}.holdout.json").read_text())
    corpus = load_corpus(DATA_ROOT, "holdout")

    if policy == "baseline":
        from ledgergate.policies.baseline import BaselinePolicy
        instance = BaselinePolicy()
    else:
        from ledgergate.policies.guarded import GuardedPolicy
        instance = GuardedPolicy(use_gate=(policy == "guarded"))

    decisions = run_policy(instance, corpus, max_steps_per_payment=40).decisions
    fresh = score(policy, corpus, decisions)

    assert fresh.net_value == committed["headline"]["net_value"]
    assert fresh.false_pay_count == committed["headline"]["false_pay_count"]
    assert fresh.counts == {k: committed["counts"][k] for k in fresh.counts}
    assert fresh.verifier_sha256 == committed["verifier_sha256"], (
        "the verifier changed after these results were published"
    )
