import asyncio
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from news_service import get_headlines

mcp = FastMCP("News MCP Server")


@mcp.tool(description="Fetch top Google News headlines")
async def headlines(
    category: Annotated[str | None, Field(description="Google News topic", example="WORLD")] = None,
    region: Annotated[str | None, Field(description="Region code", example="US")] = None,
    limit: Annotated[int, Field(gt=0, le=10, description="Number of headlines to return")] = 5,
) -> str:
    return await get_headlines(category=category, region=region, limit=limit)


async def main() -> None:
    print("\U0001F4F0 Starting News MCP server on http://0.0.0.0:8089")
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8089)


if __name__ == "__main__":
    asyncio.run(main())
