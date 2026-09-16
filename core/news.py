"""Google News RSS client.

Fetches headlines by category or specific outlet and returns structured
news items ready for both display and TTS consumption.
"""

from __future__ import annotations

import re
from typing import Any

import feedparser

from core.logger import get_logger

log = get_logger(__name__)

_CATEGORY_URLS: dict[str, str] = {
    "ai":            "https://news.google.com/rss/search?q=artificial+intelligence+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    "national":      "https://news.google.com/rss/headlines/section/geo/India?hl=en-IN&gl=IN&ceid=IN:en",
    "international": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en",
    "business":      "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en",
    "sports":        "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=en-IN&gl=IN&ceid=IN:en",
    "tech":          "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en",
    "general":       "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
}

_OUTLET_DOMAINS: dict[str, str] = {
    "times of india": "timesofindia.indiatimes.com",
    "hindustan times": "hindustantimes.com",
    "the hindu":       "thehindu.com",
    "indian express":  "indianexpress.com",
    "ndtv":            "ndtv.com",
    "bbc":             "bbc.com",
    "reuters":         "reuters.com",
}


_DIRECT_OUTLET_FEEDS: dict[str, str] = {
    "bbc":             "http://feeds.bbci.co.uk/news/rss.xml",
    "ndtv":            "https://feeds.feedburner.com/ndtvnews-top-stories",
    "times of india": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
}


def _source_name(entry: Any) -> str:
    try:
        return entry.source.title
    except AttributeError:
        pass
    try:
        return entry.tags[0].term
    except (AttributeError, IndexError):
        pass
    return ""


def _extract_image(entry: Any) -> str | None:
    """Try media_thumbnail → media_content → enclosures → storyimage → <img> in summary."""
    try:
        thumbs = entry.get("media_thumbnail") or entry.get("media_thumbnails", [])
        if thumbs and isinstance(thumbs, list):
            url = thumbs[0].get("url")
            if url:
                return url
    except Exception:
        pass
    try:
        media = entry.get("media_content", [])
        if media and isinstance(media, list):
            url = media[0].get("url")
            if url:
                return url
    except Exception:
        pass
    try:
        enclosures = entry.get("enclosures", [])
        for enc in enclosures:
            url = enc.get("href") or enc.get("url")
            if url:
                return url
    except Exception:
        pass
    try:
        storyimg = entry.get("storyimage")
        if storyimg and isinstance(storyimg, str):
            return storyimg
    except Exception:
        pass
    try:
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']',
                          entry.get("summary", ""), re.I)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def _parse_entries(entries: list, count: int) -> list[dict]:
    items = []
    for entry in entries[:count]:
        title = (entry.get("title") or "").strip()
        if title:
            items.append({
                "headline":  title,
                "source":    _source_name(entry),
                "image_url": _extract_image(entry),
            })
    return items


def _err(msg: str) -> list[dict]:
    return [{"headline": msg, "source": "", "image_url": None}]


def get_news(category: str = "general") -> list[dict]:
    """Return top 4 news items for the given category.

    Each item: {"headline": str, "source": str, "image_url": str | None}
    Returns a single-item error list on failure.
    """
    category = category.lower().strip()
    url = _CATEGORY_URLS.get(category, _CATEGORY_URLS["general"])
    log.info("Fetching news [%s]", category)
    try:
        feed = feedparser.parse(url)
        items = _parse_entries(feed.entries, 4)
        return items or _err("No readable headlines found.")
    except Exception as exc:
        log.error("get_news(%s): %s", category, exc)
        return _err("Could not fetch news. Please try again.")


def get_outlet_news(outlet: str) -> list[dict]:
    """Return top 3 headlines from a specific outlet with image thumbnails.

    Each item: {"headline": str, "source": str, "image_url": str | None}
    Returns a single-item error list on failure or unknown outlet.
    """
    key = outlet.lower().strip()
    domain = _OUTLET_DOMAINS.get(key)
    if domain is None:
        for k, d in _OUTLET_DOMAINS.items():
            if k in key or key in k:
                domain, key = d, k
                break

    if domain is None:
        return _err(f"No source configured for '{outlet}'. Try BBC, NDTV, or Times of India.")

    # Try direct outlet feed first for rich images
    direct_url = _DIRECT_OUTLET_FEEDS.get(key)
    if direct_url:
        try:
            feed = feedparser.parse(direct_url)
            items = _parse_entries(feed.entries, 3)
            if items:
                log.info("Fetched direct outlet news for [%s] (%d items)", key, len(items))
                return items
        except Exception as exc:
            log.warning("Direct feed failed for %s (%s), falling back to Google News", key, exc)

    url = f"https://news.google.com/rss/search?q=site:{domain}+when:1d&hl=en-IN&gl=IN&ceid=IN:en"
    log.info("Fetching outlet news [%s → %s]", key, domain)
    try:
        feed = feedparser.parse(url)
        items = _parse_entries(feed.entries, 3)
        return items or _err(f"No recent headlines for {key.title()}.")
    except Exception as exc:
        log.error("get_outlet_news(%s): %s", key, exc)
        return _err(f"Could not fetch news from {key.title()}.")


def items_to_spoken_summary(items: list[dict], label: str = "") -> str:
    """Convert news items list to a TTS-ready string."""
    if len(items) == 1 and not items[0]["source"]:
        return items[0]["headline"]
    intro = f"Here are the top {len(items)}"
    if label:
        intro += f" {label}"
    intro += " headlines. "
    body = " ... ".join(
        f"{it['source']}: {it['headline']}" if it["source"] else it["headline"]
        for it in items
    )
    return intro + body
