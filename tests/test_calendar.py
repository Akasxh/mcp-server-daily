import asyncio
import sys
import os
from pathlib import Path
import pytest
import types

# Stub dotenv if not installed
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda: None))

# Stub fastmcp and its bearer auth provider
fastmcp = types.ModuleType("fastmcp")

class DummyFastMCP:
    def __init__(self, *args, **kwargs):
        pass

    def tool(self, *args, **kwargs):
        def wrapper(func):
            return func

        return wrapper

fastmcp.FastMCP = DummyFastMCP
sys.modules.setdefault("fastmcp", fastmcp)

server_mod = types.ModuleType("fastmcp.server")
auth_mod = types.ModuleType("fastmcp.server.auth")
providers_mod = types.ModuleType("fastmcp.server.auth.providers")
bearer_mod = types.ModuleType("fastmcp.server.auth.providers.bearer")

class DummyBearerAuthProvider:
    def __init__(self, *args, **kwargs):
        pass

class DummyKeyPair:
    public_key = None

    @staticmethod
    def generate():
        return DummyKeyPair()

bearer_mod.BearerAuthProvider = DummyBearerAuthProvider
bearer_mod.RSAKeyPair = DummyKeyPair

sys.modules.setdefault("fastmcp.server", server_mod)
sys.modules.setdefault("fastmcp.server.auth", auth_mod)
sys.modules.setdefault("fastmcp.server.auth.providers", providers_mod)
sys.modules.setdefault("fastmcp.server.auth.providers.bearer", bearer_mod)

# Stub MCP core libraries
mcp_mod = types.ModuleType("mcp")

class ErrorData:
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message


class McpError(Exception):
    def __init__(self, data):
        self.data = data


mcp_mod.ErrorData = ErrorData
mcp_mod.McpError = McpError
sys.modules.setdefault("mcp", mcp_mod)

mcp_types = types.ModuleType("mcp.types")
mcp_types.TextContent = object
mcp_types.ImageContent = object
mcp_types.INVALID_PARAMS = "INVALID_PARAMS"
mcp_types.INTERNAL_ERROR = "INTERNAL_ERROR"
sys.modules.setdefault("mcp.types", mcp_types)

mcp_server = types.ModuleType("mcp.server")
mcp_server_auth = types.ModuleType("mcp.server.auth")
mcp_auth_provider = types.ModuleType("mcp.server.auth.provider")

class AccessToken:
    def __init__(self, *args, **kwargs):
        pass

mcp_auth_provider.AccessToken = AccessToken

sys.modules.setdefault("mcp.server", mcp_server)
sys.modules.setdefault("mcp.server.auth", mcp_server_auth)
sys.modules.setdefault("mcp.server.auth.provider", mcp_auth_provider)

# Stub other third-party modules
markdownify_mod = types.ModuleType("markdownify")
markdownify_mod.markdownify = lambda *args, **kwargs: ""
sys.modules.setdefault("markdownify", markdownify_mod)

class DummyAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, *args, **kwargs):
        class Resp:
            status_code = 200
            text = ""
            headers = {}

        return Resp()


httpx_mod = types.ModuleType("httpx")
httpx_mod.AsyncClient = DummyAsyncClient
httpx_mod.HTTPError = Exception
sys.modules.setdefault("httpx", httpx_mod)

readabilipy_mod = types.ModuleType("readabilipy")
class SimpleJSON:
    @staticmethod
    def simple_json_from_html_string(html, use_readability=True):
        return {"content": ""}

readabilipy_mod.simple_json = SimpleJSON
sys.modules.setdefault("readabilipy", readabilipy_mod)

legal_mod = types.ModuleType("legal_assistant")
legal_mod.answer_question = lambda *args, **kwargs: ""
sys.modules.setdefault("legal_assistant", legal_mod)

pydantic_mod = types.ModuleType("pydantic")

class BaseModel:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def model_dump_json(self):
        return "{}"

def Field(*args, **kwargs):
    return None

pydantic_mod.BaseModel = BaseModel
pydantic_mod.Field = Field
pydantic_mod.AnyUrl = str
sys.modules.setdefault("pydantic", pydantic_mod)

# Stub google libraries
googleapiclient = types.ModuleType("googleapiclient")
discovery_mod = types.ModuleType("googleapiclient.discovery")
discovery_mod.build = lambda *args, **kwargs: None
googleapiclient.discovery = discovery_mod
sys.modules.setdefault("googleapiclient", googleapiclient)
sys.modules.setdefault("googleapiclient.discovery", discovery_mod)

google_mod = types.ModuleType("google")
oauth2_mod = types.ModuleType("google.oauth2")
credentials_mod = types.ModuleType("google.oauth2.credentials")

class DummyCredentials:
    @staticmethod
    def from_authorized_user_file(*args, **kwargs):
        return None

credentials_mod.Credentials = DummyCredentials
oauth2_mod.credentials = credentials_mod
google_mod.oauth2 = oauth2_mod
sys.modules.setdefault("google", google_mod)
sys.modules.setdefault("google.oauth2", oauth2_mod)
sys.modules.setdefault("google.oauth2.credentials", credentials_mod)

# Required environment variables for mcp_starter
os.environ.setdefault("AUTH_TOKEN", "test")
os.environ.setdefault("MY_NUMBER", "123")

# Load the mcp_starter module from the subdirectory
sys.path.append(str(Path(__file__).resolve().parents[1] / "mcp-bearer-token"))
import mcp_starter


class FakeEvents:
    def insert(self, calendarId, body):
        class Res:
            def execute(self):
                return {"id": "abc123"}
        return Res()

    def list(self, calendarId, timeMin, maxResults, singleEvents, orderBy):
        class Res:
            def execute(self):
                return {
                    "items": [
                        {"start": {"dateTime": "2025-01-01T10:00:00Z"}, "summary": "Test Event"}
                    ]
                }
        return Res()


class FakeService:
    def events(self):
        return FakeEvents()


def test_add_event_unauthorized(monkeypatch):
    monkeypatch.setattr(mcp_starter, "GOOGLE_CALENDAR_AUTH_URL", "https://auth.example")
    monkeypatch.setattr(mcp_starter, "get_calendar_service", lambda uid: None)
    with pytest.raises(mcp_starter.McpError) as exc:
        asyncio.run(mcp_starter.add_event("Meeting", "2025-01-01", "09:00", "user1"))
    assert "connect_calendar" in exc.value.data.message
    assert "https://auth.example" in exc.value.data.message


def test_add_event_authorized(monkeypatch):
    monkeypatch.setattr(mcp_starter, "get_calendar_service", lambda uid: FakeService())
    monkeypatch.setattr(mcp_starter, "send_whatsapp_reminder", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp_starter, "TIME_ZONE", "UTC")
    res = asyncio.run(mcp_starter.add_event("Meeting", "2025-01-01", "09:00", "user1"))
    assert "Event 'Meeting' scheduled" in res


def test_upcoming_events_unauthorized(monkeypatch):
    monkeypatch.setattr(mcp_starter, "GOOGLE_CALENDAR_AUTH_URL", "https://auth.example")
    monkeypatch.setattr(mcp_starter, "get_calendar_service", lambda uid: None)
    with pytest.raises(mcp_starter.McpError) as exc:
        asyncio.run(mcp_starter.upcoming_events("user1"))
    assert "connect_calendar" in exc.value.data.message


def test_upcoming_events_authorized(monkeypatch):
    monkeypatch.setattr(mcp_starter, "get_calendar_service", lambda uid: FakeService())
    monkeypatch.setattr(mcp_starter, "TIME_ZONE", "UTC")
    res = asyncio.run(mcp_starter.upcoming_events("user1"))
    assert "Test Event" in res
