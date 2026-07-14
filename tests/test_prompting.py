from __future__ import annotations

import unittest
from pathlib import Path

from convention_topology.prompting import PROMPT_TEMPLATE_VERSION, build_messages, get_rules

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DELIM = "\n=====USER=====\n"

REWARDS = (-50, 100)
OPTIONS = ["A", "B"]


def _load_fixture(name: str) -> tuple[str, str]:
    text = (FIXTURES / name).read_text()
    system, user = text.split(DELIM)
    return system, user


class PromptingTests(unittest.TestCase):
    def test_get_rules_strips_llama_header_tokens(self):
        rules = get_rules(REWARDS, OPTIONS)
        self.assertNotIn("<|begin_of_text|>", rules)
        self.assertNotIn("<|start_header_id|>", rules)
        self.assertIn("REWARDED with payoff +100 points", rules)
        self.assertIn("PUNISHED with payoff -50 points", rules)

    def test_empty_history_matches_golden_fixture(self):
        expected_system, expected_user = _load_fixture("prompt_empty_history.txt")
        player = {"my_history": [], "partner_history": [], "outcome": []}
        system, user = build_messages(player, 5, REWARDS, OPTIONS)
        self.assertEqual(system, expected_system)
        self.assertEqual(user, expected_user)

    def test_five_interaction_history_matches_golden_fixture(self):
        expected_system, expected_user = _load_fixture("prompt_5_interactions.txt")
        player = {
            "my_history": ["A", "B", "A", "A", "B"],
            "partner_history": ["A", "A", "A", "B", "B"],
            "outcome": [100, -50, 100, -50, 100],
        }
        system, user = build_messages(player, 5, REWARDS, OPTIONS)
        self.assertEqual(system, expected_system)
        self.assertEqual(user, expected_user)

    def test_user_message_has_no_llama_tokens(self):
        player = {
            "my_history": ["A", "B", "A", "A", "B"],
            "partner_history": ["A", "A", "A", "B", "B"],
            "outcome": [100, -50, 100, -50, 100],
        }
        _, user = build_messages(player, 5, REWARDS, OPTIONS)
        for token in ("<|eot_id|>", "<|start_header_id|>", "<|end_header_id|>"):
            self.assertNotIn(token, user)

    def test_memory_window_caps_at_h5(self):
        # 7 interactions but memory_size=5 -> only last 5 appear, round numbering
        # continues from idx+2 on the trailing window (Ashery off-by-design, verbatim).
        player = {
            "my_history": ["A"] * 7,
            "partner_history": ["A"] * 7,
            "outcome": [100] * 7,
        }
        _, user = build_messages(player, 5, REWARDS, OPTIONS)
        self.assertEqual(user.count("'round'"), 5)
        self.assertIn("It is now round 6.", user)

    def test_prompt_template_version_is_defined(self):
        self.assertIsInstance(PROMPT_TEMPLATE_VERSION, str)
        self.assertTrue(PROMPT_TEMPLATE_VERSION)


if __name__ == "__main__":
    unittest.main()
