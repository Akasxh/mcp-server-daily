import asyncio
import importlib.util
from pathlib import Path
import sys

import pytest


def test_tool_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN", "token")
    monkeypatch.setenv("MY_NUMBER", "+19999999999")
    monkeypatch.setenv("EXPENSE_DB_PATH", str(tmp_path / "exp.db"))

    root = Path(__file__).resolve().parents[1]
    sys.path.append(str(root))
    spec = importlib.util.spec_from_file_location(
        "mcp_starter", root / "mcp-bearer-token" / "mcp_starter.py"
    )
    mcp = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mcp)

    split = asyncio.run(mcp.split_bill.fn(100, 4, 10))
    assert split == pytest.approx(27.5)

    asyncio.run(mcp.add_expense.fn("+15550000000", 25, "food"))
    asyncio.run(mcp.add_expense.fn("+15550000000", 10, "travel"))

    summary = asyncio.run(mcp.weekly_summary.fn("+15550000000"))
    assert summary["food"] == 25
    assert summary["travel"] == 10

    asyncio.run(mcp.add_expense.fn("+15556667777", 5, "food"))
    other = asyncio.run(mcp.weekly_summary.fn("+15556667777"))
    assert other["food"] == 5
    assert "travel" not in other
