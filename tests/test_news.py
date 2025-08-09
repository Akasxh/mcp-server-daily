import sys
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.append(str(Path(__file__).resolve().parents[1]))

import news  # noqa: E402


def test_get_headlines_success():
    news._cache.clear()
    sample_xml = (
        "<rss><channel>"
        "<item><title>Headline1</title><link>http://link1</link></item>"
        "<item><title>Headline2</title><link>http://link2</link></item>"
        "</channel></rss>"
    )

    class MockResponse:
        def __init__(self, text, status_code=200):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "error",
                    request=httpx.Request("GET", "http://test"),
                    response=httpx.Response(self.status_code),
                )

    with patch("httpx.Client.get", return_value=MockResponse(sample_xml)):
        result = news.get_headlines()

    assert "- Headline1 (http://link1)" in result
    assert "- Headline2 (http://link2)" in result


def test_get_headlines_network_error():
    news._cache.clear()
    request = httpx.Request("GET", "https://news.google.com/rss")
    with patch("httpx.Client.get", side_effect=httpx.RequestError("boom", request=request)):
        result = news.get_headlines()

    assert result == "Error fetching news headlines. Please try again later."
