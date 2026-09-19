"""Unit tests for Priority 7: News extraction enhancements and deduplication."""

import unittest
from unittest.mock import MagicMock, patch
from core.news import (
    is_near_duplicate,
    _extract_link,
    _extract_published,
    _parse_entries,
    get_news,
    get_outlet_news,
)


class TestNewsEnhancements(unittest.TestCase):
    def test_is_near_duplicate_high_overlap(self):
        """Headlines sharing > 80% words should be flagged as duplicates."""
        seen = [
            "Sensex plunges 500 points amid global inflation concerns and rate fears",
        ]
        # 9 out of 10 words identical (~90% overlap)
        new_headline = "Sensex drops 500 points amid global inflation concerns and rate fears"
        self.assertTrue(is_near_duplicate(new_headline, seen, threshold=0.8))

    def test_is_near_duplicate_exact_match(self):
        """Exact identical headlines should be flagged as duplicates."""
        seen = ["Tech giant reports record quarterly revenue"]
        new_headline = "Tech giant reports record quarterly revenue"
        self.assertTrue(is_near_duplicate(new_headline, seen, threshold=0.8))

    def test_is_near_duplicate_suffix_source(self):
        """Headlines with appended news source should be flagged if base headline shares >80%."""
        seen = ["ISRO successfully launches new weather satellite"]
        new_headline = "ISRO successfully launches new weather satellite - BBC News"
        # 6 of 6 seen words are in new headline (100% of seen words shared)
        self.assertTrue(is_near_duplicate(new_headline, seen, threshold=0.8))

    def test_is_distinct_headline(self):
        """Distinct headlines sharing few or no words should NOT be flagged."""
        seen = [
            "Gold rate today rises in Delhi market",
            "Sensex gains 300 points on IT rally",
        ]
        new_headline = "ISRO announces moon mission timeline"
        self.assertFalse(is_near_duplicate(new_headline, seen, threshold=0.8))

    def test_is_distinct_headline_moderate_overlap(self):
        """Headlines sharing some words (e.g. 50%) should not be flagged."""
        seen = ["Government announces new tax policy for automobile sector"]
        # Shares "announces new policy for", but different subjects (4 of 8 = 50%)
        new_headline = "Reserve Bank announces new policy for digital payments"
        self.assertFalse(is_near_duplicate(new_headline, seen, threshold=0.8))

    def test_extract_link_and_published_attributes(self):
        """Test extraction from object attributes (feedparser FeedParserDict style)."""
        mock_entry = MagicMock()
        mock_entry.link = "https://example.com/article-123"
        mock_entry.published = "Sat, 19 Sep 2026 10:00:00 GMT"

        self.assertEqual(_extract_link(mock_entry), "https://example.com/article-123")
        self.assertEqual(_extract_published(mock_entry), "Sat, 19 Sep 2026 10:00:00 GMT")

    def test_extract_link_and_published_dict(self):
        """Test extraction from dictionary format."""
        entry_dict = {
            "link": "https://example.com/news-456",
            "published": "2026-09-19T08:30:00Z",
        }
        self.assertEqual(_extract_link(entry_dict), "https://example.com/news-456")
        self.assertEqual(_extract_published(entry_dict), "2026-09-19T08:30:00Z")

    def test_parse_entries_deduplicates_and_preserves_fields(self):
        """Verify _parse_entries preserves url, link, published, and filters duplicates."""
        entries = [
            {
                "title": "Stock market today: Sensex rises 400 points on banking surge",
                "link": "https://news.example.com/art1",
                "published": "2026-09-19 09:00:00",
                "source": {"title": "Financial Express"},
            },
            # Near duplicate of entry 1 -> Should be skipped!
            {
                "title": "Stock market today: Sensex jumps 400 points on banking surge",
                "link": "https://news.example.com/art2-dup",
                "published": "2026-09-19 09:05:00",
                "source": {"title": "Economic Times"},
            },
            # Distinct entry 2 -> Should be included!
            {
                "title": "New electric vehicle policy announced by government",
                "link": "https://news.example.com/art3",
                "published": "2026-09-19 09:10:00",
                "source": {"title": "Auto News"},
            },
        ]

        items = _parse_entries(entries, count=2)
        self.assertEqual(len(items), 2)

        # First item
        self.assertIn("Sensex rises 400 points", items[0]["headline"])
        self.assertEqual(items[0]["url"], "https://news.example.com/art1")
        self.assertEqual(items[0]["link"], "https://news.example.com/art1")
        self.assertEqual(items[0]["published"], "2026-09-19 09:00:00")

        # Second item should be EV policy, NOT the duplicate Sensex headline
        self.assertIn("New electric vehicle policy", items[1]["headline"])
        self.assertEqual(items[1]["url"], "https://news.example.com/art3")
        self.assertEqual(items[1]["link"], "https://news.example.com/art3")
        self.assertEqual(items[1]["published"], "2026-09-19 09:10:00")

    @patch("core.news.feedparser.parse")
    def test_get_news_returns_enhanced_dict(self, mock_parse):
        """Verify get_news returns structured dicts with url and published fields."""
        mock_feed = MagicMock()
        mock_feed.entries = [
            {
                "title": "AI Breakthrough Announced by Researchers",
                "link": "https://tech.example.com/ai-breakthrough",
                "published": "Fri, 18 Sep 2026 18:00:00 GMT",
                "source": {"title": "TechCrunch"},
            }
        ]
        mock_parse.return_value = mock_feed

        items = get_news("tech")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["headline"], "AI Breakthrough Announced by Researchers")
        self.assertEqual(item["url"], "https://tech.example.com/ai-breakthrough")
        self.assertEqual(item["link"], "https://tech.example.com/ai-breakthrough")
        self.assertEqual(item["published"], "Fri, 18 Sep 2026 18:00:00 GMT")


if __name__ == "__main__":
    unittest.main()
