"""Async LLM boundary: concurrent client, retry, and the provider-pool /
rate-limiter scaffold used by the async orchestration engine.

This is the throughput sibling of the synchronous `llm.py`. The sync engine is
retained as the unit-tested, offline mock/reference path; the async engine here
is the real-provider production path (Steps ②–⑥ of the parallelisation plan,
WORKING.md §15).

Design locks (must match `llm.py` for reproducibility):
- `AsyncRetryPolicy` reproduces `RetryPolicy` exactly: `max_attempts` attempts,
  2/4/8s backoff, one code path for transport/rate-limit/API/parse failures
  (M03 lock). Only difference: it `await asyncio.sleep(...)` instead of blocking.
- `AsyncOpenAICompatClient` mirrors `OpenAICompatClient` header/body assembly
  (OpenRouter referer/title/cache headers, provider-routing pins) so the wire
  request is byte-identical across sync and async paths.
- SDK auto-retries stay disabled (`max_retries=0`): the thesis retry policy owns
  all attempts.

Provider switching (⑤) and adaptive rate limiting (⑥) are wired here but ship
with a single endpoint today; multi-provider fan-out is a config-only extension
(see `ProviderPool.from_specs` / WORKING.md §15 "Providers later").
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol, Sequence, runtime_checkable

from openai import AsyncOpenAI, RateLimitError

from convention_topology.llm import (
    OPENROUTER_CACHE_HEADER,
    OPENROUTER_REFERER,
    OPENROUTER_TITLE,
    LLMResponse,
    RunFailedError,
)


@runtime_checkable
class AsyncLLMClient(Protocol):
    async def complete(self, system: str, user: str) -> LLMResponse: ...


# --------------------------------------------------------------------------- #
# ② Async retry policy — exact async twin of llm.RetryPolicy
# --------------------------------------------------------------------------- #
@dataclass
class AsyncRetryPolicy:
    """`max_attempts` attempts with 2/4/8s backoff; awaits instead of blocking.

    `sleep` is injected (async callable) so tests never wait for real backoff.
    Semantics are identical to `llm.RetryPolicy` (M03 lock).
    """

    max_attempts: int = 3
    backoff_seconds: tuple[float, ...] = (2.0, 4.0, 8.0)
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    retry_on: tuple[type[Exception], ...] = (Exception,)

    async def run(
        self,
        operation: Callable[[], Awaitable[str]],
        on_attempt: Callable[[int, Exception | None], None] | None = None,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = await operation()
            except self.retry_on as exc:
                last_error = exc
                if on_attempt is not None:
                    on_attempt(attempt, exc)
                backoff_index = min(attempt - 1, len(self.backoff_seconds) - 1)
                await self.sleep(self.backoff_seconds[backoff_index])
                continue
            else:
                if on_attempt is not None:
                    on_attempt(attempt, None)
                return result
        raise RunFailedError(f"Exhausted {self.max_attempts} attempts") from last_error


# --------------------------------------------------------------------------- #
# ⑥ Adaptive rate limiter — global concurrency ceiling + Retry-After cooldown
# --------------------------------------------------------------------------- #
class RateLimiter:
    """Bounds total in-flight API calls across *all* runs and honours cooldowns.

    `max_concurrency` is the measured provider ceiling (Step ①). `pause(sec)`
    lets a caller propagate a `Retry-After` header so every worker backs off
    together instead of hammering a limited endpoint. A `max_concurrency<=0`
    limiter is unbounded (used for the offline mock path).
    """

    def __init__(self, max_concurrency: int):
        self._semaphore = asyncio.Semaphore(max_concurrency) if max_concurrency > 0 else None
        self._resume_at = 0.0
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "RateLimiter":
        # Respect any global cooldown before consuming a concurrency slot.
        while True:
            async with self._lock:
                wait = self._resume_at - time.monotonic()
            if wait <= 0:
                break
            await asyncio.sleep(wait)
        if self._semaphore is not None:
            await self._semaphore.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._semaphore is not None:
            self._semaphore.release()

    async def pause(self, seconds: float) -> None:
        """Delay all future acquisitions by `seconds` (Retry-After propagation)."""
        async with self._lock:
            self._resume_at = max(self._resume_at, time.monotonic() + seconds)


# --------------------------------------------------------------------------- #
# ② Async OpenAI-compatible client — one per model backend / endpoint
# --------------------------------------------------------------------------- #
class AsyncOpenAICompatClient:
    """Async twin of `llm.OpenAICompatClient` (one endpoint = one backend).

    Wire assembly is identical to the sync client so runs are reproducible
    regardless of engine. Rate limiting is external (`ProviderPool` owns the
    shared `RateLimiter`), keeping this object a thin transport.
    """

    def __init__(
        self,
        base_url: str,
        model_id: str,
        api_key_env: str,
        *,
        api_key: str | None = None,
        temperature: float = 0.5,
        max_tokens: int = 512,
        timeout: float = 120.0,
        openrouter_provider: dict | None = None,
    ):
        key = api_key if api_key is not None else os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(f"Missing env var {api_key_env} for model {model_id}")
        self._client = AsyncOpenAI(
            api_key=key,
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

    async def complete(self, system: str, user: str) -> LLMResponse:
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
                "X-OpenRouter-Cache": OPENROUTER_CACHE_HEADER,
            }
        if self._openrouter_provider is not None:
            kwargs["extra_body"] = {"provider": self._openrouter_provider}
        response = await self._client.chat.completions.create(**kwargs)
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


# --------------------------------------------------------------------------- #
# ⑤ Provider pool — round-robin across endpoints with 429 cooldown/failover
# --------------------------------------------------------------------------- #
@dataclass
class _Endpoint:
    client: AsyncLLMClient
    name: str
    cooldown_until: float = field(default=0.0)


class RateLimitedError(Exception):
    """Endpoint-level 429/quota signal; carries an optional Retry-After hint."""

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after_seconds(exc: Exception, *, default: float = 5.0) -> float:
    """Best-effort Retry-After (seconds) from a pool or SDK rate-limit error.

    Prefers an explicit ``retry_after`` attribute (our `RateLimitedError`), then
    the ``Retry-After`` response header the OpenAI SDK exposes on
    `openai.RateLimitError`, else a conservative default so a global cooldown is
    always applied on a 429.
    """
    hint = getattr(exc, "retry_after", None)
    if hint is not None:
        try:
            return max(0.0, float(hint))
        except (TypeError, ValueError):
            pass
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        raw = headers.get("retry-after")
        if raw is not None:
            try:
                return max(0.0, float(raw))
            except (TypeError, ValueError):
                pass
    return default


class ProviderPool:
    """One `AsyncLLMClient` facade over N interchangeable endpoints (same model).

    Today N=1 (single key/provider). When more keys/providers for the *same
    model weights* are added (Step ⑤, config-only), each call picks the next
    endpoint that is not cooling down; a `RateLimitedError` marks its endpoint
    on cooldown and re-raises so `AsyncRetryPolicy` retries on a sibling.

    Guardrail: every endpoint in a pool must serve the *same model identity*.
    Mixing model weights inside one pool would break run-level model provenance
    (Methods lock) and is a caller error, not enforced here.
    """

    def __init__(self, endpoints: Sequence[AsyncLLMClient], *, rate_limiter: RateLimiter, names: Sequence[str] | None = None):
        if not endpoints:
            raise ValueError("ProviderPool requires at least one endpoint")
        labels = list(names) if names is not None else [f"endpoint{i}" for i in range(len(endpoints))]
        self._endpoints = [_Endpoint(client=c, name=n) for c, n in zip(endpoints, labels)]
        self._rate_limiter = rate_limiter
        self._cursor = 0
        self._lock = asyncio.Lock()

    @property
    def model_id(self) -> str:
        first = self._endpoints[0].client
        return getattr(first, "model_id", "unknown")

    async def _next_endpoint(self) -> _Endpoint:
        async with self._lock:
            n = len(self._endpoints)
            now = time.monotonic()
            # Prefer an endpoint that is not cooling down; rotate the cursor.
            for offset in range(n):
                cand = self._endpoints[(self._cursor + offset) % n]
                if cand.cooldown_until <= now:
                    self._cursor = (self._cursor + offset + 1) % n
                    return cand
            # All cooling: pick the one that frees up soonest.
            return min(self._endpoints, key=lambda e: e.cooldown_until)

    async def complete(self, system: str, user: str) -> LLMResponse:
        endpoint = await self._next_endpoint()
        async with self._rate_limiter:
            try:
                return await endpoint.client.complete(system, user)
            except (RateLimitedError, RateLimitError) as exc:
                # Both the pool's synthetic 429 and the OpenAI SDK's real
                # RateLimitError take the same path: cool this endpoint down and
                # pause *all* workers (Retry-After) so a live 429 throttles the
                # whole loop instead of every worker retrying into the wall (⑥).
                cooldown = _retry_after_seconds(exc)
                endpoint.cooldown_until = time.monotonic() + cooldown
                await self._rate_limiter.pause(cooldown)
                raise


# --------------------------------------------------------------------------- #
# Mock adapter — keep the sync mock (llm.MockLLMClient) for the async path
# --------------------------------------------------------------------------- #
class AsyncClientAdapter:
    """Awaitable wrapper over a synchronous `LLMClient` (e.g. `MockLLMClient`).

    The wrapped `complete` runs to completion with no intervening `await`, so
    under `asyncio.gather` two calls resolve in submission order — preserving
    the mock's RNG draw order and byte-identical outcomes vs. the sync engine
    (async↔sync determinism test, `tests/test_async_run_integration.py`).
    """

    def __init__(self, sync_client):
        self._sync = sync_client

    @property
    def model_id(self) -> str:
        return getattr(self._sync, "model_id", "mock")

    @property
    def call_count(self) -> int:
        return getattr(self._sync, "call_count", 0)

    async def complete(self, system: str, user: str) -> LLMResponse:
        return self._sync.complete(system, user)
