import sys
from pathlib import Path
import asyncio

import pytest

# Add path to the mcp-calculator module
sys.path.append(str(Path(__file__).resolve().parents[1] / "mcp-calculator"))

from mcp_calculator import calculate  # noqa: E402
from mcp import McpError  # noqa: E402


def test_calculate():
    result = asyncio.run(calculate.fn("sin(pi / 2) + 2**3"))
    assert result == pytest.approx(9.0)


def test_calculate_invalid():
    with pytest.raises(McpError):
        asyncio.run(calculate.fn("2 +"))

