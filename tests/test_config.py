from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import yaml

from convention_topology.config import (
    ConfigError,
    DIAG_LETTER_POOL,
    LOCK_PROTOCOL,
    SERVE_PROFILE_KEYS,
    TOPOLOGIES,
    apply_diag_protocol,
    apply_diag_tech_interactions,
    apply_pilot_bounds,
    apply_serve_base_url,
    campaign_requires_full_diag_knobs,
    check_campaign_name,
    config_hash,
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
        self.assertNotIn("diag_decode", self.config["protocol"])
        self.assertEqual(set(self.config["pool"]), {"seed"})

    def test_required_sections_and_identities(self):
        self.assertEqual(tuple(self.config["network"]["topologies"]), TOPOLOGIES)
        self.assertNotIn("complete", self.config["network"]["topologies"])
        self.assertEqual(self.config["minority"]["k_set"], [5, 10, 14])
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
        spec = resolve_model(self.config, "nemotron35_lightning")
        self.assertEqual(spec.provider, "openai_compat")
        self.assertIn("127.0.0.1", spec.base_url)

    def test_apply_serve_base_url_overrides_resolved_model(self):
        config = load_config()
        apply_serve_base_url(config, "http://127.0.0.1:9999/v1")
        spec = resolve_model(config, "nemotron35_lightning")
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

    def test_default_jobs_models_are_the_four_keepers(self):
        self.assertEqual(
            self.config["jobs"]["models"],
            [
                "gemma4_31b",
                "qwen38_27b",
                "olmo31_32b",
                "glm4_32b",
            ],
        )

    def test_olmo_and_glm_registry_ids(self):
        self.assertEqual(
            resolve_model(self.config, "olmo31_32b").model_id,
            "allenai/Olmo-3.1-32B-Instruct",
        )
        self.assertEqual(
            resolve_model(self.config, "glm4_32b").model_id,
            "zai-org/GLM-4-32B-0414",
        )

    def test_mistral_small32_uses_mistral_tokenizer_flags(self):
        extra = self.config["models"]["mistral_small32"].get("vllm_extra_args") or []
        self.assertEqual(
            extra,
            [
                "--tokenizer-mode",
                "mistral",
                "--config-format",
                "mistral",
                "--load-format",
                "mistral",
                "--generation-config",
                "vllm",
            ],
        )
        spec = resolve_model(self.config, "mistral_small32")
        self.assertFalse(spec.send_chat_template_kwargs)
        nemo = resolve_model(self.config, "nemotron35_lightning")
        self.assertTrue(nemo.send_chat_template_kwargs)

    def test_gemma4_e2b_is_registry_only(self):
        spec = resolve_model(self.config, "gemma4_e2b")
        self.assertEqual(spec.model_id, "google/gemma-4-E2B-it")
        self.assertNotIn("gemma4_e2b", self.config["jobs"]["models"])

    def test_think_shorthands_are_registry_only(self):
        lightning = resolve_model(self.config, "nemotron35_lightning_think")
        self.assertEqual(
            lightning.model_id,
            "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16",
        )
        self.assertTrue(lightning.thinking)
        self.assertFalse(lightning.thinking_always_on)
        self.assertEqual(lightning.max_tokens, 4096)
        self.assertEqual(lightning.thinking_token_budget, 2048)
        olmo = resolve_model(self.config, "olmo31_32b_think")
        self.assertEqual(olmo.model_id, "allenai/Olmo-3.1-32B-Think")
        self.assertTrue(olmo.thinking)
        self.assertTrue(olmo.thinking_always_on)
        self.assertEqual(olmo.max_tokens, 4096)
        self.assertEqual(olmo.thinking_token_budget, 2048)
        gemma = resolve_model(self.config, "gemma4_31b_think")
        self.assertIsNone(gemma.thinking_token_budget)
        self.assertEqual(gemma.max_tokens, 1024)
        for name in ("nemotron35_lightning_think", "olmo31_32b_think"):
            self.assertNotIn(name, self.config["jobs"]["models"])

    def test_thinking_on_and_off_in_jobs_models_loads(self):
        raw = copy.deepcopy(self.config)
        raw["jobs"]["models"] = ["nemotron35_lightning", "gemma4_31b_think"]
        validated = validate_config(raw)
        self.assertFalse(validated["models"]["nemotron35_lightning"]["thinking"])
        self.assertTrue(validated["models"]["gemma4_31b_think"]["thinking"])

    def test_rejects_thinking_token_budget_without_room(self):
        raw = copy.deepcopy(self.config)
        raw["models"]["nemotron35_lightning"]["thinking_token_budget"] = 256
        with self.assertRaises(ConfigError):
            validate_config(raw)
        raw = copy.deepcopy(self.config)
        raw["models"]["nemotron35_lightning_think"]["thinking_token_budget"] = 4096
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_rejects_slate_model_key(self):
        raw = copy.deepcopy(self.config)
        raw["models"]["nemotron35_lightning"]["slate"] = "A"
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

    def test_rejects_h_5(self):
        raw = self._raw()
        raw["protocol"]["H"] = 5
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_rejects_yaml_diag_decode(self):
        raw = self._raw()
        raw["protocol"]["diag_decode"] = "parse"
        with self.assertRaises(ConfigError):
            validate_config(raw)

    def test_rejects_yaml_pool_labels(self):
        raw = self._raw()
        raw["pool"]["labels"] = ["Q", "M"]
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

    def test_diag_protocol_requires_diag_campaign(self):
        raw = self._raw()
        with self.assertRaises(ConfigError):
            apply_diag_protocol(raw, memory_h=5, pool_kind="letters")

    def test_full_diag_knobs_required_for_n24_scout_not_tech(self):
        self.assertTrue(campaign_requires_full_diag_knobs("diag-n24-scout", {}))
        self.assertTrue(campaign_requires_full_diag_knobs("diag-lockcell-gemma", {}))
        self.assertFalse(campaign_requires_full_diag_knobs("diag-tech-gemma4_31b", {}))
        self.assertFalse(campaign_requires_full_diag_knobs("pilot-run", {}))
        self.assertFalse(
            campaign_requires_full_diag_knobs("diag-n24-scout", {"DIAG_TECH_INTERACTIONS": "8"})
        )

    def test_diag_protocol_allows_h5_letters_after_validate(self):
        raw = self._raw()
        raw["run"]["campaign"] = "diag-h5-letters"
        apply_diag_protocol(raw, memory_h=5, pool_kind="letters", cap_phase1=1200)
        self.assertEqual(raw["protocol"]["H"], 5)
        self.assertEqual(raw["protocol"]["string_length"], 1)
        self.assertEqual(raw["protocol"]["cap_phase1"], 1200)
        self.assertEqual(raw["pool"]["labels"], list(DIAG_LETTER_POOL))
        self.assertEqual(raw["protocol"]["N"], 48)
        self.assertEqual(raw["protocol"]["gate_window"], 144)

    def test_diag_ashery_n24_letters_parse(self):
        raw = self._raw()
        raw["run"]["campaign"] = "diag-ashery-parse-mock"
        apply_diag_protocol(
            raw,
            memory_h=5,
            pool_kind="letters",
            cap_phase1=400,
            population_n=24,
            decode="parse",
        )
        self.assertEqual(raw["protocol"]["N"], 24)
        self.assertEqual(raw["protocol"]["H"], 5)
        self.assertEqual(raw["protocol"]["gate_window"], 72)
        self.assertEqual(raw["protocol"]["diag_decode"], "parse")
        self.assertEqual(raw["protocol"]["string_length"], 1)
        self.assertEqual(raw["protocol"]["cap_phase1"], 400)
        self.assertEqual(raw["pool"]["labels"], list(DIAG_LETTER_POOL))

    def test_diag_tech_interactions_allows_tiny_cap(self):
        raw = self._raw()
        raw["run"]["campaign"] = "diag-tech-gemma4-31b"
        apply_diag_tech_interactions(raw, 5)
        self.assertEqual(raw["protocol"]["cap_phase1"], 5)

    def test_diag_tech_interactions_requires_diag_campaign(self):
        raw = self._raw()
        with self.assertRaises(ConfigError):
            apply_diag_tech_interactions(raw, 5)

    def test_diag_tech_interactions_rejects_out_of_range(self):
        raw = self._raw()
        raw["run"]["campaign"] = "diag-tech-mock"
        with self.assertRaises(ConfigError):
            apply_diag_tech_interactions(raw, 0)
        with self.assertRaises(ConfigError):
            apply_diag_tech_interactions(raw, 21)

    def test_diag_protocol_strings_keeps_five_char_generator(self):
        raw = self._raw()
        raw["run"]["campaign"] = "diag-h5-strings"
        apply_diag_protocol(raw, memory_h=5, pool_kind="strings", cap_phase1=1200)
        self.assertEqual(raw["protocol"]["H"], 5)
        self.assertEqual(raw["protocol"]["string_length"], 5)
        self.assertNotIn("labels", raw["pool"])

    def test_pilot_bounds_require_pilot_campaign(self):
        raw = self._raw()
        with self.assertRaises(ConfigError):
            apply_pilot_bounds(raw, cap_phase1=1000, phase2_horizon=500)

    def test_pilot_bounds_set_cap_and_horizon(self):
        raw = self._raw()
        raw["run"]["campaign"] = "pilot-run"
        apply_pilot_bounds(raw, cap_phase1=1000, phase2_horizon=500)
        self.assertEqual(raw["protocol"]["cap_phase1"], 1000)
        self.assertEqual(raw["protocol"]["phase2_horizon"], 500)
        self.assertEqual(raw["protocol"]["N"], 48)
        self.assertEqual(raw["protocol"]["H"], 12)

    def test_pilot_bounds_reject_out_of_range(self):
        raw = self._raw()
        raw["run"]["campaign"] = "pilot-run"
        with self.assertRaises(ConfigError):
            apply_pilot_bounds(raw, cap_phase1=100)
        with self.assertRaises(ConfigError):
            apply_pilot_bounds(raw, phase2_horizon=1501)


class FillOverrideTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        import os
        from unittest.mock import patch

        env = dict(os.environ)
        env.pop("FILL_MAX_CONCURRENT_RUNS", None)
        env.pop("FILL_IN_FLIGHT_LIMIT", None)
        env.pop("FILL_MAX_NUM_SEQS", None)
        with patch.dict("os.environ", env, clear=True):
            self.yaml_spec = resolve_model(self.config, "mock")

    def test_unset_fill_keeps_yaml_caps(self):
        import os
        from unittest.mock import patch

        env = dict(os.environ)
        env.pop("FILL_MAX_CONCURRENT_RUNS", None)
        env.pop("FILL_IN_FLIGHT_LIMIT", None)
        env.pop("FILL_MAX_NUM_SEQS", None)
        with patch.dict("os.environ", env, clear=True):
            spec = resolve_model(self.config, "mock")
        self.assertEqual(spec.max_concurrent_runs, self.yaml_spec.max_concurrent_runs)
        self.assertEqual(spec.in_flight_limit, self.yaml_spec.in_flight_limit)
        self.assertEqual(spec.max_num_seqs, self.yaml_spec.max_num_seqs)

    def test_one_fill_field_overrides_only_that_cap(self):
        import os
        from unittest.mock import patch

        env = dict(os.environ)
        env.pop("FILL_IN_FLIGHT_LIMIT", None)
        env.pop("FILL_MAX_NUM_SEQS", None)
        env["FILL_MAX_CONCURRENT_RUNS"] = "9"
        with patch.dict("os.environ", env, clear=True):
            spec = resolve_model(self.config, "mock")
        self.assertEqual(spec.max_concurrent_runs, 9)
        self.assertEqual(spec.in_flight_limit, self.yaml_spec.in_flight_limit)
        self.assertEqual(spec.max_num_seqs, self.yaml_spec.max_num_seqs)

    def test_all_three_fill_overrides(self):
        from unittest.mock import patch

        env = {
            "FILL_MAX_CONCURRENT_RUNS": "3",
            "FILL_IN_FLIGHT_LIMIT": "6",
            "FILL_MAX_NUM_SEQS": "12",
        }
        with patch.dict("os.environ", env, clear=False):
            spec = resolve_model(self.config, "mock")
        self.assertEqual(spec.max_concurrent_runs, 3)
        self.assertEqual(spec.in_flight_limit, 6)
        self.assertEqual(spec.max_num_seqs, 12)

    def test_non_int_and_non_positive_fill_raise(self):
        from unittest.mock import patch

        for name, value in (
            ("FILL_MAX_CONCURRENT_RUNS", "x"),
            ("FILL_IN_FLIGHT_LIMIT", "0"),
            ("FILL_MAX_NUM_SEQS", "-2"),
            ("FILL_MAX_CONCURRENT_RUNS", ""),
            ("FILL_IN_FLIGHT_LIMIT", "1.5"),
        ):
            with self.subTest(name=name, value=value):
                with patch.dict("os.environ", {name: value}, clear=False):
                    with self.assertRaises(ConfigError):
                        resolve_model(self.config, "mock")

    def test_fill_does_not_change_config_hash(self):
        from unittest.mock import patch

        before = config_hash(self.config)
        with patch.dict("os.environ", {"FILL_MAX_NUM_SEQS": "24"}, clear=False):
            resolve_model(self.config, "mock")
            self.assertEqual(config_hash(self.config), before)

    def test_gpu_fill_campaign_accepted_slate_a_rejected(self):
        self.assertEqual(check_campaign_name("gpu-fill-gemma4_31b-c2"), "gpu-fill-gemma4_31b-c2")
        with self.assertRaises(ConfigError):
            check_campaign_name("slate-a")
        raw = copy.deepcopy(self.config)
        raw["run"]["campaign"] = "gpu-fill-gemma4_31b-c2"
        validate_config(raw)


if __name__ == "__main__":
    unittest.main()
