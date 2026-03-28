from unittest.mock import AsyncMock, call

import pytest

from app.schemas import BroadcastPayload
from app.services.connection_service import ConnectionService

# --- Fixtures for Mocking and Setup ---


@pytest.fixture
def mock_redis_service() -> AsyncMock:
    """Provides a mock for the RedisService."""
    return AsyncMock()


@pytest.fixture
def connection_service(mock_redis_service: AsyncMock) -> ConnectionService:
    """Provides a ConnectionService instance initialized with a mock RedisService."""
    return ConnectionService(redis_service=mock_redis_service)


@pytest.fixture
def mock_websocket() -> AsyncMock:
    """Provides a mock WebSocket object with an async send_json method."""
    return AsyncMock()


# --- Test Cases ---


class TestConnectionService:
    @pytest.mark.asyncio
    async def test_connect_adds_user_to_active_connections(
        self, connection_service: ConnectionService, mock_websocket: AsyncMock
    ):
        # ACT: Connect a new user
        await connection_service.connect(mock_websocket, "user1")

        # ASSERT: The user and their websocket are stored in the internal dictionary
        assert "user1" in connection_service._active_connections
        assert connection_service._active_connections["user1"] is mock_websocket

    @pytest.mark.asyncio
    async def test_disconnect_removes_existing_user(
        self, connection_service: ConnectionService, mock_websocket: AsyncMock
    ):
        # ARRANGE: Connect a user first
        await connection_service.connect(mock_websocket, "user1")
        assert "user1" in connection_service._active_connections  # Sanity check

        # ACT: Disconnect the user
        connection_service.disconnect("user1")

        # ASSERT: The user is no longer in the dictionary
        assert "user1" not in connection_service._active_connections

    def test_disconnect_handles_nonexistent_user_gracefully(
        self, connection_service: ConnectionService
    ):
        # ACT & ASSERT: Disconnecting a user who isn't connected should not raise an error
        try:
            connection_service.disconnect("user_who_never_connected")
        except KeyError:
            pytest.fail("Disconnecting a nonexistent user should not raise a KeyError.")

    @pytest.mark.asyncio
    async def test_send_message_to_connected_user(
        self, connection_service: ConnectionService, mock_websocket: AsyncMock
    ):
        # ARRANGE: Connect a user with our mock websocket
        await connection_service.connect(mock_websocket, "user1")
        message = {"type": "GREETING", "text": "hello"}

        # ACT: Send a message to that user
        await connection_service.send_message(message, "user1")

        # ASSERT: The websocket's send_json method was called with the correct message
        mock_websocket.send_json.assert_awaited_once_with(message)

    @pytest.mark.asyncio
    async def test_send_message_to_disconnected_user(
        self, connection_service: ConnectionService, mock_websocket: AsyncMock
    ):
        # ARRANGE: Connect a user
        await connection_service.connect(mock_websocket, "user1")
        message = {"type": "GREETING", "text": "hello"}

        # ACT: Attempt to send a message to a different, unconnected user
        await connection_service.send_message(message, "user2")

        # ASSERT: The connected user's websocket was not used
        mock_websocket.send_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_users_when_all_are_active(
        self, connection_service: ConnectionService, mocker
    ):
        # ARRANGE
        user_list = ["user1", "user2", "user3"]
        message = {"type": "ANNOUNCEMENT", "text": "Server is up!"}
        payload = BroadcastPayload(user_list=user_list, message=message)

        # Mock the dependencies:
        # 1. Assume get_active_users_from_list returns the same list it was given.
        mocker.patch.object(
            connection_service, "get_active_users_from_list", return_value=user_list
        )

        # 2. Mock the send_message method to monitor its calls.
        mock_send = mocker.patch.object(
            connection_service, "send_message", new_callable=AsyncMock
        )

        # ACT
        await connection_service.broadcast(payload)

        # ASSERT
        # Check that send_message was called for every user.
        assert mock_send.call_count == len(user_list)

        expected_calls = [
            call(message=message, user_id="user1"),
            call(message=message, user_id="user2"),
            call(message=message, user_id="user3"),
        ]
        mock_send.assert_has_calls(expected_calls, any_order=True)

    @pytest.mark.asyncio
    async def test_broadcast_sends_only_to_active_users_from_mixed_list(
        self, connection_service: ConnectionService, mocker
    ):
        # ARRANGE
        full_user_list = ["active_user1", "inactive_user1", "active_user2"]
        active_users = [
            "active_user1",
            "active_user2",
        ]  # The subset that should get the message

        message = {"type": "GAME_UPDATE", "text": "Your turn!"}
        payload = BroadcastPayload(user_list=full_user_list, message=message)

        # Mock the dependencies:
        # 1. CRITICAL: Make get_active_users_from_list return ONLY the active subset.
        mocker.patch.object(
            connection_service, "get_active_users_from_list", return_value=active_users
        )

        # 2. Mock the send_message method to monitor its calls.
        mock_send = mocker.patch.object(
            connection_service, "send_message", new_callable=AsyncMock
        )

        # ACT
        await connection_service.broadcast(payload)

        # ASSERT
        # 1. The number of calls should match the number of ACTIVE users.
        assert mock_send.call_count == len(active_users)

        # 2. Check that a message was sent to each active user.
        expected_calls = [
            call(message=message, user_id="active_user1"),
            call(message=message, user_id="active_user2"),
        ]
        mock_send.assert_has_calls(expected_calls, any_order=True)

        # 3. Explicitly check that no message was sent to the inactive user.
        called_user_ids = [c.kwargs["user_id"] for c in mock_send.call_args_list]
        assert "inactive_user1" not in called_user_ids

    @pytest.mark.asyncio
    async def test_get_active_users_from_list(
        self, connection_service: ConnectionService, mock_websocket: AsyncMock
    ):
        # ARRANGE: Connect some users but not others
        await connection_service.connect(mock_websocket, "user1")
        await connection_service.connect(mock_websocket, "user3")

        all_users_to_check = ["user1", "user2", "user3", "user4"]

        # ACT
        active_users = connection_service.get_active_users_from_list(all_users_to_check)

        # ASSERT: The result should only contain the users who are actually connected
        assert sorted(active_users) == ["user1", "user3"]

    @pytest.mark.asyncio
    async def test_publish_event_calls_redis_service_correctly(
        self, connection_service: ConnectionService, mock_redis_service: AsyncMock
    ):
        # ARRANGE
        channel = "game-updates"
        user_list = {"user1", "user2"}
        message_data = {"move": "e4"}

        # ACT
        await connection_service.publish_event(channel, user_list, message_data)

        # ASSERT: Check that the redis service's method was called
        mock_redis_service.publish_message.assert_awaited_once()

        # ASSERT: Inspect the arguments to ensure the message was constructed correctly
        call_kwargs = mock_redis_service.publish_message.call_args.kwargs
        assert call_kwargs["channel_name"] == "global-channel"

        published_message = call_kwargs["message"]
        assert published_message["channel"] == channel
        assert set(published_message["payload"]["user_list"]) == user_list
        assert published_message["payload"]["message"] == message_data
