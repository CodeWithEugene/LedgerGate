"""Minimal Anthropic-Messages client built on the standard library.

There is no SDK dependency here, and that is a deliberate reproducibility
decision rather than minimalism for its own sake. A judge running this repo in
a clean container should never be blocked by a wheel that has not been built
for their Python version. The wire format is small, stable and easy to read.

Credentials are read from the environment and never written to disk, never
logged, and never recorded into a cassette.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Sequence

DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_MODEL = "claude-opus-5"
ANTHROPIC_VERSION = "2023-06-01"

#: The client identifies itself honestly, and this is not configurable.
#:
#: Some Anthropic-compatible reseller gateways reject any client that does not
#: claim to be a first-party tool. Making the user agent overridable would make
#: it trivially easy to satisfy one of those, which is why the hook was removed
#: rather than left in place with a warning. If an endpoint refuses an honest
#: client, this project does not record against that endpoint. See
#: docs/PROBLEM.md, "The model arm, and why it is not the headline".
USER_AGENT = "ledgergate/0.1 (frontier-engineering-challenge)"

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}


class LLMError(RuntimeError):
    pass


class CassetteMiss(LLMError):
    """A replay run asked for a request that was never recorded."""


@dataclass(slots=True)
class LLMResponse:
    content: list[dict[str, Any]]
    stop_reason: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 1
    replayed: bool = False

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, attempts: int = 1, replayed: bool = False):
        usage = payload.get("usage") or {}
        return cls(
            content=list(payload.get("content") or []),
            stop_reason=str(payload.get("stop_reason") or ""),
            model=str(payload.get("model") or ""),
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            attempts=attempts,
            replayed=replayed,
        )

    def text(self) -> str:
        return "\n".join(
            str(block.get("text", "")) for block in self.content if block.get("type") == "text"
        ).strip()

    def tool_uses(self) -> list[dict[str, Any]]:
        return [block for block in self.content if block.get("type") == "tool_use"]


def canonical_request(
    model: str,
    system: str,
    messages: Sequence[dict[str, Any]],
    tools: Sequence[dict[str, Any]],
    max_tokens: int,
    temperature: float,
) -> str:
    """Stable JSON used as the cassette key. Order-independent, no timestamps."""
    return json.dumps(
        {
            "model": model,
            "system": system,
            "messages": list(messages),
            "tools": list(tools),
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


@dataclass
class AnthropicClient:
    """Live client. Retries transient failures with exponential backoff."""

    model: str = DEFAULT_MODEL
    base_url: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_BASE_URL", DEFAULT_BASE_URL))
    token: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("ANTHROPIC_API_KEY")
        or ""
    )
    timeout: float = 120.0
    max_attempts: int = 4

    def complete(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.token:
            raise LLMError(
                "no API credential found; set ANTHROPIC_API_KEY (or "
                "ANTHROPIC_AUTH_TOKEN), or use a replay policy such as "
                "'llm-gated' which reads the committed cassettes"
            )

        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system,
                "messages": list(messages),
                "tools": list(tools),
            }
        ).encode("utf-8")

        headers = {
            "content-type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
            "authorization": f"Bearer {self.token}",
            "x-api-key": self.token,
            "user-agent": USER_AGENT,
        }

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            request = urllib.request.Request(
                f"{self.base_url.rstrip('/')}/v1/messages", data=body, headers=headers
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                return LLMResponse.from_payload(payload, attempts=attempt)
            except urllib.error.HTTPError as exc:
                detail = exc.read()[:400].decode("utf-8", errors="replace")
                last_error = LLMError(f"HTTP {exc.code}: {detail}")
                if exc.code not in RETRYABLE_STATUS:
                    raise last_error from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = LLMError(f"{type(exc).__name__}: {exc}")

            if attempt < self.max_attempts:
                time.sleep(min(2 ** attempt, 16))

        raise last_error or LLMError("request failed for an unknown reason")
