from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import yaml

from convention_topology.config import (
    ConfigError,
    LOCK_PROTOCOL,
    SERVE_PROFILE_KEYS,
    TOPOLOGIES,
    apply_serve_base_url,
    load_config,
    protocol_fingerprint,
    resolve_model,
    trajectory_module_hashes,
    validate_config,
)


class ConfigLockTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_protocol_defaults_match_lock_table(self):
        for key, expected in LOCK_PROTOCOL.items():
            self.assertEqual(self.config["protocol"][key], expected)
        self.assertEqual(self.config["protocol"]["gate_window"], 3 * self.config["protocol"]["N"])

    def test_required_sections_and_identities(self):
        self.assertEqual(tuple(self.config["network"]["topologies"]), TOPOLOGIES)
        self.assertNotIn("complete", self.config["network"]["topologies"])
        self.assertEqual(self.config["minority"]["k_set"], [2, 4, 6, 8, 10, 12])
        self.assertEqual(self.config["run"]["attempted_per_cell"], 32)
        self.assertEqual(self.config["run"]["sampling_plan"], "fixed_attempted")
        self.assertEqual(self.config["run"]["checkpoint_every"], 1)
        self.assertIn(self.config["serve"]["provider"], ("openai_compat", "mock"))
        self.assertEqual(self.config["serve"]["api_key"], "EMPTY")

    def test_each_model_has_serve_profile_keys(self):
        for name, entry in self.config["models"].items():
            for key in SERVE_PROFILE_KEYS:
                self.assertIn(key, entry, msg=name)
            self.assertTrue(entry["max_tokens"])

    def test_mock_resolves_without_api_key(self):
        spec = resolve_model(self.config, "mock")
        self.assertEqual(spec.provider, "mock")
        self.assertEqual(spec.api_key, "EMPTY")

    def test_localhost_openai_compat_does_not_need_real_key(self):
        spec = resolve_model(self.config, "llama4_scout")
        self.assertEqual(spec.provider, "openai_compat")
        self.assertIn("127.0.0.1", spec.base_url)

    def test_apply_serve_base_url_overrides_resolved_model(self):
        config = load_config()
        apply_serve_base_url(config, "http://127.0.0.1:9999/v1")
        spec = resolve_model(config, "llama4_scout")
        self.assertEqual(spec.base_url, "http://127.0.0.1:9999/v1")

    def test_protocol_fingerprint_includes_trajectory_modules(self):
        from unittest.mock import patch

        hashes = trajectory_module_hashes()
        self.assertEqual(set(hashes), {"prompting.py", "llm.py", "persistence.py"})
        fp = protocol_fingerprint(self.config)
        patched = dict(hashes)
        patched["llm.py"] = "0" * 64
        with patch("convention_topology.config.trajectory_module_hashes", return_value=patched):
            self.assertNotEqual(protocol_fingerprint(self.config), fp)

    def test_empty_jobs_models_rejected(self):
        raw = copy.deepcopy(self.config)
        raw["jobs"]["models"] = []
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_default_jobs_models_are_the_four_shorthands(self):
        self.assertEqual(
            self.config["jobs"]["models"],
            ["llama4_scout", "gemma4_31b", "qwen38_27b", "mistral_small4"],
        )

    def test_thinking_on_and_off_in_jobs_models_loads(self):
        raw = copy.deepcopy(self.config)
        raw["jobs"]["models"] = ["llama4_scout", "gemma4_31b_think"]
        validated = validate_config(raw)
        self.assertFalse(validated["models"]["llama4_scout"]["thinking"])
        self.assertTrue(validated["models"]["gemma4_31b_think"]["thinking"])

    def test_rejects_slate_model_key(self):
        raw = copy.deepcopy(self.config)
        raw["models"]["llama4_scout"]["slate"] = "A"
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_rejects_banned_campaign_names(self):
        raw = copy.deepcopy(self.config)
        for name in ("slate-a", "fit-slate-a"):
            raw["run"]["campaign"] = name
            with self.assertRaises(ConfigError):
                validate_config(raw)


class BannedConfigTests(unittest.TestCase):
    def _raw(self):
        return copy.deepcopy(load_config())

    def test_rejects_n_24(self):
        raw = self._raw()
        raw["protocol"]["N"] = 24
        raw["protocol"]["gate_window"] = 72
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_rejects_letter_pool_keys(self):
        raw = self._raw()
        raw["options_emergence"] = ["Q", "M"]
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_rejects_topology_complete(self):
        raw = self._raw()
        raw["network"]["topologies"] = ["complete", "random_regular", "lattice"]
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_rejects_k_one_through_six(self):
        raw = self._raw()
        raw["minority"]["k_set"] = [1, 2, 3, 4, 5, 6]
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_rejects_workers_key(self):
        raw = self._raw()
        raw["run"]["workers"] = 1
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_rejects_cloud_provider(self):
        raw = self._raw()
        raw["serve"]["provider"] = "together"
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_rejects_non_localhost_unless_mock(self):
        raw = self._raw()
        raw["serve"]["base_url"] = "https://api.together.xyz/v1"
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_rejects_tbd_placeholder(self):
        raw = self._raw()
        raw["models"]["gpt"] = copy.deepcopy(raw["models"]["mock"])
        raw["models"]["gpt"]["model_id"] = "TBD-doug"
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_yaml_file_with_banned_values(self):
        payload = load_config()
        payload["protocol"]["N"] = 24
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            path.write_text(yaml.safe_dump(payload))
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
