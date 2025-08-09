import asyncio
import os
from typing import Annotated

from dotenv import load_dotenv
import httpx
from fastmcp import FastMCP
from mcp import ErrorData, McpError
from mcp.server.auth.provider import AccessToken
from mcp.types import INVALID_PARAMS, INTERNAL_ERROR
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair

# Load environment variables
load_dotenv()

# Environment variables for bearer auth (required by Puch)
TOKEN = os.environ.get("AUTH_TOKEN")
assert TOKEN is not None, "Please set AUTH_TOKEN in your .env file"

# Spotify OAuth credentials
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REFRESH_TOKEN = os.environ.get("SPOTIFY_REFRESH_TOKEN")

assert SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET and SPOTIFY_REFRESH_TOKEN, (
    "Please set SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, and SPOTIFY_REFRESH_TOKEN"
)

class SimpleBearerAuthProvider(BearerAuthProvider):
    def __init__(self, token: str):
        k = RSAKeyPair.generate()
        super().__init__(public_key=k.public_key, jwks_uri=None, issuer=None, audience=None)
        self.token = token

    async def load_access_token(self, token: str) -> AccessToken | None:
        if token == self.token:
            return AccessToken(token=token, client_id="puch-client", scopes=["*"], expires_at=None)
        return None

mcp = FastMCP("Spotify MCP Server", auth=SimpleBearerAuthProvider(TOKEN))

_ACCESS_TOKEN: str | None = None

async def _refresh_access_token() -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "refresh_token", "refresh_token": SPOTIFY_REFRESH_TOKEN},
            auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        )
    if resp.status_code != 200:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="Failed to refresh Spotify token"))
    return resp.json()["access_token"]

async def _spotify_request(method: str, url: str, **kwargs) -> httpx.Response:
    global _ACCESS_TOKEN
    if _ACCESS_TOKEN is None:
        _ACCESS_TOKEN = await _refresh_access_token()

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {_ACCESS_TOKEN}"
    async with httpx.AsyncClient() as client:
        resp = await client.request(method, url, headers=headers, **kwargs)
    if resp.status_code == 401:
        _ACCESS_TOKEN = await _refresh_access_token()
        headers["Authorization"] = f"Bearer {_ACCESS_TOKEN}"
        async with httpx.AsyncClient() as client:
            resp = await client.request(method, url, headers=headers, **kwargs)
    return resp

@mcp.tool(description="Play a track by Spotify ID")
async def play(track_id: Annotated[str, "Spotify track ID"]) -> str:
    resp = await _spotify_request(
        "PUT",
        "https://api.spotify.com/v1/me/player/play",
        json={"uris": [f"spotify:track:{track_id}"]},
    )
    if resp.status_code == 404:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="No active device found"))
    if resp.status_code >= 400:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=resp.text))
    return "Playing"

@mcp.tool
async def pause() -> str:
    resp = await _spotify_request("PUT", "https://api.spotify.com/v1/me/player/pause")
    if resp.status_code == 404:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="No active device found"))
    if resp.status_code >= 400:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=resp.text))
    return "Paused"

@mcp.tool
async def next_track() -> str:
    resp = await _spotify_request("POST", "https://api.spotify.com/v1/me/player/next")
    if resp.status_code == 404:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="No active device found"))
    if resp.status_code >= 400:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=resp.text))
    return "Skipped to next track"

@mcp.tool
async def previous_track() -> str:
    resp = await _spotify_request("POST", "https://api.spotify.com/v1/me/player/previous")
    if resp.status_code == 404:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="No active device found"))
    if resp.status_code >= 400:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=resp.text))
    return "Went to previous track"

@mcp.tool
async def current_track() -> str:
    resp = await _spotify_request("GET", "https://api.spotify.com/v1/me/player/currently-playing")
    if resp.status_code == 204:
        return "No track currently playing"
    if resp.status_code == 404:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="No active device found"))
    if resp.status_code >= 400:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=resp.text))
    data = resp.json()
    item = data.get("item")
    if not item:
        return "No track currently playing"
    title = item.get("name", "Unknown")
    artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
    duration_ms = item.get("duration_ms", 0)
    duration = int(duration_ms // 1000)
    return f"{title} by {artists} ({duration}s)"

async def main():
    print("🚀 Starting Spotify MCP server on http://0.0.0.0:8087")
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8087)

if __name__ == "__main__":
    asyncio.run(main())
