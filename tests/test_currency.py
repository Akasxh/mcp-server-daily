from pathlib import Path
import json
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from utility_dispatcher import convert_currency, dispatch, _RATE_CACHE


def test_convert_currency_uses_cache(monkeypatch):
    _RATE_CACHE.clear()
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def read(self):
            data = {"data": {"EUR": {"value": 0.5}}}
            return json.dumps(data).encode("utf-8")

    def fake_urlopen(url, timeout=10):
        calls.append(url)
        return FakeResponse()

    times = [0, 10]
    monkeypatch.setattr("utility_dispatcher.time.time", lambda: times.pop(0))
    monkeypatch.setattr("utility_dispatcher.request.urlopen", fake_urlopen)
    monkeypatch.setenv("CURRENCY_API_KEY", "test")

    result1 = convert_currency(2, "USD", "EUR")
    result2 = convert_currency(2, "USD", "EUR")
    assert result1 == pytest.approx(1.0)
    assert result2 == pytest.approx(1.0)
    assert len(calls) == 1


def test_dispatch_currency_network_error(monkeypatch):
    def fake_convert(*args, **kwargs):
        raise RuntimeError("Network down")

    monkeypatch.setattr("utility_dispatcher.convert_currency", fake_convert)
    result = dispatch("currency 10 USD EUR")
    assert result == "Currency conversion failed: Network down"
