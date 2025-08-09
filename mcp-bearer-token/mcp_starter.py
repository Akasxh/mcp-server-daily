import asyncio
import json
from datetime import datetime, timedelta
from typing import Annotated
import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair
try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
except Exception:  # pragma: no cover - optional dependency
    build = Credentials = Request = None
from mcp import ErrorData, McpError
from mcp.server.auth.provider import AccessToken
from mcp.types import TextContent, ImageContent, INVALID_PARAMS, INTERNAL_ERROR
from pydantic import BaseModel, Field, AnyUrl

import markdownify
import httpx
import readabilipy
try:
    from legal_assistant import answer_question
except Exception:  # pragma: no cover - optional dependency
    def answer_question(_: str) -> str:
        return "Legal assistant unavailable."
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from expense_tracker import ExpenseStorage
from utility_dispatcher import split_bill as split_bill_func, scientific_calculator

# --- Load environment variables ---
load_dotenv()

TOKEN = os.environ.get("AUTH_TOKEN")
MY_NUMBER = os.environ.get("MY_NUMBER")
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")
EXPENSE_DB_PATH = os.environ.get("EXPENSE_DB_PATH", "expenses.db")
CALENDAR_TOKENS_FILE = os.environ.get("CALENDAR_TOKENS_FILE", "calendar_tokens.json")

# Spotify OAuth credentials
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REFRESH_TOKEN = os.environ.get("SPOTIFY_REFRESH_TOKEN")


SCOPES = ["https://www.googleapis.com/auth/calendar"]

# In-memory token store, persisted to disk
_calendar_tokens: dict[str, dict] = {}
if os.path.exists(CALENDAR_TOKENS_FILE):
    try:
        with open(CALENDAR_TOKENS_FILE, "r", encoding="utf-8") as f:
            _calendar_tokens.update(json.load(f))
    except Exception:
        pass

# Spotify access token
_spotify_access_token: str | None = None


def _save_calendar_tokens() -> None:
    try:
        with open(CALENDAR_TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump(_calendar_tokens, f)
    except Exception:
        pass

assert TOKEN is not None, "Please set AUTH_TOKEN in your .env file"
assert MY_NUMBER is not None, "Please set MY_NUMBER in your .env file"

expense_storage = ExpenseStorage(db_path=EXPENSE_DB_PATH)

# --- Auth Provider ---
class SimpleBearerAuthProvider(BearerAuthProvider):
    def __init__(self, token: str):
        k = RSAKeyPair.generate()
        super().__init__(public_key=k.public_key, jwks_uri=None, issuer=None, audience=None)
        self.token = token

    async def load_access_token(self, token: str) -> AccessToken | None:
        if token == self.token:
            return AccessToken(
                token=token,
                client_id="puch-client",
                scopes=["*"],
                expires_at=None,
            )
        return None

# --- Rich Tool Description model ---
class RichToolDescription(BaseModel):
    description: str
    use_when: str
    side_effects: str | None = None

# --- Fetch Utility Class ---
class Fetch:
    USER_AGENT = "Puch/1.0 (Autonomous)"

    @classmethod
    async def fetch_url(
        cls,
        url: str,
        user_agent: str,
        force_raw: bool = False,
    ) -> tuple[str, str]:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    follow_redirects=True,
                    headers={"User-Agent": user_agent},
                    timeout=30,
                )
            except httpx.HTTPError as e:
                raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Failed to fetch {url}: {e!r}"))

            if response.status_code >= 400:
                raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Failed to fetch {url} - status code {response.status_code}"))

            page_raw = response.text

        content_type = response.headers.get("content-type", "")
        is_page_html = "text/html" in content_type

        if is_page_html and not force_raw:
            return cls.extract_content_from_html(page_raw), ""

        return (
            page_raw,
            f"Content type {content_type} cannot be simplified to markdown, but here is the raw content:\n",
        )

    @staticmethod
    def extract_content_from_html(html: str) -> str:
        """Extract and convert HTML content to Markdown format."""
        ret = readabilipy.simple_json.simple_json_from_html_string(html, use_readability=True)
        if not ret or not ret.get("content"):
            return "<error>Page failed to be simplified from HTML</error>"
        content = markdownify.markdownify(ret["content"], heading_style=markdownify.ATX)
        return content

    @staticmethod
    async def google_search_links(query: str, num_results: int = 5) -> list[str]:
        """
        Perform a scoped DuckDuckGo search and return a list of job posting URLs.
        (Using DuckDuckGo because Google blocks most programmatic scraping.)
        """
        ddg_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        links = []

        async with httpx.AsyncClient() as client:
            resp = await client.get(ddg_url, headers={"User-Agent": Fetch.USER_AGENT})
            if resp.status_code != 200:
                return ["<error>Failed to perform search.</error>"]

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", class_="result__a", href=True):
            href = a["href"]
            if "http" in href:
                links.append(href)
            if len(links) >= num_results:
                break

        return links or ["<error>No results found.</error>"]

# --- Spotify Helper Functions ---
async def _refresh_spotify_access_token() -> str:
    """Refresh Spotify access token using refresh token."""
    if not all([SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN]):
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="Spotify credentials not configured"))
    
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
    """Make authenticated request to Spotify API."""
    global _spotify_access_token
    if _spotify_access_token is None:
        _spotify_access_token = await _refresh_spotify_access_token()

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {_spotify_access_token}"
    async with httpx.AsyncClient() as client:
        resp = await client.request(method, url, headers=headers, **kwargs)
    if resp.status_code == 401:
        _spotify_access_token = await _refresh_spotify_access_token()
        headers["Authorization"] = f"Bearer {_spotify_access_token}"
        async with httpx.AsyncClient() as client:
            resp = await client.request(method, url, headers=headers, **kwargs)
    return resp

# --- News Helper Functions ---
async def get_headlines(
    query: str | None = None,
    country: str | None = "us",
    category: str | None = None,
    limit: int = 5,
) -> dict:
    """Fetch top headlines from NewsAPI and return JSON data."""
    api_key = os.getenv("NEWS_API")
    if not api_key:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="NEWS_API environment variable not set"))

    params: dict[str, str | int] = {"apiKey": api_key, "pageSize": limit}
    if query:
        params["q"] = query
    if country:
        params["country"] = country
    if category:
        params["category"] = category

    async with httpx.AsyncClient() as client:
        resp = await client.get("https://newsapi.org/v2/top-headlines", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

# --- MCP Server Setup ---
mcp = FastMCP(
    "Job Finder MCP Server",
    auth=SimpleBearerAuthProvider(TOKEN),
)

# --- Tool: validate (required by Puch) ---
@mcp.tool
async def validate() -> str:
    return MY_NUMBER

# --- Tool: job_finder (now smart!) ---
JobFinderDescription = RichToolDescription(
    description="Smart job tool: analyze descriptions, fetch URLs, or search jobs based on free text.",
    use_when="Use this to evaluate job descriptions or search for jobs using freeform goals.",
    side_effects="Returns insights, fetched job descriptions, or relevant job links.",
)

@mcp.tool(description=JobFinderDescription.model_dump_json())
async def job_finder(
    user_goal: Annotated[str, Field(description="The user's goal (can be a description, intent, or freeform query)")],
    job_description: Annotated[str | None, Field(description="Full job description text, if available.")] = None,
    job_url: Annotated[AnyUrl | None, Field(description="A URL to fetch a job description from.")] = None,
    raw: Annotated[bool, Field(description="Return raw HTML content if True")] = False,
) -> str:
    """
    Handles multiple job discovery methods: direct description, URL fetch, or freeform search query.
    """
    if job_description:
        return (
            f"📝 **Job Description Analysis**\n\n"
            f"---\n{job_description.strip()}\n---\n\n"
            f"User Goal: **{user_goal}**\n\n"
            f"💡 Suggestions:\n- Tailor your resume.\n- Evaluate skill match.\n- Consider applying if relevant."
        )

    if job_url:
        content, _ = await Fetch.fetch_url(str(job_url), Fetch.USER_AGENT, force_raw=raw)
        return (
            f"🔗 **Fetched Job Posting from URL**: {job_url}\n\n"
            f"---\n{content.strip()}\n---\n\n"
            f"User Goal: **{user_goal}**"
        )

    if "look for" in user_goal.lower() or "find" in user_goal.lower():
        links = await Fetch.google_search_links(user_goal)
        return (
            f"🔍 **Search Results for**: _{user_goal}_\n\n" +
            "\n".join(f"- {link}" for link in links)
        )

    raise McpError(ErrorData(code=INVALID_PARAMS, message="Please provide either a job description, a job URL, or a search query in user_goal."))
 

# --- Google Calendar Tools ---


def connect_calendar(user_id: str, token_json: str) -> str:
    """Store OAuth tokens for a user after the authorization flow."""
    try:
        _calendar_tokens[user_id] = json.loads(token_json)
        _save_calendar_tokens()
        return "Calendar connected"
    except json.JSONDecodeError:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="Invalid token JSON"))


def get_calendar_service(user_id: str):
    """Return a Google Calendar service for the given user, if authorized."""
    if not build or not Credentials:
        return None
    token = _calendar_tokens.get(user_id)
    if not token:
        return None
    try:
        creds = Credentials.from_authorized_user_info(token, SCOPES)
        if creds.expired and creds.refresh_token and Request:
            try:
                creds.refresh(Request())
                _calendar_tokens[user_id] = json.loads(creds.to_json())
                _save_calendar_tokens()
            except Exception:
                return None
        return build("calendar", "v3", credentials=creds)
    except Exception:
        return None


def send_whatsapp_reminder(summary: str, start_iso: str) -> None:
    """Send a WhatsApp message for an event if Twilio credentials are configured."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    whatsapp_from = os.environ.get("TWILIO_WHATSAPP_FROM")
    to_number = os.environ.get("MY_NUMBER")
    if not all([account_sid, auth_token, whatsapp_from, to_number]):
        return
    from twilio.rest import Client

    client = Client(account_sid, auth_token)
    body = f"Reminder: {summary} at {start_iso}"
    try:
        client.messages.create(
            body=body,
            from_=whatsapp_from,
            to=f"whatsapp:+{to_number}",
        )
    except Exception:
        pass


AddEventDescription = RichToolDescription(
    description="Add an event to Google Calendar using the command 'add event <title> on <date> at <time>'.",
    use_when="Schedule a meeting or reminder at a specific date and time.",
    side_effects="Creates a new event in Google Calendar and optionally sends a WhatsApp reminder.",
)


@mcp.tool(description=AddEventDescription.model_dump_json())
async def add_event(
    user_id: Annotated[str, Field(description="User identifier")],
    title: Annotated[str, Field(description="Title of the event")],
    date: Annotated[str, Field(description="Event date in YYYY-MM-DD format")],
    time: Annotated[str, Field(description="Event time in HH:MM (24h) format")],
) -> str:
    service = get_calendar_service(user_id)
    if service is None:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="Calendar not authorized"))

    start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(TIME_ZONE))
    end_dt = start_dt + timedelta(hours=1)
    event = {
        "summary": title,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": TIME_ZONE},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": TIME_ZONE},
    }

    def _insert():
        return service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()

    created = await asyncio.to_thread(_insert)
    await asyncio.to_thread(send_whatsapp_reminder, title, start_dt.isoformat())

    return f"Event '{title}' scheduled for {start_dt.strftime('%Y-%m-%d %H:%M %Z')}" + (f" (id: {created.get('id')})" if created else "")


UpcomingEventsDescription = RichToolDescription(
    description="List upcoming Google Calendar events.",
    use_when="The user asks for the next scheduled events.",
    side_effects=None,
)


@mcp.tool(description=UpcomingEventsDescription.model_dump_json())
async def upcoming_events(
    user_id: Annotated[str, Field(description="User identifier")],
    count: Annotated[int, Field(description="Number of events to return", ge=1)] = 5,
) -> str:
    service = get_calendar_service(user_id)
    if service is None:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="Calendar not authorized"))

    now = datetime.utcnow().isoformat() + "Z"

    def _list():
        return (
            service.events()
            .list(
                calendarId=GOOGLE_CALENDAR_ID,
                timeMin=now,
                maxResults=count,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

    events = await asyncio.to_thread(_list)
    items = events.get("items", [])
    if not items:
        return "No upcoming events found."

    lines: list[str] = []
    for ev in items:
        start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
        if start and start.endswith("Z"):
            start = start[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(start).astimezone(ZoneInfo(TIME_ZONE))
            start_str = dt.strftime("%Y-%m-%d %H:%M %Z")
        except Exception:
            start_str = start
        lines.append(f"- {start_str} {ev.get('summary', '')}")

    return "\n".join(lines)


# --- Legal Question Answering ---
LegalQuestionDescription = RichToolDescription(
    description="Answer basic legal questions using a small knowledge base.",
    use_when="Use for landlord/tenant, traffic fines, simple contracts, or other common legal scenarios.",
    side_effects="Returns informational guidance with a legal disclaimer.",
)


@mcp.tool(description=LegalQuestionDescription.model_dump_json())
async def answer_legal_question(
    question: Annotated[str, Field(description="Legal question to ask")]
) -> str:
    return answer_question(question)


# Translation tool

TRANSLATE_DESCRIPTION = RichToolDescription(
    description="Translate text between languages using Google Translate.",
    use_when="The user needs text translated from one language to another.",
    side_effects="Makes a network request to an external translation service.",
)

@mcp.tool(description=TRANSLATE_DESCRIPTION.model_dump_json())
async def translate(
    text: Annotated[str, Field(description="Text to translate")],
    target_lang: Annotated[str, Field(description="Target language code, e.g., 'es' for Spanish")],
    source_lang: Annotated[str | None, Field(description="Source language code or 'auto' to detect automatically")] = "auto",
) -> str:
    """Translate text using the public Google Translate endpoint."""
    src = "auto" if not source_lang or source_lang.lower() == "auto" else source_lang.lower()
    dest = target_lang.lower()

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://translate.googleapis.com/translate_a/single",
                params={"client": "gtx", "sl": src, "tl": dest, "dt": "t", "q": text},
                timeout=10,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                raise McpError(ErrorData(code=INVALID_PARAMS, message="Unsupported language specified."))
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Translation API error: {e.response.text}"))
        except Exception as e:
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Translation request failed: {e}"))

    try:
        data = resp.json()
        translated = "".join(part[0] for part in data[0])
    except Exception as e:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Unexpected translation response: {e}"))

    return translated


# --- Expense and Bill Tools ---

SPLIT_BILL_DESCRIPTION = RichToolDescription(
    description="Split a bill among people with an optional tip.",
    use_when="Use when the user wants to know each person's share of a bill.",
)

@mcp.tool(name="split_bill", description=SPLIT_BILL_DESCRIPTION.model_dump_json())
async def split_bill(
    total: Annotated[float, Field(description="Total bill amount", gt=0)],
    num_people: Annotated[int, Field(description="Number of people", gt=0)],
    tip_percent: Annotated[float, Field(description="Tip percentage", ge=0)] = 0.0,
) -> float:
    try:
        return split_bill_func(total, num_people, tip_percent)
    except ValueError as e:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=str(e)))


ADD_EXPENSE_DESCRIPTION = RichToolDescription(
    description="Store an expense for a user identified by phone number.",
    use_when="The user reports spending and wants it saved.",
)

@mcp.tool(name="add_expense", description=ADD_EXPENSE_DESCRIPTION.model_dump_json())
async def add_expense(
    phone: Annotated[str, Field(description="User phone number")],
    amount: Annotated[float, Field(description="Expense amount", gt=0)],
    category: Annotated[str, Field(description="Expense category")],
    timestamp: Annotated[str | None, Field(description="ISO timestamp") ] = None,
) -> str:
    try:
        ts = datetime.fromisoformat(timestamp) if timestamp else datetime.now()
        expense_storage.add_expense(phone, amount, category, ts)
        return "Expense recorded"
    except ValueError as e:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=str(e)))


WEEKLY_SUMMARY_DESCRIPTION = RichToolDescription(
    description="Get this week's spending totals per category for a user.",
    use_when="The user asks for a weekly expense summary.",
)

@mcp.tool(name="weekly_summary", description=WEEKLY_SUMMARY_DESCRIPTION.model_dump_json())
async def weekly_summary(
    phone: Annotated[str, Field(description="User phone number")],
) -> dict[str, float]:
    try:
        return expense_storage.weekly_summary(phone)
    except ValueError as e:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=str(e)))


# --- Spotify Tools ---

SPOTIFY_PLAY_DESCRIPTION = RichToolDescription(
    description="Play a track by Spotify ID",
    use_when="Use this tool when the user wants to play a specific track on Spotify.",
    side_effects="The track will start playing on the user's active Spotify device.",
)

SPOTIFY_PAUSE_DESCRIPTION = RichToolDescription(
    description="Pause Spotify playback",
    use_when="Use this tool when the user wants to pause the currently playing track.",
    side_effects="Playback will be paused on the user's active Spotify device.",
)

SPOTIFY_NEXT_DESCRIPTION = RichToolDescription(
    description="Skip to the next track",
    use_when="Use this tool when the user wants to skip to the next track in their queue.",
    side_effects="The next track in the queue will start playing.",
)

SPOTIFY_PREVIOUS_DESCRIPTION = RichToolDescription(
    description="Go to the previous track",
    use_when="Use this tool when the user wants to go back to the previous track.",
    side_effects="The previous track will start playing.",
)

SPOTIFY_CURRENT_DESCRIPTION = RichToolDescription(
    description="Get information about the currently playing track",
    use_when="Use this tool when the user wants to know what's currently playing on Spotify.",
    side_effects="Returns information about the current track including title, artist, and duration.",
)

@mcp.tool(description=SPOTIFY_PLAY_DESCRIPTION.model_dump_json())
async def spotify_play(track_id: Annotated[str, Field(description="Spotify track ID")]) -> str:
    """Play a track by Spotify ID."""
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

@mcp.tool(description=SPOTIFY_PAUSE_DESCRIPTION.model_dump_json())
async def spotify_pause() -> str:
    """Pause Spotify playback."""
    resp = await _spotify_request("PUT", "https://api.spotify.com/v1/me/player/pause")
    if resp.status_code == 404:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="No active device found"))
    if resp.status_code >= 400:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=resp.text))
    return "Paused"

@mcp.tool(description=SPOTIFY_NEXT_DESCRIPTION.model_dump_json())
async def spotify_next() -> str:
    """Skip to the next track."""
    resp = await _spotify_request("POST", "https://api.spotify.com/v1/me/player/next")
    if resp.status_code == 404:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="No active device found"))
    if resp.status_code >= 400:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=resp.text))
    return "Skipped to next track"

@mcp.tool(description=SPOTIFY_PREVIOUS_DESCRIPTION.model_dump_json())
async def spotify_previous() -> str:
    """Go to the previous track."""
    resp = await _spotify_request("POST", "https://api.spotify.com/v1/me/player/previous")
    if resp.status_code == 404:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="No active device found"))
    if resp.status_code >= 400:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=resp.text))
    return "Went to previous track"

@mcp.tool(description=SPOTIFY_CURRENT_DESCRIPTION.model_dump_json())
async def spotify_current() -> str:
    """Get information about the currently playing track."""
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


# --- News Tools ---

NEWS_HEADLINES_DESCRIPTION = RichToolDescription(
    description="Fetch top headlines from NewsAPI",
    use_when="Use this tool when the user wants the latest news headlines.",
    side_effects="Returns JSON data with current news articles.",
)

@mcp.tool(description=NEWS_HEADLINES_DESCRIPTION.model_dump_json())
async def news_headlines(
    query: Annotated[str | None, Field(description="Search term", example="AI")] = None,
    country: Annotated[str | None, Field(description="Two-letter country code", example="us")] = "us",
    category: Annotated[str | None, Field(description="News category", example="technology")] = None,
    limit: Annotated[int, Field(gt=0, le=100, description="Number of articles to return")] = 5,
) -> dict:
    return await get_headlines(query=query, country=country, category=category, limit=limit)


# --- Calculator Tools ---

CALCULATOR_DESCRIPTION = RichToolDescription(
    description="Evaluate a mathematical expression",
    use_when="Use this tool when the user wants to perform mathematical calculations.",
    side_effects="Returns the result of the mathematical expression evaluation.",
)

@mcp.tool(description=CALCULATOR_DESCRIPTION.model_dump_json())
async def calculate(
    expression: Annotated[str, Field(description="The expression to evaluate")]
) -> float:
    """Evaluate a math expression using the scientific calculator."""
    try:
        return scientific_calculator(expression)
    except ValueError as exc:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=str(exc)))


# Image inputs and sending images

MAKE_IMG_BLACK_AND_WHITE_DESCRIPTION = RichToolDescription(
    description="Convert an image to black and white and save it.",
    use_when="Use this tool when the user provides an image URL and requests it to be converted to black and white.",
    side_effects="The image will be processed and saved in a black and white format.",
)

@mcp.tool(description=MAKE_IMG_BLACK_AND_WHITE_DESCRIPTION.model_dump_json())
async def make_img_black_and_white(
    puch_image_data: Annotated[str, Field(description="Base64-encoded image data to convert to black and white")] = None,
) -> list[TextContent | ImageContent]:
    import base64
    import io

    from PIL import Image

    try:
        image_bytes = base64.b64decode(puch_image_data)
        image = Image.open(io.BytesIO(image_bytes))

        bw_image = image.convert("L")

        buf = io.BytesIO()
        bw_image.save(buf, format="PNG")
        bw_bytes = buf.getvalue()
        bw_base64 = base64.b64encode(bw_bytes).decode("utf-8")

        return [ImageContent(type="image", mimeType="image/png", data=bw_base64)]
    except Exception as e:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=str(e)))

# --- Run MCP Server ---
async def main():
    print("🚀 Starting MCP server on http://0.0.0.0:8086")
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8086)

if __name__ == "__main__":
    asyncio.run(main())
