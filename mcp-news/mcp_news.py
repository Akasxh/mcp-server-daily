import asyncio
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from news_service import get_headlines

mcp = FastMCP("News MCP Server")


@mcp.tool(description="Fetch news headlines from NewsAPI")
async def headlines(
    query: Annotated[str | None, Field(description="Search term", example="AI")] = None,
    country: Annotated[str | None, Field(description="Two-letter country code", example="us")] = "us",
    category: Annotated[str | None, Field(description="News category", example="technology")] = None,
    limit: Annotated[int, Field(gt=0, le=100, description="Number of articles to return")] = 5,
) -> dict:
    return await get_headlines(query=query, country=country, category=category, limit=limit)


async def main() -> None:
    print("\U0001F4F0 Starting News MCP server on http://0.0.0.0:8089")
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8089)


if __name__ == "__main__":
    asyncio.run(main())
