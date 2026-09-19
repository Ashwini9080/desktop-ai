"""Unit test for App Discovery Fallback in core/executor.py."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

import core.executor as executor


class TestAppDiscoveryFallback(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_config = Path(self.temp_dir.name) / "apps.json"
        self.patch_config = patch.object(executor, "CONFIG_FILE", self.mock_config)
        self.patch_config.start()

    def tearDown(self):
        self.patch_config.stop()
        self.temp_dir.cleanup()

    def test_configured_and_valid_in_apps_json(self):
        # 1. Configured and valid in apps.json
        test_data = {
            "notepad": r"%SystemRoot%\System32\notepad.exe"
        }
        with open(self.mock_config, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        with patch("subprocess.Popen") as mock_popen, \
             patch("shutil.which") as mock_which, \
             patch.object(executor, "_find_in_common_locations") as mock_find_common:
            
            res = executor.launch_app("notepad")
            self.assertIn("Successfully launched 'notepad'", res)
            mock_popen.assert_called_once()
            # Since it was already valid in apps.json, fallback should not have been called
            mock_which.assert_not_called()
            mock_find_common.assert_not_called()

    def test_not_configured_found_via_path(self):
        # 2. Not in apps.json, found via PATH
        with open(self.mock_config, "w", encoding="utf-8") as f:
            json.dump({}, f)

        dummy_path = os.path.join(self.temp_dir.name, "mycli.exe")
        with open(dummy_path, "w") as f:
            f.write("mock")

        with patch("subprocess.Popen") as mock_popen, \
             patch("shutil.which", return_value=dummy_path):
            
            res = executor.launch_app("mycli")
            self.assertIn("Successfully launched 'mycli'", res)
            mock_popen.assert_called_once()

        # Should be auto-saved to apps.json
        with open(self.mock_config, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved.get("mycli"), dummy_path)

    def test_invalid_path_in_apps_json_falls_back_and_updates(self):
        # Path in apps.json is broken / does not exist
        test_data = {
            "antigravity": r"C:\NonExistent\antigravity.exe"
        }
        with open(self.mock_config, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        real_discovered = os.path.join(self.temp_dir.name, "Antigravity IDE.exe")
        with open(real_discovered, "w") as f:
            f.write("mock")

        with patch("subprocess.Popen") as mock_popen, \
             patch("shutil.which", return_value=None), \
             patch.object(executor, "_find_in_common_locations", return_value=real_discovered):
            
            res = executor.launch_app("antigravity")
            self.assertIn("Successfully launched 'antigravity'", res)
            mock_popen.assert_called_once()

        # Should overwrite broken path with newly discovered path
        with open(self.mock_config, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved.get("antigravity"), real_discovered)

    def test_empty_path_in_apps_json_falls_back_to_common_locations(self):
        # Entry exists in apps.json but is empty string (like current apps.json antigravity: "")
        test_data = {
            "antigravity": ""
        }
        with open(self.mock_config, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        real_discovered = os.path.join(self.temp_dir.name, "Antigravity IDE.exe")
        with open(real_discovered, "w") as f:
            f.write("mock")

        with patch("subprocess.Popen") as mock_popen, \
             patch("shutil.which", return_value=None), \
             patch.object(executor, "_find_in_common_locations", return_value=real_discovered):
            
            res = executor.launch_app("antigravity")
            self.assertIn("Successfully launched 'antigravity'", res)
            mock_popen.assert_called_once()

        # apps.json must now have the discovered path
        with open(self.mock_config, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved.get("antigravity"), real_discovered)

    def test_not_found_returns_friendly_error(self):
        # 4. App not found anywhere
        with open(self.mock_config, "w", encoding="utf-8") as f:
            json.dump({}, f)

        with patch("shutil.which", return_value=None), \
             patch.object(executor, "_find_in_common_locations", return_value=None):
            
            res = executor.launch_app("SuperRareApp")
            self.assertEqual(res, "Mujhe SuperRareApp nahi mila, apps.json mein path add kar do.")


if __name__ == "__main__":
    unittest.main()
