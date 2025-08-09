import asyncio
import importlib.util
from pathlib import Path

import httpx


def test_get_headlines(monkeypatch):
    monkeypatch.setenv("NEWS_API", "test-key")

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "news_service", root / "mcp-news" / "news_service.py"
    )
    news_service = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(news_service)

    class MockResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    async def mock_get(self, url, params=None, timeout=10):
        assert params["apiKey"] == "test-key"
        return MockResp({"status": "ok", "articles": [{"title": "Test"}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    data = asyncio.run(news_service.get_headlines(limit=1))
    assert data["status"] == "ok"
    assert data["articles"][0]["title"] == "Test"

