"""LLM boundary: client protocol, response parsing, retry policy, mock backend.

Ashery `run_API.py::query`/`get_response` port (WORKING.md §2, §4): thesis
replaces the infinite-retry HF loop with a bounded 3x `RetryPolicy` and an
OpenAI-compatible chat client (`OpenAICompatClient`, wired in Phase C).
Boundaries return data (`LLMResponse`); parsing/retry are separate,
unit-testable functions (§0 architecture principle 4).
"""

from __future__ import annotations

import os
import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Protocol, Sequence, runtime_checkable

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError


class ParseError(Exception):
    """Raised when parse_label cannot recover exactly one valid option from text."""


class RunFailedError(Exception):
    """Raised when RetryPolicy exhausts all attempts without a successful call."""


@dataclass(frozen=True)
class LLMResponse:
    text: str
    usage: dict
    model_id: str


@runtime_checkable
class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> LLMResponse: ...


_VALUE_FIELD_RE = re.compile(r"['\"]?value['\"]?\s*:\s*['\"]?\s*([^'\",;}\s]+)")


def parse_label(text: str, options: Sequence[str]) -> str:
    """Recover a single option label from raw LLM output.

    Mirrors Ashery's quote-split semantics: (1) structured parse of the
    `'value':` field, (2) fallback match of an option token at a
    quote/word boundary. Zero or >=2 distinct options matched -> ParseError.
    """
    option_set = set(options)

    match = _VALUE_FIELD_RE.search(text)
    if match:
        candidate = match.group(1).strip().strip("'\".")
        if candidate in option_set:
            return candidate

    found = [
        option
        for option in options
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(option)}(?![A-Za-z0-9])", text)
    ]
    distinct = set(found)
    if len(distinct) != 1:
        raise ParseError(f"Could not recover a single option from response: {text!r}")
    return found[0]


@dataclass
class RetryPolicy:
    """Exactly `max_attempts` attempts; exponential backoff between failures.

    M03 lock: timeout, rate limit, HTTP error, or parse failure all retry
    through the same code path. Sleep is injected so tests never wait for
    real backoff.
    """

    max_attempts: int = 3
    backoff_seconds: tuple[float, ...] = (2.0, 4.0, 8.0)
    sleep: Callable[[float], None] = time.sleep
    retry_on: tuple[type[Exception], ...] = (Exception,)

    def run(
        self,
        operation: Callable[[], str],
        on_attempt: Callable[[int, Exception | None], None] | None = None,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = operation()
            except self.retry_on as exc:
                last_error = exc
                if on_attempt is not None:
                    on_attempt(attempt, exc)
                backoff_index = min(attempt - 1, len(self.backoff_seconds) - 1)
                self.sleep(self.backoff_seconds[backoff_index])
                continue
            else:
                if on_attempt is not None:
                    on_attempt(attempt, None)
                return result
        raise RunFailedError(f"Exhausted {self.max_attempts} attempts") from last_error


# Exception classes a `RetryPolicy` should catch when wired to
# `OpenAICompatClient`: transport/rate-limit/API errors plus local parse
# failures (M03 lock: one retry code path for all of them, §4).
OPENAI_RETRY_EXCEPTIONS: tuple[type[Exception], ...] = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    APIError,
    ParseError,
)


OPENROUTER_REFERER = "https://github.com/jannikend99/llm-convention-topology"
OPENROUTER_TITLE = "TUM Master Thesis Naming Game"


class OpenAICompatClient:
    """OpenAI-compatible chat client (`openai` SDK v2) -- one client per model backend.

    Routes open-weight models via OpenRouter; proprietary models via direct
    provider endpoints (OpenAI, Anthropic OpenAI-compat, Google OpenAI-compat).
    SDK auto-retries are disabled (`max_retries=0`): the thesis `RetryPolicy`
    owns all 3x attempts (M03 lock) -- stacking SDK retries breaks the
    2/4/8s backoff semantics.
    """

    def __init__(
        self,
        base_url: str,
        model_id: str,
        api_key_env: str,
        temperature: float = 0.5,
        max_tokens: int = 200,
        timeout: float = 120.0,
        openrouter_provider: dict | None = None,
    ):
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing env var {api_key_env} for model {model_id}")
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/") + "/",
            max_retries=0,
            timeout=timeout,
        )
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url
        self._openrouter_provider = openrouter_provider
        self._is_openrouter = "openrouter.ai" in base_url

    def complete(self, system: str, user: str) -> LLMResponse:
        kwargs: dict = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self._is_openrouter:
            kwargs["extra_headers"] = {
                "HTTP-Referer": OPENROUTER_REFERER,
                "X-OpenRouter-Title": OPENROUTER_TITLE,
            }
        if self._openrouter_provider is not None:
            kwargs["extra_body"] = {"provider": self._openrouter_provider}
        response = self._client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            usage=(
                {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens}
                if usage
                else {}
            ),
            model_id=self.model_id,
        )


_PARTNER_ANSWER_RE = re.compile(r"'Player 2':\s*'([^']*)'")


@dataclass
class MockLLMClient:
    """Deterministic no-network test/dev backend.

    Policies:
    - ``scripted``: replay ``scripted_responses`` in order (wraps around).
    - ``imitate_modal``: answer the modal label of the partner answers the
      caller has observed (parsed from the rendered `user` prompt's
      ``'Player 2'`` fields) -> a hearer-adopts-speaker convergence rule, so
      a mocked population converges. (A self-history-only mode is absorbing
      after one round and does not propagate information across the
      population -- documented deviation for a testable mock backend.)
    - ``always``: always emit ``always_label``.
    - ``random``: uniform random choice among ``options`` -> never converges.
    """

    policy: str
    rng: random.Random
    options: Sequence[str] | None = None
    scripted_responses: Sequence[str] = field(default_factory=tuple)
    always_label: str | None = None
    model_id: str = "mock"
    call_count: int = field(default=0, init=False)
    _scripted_index: int = field(default=0, init=False)

    def complete(self, system: str, user: str) -> LLMResponse:
        self.call_count += 1
        if self.policy == "scripted":
            text = self._next_scripted()
        elif self.policy == "always":
            text = self._format_response(self.always_label)
        elif self.policy == "imitate_modal":
            text = self._format_response(self._imitate_modal(user))
        elif self.policy == "random":
            text = self._format_response(self.rng.choice(list(self.options)))
        else:
            raise ValueError(f"Unknown mock policy: {self.policy}")
        return LLMResponse(text=text, usage={"prompt_tokens": 0, "completion_tokens": 0}, model_id=self.model_id)

    def _next_scripted(self) -> str:
        if not self.scripted_responses:
            raise RuntimeError("scripted policy requires scripted_responses")
        text = self.scripted_responses[self._scripted_index % len(self.scripted_responses)]
        self._scripted_index += 1
        return text

    def _imitate_modal(self, user: str) -> str:
        partner_answers = _PARTNER_ANSWER_RE.findall(user)
        if not partner_answers:
            return self.rng.choice(list(self.options))
        return Counter(partner_answers).most_common(1)[0][0]

    @staticmethod
    def _format_response(label: str | None) -> str:
        return f"{{'value': '{label}'; 'reason': 'mock'}}"
