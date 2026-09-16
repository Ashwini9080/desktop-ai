"""Rule-based intent classifier — fast regex matching for Hinglish + English commands.

Returns an action dict on confident match, or None to trigger the AI fallback.
"""

from __future__ import annotations

import re
from typing import Any

_OPEN_VERB = r"(?:khol|kholo|khol\s*do|open(?:\s+karo)?)"

POPULAR_SITES: dict[str, str] = {
    "youtube":   "https://youtube.com",
    "google":    "https://google.com",
    "github":    "https://github.com",
    "reddit":    "https://reddit.com",
    "twitter":   "https://twitter.com",
    "instagram": "https://instagram.com",
    "facebook":  "https://facebook.com",
    "linkedin":  "https://linkedin.com",
    "wikipedia": "https://wikipedia.org",
    "netflix":   "https://netflix.com",
    "amazon":    "https://amazon.com",
    "flipkart":  "https://flipkart.com",
}

_NEWS_OUTLETS = [
    "times of india", "hindustan times", "the hindu",
    "indian express", "ndtv", "bbc", "reuters",
]


def _norm(text: str) -> str:
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r"^[^\w]+|[^\w.\/]+$", "", t)
    return re.sub(r"\s+", " ", t)


def classify(text: str) -> dict[str, Any] | None:
    """Match text to a known action; return None if no rule fires.

    Return shape: {"action": str, "target": str | None}
    """
    if not text or not isinstance(text, str):
        return None

    norm = _norm(text)
    if not norm:
        return None

    # --- App launches ---
    if re.search(rf"\b(open\s+antigravity|antigravity\s+({_OPEN_VERB}))\b", norm) \
            or norm == "antigravity":
        return {"action": "launch_app", "target": "antigravity"}

    if re.search(rf"\b(open\s+(chrome|browser)|(chrome|browser)\s+{_OPEN_VERB})\b", norm):
        return {"action": "launch_app", "target": "chrome"}

    # --- Folder / Explorer ---
    if re.search(
        rf"\b(open\s+(file\s+manager|file\s+explorer|explorer)"
        rf"|(file\s+manager|file\s+explorer|explorer)\s+{_OPEN_VERB})\b",
        norm,
    ):
        return {"action": "open_folder", "target": None}

    m = re.search(rf"^(?:open\s+)?([a-zA-Z0-9_\-\s]+?)\s+folder(?:\s+{_OPEN_VERB})?$", norm)
    if m:
        name = m.group(1).strip()
        if name and name not in {"file", "the"}:
            return {"action": "open_folder", "target": name}

    m = re.search(r"^open\s+folder\s+([a-zA-Z0-9_\-\s]+)$", norm)
    if m and m.group(1).strip():
        return {"action": "open_folder", "target": m.group(1).strip()}

    # --- URLs ---
    m = re.search(
        rf"(?:open\s+)?([a-zA-Z0-9\-]+\.(?:com|org|in|net|io|co|ai|dev|app|edu|gov))"
        rf"(?:\s+{_OPEN_VERB})?",
        norm,
    )
    if m:
        return {"action": "open_url", "target": f"https://{m.group(1).strip()}"}

    for site, url in POPULAR_SITES.items():
        if re.search(rf"^(?:open\s+)?{site}(?:\s+{_OPEN_VERB})?$", norm):
            return {"action": "open_url", "target": url}

    # --- News: category ---
    news_rules: list[tuple[str, str]] = [
        (r"\b(ai\s+(news|khabar)|ai\s+mein\s+kya\s+naya)\b",                       "ai"),
        (r"\b(news\s+batao|aaj\s+ki\s+khabar|headlines\s+batao|khabar\s+batao)\b", "general"),
        (r"\b(india\s+ki\s+news|national\s+news\s+batao|desh\s+ki\s+khabar)\b",    "national"),
        (r"\b(international\s+news|duniya\s+ki\s+khabar|world\s+news\s+batao)\b",  "international"),
        (r"\b(business\s+news|market\s+ki\s+khabar)\b",                             "business"),
        (r"\b(sports\s+news|khel\s+ki\s+khabar)\b",                                "sports"),
        (r"\b(tech\s+news|technology\s+ki\s+khabar)\b",                             "tech"),
    ]
    for pattern, category in news_rules:
        if re.search(pattern, norm):
            return {"action": "get_news", "target": category}

    # --- News: outlet-specific ---
    for outlet in _NEWS_OUTLETS:
        if re.search(rf"\b{re.escape(outlet)}\s+ki\s+(news|khabar|headlines)\b", norm):
            return {"action": "get_outlet_news", "target": outlet}

    # --- Stock market ---
    if re.search(
        r"\b(stock\s+market\s+batao|trading\s+ke\s+baare\s+mein\s+bata"
        r"|kaunse\s+stock\s+acche\s+chal\s+rahe\s+hain"
        r"|stock\s+analysis\s+karo|nifty\s+sensex\s+batao"
        r"|market\s+analysis\s+karo)\b",
        norm,
    ):
        return {"action": "get_stock_movers", "target": None}

    # --- YouTube search / play ---
    m = re.search(
        r"(?:"
        r"youtube\s+pe\s+(.+?)\s+(?:khojo|bajao|chalao|play\s+karo)"
        r"|play\s+(.+?)\s+on\s+youtube"
        r"|(.+?)\s+gaana?\s+(?:bajao|chalao|sunao)"
        r"|youtube\s+pe\s+(.+?)\s+search\s+karo"
        r"|play\s+(.+?)\s+song"
        r")",
        norm,
    )
    if m:
        query = next(g for g in m.groups() if g is not None).strip()
        if query:
            return {"action": "search_youtube", "target": query}

    # --- Google search ---
    m = re.search(
        r"(?:"
        r"google\s+pe\s+(.+?)\s+(?:search\s+karo|dhundo|khojo)"
        r"|(.+?)\s+google\s+karo"
        r"|^search\s+(?:for\s+)?(.+?)(?:\s+on\s+google)?$"
        r"|google\s+karo\s+(.+)"
        r"|(.+?)\s+dhundo(?:\s+google\s+pe)?"
        r")",
        norm,
    )
    if m:
        query = next(g for g in m.groups() if g is not None).strip()
        # Avoid matching single-word site names already handled above
        if query and len(query) > 2:
            return {"action": "search_google", "target": query}

    return None
