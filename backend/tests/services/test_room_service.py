from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas import RoomCreate
from app.services.room_service import RoomService

# --- Test Data Constants ---
TEST_USER_ID = "user-123"
TEST_ROOM_ID = "room-abc"
TEST_GAME_TYPE = "chess"
TEST_ROOM_NAME = "Test Room"


# --- Fixtures for Mocking Dependencies ---


@pytest.fixture
def mock_cosmos_service() -> AsyncMock:
    """Provides a mock for the asynchronous CosmosService."""
    return AsyncMock()


@pytest.fixture
def mock_redis_service() -> AsyncMock:
    """Provides a mock for the asynchronous RedisService."""
    return AsyncMock()


@pytest.fixture
def mock_connection_service() -> MagicMock:
    """
    Provides a mock for ConnectionService that handles both sync and async methods.
    We start with a MagicMock (for sync methods) and then attach an AsyncMock
    for any methods that need to be awaited.
    """
    mock = MagicMock()
    # RoomService calls `broadcast` asynchronously
    mock.broadcast = AsyncMock()
    return mock


@pytest.fixture
def room_service(
    mock_cosmos_service, mock_redis_service, mock_connection_service
) -> RoomService:
    """Provides an instance of RoomService with all dependencies mocked."""
    return RoomService(
        cosmos_service=mock_cosmos_service,
        redis_service=mock_redis_service,
        connection_service=mock_connection_service,
    )


# --- Test Cases for each method ---


## Tests for create_room
class TestCreateRoom:
    @pytest.mark.asyncio
    async def test_create_room_success(
        self, room_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE: Mock that the user is not currently in any room.
        room_service.get_user_room = AsyncMock(return_value=None)

        # ACT: Call the create_room method, patching uuid to control the room_id.
        with patch("uuid.uuid4", return_value=TEST_ROOM_ID):
            created_room = await room_service.create_room(
                RoomCreate(room_name=TEST_ROOM_NAME, game_type=TEST_GAME_TYPE),
                TEST_USER_ID,
            )

        # ASSERT: Check that the returned Room object is correct.
        assert created_room.id == TEST_ROOM_ID
        assert created_room.name == TEST_ROOM_NAME
        assert created_room.creator_id == TEST_USER_ID
        assert TEST_USER_ID in created_room.users

        # ASSERT: Verify that data was written to Redis correctly.
        assert mock_redis_service.dict_add.call_count == 1
        assert mock_redis_service.set_add.call_count == 1
        assert (
            mock_redis_service.set_value.call_count == 2
        )  # Once for state, once for user's room.

        # ASSERT: Verify that data was written to Cosmos correctly.
        mock_cosmos_service.add_item.assert_awaited_once()
        mock_cosmos_service.patch_item.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_room_fails_if_user_already_in_room(self, room_service):
        # ARRANGE: Mock that the user is already in a room.
        room_service.get_user_room = AsyncMock(return_value="existing-room")

        # ACT & ASSERT: Expect a 409 Conflict HTTPException.
        with pytest.raises(HTTPException) as exc_info:
            await room_service.create_room(
                RoomCreate(room_name=TEST_ROOM_NAME, game_type=TEST_GAME_TYPE),
                TEST_USER_ID,
            )

        assert exc_info.value.status_code == 409
        assert "User already in another room" in exc_info.value.detail


## Tests for join_room
class TestJoinRoom:
    @pytest.mark.asyncio
    async def test_join_room_success(
        self, room_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE
        joining_user_id = "user-456"
        room_service.get_user_room = AsyncMock(return_value=None)

        mock_room = MagicMock()
        mock_room.model_dump.return_value = {"users": ["user-123"]}

        room_service.get_room = AsyncMock(return_value=mock_room)

        # ACT
        await room_service.join_room(TEST_ROOM_ID, joining_user_id)

        # ASSERT: Redis was updated
        mock_redis_service.set_add.assert_awaited_once_with(
            key=f"room:{TEST_ROOM_ID}:users", values=[joining_user_id]
        )
        mock_redis_service.set_value.assert_awaited_once_with(
            key=f"user:{joining_user_id}:room", value=TEST_ROOM_ID
        )
        assert mock_redis_service.expire.call_count == 2

        # ASSERT: Cosmos was updated twice
        assert mock_cosmos_service.patch_item.call_count == 2

    @pytest.mark.asyncio
    async def test_join_room_fails_if_user_already_in_room(self, room_service):
        # ARRANGE
        room_service.get_user_room = AsyncMock(return_value="existing-room")

        # ACT & ASSERT
        with pytest.raises(HTTPException) as exc_info:
            await room_service.join_room(TEST_ROOM_ID, TEST_USER_ID)

        assert exc_info.value.status_code == 409


## Tests for get_room
class TestGetRoom:
    @pytest.mark.asyncio
    async def test_get_room_from_cache_success(
        self, room_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE: Simulate a full cache hit.
        mock_redis_service.dict_get_all.return_value = {
            "id": TEST_ROOM_ID,
            "room_id": TEST_ROOM_ID,
            "name": "Cached Room",
            "creator_id": "user1",
            "game_type": "chess",
        }
        mock_redis_service.set_get.return_value = {"user1"}
        mock_redis_service.get_value.return_value = "{}"

        # ACT
        room = await room_service.get_room(TEST_ROOM_ID)

        # ASSERT
        assert room is not None
        assert room.id == TEST_ROOM_ID
        assert room.name == "Cached Room"
        mock_cosmos_service.get_item.assert_not_awaited()  # Should not touch the database

    @pytest.mark.asyncio
    async def test_get_room_from_db_on_cache_miss(
        self, room_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE: Simulate a cache miss and a database hit.
        mock_redis_service.dict_get_all.return_value = {}  # Cache is empty
        db_data = {
            "id": TEST_ROOM_ID,
            "room_id": TEST_ROOM_ID,
            "name": "DB Room",
            "creator_id": "user1",
            "game_type": "chess",
            "users": ["user1"],
            "game_state": {},
        }
        mock_cosmos_service.get_item.return_value = db_data

        # ACT
        room = await room_service.get_room(TEST_ROOM_ID)

        # ASSERT
        assert room is not None
        assert room.name == "DB Room"
        mock_cosmos_service.get_item.assert_awaited_once()
        # ASSERT: Check that the cache was repopulated.
        mock_redis_service.dict_add.assert_awaited_once()
        mock_redis_service.set_add.assert_awaited_once()


## Tests for add_agent & remove_agent
class TestAddRemoveAgent:
    TEST_AGENT_ID = "agent-abc"

    @pytest.mark.asyncio
    async def test_add_agent_success(
        self, room_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE
        mock_room = MagicMock()
        mock_room.id = TEST_ROOM_ID
        room_service.get_room = AsyncMock(return_value=mock_room)
        room_service.get_room.return_value.model_dump.return_value = {
            "users": ["user-123"]
        }

        # ACT
        result = await room_service.add_agent(TEST_ROOM_ID, self.TEST_AGENT_ID)

        # ASSERT: Redis user set updated
        mock_redis_service.set_add.assert_awaited_once_with(
            key=f"room:{TEST_ROOM_ID}:users", values=[self.TEST_AGENT_ID]
        )
        mock_redis_service.expire.assert_awaited_once()

        # ASSERT: Cosmos patch adds agent to users
        mock_cosmos_service.patch_item.assert_awaited_once()
        _, kwargs = mock_cosmos_service.patch_item.await_args
        assert kwargs["item_id"] == TEST_ROOM_ID
        assert kwargs["container_type"] == "rooms"

        # ASSERT: Re-reads room after adding
        room_service.get_room.assert_awaited()
        assert result is not None

    @pytest.mark.asyncio
    async def test_add_agent_room_not_found(self, room_service):
        # ARRANGE
        room_service.get_room = AsyncMock(return_value=None)

        # ACT & ASSERT
        with pytest.raises(ValueError, match="Room not found"):
            await room_service.add_agent(TEST_ROOM_ID, self.TEST_AGENT_ID)

    @pytest.mark.asyncio
    async def test_remove_agent_success(
        self, room_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE
        mock_room = MagicMock()
        room_service.get_room = AsyncMock(return_value=mock_room)
        mock_cosmos_service.get_item.return_value = {
            "id": TEST_ROOM_ID,
            "users": [TEST_USER_ID, self.TEST_AGENT_ID],
        }

        # ACT
        await room_service.remove_agent(TEST_ROOM_ID, self.TEST_AGENT_ID)

        # ASSERT: Redis user set updated
        mock_redis_service.set_remove.assert_awaited_once_with(
            key=f"room:{TEST_ROOM_ID}:users", values=[self.TEST_AGENT_ID]
        )

        # ASSERT: Cosmos patch removes agent from users
        _, kwargs = mock_cosmos_service.patch_item.await_args
        assert kwargs["item_id"] == TEST_ROOM_ID
        assert kwargs["container_type"] == "rooms"

    @pytest.mark.asyncio
    async def test_remove_agent_not_in_room(
        self, room_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE
        mock_room = MagicMock()
        room_service.get_room = AsyncMock(return_value=mock_room)
        mock_cosmos_service.get_item.return_value = {
            "id": TEST_ROOM_ID,
            "users": [TEST_USER_ID],
        }

        # ACT & ASSERT
        with pytest.raises(HTTPException) as exc_info:
            await room_service.remove_agent(TEST_ROOM_ID, self.TEST_AGENT_ID)

        assert exc_info.value.status_code == 404
