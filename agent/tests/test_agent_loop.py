import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_loop import MicroserviceAgentLoop
from schemas import AgentProfile, AgentSession


def make_fake_tool(name: str) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.description = f"Description for {name}"
    tool.inputSchema = {"type": "object", "properties": {}}
    return tool


def make_fake_function_call(name: str, **args) -> MagicMock:
    call = MagicMock()
    call.name = name
    call.args = args
    return call


def make_mcp_session(tools: list) -> MagicMock:
    session = AsyncMock()
    list_response = MagicMock()
    list_response.tools = [make_fake_tool(t) for t in tools]
    session.list_tools = AsyncMock(return_value=list_response)

    call_response = MagicMock()
    call_content = MagicMock()
    call_content.text = '{"result": "ok"}'
    call_response.content = [call_content]
    session.call_tool = AsyncMock(return_value=call_response)
    return session


@pytest.fixture
def profile():
    return AgentProfile(
        id="profile-1",
        name="Test Agent",
        system_prompt="You are a helpful player.",
        difficulty_level=5,
    )


@pytest.fixture
def session():
    return AgentSession(id="agent-1", room_id="room-1", profile_id="profile-1")


def make_response(**kwargs) -> MagicMock:
    response = MagicMock()
    for key, value in kwargs.items():
        setattr(response, key, value)
    return response


class AsyncSendMessage:
    """Dual-purpose send_message_async that returns scripts of responses."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.calls = []
        self.__name__ = "send_message_async"

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.responses:
            return self.responses.pop(0)
        return make_response(function_calls=None)


async def test_equip_tools_on_game_type_change(profile, session):
    mcp_session = make_mcp_session(
        ["get_room_manifest", "get_chess_game_state", "play_chess_move", "send_chat_message"]
    )

    chat = AsyncMock()
    chat.history = []
    chat.send_message_async = AsyncSendMessage([make_response(function_calls=None)])

    loop = MicroserviceAgentLoop(profile, session, mcp_session)
    loop.chat = chat
    loop.model = MagicMock()

    call_response = MagicMock()
    call_content = MagicMock()
    call_content.text = (
        '{"game_type": "chess", "is_agent_turn": true, "game_status": "active"}'
    )
    call_response.content = [call_content]
    mcp_session.call_tool.return_value = call_response

    await loop.step()

    assert loop.current_game_type == "chess"
    assert mcp_session.call_tool.await_count == 1


async def test_no_tools_equipped_for_irrelevant_game(profile, session, monkeypatch):
    mcp_session = make_mcp_session(
        ["get_room_manifest", "get_chess_game_state", "play_chess_move"]
    )

    manifest_response = MagicMock()
    content = MagicMock()
    content.text = '{"game_type": "lands", "is_agent_turn": false, "game_status": "active"}'
    manifest_response.content = [content]
    mcp_session.call_tool.return_value = manifest_response

    loop = MicroserviceAgentLoop(profile, session, mcp_session)

    tools = await loop._get_active_tools_for_game("lands")

    # Only the manifest tool should be selected (no lands tools registered)
    declarations = tools[0]["function_declarations"]
    names = [d["name"] for d in declarations]
    assert names == ["get_room_manifest"]


async def test_skips_action_when_not_agents_turn(profile, session, monkeypatch):
    mcp_session = make_mcp_session(
        ["get_room_manifest", "get_chess_game_state", "play_chess_move"]
    )
    manifest_response = MagicMock()
    content = MagicMock()
    content.text = '{"game_type": "chess", "is_agent_turn": false, "game_status": "active"}'
    manifest_response.content = [content]
    mcp_session.call_tool.return_value = manifest_response

    loop = MicroserviceAgentLoop(profile, session, mcp_session)
    loop.current_game_type = "chess"
    loop.chat = AsyncMock()

    await loop.step()

    loop.chat.send_message_async.assert_not_awaited()


async def test_tool_calls_executed_and_result_feeds_back(profile, session):
    mcp_session = make_mcp_session(
        ["get_room_manifest", "get_chess_game_state", "play_chess_move"]
    )
    manifest_response = MagicMock()
    content = MagicMock()
    content.text = '{"game_type": "chess", "is_agent_turn": true, "game_status": "active"}'
    manifest_response.content = [content]
    mcp_session.call_tool.return_value = manifest_response

    play_move_call = make_fake_function_call(
        "play_chess_move", room_id="room-1", agent_id="agent-1", move_uci="e2e4"
    )
    first_response = make_response(function_calls=[play_move_call])
    second_response = make_response(function_calls=None)

    loop = MicroserviceAgentLoop(profile, session, mcp_session)
    loop.current_game_type = "chess"

    chat = AsyncMock()
    chat.history = []
    chat.send_message_async = AsyncSendMessage([first_response, second_response])
    loop.chat = chat
    loop.model = MagicMock()

    await loop.step()

    # First call is the "it's your turn" observation, second is the tool result feed
    assert len(chat.send_message_async.calls) == 2
    parent_parts = chat.send_message_async.calls[1][0][0]
    parts = parent_parts if isinstance(parent_parts, list) else [parent_parts]
    assert any("function_response" in str(part) for part in parts)


async def test_manifest_error_is_ignored(profile, session):
    mcp_session = make_mcp_session(["get_room_manifest"])
    manifest_response = MagicMock()
    content = MagicMock()
    content.text = '{"error": "Room not found."}'
    manifest_response.content = [content]
    mcp_session.call_tool.return_value = manifest_response

    loop = MicroserviceAgentLoop(profile, session, mcp_session)
    loop.chat = AsyncMock()

    await loop.step()

    loop.chat.send_message_async.assert_not_awaited()


async def test_start_loop_cancels_gracefully(profile, session):
    mcp_session = make_mcp_session(["get_room_manifest"])
    manifest_response = MagicMock()
    content = MagicMock()
    content.text = '{"game_type": "chess", "is_agent_turn": false, "game_status": "active"}'
    manifest_response.content = [content]
    mcp_session.call_tool.return_value = manifest_response

    loop = MicroserviceAgentLoop(profile, session, mcp_session)
    loop.chat = MagicMock()

    task = asyncio.create_task(loop.start_loop(poll_interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    await task  # should not raise CancelledError to caller

    assert loop.current_game_type == "chess"


async def test_handle_tool_calls_bounded_by_max_depth(profile, session):
    mcp_session = make_mcp_session(["get_room_manifest"])

    loop = MicroserviceAgentLoop(profile, session, mcp_session)
    loop._max_tool_calls = 3

    always_calling = make_response(
        function_calls=[make_fake_function_call("get_room_manifest")]
    )
    chat = AsyncMock()
    chat.history = []
    chat.send_message_async = AsyncSendMessage(
        [
            always_calling,
            always_calling,
            always_calling,
            always_calling,
            always_calling,
        ]
    )
    loop.chat = chat
    loop.model = MagicMock()

    result = await loop.handle_tool_calls(always_calling, depth=0)

    assert result is True
    assert len(chat.send_message_async.calls) == loop._max_tool_calls
