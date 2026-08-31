#!/usr/bin/env python3
"""Export the coding-agent sessions that produced this repository, redacted.

The challenge asks for the trajectories of every agent involved. There are two
kinds here and both are shipped:

* the **runtime** agent, whose trajectories are a product artifact written by
  ``ledgergate.runtime`` into ``traces/``;
* the **coding** agent that built the repository, whose session transcripts
  this script copies out of the local IDE store into ``docs/agent-sessions/``.

Redaction is deliberately paranoid and runs on every line: it is far better to
over-redact a session log than to leak a credential into a public repository.
Anything that survives is either prose or a command that was safe to print.

    python3 scripts/export_agent_sessions.py [--check]

``--check`` verifies the committed exports contain no secret-shaped strings and
exits non-zero if they do. It runs in the test suite.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "agent-sessions"

SOURCE_DIRS = [
    Path.home() / ".cursor" / "projects"
    / "Users-eugenius-Life-Frontier-Engineering-Challenge-2026" / "agent-transcripts",
]

REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "sk-REDACTED"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer REDACTED"),
    (re.compile(r"(?i)(ANTHROPIC_AUTH_TOKEN|ANTHROPIC_API_KEY|OPENAI_API_KEY|"
                r"GEMINI_API_KEY|GROQ_API_KEY)\s*[=:]\s*\S+"), r"\1=REDACTED"),
    (re.compile(r"(?i)\"(api[_-]?key|auth[_-]?token|password|secret)\"\s*:\s*\"[^\"]+\""),
     r'"\1": "REDACTED"'),
    (re.compile(r"(?i)\b(x-api-key|authorization)\b\s*:\s*\S+"), r"\1: REDACTED"),
]

#: Patterns that must not survive redaction. Checked by --check and by a test.
FORBIDDEN = [
    re.compile(r"sk-(?!REDACTED)[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)bearer\s+(?!REDACTED)[A-Za-z0-9._\-]{16,}"),
]


def redact(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def find_sources() -> list[Path]:
    found: list[Path] = []
    for directory in SOURCE_DIRS:
        if directory.exists():
            found.extend(sorted(directory.rglob("*.jsonl")))
    return found


def export() -> int:
    sources = find_sources()
    if not sources:
        print("no local agent transcripts found; nothing to export", file=sys.stderr)
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, object]] = []

    for source in sources:
        cleaned_lines: list[str] = []
        turns = 0
        for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
            cleaned = redact(line)
            cleaned_lines.append(cleaned)
            try:
                if json.loads(cleaned).get("role") in ("user", "assistant"):
                    turns += 1
            except (json.JSONDecodeError, AttributeError):
                pass

        destination = OUTPUT_DIR / source.name
        destination.write_text("\n".join(cleaned_lines) + "\n", encoding="utf-8")
        index.append({
            "file": destination.name,
            "lines": len(cleaned_lines),
            "conversation_turns": turns,
            "bytes": destination.stat().st_size,
        })
        print(f"exported {destination.relative_to(REPO_ROOT)} "
              f"({len(cleaned_lines)} lines, {turns} turns)")

    (OUTPUT_DIR / "index.json").write_text(
        json.dumps({"sessions": index}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


def check() -> int:
    if not OUTPUT_DIR.exists():
        print("no exported sessions to check", file=sys.stderr)
        return 0
    problems = []
    for path in OUTPUT_DIR.glob("*.jsonl"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in FORBIDDEN:
            for match in pattern.findall(text):
                problems.append(f"{path.name}: {str(match)[:24]}...")
    if problems:
        print("SECRET-SHAPED STRINGS SURVIVED REDACTION:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"checked {len(list(OUTPUT_DIR.glob('*.jsonl')))} exported session(s): clean")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify exports are clean")
    args = parser.parse_args()
    return check() if args.check else export()


if __name__ == "__main__":
    sys.exit(main())
