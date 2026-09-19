"""Unit test suite for Mobile Server Security (core/mobile_server.py)."""

import json
import os
import time
import unittest
from unittest.mock import patch

from core.mobile_server import app, limiter, _active_sessions, _create_session_token, _validate_session_token, _is_allowed_origin


class TestMobileServerSecurity(unittest.TestCase):

    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        os.environ["MOBILE_APP_PASSWORD"] = "SecretPass123"
        _active_sessions.clear()
        limiter.reset()

        # Dummy command handler
        import core.mobile_server as ms
        ms._command_handler = lambda text: f"Echo: {text}"

    def tearDown(self):
        _active_sessions.clear()

    def test_max_content_length_rejects_oversized_payload(self):
        # Payloads over 1KB (1024 bytes) must be rejected with 413
        large_text = "x" * 1500
        res = self.client.post(
            "/command",
            headers={"X-App-Password": "SecretPass123"},
            json={"text": large_text}
        )
        self.assertEqual(res.status_code, 413)

    def test_session_token_issue_and_reuse(self):
        # 1. First call with password creates session token
        res = self.client.post(
            "/command",
            headers={"X-App-Password": "SecretPass123"},
            json={"text": "open notepad"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("token", data)
        token = data["token"]
        self.assertTrue(len(token) >= 32)
        self.assertIn(token, _active_sessions)

        # 2. Subsequent call uses X-Session-Token without X-App-Password
        res2 = self.client.post(
            "/command",
            headers={"X-Session-Token": token},
            json={"text": "open chrome"}
        )
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertEqual(data2["message"], "Echo: open chrome")

    def test_auth_endpoint_issues_token(self):
        # /auth issues token upon valid password
        res = self.client.post(
            "/auth",
            headers={"X-App-Password": "SecretPass123"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("token", data)
        self.assertEqual(data["expires_in"], 3600)

        # Test invalid password on /auth
        res_bad = self.client.post(
            "/auth",
            headers={"X-App-Password": "WrongPassword"}
        )
        self.assertEqual(res_bad.status_code, 401)

    def test_invalid_or_expired_token_rejected(self):
        # 1. Nonexistent token rejected
        res = self.client.post(
            "/command",
            headers={"X-Session-Token": "invalid_fake_token"},
            json={"text": "calc"}
        )
        self.assertEqual(res.status_code, 401)

        # 2. Expired token rejected
        expired_token = _create_session_token()
        _active_sessions[expired_token] = time.time() - 10  # in the past
        res_exp = self.client.post(
            "/command",
            headers={"X-Session-Token": expired_token},
            json={"text": "calc"}
        )
        self.assertEqual(res_exp.status_code, 401)

    def test_origin_csrf_checks(self):
        # 1. Allowed local / private origins
        self.assertTrue(_is_allowed_origin("http://localhost:5000"))
        self.assertTrue(_is_allowed_origin("http://127.0.0.1:5000"))
        self.assertTrue(_is_allowed_origin("http://192.168.1.105:5000"))
        self.assertTrue(_is_allowed_origin("http://10.0.0.12:5000"))
        self.assertTrue(_is_allowed_origin("http://172.20.10.4:5000"))

        # 2. Disallowed foreign origins
        self.assertFalse(_is_allowed_origin("http://evil.com"))
        self.assertFalse(_is_allowed_origin("https://attacker.org:5000"))

        # 3. Request with evil Origin rejected with 403
        res = self.client.post(
            "/command",
            headers={
                "X-App-Password": "SecretPass123",
                "Origin": "http://evil-attacker.com"
            },
            json={"text": "hello"}
        )
        self.assertEqual(res.status_code, 403)

    def test_rate_limiting_max_20_per_minute(self):
        # First 20 requests succeed
        token = _create_session_token()
        for i in range(20):
            res = self.client.post(
                "/command",
                headers={"X-Session-Token": token},
                json={"text": f"ping {i}"}
            )
            self.assertEqual(res.status_code, 200, f"Request {i+1} failed with {res.status_code}")

        # 21st request must be rate-limited (429)
        res_blocked = self.client.post(
            "/command",
            headers={"X-Session-Token": token},
            json={"text": "ping 21"}
        )
        self.assertEqual(res_blocked.status_code, 429)
        data = res_blocked.get_json()
        self.assertIn("Rate limit exceeded", data["message"])


if __name__ == "__main__":
    unittest.main()
