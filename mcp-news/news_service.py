"""Fetch news headlines using the NewsAPI service."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

API_KEY = os.getenv("NEWS_API_KEY")


class NewsAPIError(Exception):
    """Raised when the NewsAPI request fails."""


async def get_headlines(
    *,
    query: Optional[str] = None,
    country: Optional[str] = "us",
    category: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """Retrieve headlines from NewsAPI and return the JSON response.

    Args:
        query: Optional search term to filter articles.
        country: Two-letter country code. Defaults to "us".
        category: News category such as "technology" or "sports".
        limit: Number of articles to return (max 100 per NewsAPI docs).

    Returns:
        Parsed JSON response from NewsAPI.

    Raises:
        NewsAPIError: If the request fails or the API key is missing.
    """
    print("TOOL NEWS CALLED")
    if not API_KEY:
        raise NewsAPIError("NEWS_API environment variable not set")

    params = {"apiKey": API_KEY, "pageSize": limit}
    if query:
        params["q"] = query
    if country:
        params["country"] = country
    if category:
        params["category"] = category

    url = "https://newsapi.org/v2/top-headlines"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, timeout=10)
            resp.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - network errors
            raise NewsAPIError(str(exc)) from exc

    return resp.json()

