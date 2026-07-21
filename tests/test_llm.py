from __future__ import annotations

import json
import os
import random
import unittest
from pathlib import Path

from convention_topology.gate import evaluate_phase1_gate, has_tracker_converged
from convention_topology.llm import (
    LLMClient,
    LLMResponse,
    MockLLMClient,
    OpenAICompatClient,
    ParseError,
    RetryPolicy,
    RunFailedError,
    parse_label,
)
from convention_topology.prompting import build_messages
from convention_topology.tracker import empty_tracker, get_outcome, update_tracker

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OPTIONS = ["A", "B"]
REWARDS = (-50, 100)


class ProtocolTests(unittest.TestCase):
    def test_mock_client_satisfies_llm_client_protocol(self):
        client = MockLLMClient(policy="always", rng=random.Random(0), options=OPTIONS, always_label="A")
        self.assertIsInstance(client, LLMClient)

    def test_llm_response_fields(self):
        response = LLMResponse(text="hi", usage={"prompt_tokens": 1}, model_id="mock")
        self.assertEqual(response.text, "hi")
        self.assertEqual(response.model_id, "mock")


class ParseLabelTests(unittest.TestCase):
    def setUp(self):
        with (FIXTURES / "canned_responses.json").open() as handle:
            self.fixtures = json.load(handle)

    def test_all_canned_fixtures_match_expected(self):
        self.assertGreaterEqual(len(self.fixtures), 5)
        for case in self.fixtures:
            with self.subTest(case["name"]):
                if "expected" in case:
                    self.assertEqual(parse_label(case["text"], case["options"]), case["expected"])
                else:
                    with self.assertRaises(ParseError):
                        parse_label(case["text"], case["options"])

    def test_zero_matches_raises_parse_error(self):
        with self.assertRaises(ParseError):
            parse_label("no valid option mentioned here", OPTIONS)

    def test_ambiguous_matches_raise_parse_error(self):
        with self.assertRaises(ParseError):
            parse_label("could be 'A' or 'B'", OPTIONS)


class RetryPolicyTests(unittest.TestCase):
    def test_succeeds_on_first_attempt_without_sleeping(self):
        sleeps = []
        policy = RetryPolicy(sleep=sleeps.append)
        result = policy.run(lambda: "ok")
        self.assertEqual(result, "ok")
        self.assertEqual(sleeps, [])

    def test_exhausts_exactly_three_attempts_then_raises(self):
        sleeps = []
        attempts = []

        def always_fails():
            raise ValueError("boom")

        policy = RetryPolicy(sleep=sleeps.append)
        with self.assertRaises(RunFailedError):
            policy.run(always_fails, on_attempt=lambda n, exc: attempts.append((n, exc)))

        self.assertEqual(len(attempts), 3)
        self.assertEqual([n for n, _ in attempts], [1, 2, 3])
        self.assertEqual(sleeps, [2.0, 4.0, 8.0])

    def test_recovers_on_second_attempt(self):
        sleeps = []
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError("transient")
            return "recovered"

        policy = RetryPolicy(sleep=sleeps.append)
        result = policy.run(flaky)
        self.assertEqual(result, "recovered")
        self.assertEqual(sleeps, [2.0])

    def test_max_attempts_beyond_backoff_table_does_not_index_error(self):
        sleeps = []
        policy = RetryPolicy(max_attempts=5, sleep=sleeps.append)
        with self.assertRaises(RunFailedError):
            policy.run(lambda: (_ for _ in ()).throw(ValueError("boom")))
        # 5 attempts but only 3 backoff values -- last one reused, no IndexError.
        self.assertEqual(sleeps, [2.0, 4.0, 8.0, 8.0, 8.0])


class MockLLMClientTests(unittest.TestCase):
    def test_always_policy_returns_fixed_label(self):
        client = MockLLMClient(policy="always", rng=random.Random(0), options=OPTIONS, always_label="B")
        response = client.complete("system", "user")
        self.assertEqual(parse_label(response.text, OPTIONS), "B")

    def test_scripted_policy_replays_fixture_order(self):
        scripted = ["{'value': 'A'; 'reason': 'x'}", "{'value': 'B'; 'reason': 'y'}"]
        client = MockLLMClient(policy="scripted", rng=random.Random(0), scripted_responses=scripted)
        first = parse_label(client.complete("s", "u").text, OPTIONS)
        second = parse_label(client.complete("s", "u").text, OPTIONS)
        third = parse_label(client.complete("s", "u").text, OPTIONS)  # wraps around
        self.assertEqual([first, second, third], ["A", "B", "A"])

    def test_random_policy_never_passes_gate(self):
        rng = random.Random(42)
        client_a = MockLLMClient(policy="random", rng=random.Random(1), options=OPTIONS)
        client_b = MockLLMClient(policy="random", rng=random.Random(2), options=OPTIONS)
        tracker = empty_tracker()
        for _ in range(300):
            resp_a = parse_label(client_a.complete("s", "u").text, OPTIONS)
            resp_b = parse_label(client_b.complete("s", "u").text, OPTIONS)
            outcome = get_outcome(resp_a, resp_b, REWARDS)
            update_tracker(tracker, 0, 1, resp_a, resp_b, outcome)
        self.assertFalse(has_tracker_converged(tracker, convergence_time=3 * 2, threshold=0.95))

    def test_imitate_modal_population_converges_in_toy_loop(self):
        # Seeds chosen so both agents' first (history-empty) rng.choice draws
        # the same label; imitate_modal then repeats each agent's own modal
        # history forever, so the pair locks onto full coordination.
        client_a = MockLLMClient(policy="imitate_modal", rng=random.Random(0), options=OPTIONS)
        client_b = MockLLMClient(policy="imitate_modal", rng=random.Random(1000), options=OPTIONS)
        player_a = {"my_history": [], "partner_history": [], "outcome": []}
        player_b = {"my_history": [], "partner_history": [], "outcome": []}
        tracker = empty_tracker()

        for _ in range(12):
            sys_a, user_a = build_messages(player_a, 5, REWARDS, OPTIONS)
            sys_b, user_b = build_messages(player_b, 5, REWARDS, OPTIONS)
            ans_a = parse_label(client_a.complete(sys_a, user_a).text, OPTIONS)
            ans_b = parse_label(client_b.complete(sys_b, user_b).text, OPTIONS)
            outcome = get_outcome(ans_a, ans_b, REWARDS)
            player_a["my_history"].append(ans_a)
            player_a["partner_history"].append(ans_b)
            player_a["outcome"].append(outcome)
            player_b["my_history"].append(ans_b)
            player_b["partner_history"].append(ans_a)
            player_b["outcome"].append(outcome)
            update_tracker(tracker, 0, 1, ans_a, ans_b, outcome)

        self.assertTrue(has_tracker_converged(tracker, convergence_time=6, threshold=0.95))
        gate = evaluate_phase1_gate(
            tracker, convergence_time=6, threshold=0.95, max_phase1_interactions=5000
        )
        self.assertEqual(gate.eligibility, 1)

    def test_unknown_policy_raises(self):
        client = MockLLMClient(policy="bogus", rng=random.Random(0), options=OPTIONS)
        with self.assertRaises(ValueError):
            client.complete("s", "u")


class OpenAICompatClientTests(unittest.TestCase):
    ENV_VAR = "TEST_OPENAI_COMPAT_KEY"

    def setUp(self):
        os.environ[self.ENV_VAR] = "sk-fake-test-key"
        self.addCleanup(os.environ.pop, self.ENV_VAR, None)

    def test_missing_env_var_raises(self):
        with self.assertRaises(RuntimeError):
            OpenAICompatClient(base_url="https://example.com/v1", model_id="m", api_key_env="NOT_SET_XYZ")

    def test_complete_assembles_messages_and_captures_usage(self):
        client = OpenAICompatClient(
            base_url="https://example.com/v1", model_id="test-model", api_key_env=self.ENV_VAR
        )

        class FakeMessage:
            content = "{'value': 'A'; 'reason': 'stub'}"

        class FakeChoice:
            message = FakeMessage()

        class FakeUsage:
            prompt_tokens = 12
            completion_tokens = 5

        class FakeResponse:
            choices = [FakeChoice()]
            usage = FakeUsage()

        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return FakeResponse()

        client._client.chat.completions.create = fake_create  # inject stub transport (no network)
        response = client.complete("system text", "user text")

        self.assertEqual(captured["model"], "test-model")
        self.assertEqual(
            captured["messages"],
            [{"role": "system", "content": "system text"}, {"role": "user", "content": "user text"}],
        )
        self.assertEqual(captured["temperature"], 0.5)
        self.assertEqual(captured["max_tokens"], 512)
        self.assertEqual(response.text, "{'value': 'A'; 'reason': 'stub'}")
        self.assertEqual(response.usage, {"prompt_tokens": 12, "completion_tokens": 5})
        self.assertEqual(response.model_id, "test-model")

    def test_openrouter_passes_provider_body_and_headers(self):
        client = OpenAICompatClient(
            base_url="https://openrouter.ai/api/v1",
            model_id="meta-llama/llama-3.1-70b-instruct",
            api_key_env=self.ENV_VAR,
            openrouter_provider={"allow_fallbacks": False, "only": ["together"]},
        )

        class FakeMessage:
            content = "ok"

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return FakeResponse()

        client._client.chat.completions.create = fake_create
        client.complete("sys", "usr")

        self.assertEqual(
            captured["extra_headers"],
            {
                "HTTP-Referer": "https://github.com/jannikend99/llm-convention-topology",
                "X-OpenRouter-Title": "TUM Master Thesis Naming Game",
                "X-OpenRouter-Cache": "false",
            },
        )
        self.assertEqual(
            captured["extra_body"],
            {"provider": {"allow_fallbacks": False, "only": ["together"]}},
        )


if __name__ == "__main__":
    unittest.main()
