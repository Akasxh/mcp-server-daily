import asyncio
from typing import Annotated

from fastmcp import FastMCP
from mcp import ErrorData, McpError
from mcp.types import INVALID_PARAMS
from pydantic import Field

from utility_dispatcher import scientific_calculator

mcp = FastMCP("Calculator MCP Server")


@mcp.tool(description="Evaluate a mathematical expression")
async def calculate(
    expression: Annotated[str, Field(description="The expression to evaluate")]
) -> float:
    """Evaluate a math expression using the scientific calculator."""
    try:
        return scientific_calculator(expression)
    except ValueError as exc:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=str(exc)))


async def main() -> None:
    print("\U0001F680 Starting Calculator MCP server on http://0.0.0.0:8088")
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8088)


if __name__ == "__main__":
    asyncio.run(main())
