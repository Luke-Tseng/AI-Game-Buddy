from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.schemas import AgentProfile, AgentSession
from app.services.agent_service import AgentService

TEST_MCP_SSE_URL = "http://localhost:8000/mcp/sse"
TEST_AGENT_SERVICE_URL = "http://localhost:8080"


@pytest.fixture
def profile():
    return AgentProfile(
        id="profile-1",
        name="Test Agent",
        system_prompt="You are a helpful player.",
        difficulty_level=5,
        traits=["strategic"],
    )


@pytest.fixture
def session():
    return AgentSession(
        id="agent-1", room_id="room-1", profile_id="profile-1", history=[]
    )


def make_agent_service(mcp_sse_url: str = TEST_MCP_SSE_URL) -> AgentService:
    return AgentService(mcp_sse_url=mcp_sse_url)


def make_response(**kwargs) -> MagicMock:
    response = MagicMock()
    for key, value in kwargs.items():
        setattr(response, key, value)
    return response


def make_async_client() -> MagicMock:
    """Builds a mock httpx.AsyncClient supporting the `async with` protocol."""
    client = MagicMock()
    client.post = AsyncMock(return_value=make_response())
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@patch("app.services.agent_service.settings")
def test_connect_agent_posts_payload(mock_settings, profile, session):
    mock_settings.AGENT_SERVICE_URL = TEST_AGENT_SERVICE_URL
    mock_settings.MCP_SSE_URL = TEST_MCP_SSE_URL

    service = make_agent_service()
    fake_client = make_async_client()

    with patch("httpx.AsyncClient", return_value=fake_client):
        import asyncio

        asyncio.run(service.connect_agent(profile=profile, session=session))

    fake_client.post.assert_awaited_once()
    args, kwargs = fake_client.post.await_args
    assert args[0] == f"{TEST_AGENT_SERVICE_URL}/connect"

    payload = kwargs["json"]
    assert payload["mcp_sse_url"] == TEST_MCP_SSE_URL
    assert payload["session"]["id"] == "agent-1"
    assert payload["session"]["room_id"] == "room-1"
    assert payload["profile"]["name"] == "Test Agent"


@patch("app.services.agent_service.settings")
def test_disconnect_agent_posts_params(mock_settings):
    mock_settings.AGENT_SERVICE_URL = TEST_AGENT_SERVICE_URL
    mock_settings.MCP_SSE_URL = TEST_MCP_SSE_URL

    service = make_agent_service()
    fake_client = make_async_client()

    with patch("httpx.AsyncClient", return_value=fake_client):
        import asyncio

        asyncio.run(service.disconnect_agent(room_id="room-1", agent_id="agent-1"))

    fake_client.post.assert_awaited_once()
    args, kwargs = fake_client.post.await_args
    assert args[0] == f"{TEST_AGENT_SERVICE_URL}/disconnect"
    assert kwargs["params"] == {"room_id": "room-1", "profile_id": "agent-1"}


@patch("app.services.agent_service.settings")
def test_connect_agent_raises_on_http_error(mock_settings, profile, session):
    mock_settings.AGENT_SERVICE_URL = TEST_AGENT_SERVICE_URL
    mock_settings.MCP_SSE_URL = TEST_MCP_SSE_URL

    service = make_agent_service()
    fake_client = make_async_client()
    error_response = make_response()
    error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "error",
        request=httpx.Request("POST", "http://x"),
        response=error_response,
    )
    fake_client.post = AsyncMock(return_value=error_response)

    with patch("httpx.AsyncClient", return_value=fake_client):
        import asyncio

        with pytest.raises(httpx.HTTPError):
            asyncio.run(service.connect_agent(profile=profile, session=session))
