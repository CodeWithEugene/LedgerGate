"""Record and replay model responses so an agent run is reproducible.

This is the piece that makes the headline numbers checkable. A language model
run is not reproducible by nature: the endpoint may be rate limited, the
weights behind a model alias change, and a reviewer may have no credential at
all. Publishing a number that nobody else can regenerate is not evidence.

So every live call is recorded, keyed by the exact request that produced it,
and the recordings are committed. ``make eval-advanced`` replays them, offline,
with no API key, and reproduces the published scorecard byte for byte. Re-run
with ``LEDGERGATE_LLM_MODE=record`` and a credential to refresh them against
the live model.

A replay miss is a hard error rather than a silent fallback. If the prompt
changed, the cassette no longer describes the system being measured, and
quietly substituting a different answer would be the most misleading thing
this file could do.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence

from .client import CassetteMiss, LLMResponse, canonical_request


class Completer(Protocol):
    model: str

    def complete(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse: ...


def request_key(
    model: str,
    system: str,
    messages: Sequence[dict[str, Any]],
    tools: Sequence[dict[str, Any]],
    max_tokens: int,
    temperature: float,
) -> str:
    canonical = canonical_request(model, system, messages, tools, max_tokens, temperature)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class CassetteClient:
    """Wraps a live client with a durable, content-addressed cache."""

    path: Path
    model: str
    inner: Completer | None = None
    mode: str = "replay"  # "replay" | "record"
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    _dirty: bool = False

    def __post_init__(self) -> None:
        if self.mode not in ("replay", "record"):
            raise ValueError(f"cassette mode must be 'replay' or 'record', got {self.mode!r}")
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.entries = dict(raw.get("entries") or {})
        elif self.mode == "replay":
            raise CassetteMiss(
                f"no cassette at {self.path}. Record one with "
                f"LEDGERGATE_LLM_MODE=record and an API credential, or run a "
                f"deterministic policy such as 'guarded'."
            )

    def complete(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        key = request_key(self.model, system, messages, tools, max_tokens, temperature)
        cached = self.entries.get(key)
        if cached is not None:
            self.hits += 1
            return LLMResponse.from_payload(cached["response"], replayed=True)

        self.misses += 1
        if self.mode == "replay":
            raise CassetteMiss(
                f"cassette {self.path.name} has no entry for this request "
                f"({key[:12]}). The prompt or tool schema changed since it was "
                f"recorded, so the recording no longer describes this system. "
                f"Re-record with LEDGERGATE_LLM_MODE=record."
            )
        if self.inner is None:
            raise CassetteMiss("record mode needs a live client")

        response = self.inner.complete(
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self.entries[key] = {
            "response": {
                "content": response.content,
                "stop_reason": response.stop_reason,
                "model": response.model,
                "usage": {
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                },
            },
            # Stored for human review of the tape. Never includes credentials.
            "request_preview": {
                "model": self.model,
                "last_message": messages[-1] if messages else None,
            },
        }
        self._dirty = True
        # Flush as we go. A recording pass costs real time and real tokens; a
        # crash at receipt 55 of 60 should not throw away the first 54.
        if self.misses % 10 == 0:
            self.save()
        return response

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self.model,
            "entry_count": len(self.entries),
            "entries": self.entries,
        }
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self._dirty = False
