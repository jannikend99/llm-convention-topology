from __future__ import annotations

import unittest

from convention_topology.config import ConfigError, load_config, resolve_model


class ResolveModelTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_llama31_matches_registry_defaults(self):
        spec = resolve_model(self.config, "llama31")
        self.assertEqual(spec.provider, "openrouter")
        self.assertEqual(spec.model_id, "meta-llama/llama-3.1-70b-instruct")
        self.assertEqual(spec.base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(spec.api_key_env, "OPENROUTER_API_KEY")
        self.assertEqual(
            spec.openrouter_provider,
            {"allow_fallbacks": False, "only": ["deepinfra"]},
        )
        self.assertEqual(spec.max_tokens, 512)

    def test_qwen25_matches_registry_defaults(self):
        spec = resolve_model(self.config, "qwen25")
        self.assertEqual(spec.provider, "openrouter")
        self.assertEqual(spec.model_id, "qwen/qwen-2.5-72b-instruct")
        self.assertEqual(spec.api_key_env, "OPENROUTER_API_KEY")
        self.assertEqual(
            spec.openrouter_provider,
            {"allow_fallbacks": False, "only": ["deepinfra"]},
        )
        self.assertEqual(spec.max_tokens, 512)

    def test_gemini35_matches_registry_defaults(self):
        spec = resolve_model(self.config, "gemini35")
        self.assertEqual(spec.provider, "google")
        self.assertEqual(spec.model_id, "gemini-3.5-flash")
        self.assertEqual(spec.base_url, "https://generativelanguage.googleapis.com/v1beta/openai/")
        self.assertEqual(spec.api_key_env, "GEMINI_API_KEY")
        self.assertIsNone(spec.openrouter_provider)

    def test_mock_needs_no_env_vars(self):
        spec = resolve_model(self.config, "mock")
        self.assertEqual(spec.provider, "mock")
        self.assertEqual(spec.model_id, "mock")
        self.assertEqual(spec.api_key_env, "")

    def test_tbd_placeholder_fails_fast(self):
        with self.assertRaises(ConfigError):
            resolve_model(self.config, "gpt54")
        with self.assertRaises(ConfigError):
            resolve_model(self.config, "claude55")

    def test_unknown_shorthand_raises(self):
        with self.assertRaises(ConfigError):
            resolve_model(self.config, "not-a-model")


if __name__ == "__main__":
    unittest.main()
