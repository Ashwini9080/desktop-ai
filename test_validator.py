"""Unit test suite for Action Validation Layer (core/validator.py) & main.py integration."""

import unittest
from unittest.mock import patch, MagicMock

from core.validator import validate_action, ALLOWED_ACTIONS, SHELL_METACHARACTERS
import main


class TestActionValidator(unittest.TestCase):

    def test_allowlist_matches_specification(self):
        expected = {
            "launch_app",
            "open_url",
            "open_folder",
            "search_google",
            "search_youtube",
            "get_news",
            "get_outlet_news",
            "get_stock_movers",
            "media_control",
            "make_call",
        }
        self.assertEqual(ALLOWED_ACTIONS, expected)

    def test_valid_actions_pass(self):
        valid_cases = [
            {"action": "launch_app", "target": "notepad"},
            {"action": "open_url", "target": "https://google.com"},
            {"action": "open_folder", "target": "C:\\Users\\Public"},
            {"action": "search_google", "target": "Python 3 tutorial"},
            {"action": "search_youtube", "target": "lofi beats"},
            {"action": "get_news", "target": "technology"},
            {"action": "get_outlet_news", "target": "bbc"},
            {"action": "get_stock_movers", "target": None},
            {"action": "media_control", "target": "play"},
            {"action": "media_control", "target": "pause"},
            {"action": "media_control", "target": "next"},
            {"action": "media_control", "target": None},
            {"action": "make_call", "target": "rahul"},
        ]
        for case in valid_cases:
            res = validate_action(case)
            self.assertIsNotNone(res, f"Failed for valid case: {case}")
            self.assertEqual(res["action"], case["action"])

    def test_rejected_unknown_actions(self):
        invalid_actions = [
            "run_shell",
            "execute_bash",
            "delete_system32",
            "eval",
            "subprocess",
            "download_file",
            "format_c",
            "",
            None,
        ]
        for act in invalid_actions:
            res = validate_action({"action": act, "target": "something"})
            self.assertIsNone(res, f"Should reject action: {act}")

    def test_non_dict_rejected(self):
        for invalid_input in [None, "launch_app", 123, ["launch_app"], True]:
            res = validate_action(invalid_input)
            self.assertIsNone(res)

    def test_target_type_and_length(self):
        # Target must be string or None
        self.assertIsNone(validate_action({"action": "launch_app", "target": 12345}))
        self.assertIsNone(validate_action({"action": "launch_app", "target": ["calc"]}))

        # Target under 200 chars passes
        ok_target = "a" * 199
        self.assertIsNotNone(validate_action({"action": "search_google", "target": ok_target}))

        # Target >= 200 chars rejected
        long_target_200 = "a" * 200
        self.assertIsNone(validate_action({"action": "search_google", "target": long_target_200}))

        long_target_300 = "a" * 300
        self.assertIsNone(validate_action({"action": "search_google", "target": long_target_300}))

    def test_shell_metacharacters_injection_rejected(self):
        metas = [";", "&", "|", "`", "$("]
        for meta in metas:
            payload = f"calc.exe {meta} echo pwned"
            res = validate_action({"action": "launch_app", "target": payload})
            self.assertIsNone(res, f"Should reject metacharacter {meta!r} in target: {payload}")

    def test_open_url_validation(self):
        # Valid URLs
        self.assertIsNotNone(validate_action({"action": "open_url", "target": "https://google.com"}))
        self.assertIsNotNone(validate_action({"action": "open_url", "target": "http://localhost:8080/app"}))
        self.assertIsNotNone(validate_action({"action": "open_url", "target": "https://sub.domain.org/path"}))

        # Malformed / dangerous URLs
        malformed = [
            "google.com",                  # missing scheme
            "javascript:alert(1)",         # invalid scheme
            "ftp://ftp.example.com",       # invalid scheme
            "file:///C:/Windows/System32", # invalid scheme
            "https://",                    # missing netloc
            "",                            # empty string
            None,                          # None target for open_url
            "https://example.com;rm -rf",  # shell injection character in URL
        ]
        for url in malformed:
            res = validate_action({"action": "open_url", "target": url})
            self.assertIsNone(res, f"Should reject malformed URL: {url!r}")

    def test_main_handle_command_blocks_malicious_actions(self):
        # If AI/classifier suggests a dangerous command, main.handle_command blocks it
        malicious_action = {"action": "launch_app", "target": "calc.exe; format C:"}

        with patch("main.classify", return_value=malicious_action), \
             patch("main.execute") as mock_execute, \
             patch("main._speak_bg") as mock_speak:

            result = main.handle_command("run exploit")
            self.assertIn("Security alert", result)
            mock_execute.assert_not_called()
            mock_speak.assert_called_once()


if __name__ == "__main__":
    unittest.main()
