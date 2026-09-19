"""Unit tests for Priority 8: Stocks batch download optimization and Nifty 50 caching."""

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
from core.stocks import (
    get_cached_nifty50_constituents,
    get_candidates,
    _pct,
    _fmt,
    _NSE_SYMBOLS,
    _BSE_SYMBOLS,
)


class TestStocksOptimization(unittest.TestCase):
    def test_nifty50_cache_presence_and_count(self):
        """Verify Nifty 50 constituent list is cached and contains exactly 50 symbols."""
        constituents = get_cached_nifty50_constituents()
        self.assertEqual(len(constituents), 50)
        self.assertIn("RELIANCE.NS", constituents)
        self.assertIn("TCS.NS", constituents)
        self.assertIn("HDFCBANK.NS", constituents)
        self.assertEqual(len(_NSE_SYMBOLS), 50)
        self.assertEqual(len(_BSE_SYMBOLS), 50)

    @patch("core.stocks.yf.download")
    def test_get_candidates_uses_batch_download(self, mock_download):
        """Verify get_candidates uses yf.download with tickers, period='3mo', group_by='ticker'."""
        # Create a mock MultiIndex DataFrame for 2 tickers: RELIANCE.NS and TCS.NS
        dates = pd.date_range("2026-06-01", periods=60, freq="B")
        cols = pd.MultiIndex.from_tuples([
            ("RELIANCE.NS", "Close"),
            ("TCS.NS", "Close"),
        ])
        # Synthetic prices: RELIANCE gained 20%, TCS gained 5%
        rel_prices = [100.0 + i * 0.35 for i in range(60)] # starts 100, ends ~120
        tcs_prices = [3000.0 + i * 2.5 for i in range(60)] # starts 3000, ends ~3150
        mock_df = pd.DataFrame(
            data=list(zip(rel_prices, tcs_prices)),
            index=dates,
            columns=cols
        )
        mock_download.return_value = mock_df

        candidates = get_candidates()

        # Check that yf.download was called in batch mode
        mock_download.assert_called_once()
        call_kwargs = mock_download.call_args[1]
        self.assertEqual(call_kwargs.get("period"), "3mo")
        self.assertEqual(call_kwargs.get("group_by"), "ticker")
        self.assertIn("tickers", call_kwargs)
        self.assertGreaterEqual(len(call_kwargs["tickers"]), 100)

        # Check candidate results
        self.assertGreaterEqual(len(candidates), 2)
        top1 = candidates[0]
        self.assertEqual(top1["symbol"], "RELIANCE.NS")
        self.assertEqual(top1["company"], "Reliance Industries")
        self.assertIn("change_3m", top1)
        self.assertIn("change_1m", top1)
        self.assertIn("change_day", top1)

    @patch("core.stocks.yf.download")
    @patch("core.stocks._fetch_symbol")
    def test_get_candidates_fallback_on_batch_failure(self, mock_fetch, mock_download):
        """Verify graceful fallback if batch download returns None or raises an exception."""
        mock_download.side_effect = Exception("Batch API network timeout")
        mock_fetch.return_value = {
            "symbol": "INFY.NS",
            "base": "INFY",
            "company": "Infosys",
            "exchange": "NSE",
            "price": 1800.0,
            "change_day": 1.2,
            "change_1m": 4.5,
            "change_3m": 12.0,
        }

        candidates = get_candidates()
        self.assertIsInstance(candidates, list)
        self.assertTrue(len(candidates) >= 1)
        self.assertEqual(candidates[0]["symbol"], "INFY.NS")

    def test_pct_and_fmt_helpers(self):
        """Test percentage calculation and formatting helpers."""
        self.assertAlmostEqual(_pct(110.0, 100.0), 10.0)
        self.assertAlmostEqual(_pct(90.0, 100.0), -10.0)
        self.assertEqual(_pct(100.0, 0.0), 0.0)
        self.assertEqual(_fmt(5.25), "+5.25%")
        self.assertEqual(_fmt(-3.10), "-3.10%")


if __name__ == "__main__":
    unittest.main()
