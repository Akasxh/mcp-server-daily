"""Utility to fetch top news headlines using Google News RSS."""
from __future__ import annotations

import os
import time
from typing import List, Tuple

import httpx
import xml.etree.ElementTree as ET

# Cache structure: { (category, region): (timestamp, summary_string) }
_cache: dict[Tuple[str, str], Tuple[float, str]] = {}

# Cache duration in seconds, configurable via env var NEWS_CACHE_TTL (default 600 sec)
CACHE_TTL = int(os.getenv("NEWS_CACHE_TTL", "600"))


def _build_url(category: str | None, region: str | None) -> str:
    """Build the Google News RSS URL for given category and region."""
    base = "https://news.google.com/rss"
    params = []
    if region:
        region = region.upper()
        params.append(f"hl={region}")
        params.append(f"gl={region}")
        params.append(f"ceid={region}:{region}")
    if category:
        params.append(f"topic={category.upper()}")
    return f"{base}?{'&'.join(params)}" if params else base


def _parse_rss(xml_text: str, limit: int = 5) -> List[Tuple[str, str]]:
    """Parse RSS XML and return list of (title, link)."""
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall("./channel/item")[:limit]:
        title = item.findtext("title")
        link = item.findtext("link")
        if title and link:
            items.append((title, link))
    return items


def get_headlines(category: str | None = None, region: str | None = None) -> str:
    """Return a chatbot-friendly summary of top news headlines.

    Args:
        category: Optional Google News topic (e.g., 'WORLD', 'BUSINESS').
        region: Optional region code (e.g., 'US', 'GB').

    Returns:
        A string with bullet-point headlines and URLs.
    """
    key = (category or "", region or "")
    now = time.time()
    # Return cached result if valid
    if key in _cache:
        ts, summary = _cache[key]
        if now - ts < CACHE_TTL:
            return summary

    url = _build_url(category, region)
    try:
        with httpx.Client() as client:
            resp = client.get(url, timeout=10, follow_redirects=True)
            resp.raise_for_status()
            xml_text = resp.text
    except httpx.HTTPError:
        return "Error fetching news headlines. Please try again later."

    headlines = _parse_rss(xml_text)
    if not headlines:
        summary = "No headlines found."
    else:
        lines = [f"- {title} ({link})" for title, link in headlines]
        summary = "\n".join(lines)

    _cache[key] = (now, summary)
    return summary
