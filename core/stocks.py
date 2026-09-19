"""Indian stock market analysis — Nifty 50 (NSE + BSE).

Scans all Nifty 50 constituents on both exchanges, ranks by 3-month
return, attaches recent news, and produces a spoken summary.
"""

from __future__ import annotations

import time
from typing import Optional

import feedparser
import pandas as pd
import yfinance as yf

from core.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Nifty 50 Constituent List Cache
#
# NOTE: This constituent list is cached locally to avoid recurrent network discovery.
# It should be periodically refreshed (e.g. checked/updated every few months)
# because index constituents change over time — the National Stock Exchange (NSE)
# rebalances the Nifty 50 semi-annually (typically effective in March and September).
# ---------------------------------------------------------------------------
_CACHED_NIFTY50_CONSTITUENTS: list[str] = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "KOTAKBANK.NS", "LT.NS", "AXISBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ASIANPAINT.NS", "MARUTI.NS", "HCLTECH.NS",
    "SUNPHARMA.NS", "BAJFINANCE.NS", "ULTRACEMCO.NS", "TITAN.NS", "WIPRO.NS",
    "BAJAJFINSV.NS", "NESTLEIND.NS", "POWERGRID.NS", "TECHM.NS", "NTPC.NS",
    "ONGC.NS", "COALINDIA.NS", "M&M.NS", "ADANIPORTS.NS", "JSWSTEEL.NS",
    "TATASTEEL.NS", "TATAMOTORS.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS",
    "GRASIM.NS", "HINDALCO.NS", "ADANIENT.NS", "APOLLOHOSP.NS", "BPCL.NS",
    "BRITANNIA.NS", "EICHERMOT.NS", "INDUSINDBK.NS", "HDFCLIFE.NS",
    "SBILIFE.NS", "TATACONSUM.NS", "UPL.NS", "HEROMOTOCO.NS",
    "BEL.NS", "SHREECEM.NS",
]

_NSE_SYMBOLS: list[str] = list(_CACHED_NIFTY50_CONSTITUENTS)
_BSE_SYMBOLS: list[str] = [s.replace(".NS", ".BO") for s in _NSE_SYMBOLS]


def get_cached_nifty50_constituents() -> list[str]:
    """Return the cached list of Nifty 50 NSE ticker symbols.

    NOTE: Index constituents change over time. This list should be periodically
    refreshed (e.g. checked/updated every few months) against official NSE data.
    """
    return list(_CACHED_NIFTY50_CONSTITUENTS)

_COMPANY_NAMES: dict[str, str] = {
    "RELIANCE": "Reliance Industries",  "TCS": "Tata Consultancy Services",
    "HDFCBANK": "HDFC Bank",            "INFY": "Infosys",
    "ICICIBANK": "ICICI Bank",          "HINDUNILVR": "Hindustan Unilever",
    "ITC": "ITC",                       "KOTAKBANK": "Kotak Mahindra Bank",
    "LT": "Larsen & Toubro",            "AXISBANK": "Axis Bank",
    "SBIN": "State Bank of India",      "BHARTIARTL": "Bharti Airtel",
    "ASIANPAINT": "Asian Paints",       "MARUTI": "Maruti Suzuki",
    "HCLTECH": "HCL Technologies",      "SUNPHARMA": "Sun Pharma",
    "BAJFINANCE": "Bajaj Finance",      "ULTRACEMCO": "UltraTech Cement",
    "TITAN": "Titan",                   "WIPRO": "Wipro",
    "BAJAJFINSV": "Bajaj Finserv",      "NESTLEIND": "Nestle India",
    "POWERGRID": "Power Grid",          "TECHM": "Tech Mahindra",
    "NTPC": "NTPC",                     "ONGC": "ONGC",
    "COALINDIA": "Coal India",          "M&M": "Mahindra & Mahindra",
    "ADANIPORTS": "Adani Ports",        "JSWSTEEL": "JSW Steel",
    "TATASTEEL": "Tata Steel",          "TATAMOTORS": "Tata Motors",
    "DRREDDY": "Dr. Reddy's",           "CIPLA": "Cipla",
    "DIVISLAB": "Divi's Laboratories",  "GRASIM": "Grasim Industries",
    "HINDALCO": "Hindalco",             "ADANIENT": "Adani Enterprises",
    "APOLLOHOSP": "Apollo Hospitals",   "BPCL": "BPCL",
    "BRITANNIA": "Britannia",           "EICHERMOT": "Eicher Motors",
    "INDUSINDBK": "IndusInd Bank",      "HDFCLIFE": "HDFC Life",
    "SBILIFE": "SBI Life",              "TATACONSUM": "Tata Consumer",
    "UPL": "UPL",                       "HEROMOTOCO": "Hero MotoCorp",
    "BEL": "Bharat Electronics",        "SHREECEM": "Shree Cement",
}


def _pct(new: float, old: float) -> float:
    return 0.0 if old == 0 else (new - old) / old * 100


def _fmt(p: float) -> str:
    return f"{'+' if p >= 0 else ''}{p:.2f}%"


def _fetch_symbol(symbol: str) -> Optional[dict]:
    try:
        hist = yf.Ticker(symbol).history(period="3mo")
        if hist.empty or len(hist) < 2:
            return None
        closes = hist["Close"]
        cur     = float(closes.iloc[-1])
        prev    = float(closes.iloc[-2])
        p_1m    = float(closes.iloc[max(0, len(closes) - 22)])
        p_3m    = float(closes.iloc[0])
        base    = symbol.rsplit(".", 1)[0]
        return {
            "symbol":     symbol,
            "base":       base,
            "company":    _COMPANY_NAMES.get(base, base),
            "exchange":   "BSE" if symbol.endswith(".BO") else "NSE",
            "price":      cur,
            "change_day": _pct(cur, prev),
            "change_1m":  _pct(cur, p_1m),
            "change_3m":  _pct(cur, p_3m),
        }
    except Exception as exc:
        log.debug("_fetch_symbol(%s): %s", symbol, exc)
        return None


def get_market_overview() -> str:
    """Return a one-line Nifty 50 + Sensex snapshot string."""
    indices = [("^NSEI", "Nifty 50"), ("^BSESN", "Sensex")]
    parts = []
    for sym, label in indices:
        try:
            hist = yf.Ticker(sym).history(period="2d")
            if len(hist) >= 2:
                cur, prev = float(hist["Close"].iloc[-1]), float(hist["Close"].iloc[-2])
                parts.append(f"{label}: {cur:,.0f} ({_fmt(_pct(cur, prev))})")
        except Exception as exc:
            log.warning("Index fetch failed (%s): %s", sym, exc)
    return " | ".join(parts) if parts else "Market indices unavailable."


def get_candidates() -> list[dict]:
    """Scan all Nifty 50 NSE + BSE symbols; return top 5 by 3-month return.

    Uses yfinance's batch download feature (yf.download(tickers=list_of_symbols, period='3mo', group_by='ticker'))
    to fetch all symbols in far fewer network round-trips rather than sequential .history() calls.
    Deduplicates by company — keeps the better-performing exchange listing.
    """
    symbols = _NSE_SYMBOLS + _BSE_SYMBOLS
    raw: list[dict] = []
    t0 = time.time()

    log.info("Batch downloading 3-month market data for %d symbols...", len(symbols))
    try:
        df = yf.download(
            tickers=symbols,
            period="3mo",
            group_by="ticker",
            progress=False,
        )
    except Exception as exc:
        log.error("Batch download failed in get_candidates: %s", exc)
        df = None

    if df is not None and not df.empty:
        for sym in symbols:
            try:
                closes = None
                if isinstance(df.columns, pd.MultiIndex):
                    if sym in df.columns.levels[0] or sym in df:
                        closes = df[sym]["Close"].dropna()
                    elif "Close" in df.columns.levels[0] and sym in df["Close"].columns:
                        closes = df["Close"][sym].dropna()
                else:
                    if "Close" in df.columns:
                        closes = df["Close"].dropna()

                if closes is None or len(closes) < 2:
                    continue

                cur  = float(closes.iloc[-1])
                prev = float(closes.iloc[-2])
                p_1m = float(closes.iloc[max(0, len(closes) - 22)])
                p_3m = float(closes.iloc[0])
                base = sym.rsplit(".", 1)[0]

                raw.append({
                    "symbol":     sym,
                    "base":       base,
                    "company":    _COMPANY_NAMES.get(base, base),
                    "exchange":   "BSE" if sym.endswith(".BO") else "NSE",
                    "price":      cur,
                    "change_day": _pct(cur, prev),
                    "change_1m":  _pct(cur, p_1m),
                    "change_3m":  _pct(cur, p_3m),
                })
            except Exception as exc:
                log.debug("Error processing batch data for %s: %s", sym, exc)
                continue

    # Fallback to individual fetch if batch download returned no usable results
    if not raw:
        log.warning("Batch download returned no data; falling back to individual symbol fetch...")
        for sym in symbols[:10]:
            data = _fetch_symbol(sym)
            if data:
                raw.append(data)

    best: dict[str, dict] = {}
    for item in raw:
        b = item["base"]
        if b not in best or item["change_3m"] > best[b]["change_3m"]:
            best[b] = item

    top5 = sorted(best.values(), key=lambda x: x["change_3m"], reverse=True)[:5]
    log.info("Batch candidates fetch completed in %.2fs. Top 5: %s",
             time.time() - t0, [d["symbol"] for d in top5])
    return top5


def get_company_news(symbol: str, company_name: str) -> list[str]:
    """Return up to 2 recent headlines for a company from Google News."""
    query = company_name.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={query}+when:7d&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        feed = feedparser.parse(url)
        return [e.get("title", "").strip() for e in feed.entries[:2] if e.get("title")]
    except Exception as exc:
        log.warning("get_company_news(%s): %s", symbol, exc)
        return []


def get_stock_analysis() -> str:
    """Build a full spoken market summary: indices + top 5 movers + news."""
    log.info("Running stock analysis …")

    lines = [
        "Ye pichle 3 mahine ka trend aur latest news hai, "
        "final decision tumhara — main koi guarantee nahi de sakta.",
        f"Aaj ka market: {get_market_overview()}.",
    ]

    candidates = get_candidates()
    if not candidates:
        lines.append("Stock data unavailable right now.")
    else:
        lines.append(f"Top {len(candidates)} performers from Nifty 50:")
        for i, s in enumerate(candidates, 1):
            news = get_company_news(s["symbol"], s["company"])
            line = (
                f"Number {i}: {s['company']} on {s['exchange']}. "
                f"Price: {s['price']:,.1f}. "
                f"Today {_fmt(s['change_day'])}, "
                f"1 month {_fmt(s['change_1m'])}, "
                f"3 months {_fmt(s['change_3m'])}."
            )
            if news:
                line += f" Recent news: {news[0]}."
            lines.append(line)

    lines.append(
        "Invest karne se pehle apne financial advisor se baat karo "
        "aur company ke fundamentals khud verify karo."
    )
    return " ".join(lines)
