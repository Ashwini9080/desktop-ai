"""Unit test suite for URL Validation & Gmail Protection Fix (core/executor.py)."""

import unittest
from unittest.mock import patch

from core.executor import open_url, is_domain_match, BLOCKED_MAIL_DOMAINS


class TestUrlValidation(unittest.TestCase):

    def test_is_domain_match_helper(self):
        # Exact domain matches
        self.assertTrue(is_domain_match("google.com", "google.com"))
        self.assertTrue(is_domain_match("mail.google.com", "mail.google.com"))
        self.assertTrue(is_domain_match("GMAIL.COM", "gmail.com"))

        # Subdomain matches
        self.assertTrue(is_domain_match("sub.mail.google.com", "mail.google.com"))
        self.assertTrue(is_domain_match("inbox.mail.yahoo.com", "mail.yahoo.com"))

        # Rejects prefixes / spoofed domains
        self.assertFalse(is_domain_match("evil-google.com", "google.com"))
        self.assertFalse(is_domain_match("fakegmail.com", "gmail.com"))
        self.assertFalse(is_domain_match("not-gmail.com", "gmail.com"))

        # Rejects domain as suffix in other TLDs / spoofed suffix
        self.assertFalse(is_domain_match("google.com.evil.net", "google.com"))
        self.assertFalse(is_domain_match("gmail.com.attacker.com", "gmail.com"))

        # Empty / None handling
        self.assertFalse(is_domain_match(None, "google.com"))
        self.assertFalse(is_domain_match("", "google.com"))
        self.assertFalse(is_domain_match("google.com", ""))

    def test_blocked_mail_domains(self):
        blocked_urls = [
            "https://mail.google.com",
            "https://mail.google.com/mail/u/0/#inbox",
            "https://sub.mail.google.com",
            "https://gmail.com",
            "http://gmail.com/login",
            "https://outlook.live.com",
            "https://outlook.live.com/mail/0/",
            "https://mail.yahoo.com",
            "mail.google.com",
            "gmail.com",
        ]

        for url in blocked_urls:
            with patch("webbrowser.open") as mock_open:
                res = open_url(url)
                self.assertIn("Privacy Protection", res, f"Expected {url} to be blocked by Privacy Protection")
                mock_open.assert_not_called()

    def test_safe_domains_allowed(self):
        safe_urls = [
            "https://evil-google.com",
            "https://google.com.evil.net",
            "https://not-gmail.com",
            "https://google.com",
            "https://github.com",
            "https://wikipedia.org",
            "https://example.com/search?q=gmail.com",
            "https://search.yahoo.com",
        ]

        for url in safe_urls:
            with patch("webbrowser.open", return_value=True) as mock_open:
                res = open_url(url)
                self.assertIn("Successfully opened URL", res, f"Expected {url} to be allowed")
                mock_open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
