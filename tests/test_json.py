from __future__ import annotations

import json
import random
import unittest
from unittest.mock import patch

from convention_topology.config import ConfigError, load_config, resolve_model
from convention_topology.json_output import ParseError, parse_decision
from convention_topology.llm import MockLLMClient, OpenAICompatClient, openai_extra_body
from convention_topology.prompting import build_user_prompt, format_history


OPTIONS = ["aaaaa", "bbbbb"]


class JsonEnumTests(unittest.TestCase):
    def test_accepts_strict_object(self):
        text = json.dumps({"value": "aaaaa", "reason": "ok"})
        value, reason = parse_decision(text, OPTIONS)
        self.assertEqual(value, "aaaaa")
        self.assertEqual(reason, "ok")

    def test_rejects_extra_keys(self):
        with self.assertRaises(ParseError):
            parse_decision(json.dumps({"value": "aaaaa", "reason": "ok", "x": 1}), OPTIONS)

    def test_rejects_non_enum(self):
        with self.assertRaises(ParseError):
            parse_decision(json.dumps({"value": "zzzzz", "reason": "ok"}), OPTIONS)

    def test_rejects_text_outside_object(self):
        with self.assertRaises(ParseError):
            parse_decision('prefix {"value":"aaaaa","reason":"ok"}', OPTIONS)

    def test_mock_emits_production_json(self):
        client = MockLLMClient(policy="always", rng=random.Random(0), options=OPTIONS, always_label="aaaaa")
        response = client.complete("prompt", options=OPTIONS)
        value, _reason = parse_decision(response.text, OPTIONS)
        self.assertEqual(value, "aaaaa")
        self.assertNotIn(";", response.text)


class ClientTests(unittest.TestCase):
    def test_non_localhost_hard_fails(self):
        with self.assertRaises(ConfigError):
            OpenAICompatClient(
                base_url="https://api.openai.com/v1",
                model_id="x",
                api_key="EMPTY",
                provider="openai_compat",
            )

    def test_resolve_model_localhost_no_env(self):
        spec = resolve_model(load_config(), "nemotron35_lightning")
        self.assertEqual(spec.api_key, "EMPTY")

    def test_openai_extra_body_turns_thinking_off(self):
        extra = openai_extra_body(thinking=False, reasoning_effort=None)
        self.assertEqual(extra["chat_template_kwargs"]["enable_thinking"], False)
        with_effort = openai_extra_body(thinking=True, reasoning_effort="medium")
        self.assertTrue(with_effort["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(with_effort["reasoning_effort"], "medium")

    def test_prompt_is_canonical(self):
        player = {"my_history": [], "partner_history": [], "outcome": []}
        text = build_user_prompt(player, 12, (-50, 100), OPTIONS)
        self.assertIn('Return exactly one JSON object', text)
        self.assertIn('Do not write text outside the JSON object.', text)

    def test_format_history_uses_player_decision_count(self):
        player = {
            "my_history": [f"a{i:05d}" for i in range(15)],
            "partner_history": [f"b{i:05d}" for i in range(15)],
            "outcome": [100] * 15,
        }
        text, player_round, score = format_history(player, 12)
        self.assertEqual(player_round, 16)
        self.assertEqual(score, 1200)
        self.assertIn("Round 4:", text)
        self.assertIn("Round 15:", text)
        self.assertNotIn("Round 1:", text)
        prompt = build_user_prompt(player, 12, (-50, 100), OPTIONS)
        self.assertIn("It is now round 16.", prompt)
