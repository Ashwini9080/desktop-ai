"""Unit test suite for Phone Control via ADB (core/phone_control.py), intent classification, and main routing."""

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from core.phone_control import is_device_connected, load_contacts, make_call
from core.intent_classifier import classify
from core.validator import validate_action
import main


class TestPhoneControl(unittest.TestCase):

    @patch("core.phone_control.subprocess.run")
    def test_is_device_connected_authorized(self, mock_run):
        """Test device connected and authorized (line ending in 'device')."""
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "List of devices attached\nemulator-5554\tdevice\n"
        mock_run.return_value = mock_res

        self.assertTrue(is_device_connected())

    @patch("core.phone_control.subprocess.run")
    def test_is_device_connected_unauthorized(self, mock_run):
        """Test device present but unauthorized should return False."""
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "List of devices attached\nemulator-5554\tunauthorized\n"
        mock_run.return_value = mock_res

        self.assertFalse(is_device_connected())

    @patch("core.phone_control.subprocess.run")
    def test_is_device_connected_offline(self, mock_run):
        """Test device present but offline should return False."""
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "List of devices attached\nemulator-5554\toffline\n"
        mock_run.return_value = mock_res

        self.assertFalse(is_device_connected())

    @patch("core.phone_control.subprocess.run")
    def test_is_device_connected_none_attached(self, mock_run):
        """Test empty device list should return False."""
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "List of devices attached\n\n"
        mock_run.return_value = mock_res

        self.assertFalse(is_device_connected())

    @patch("core.phone_control.subprocess.run")
    def test_is_device_connected_adb_not_installed(self, mock_run):
        """Test FileNotFoundError when ADB is not installed."""
        mock_run.side_effect = FileNotFoundError()

        self.assertFalse(is_device_connected())

    def test_load_contacts(self):
        """Test loading contact dictionary."""
        contacts = load_contacts()
        self.assertIsInstance(contacts, dict)
        self.assertIn("rahul", contacts)
        self.assertIn("mom", contacts)

    @patch("core.phone_control.is_device_connected", return_value=False)
    def test_make_call_no_device_connected(self, mock_conn):
        """Test friendly error returned when no phone is connected."""
        result = make_call("rahul", "+919876543210")
        self.assertIn("No Android device connected", result)

    @patch("core.phone_control.load_contacts", return_value={"rahul": "+919876543210"})
    def test_make_call_contact_not_found(self, mock_contacts):
        """Test contact lookup failure error."""
        result = make_call("unknown_friend")
        self.assertIn("Contact 'unknown_friend' not found", result)
        self.assertIn("contacts.json", result)

    @patch("core.phone_control.is_device_connected", return_value=True)
    @patch("core.phone_control.load_contacts", return_value={"rahul": "+919876543210"})
    @patch("core.phone_control.subprocess.run")
    def test_make_call_success_with_contact(self, mock_run, mock_contacts, mock_conn):
        """Test successful call execution via contact name lookup."""
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res

        result = make_call("rahul")
        self.assertEqual(result, "Calling rahul.")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd, ["adb", "shell", "am", "start", "-a", "android.intent.action.CALL", "-d", "tel:+919876543210"])

    @patch("core.phone_control.is_device_connected", return_value=True)
    @patch("core.phone_control.subprocess.run")
    def test_make_call_success_with_direct_number(self, mock_run, mock_conn):
        """Test successful call execution with direct phone number argument."""
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res

        result = make_call("Doctor", "+911234567890")
        self.assertEqual(result, "Calling Doctor.")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd, ["adb", "shell", "am", "start", "-a", "android.intent.action.CALL", "-d", "tel:+911234567890"])

    @patch("core.phone_control.is_device_connected", return_value=True)
    @patch("core.phone_control.subprocess.run")
    def test_make_call_adb_timeout(self, mock_run, mock_conn):
        """Test handling of subprocess TimeoutExpired."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="adb", timeout=10)

        result = make_call("rahul", "+919876543210")
        self.assertIn("timed out", result)

    def test_intent_classifier_call_patterns(self):
        """Verify intent classifier matches diverse phone call phrasings."""
        cases = [
            ("rahul ko call karo", {"action": "make_call", "target": "rahul"}),
            ("call rahul", {"action": "make_call", "target": "rahul"}),
            ("mom ko phone lagao", {"action": "make_call", "target": "mom"}),
            ("call mom", {"action": "make_call", "target": "mom"}),
            ("mom ko call karo", {"action": "make_call", "target": "mom"}),
            ("rahul ko phone lagao", {"action": "make_call", "target": "rahul"}),
            ("call 9876543210", {"action": "make_call", "target": "9876543210"}),
            ("+919876543210 ko call karo", {"action": "make_call", "target": "+919876543210"}),
        ]
        for phrase, expected in cases:
            matched = classify(phrase)
            self.assertIsNotNone(matched, f"Failed to match: {phrase}")
            self.assertEqual(matched["action"], expected["action"], f"Action mismatch for {phrase}")
            self.assertEqual(matched["target"], expected["target"], f"Target mismatch for {phrase}")

    def test_validator_permits_make_call(self):
        """Verify action validator permits valid make_call actions."""
        action = {"action": "make_call", "target": "rahul"}
        self.assertEqual(validate_action(action), action)

        # Reject injection in target
        injection = {"action": "make_call", "target": "rahul; rm -rf /"}
        self.assertIsNone(validate_action(injection))

    @patch("core.phone_control.dial_via_phone_link", return_value=True)
    @patch("core.phone_control.is_device_connected", return_value=False)
    def test_make_call_phone_link_fallback(self, mock_conn, mock_phone_link):
        """Test fallback to Windows Phone Link when ADB device is not connected."""
        result = make_call("rahul", "+919876543210")
        self.assertIn("Calling rahul via Windows Phone Link", result)
        mock_phone_link.assert_called_once_with("+919876543210")

    @patch("core.phone_control.os.startfile", create=True)
    def test_dial_via_phone_link_windows(self, mock_startfile):
        """Test dial_via_phone_link dispatches tel: protocol correctly on Windows."""
        from core.phone_control import dial_via_phone_link
        with patch("sys.platform", "win32"):
            success = dial_via_phone_link("+91 98765-43210")
            self.assertTrue(success)
            mock_startfile.assert_called_once_with("tel:+919876543210")

    @patch("main.make_call", return_value="Calling rahul.")
    @patch("main._speak_bg")
    @patch("main._update_gui_feedback")
    def test_main_handle_command_routing(self, mock_feedback, mock_speak, mock_call):
        """Verify main.handle_command routes make_call action correctly."""
        resp = main.handle_command("call rahul")
        self.assertEqual(resp, "Calling rahul.")
        mock_call.assert_called_once_with(contact_name="rahul")


if __name__ == "__main__":
    unittest.main()

