from __future__ import annotations

import asyncio
import os
import random
import unittest

import httpx
from openai import RateLimitError

from convention_topology.async_llm import (
    AsyncClientAdapter,
    AsyncOpenAICompatClient,
    AsyncRetryPolicy,
    ProviderPool,
    RateLimitedError,
    RateLimiter,
    _retry_after_seconds,
)
from convention_topology.llm import LLMResponse, MockLLMClient, RunFailedError, parse_label

OPTIONS = ["A", "B"]


async def _noop_sleep(_seconds: float) -> None:
    return None


class AsyncRetryPolicyTests(unittest.TestCase):
    def test_succeeds_first_attempt_without_sleeping(self):
        sleeps: list[float] = []

        async def sleeper(s):
            sleeps.append(s)

        async def op():
            return "ok"

        policy = AsyncRetryPolicy(sleep=sleeper)
        self.assertEqual(asyncio.run(policy.run(op)), "ok")
        self.assertEqual(sleeps, [])

    def test_exhausts_three_attempts_then_raises_with_backoff_order(self):
        sleeps: list[float] = []
        attempts: list[int] = []

        async def sleeper(s):
            sleeps.append(s)

        async def always_fails():
            raise ValueError("boom")

        policy = AsyncRetryPolicy(sleep=sleeper)

        async def go():
            with self.assertRaises(RunFailedError):
                await policy.run(always_fails, on_attempt=lambda n, exc: attempts.append(n))

        asyncio.run(go())
        self.assertEqual(attempts, [1, 2, 3])
        self.assertEqual(sleeps, [2.0, 4.0, 8.0])

    def test_recovers_on_second_attempt(self):
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError("transient")
            return "recovered"

        policy = AsyncRetryPolicy(sleep=_noop_sleep)
        self.assertEqual(asyncio.run(policy.run(flaky)), "recovered")


class RateLimiterTests(unittest.TestCase):
    def test_semaphore_bounds_concurrent_holders(self):
        limiter = RateLimiter(2)
        peak = {"now": 0, "max": 0}

        async def worker():
            async with limiter:
                peak["now"] += 1
                peak["max"] = max(peak["max"], peak["now"])
                await asyncio.sleep(0.01)
                peak["now"] -= 1

        async def go():
            await asyncio.gather(*(worker() for _ in range(6)))

        asyncio.run(go())
        self.assertLessEqual(peak["max"], 2)

    def test_zero_is_unbounded(self):
        limiter = RateLimiter(0)

        async def go():
            async with limiter:
                return "ok"

        self.assertEqual(asyncio.run(go()), "ok")


class ProviderPoolTests(unittest.TestCase):
    class _StubEndpoint:
        def __init__(self, label, fail_times=0):
            self.label = label
            self.model_id = "same-model"
            self.calls = 0
            self._fail_times = fail_times

        async def complete(self, system, user):
            self.calls += 1
            if self.calls <= self._fail_times:
                raise RateLimitedError("429", retry_after=0.0)
            return LLMResponse(text=f"{{'value': 'A'}} from {self.label}", usage={}, model_id="same-model")

    def test_round_robins_across_healthy_endpoints(self):
        e0, e1 = self._StubEndpoint("e0"), self._StubEndpoint("e1")
        pool = ProviderPool([e0, e1], rate_limiter=RateLimiter(0), names=["e0", "e1"])

        async def go():
            await pool.complete("s", "u")
            await pool.complete("s", "u")

        asyncio.run(go())
        self.assertEqual(e0.calls, 1)
        self.assertEqual(e1.calls, 1)

    def test_rate_limit_marks_cooldown_and_reraises_for_retry(self):
        # e0 always 429s; a retry policy over the pool must succeed via e1.
        e0 = self._StubEndpoint("e0", fail_times=99)
        e1 = self._StubEndpoint("e1")
        pool = ProviderPool([e0, e1], rate_limiter=RateLimiter(0), names=["e0", "e1"])
        policy = AsyncRetryPolicy(sleep=_noop_sleep, retry_on=(RateLimitedError,))

        async def call():
            return (await pool.complete("s", "u")).text

        result = asyncio.run(policy.run(call))
        self.assertIn("e1", result)
        self.assertGreaterEqual(e0.calls, 1)
        self.assertEqual(e1.calls, 1)


class ProviderPoolSdkRateLimitTests(unittest.TestCase):
    """A *real* SDK 429 (openai.RateLimitError) must take the same cooldown +
    global-pause path as the pool's synthetic RateLimitedError (⑥ live-API lock),
    then re-raise so the retry policy re-attempts."""

    class _SdkLimitEndpoint:
        def __init__(self, label, fail_times):
            self.label = label
            self.model_id = "same-model"
            self.calls = 0
            self._fail_times = fail_times

        async def complete(self, system, user):
            self.calls += 1
            if self.calls <= self._fail_times:
                response = httpx.Response(
                    429, headers={"retry-after": "0"}, request=httpx.Request("POST", "http://x")
                )
                raise RateLimitError("429 Too Many Requests", response=response, body=None)
            return LLMResponse(text="{'value': 'A'}", usage={}, model_id="same-model")

    def test_sdk_rate_limit_pauses_all_workers_then_retries(self):
        endpoint = self._SdkLimitEndpoint("e0", fail_times=1)
        limiter = RateLimiter(0)
        pauses: list[float] = []
        original_pause = limiter.pause

        async def spy_pause(seconds):
            pauses.append(seconds)
            await original_pause(seconds)

        limiter.pause = spy_pause
        pool = ProviderPool([endpoint], rate_limiter=limiter, names=["e0"])
        policy = AsyncRetryPolicy(sleep=_noop_sleep, retry_on=(RateLimitError,))

        async def call():
            return (await pool.complete("s", "u")).text

        result = asyncio.run(policy.run(call))
        self.assertIn("A", result)
        self.assertTrue(pauses, "a global Retry-After pause must be applied on a live 429")
        self.assertGreater(endpoint.cooldown_until if hasattr(endpoint, "cooldown_until") else 0, -1)
        self.assertEqual(endpoint.calls, 2)

    def test_retry_after_seconds_reads_header_and_attr(self):
        # Pool error carries an explicit attribute.
        self.assertEqual(_retry_after_seconds(RateLimitedError("x", retry_after=3.0)), 3.0)
        # SDK error exposes a Retry-After header.
        response = httpx.Response(
            429, headers={"retry-after": "7"}, request=httpx.Request("POST", "http://x")
        )
        sdk_exc = RateLimitError("429", response=response, body=None)
        self.assertEqual(_retry_after_seconds(sdk_exc), 7.0)
        # No hint anywhere → conservative default.
        self.assertEqual(_retry_after_seconds(ValueError("boom"), default=5.0), 5.0)


class AsyncOpenAICompatClientTests(unittest.TestCase):
    ENV_VAR = "TEST_ASYNC_KEY"

    def setUp(self):
        os.environ[self.ENV_VAR] = "sk-fake"
        self.addCleanup(os.environ.pop, self.ENV_VAR, None)

    def test_missing_env_var_raises(self):
        with self.assertRaises(RuntimeError):
            AsyncOpenAICompatClient(base_url="https://example.com/v1", model_id="m", api_key_env="NOPE_XYZ")

    def test_complete_assembles_messages_and_openrouter_headers(self):
        client = AsyncOpenAICompatClient(
            base_url="https://openrouter.ai/api/v1",
            model_id="meta-llama/llama-3.1-70b-instruct",
            api_key_env=self.ENV_VAR,
            openrouter_provider={"allow_fallbacks": False, "only": ["together"]},
        )

        captured = {}

        class FakeMessage:
            content = "{'value': 'A'; 'reason': 'stub'}"

        class FakeChoice:
            message = FakeMessage()

        class FakeUsage:
            prompt_tokens = 3
            completion_tokens = 4

        class FakeResponse:
            choices = [FakeChoice()]
            usage = FakeUsage()

        async def fake_create(**kwargs):
            captured.update(kwargs)
            return FakeResponse()

        client._client.chat.completions.create = fake_create
        response = asyncio.run(client.complete("system text", "user text"))

        self.assertEqual(captured["model"], "meta-llama/llama-3.1-70b-instruct")
        self.assertEqual(
            captured["messages"],
            [{"role": "system", "content": "system text"}, {"role": "user", "content": "user text"}],
        )
        self.assertEqual(
            captured["extra_headers"],
            {
                "HTTP-Referer": "https://github.com/jannikend99/llm-convention-topology",
                "X-OpenRouter-Title": "TUM Master Thesis Naming Game",
                "X-OpenRouter-Cache": "false",
            },
        )
        self.assertEqual(captured["extra_body"], {"provider": {"allow_fallbacks": False, "only": ["together"]}})
        self.assertEqual(response.usage, {"prompt_tokens": 3, "completion_tokens": 4})


class AsyncClientAdapterTests(unittest.TestCase):
    def test_wraps_sync_mock_and_preserves_model_id(self):
        mock = MockLLMClient(policy="always", rng=random.Random(0), options=OPTIONS, always_label="B")
        adapter = AsyncClientAdapter(mock)
        self.assertEqual(adapter.model_id, "mock")
        text = asyncio.run(adapter.complete("s", "u")).text
        self.assertEqual(parse_label(text, OPTIONS), "B")


if __name__ == "__main__":
    unittest.main()
