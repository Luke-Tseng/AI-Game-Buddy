from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.services.chat_service import ChatService

# --- Test Data Constants ---
TEST_USER_ID = "user-123"
TEST_ROOM_ID = "room-abc"
TEST_CHAT_ID = "chat-xyz"


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
def chat_service(mock_cosmos_service, mock_redis_service) -> ChatService:
    """Provides an instance of ChatService with all dependencies mocked."""
    return ChatService(
        cosmos_service=mock_cosmos_service,
        redis_service=mock_redis_service,
    )


# --- Test Cases for each method ---


## Tests for create_chat
class TestCreateChat:
    @pytest.mark.asyncio
    async def test_create_chat_success(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE: Mock that the user is not currently in any chat room.
        chat_service.get_user_chat = AsyncMock(return_value=None)

        # ACT: Call the create_chat method, patching uuid to control the chat_id.
        with patch("uuid.uuid4", return_value=TEST_CHAT_ID):
            created_chat = await chat_service.create_chat(TEST_USER_ID, TEST_ROOM_ID)

        # ASSERT: Check that the returned Chat object is correct.
        assert created_chat.id == TEST_CHAT_ID
        assert created_chat.room_id == TEST_ROOM_ID
        assert TEST_USER_ID in created_chat.users

        # ASSERT: Verify that data was written to Redis correctly.
        assert mock_redis_service.dict_add.call_count == 1
        assert mock_redis_service.set_add.call_count == 2  # users and bots
        assert mock_redis_service.set_value.call_count == 2  # log and user's chat

        # ASSERT: Verify that data was written to Cosmos correctly.
        mock_cosmos_service.add_item.assert_awaited_once()
        mock_cosmos_service.patch_item.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_chat_fails_if_user_already_in_room(self, chat_service):
        # ARRANGE: Mock that the user is already in a chat room.
        chat_service.get_user_chat = AsyncMock(return_value="existing-chat")

        # ACT & ASSERT: Expect a 409 Conflict HTTPException.
        with pytest.raises(HTTPException) as exc_info:
            await chat_service.create_chat(TEST_USER_ID, TEST_ROOM_ID)

        assert exc_info.value.status_code == 409


## Tests for get_chat
class TestGetChat:
    @pytest.mark.asyncio
    async def test_get_chat_from_cache_success(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE: Simulate a full cache hit.
        mock_redis_service.dict_get_all.return_value = {
            "id": TEST_CHAT_ID,
            "room_id": TEST_ROOM_ID,
            "creator_id": "user1",
        }
        mock_redis_service.set_get.side_effect = [
            {"user1"},  # For users
            set(),  # For bots
        ]
        mock_redis_service.get_value.return_value = "[]"  # Empty chat log

        # ACT
        chat = await chat_service.get_chat(TEST_CHAT_ID)

        # ASSERT
        assert chat is not None
        assert chat.id == TEST_CHAT_ID
        mock_cosmos_service.get_item.assert_not_awaited()  # Should not touch the database

    @pytest.mark.asyncio
    async def test_get_chat_from_db_on_cache_miss(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE: Simulate a cache miss and a database hit.
        mock_redis_service.dict_get_all.return_value = {}  # Cache is empty
        db_data = {
            "id": TEST_CHAT_ID,
            "room_id": TEST_ROOM_ID,
            "users": ["user1"],
            "bots": [],
            "chat_log": [],
        }
        mock_cosmos_service.get_item.return_value = db_data

        # ACT
        chat = await chat_service.get_chat(TEST_CHAT_ID)

        # ASSERT
        assert chat is not None
        assert chat.id == TEST_CHAT_ID
        mock_cosmos_service.get_item.assert_awaited_once()
        # ASSERT: Check that the cache was repopulated.
        mock_redis_service.dict_add.assert_awaited_once()
        assert mock_redis_service.set_add.call_count == 2  # users and bots
        mock_redis_service.set_value.assert_awaited_once()  # chat log

    @pytest.mark.asyncio
    async def test_get_chat_not_found(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE: Simulate a cache miss and a database miss.
        mock_redis_service.dict_get_all.return_value = {}
        mock_cosmos_service.get_item.return_value = None

        # ACT
        chat = await chat_service.get_chat(TEST_CHAT_ID)

        # ASSERT
        assert chat is None


## Tests for get_chat_log
class TestGetChatLog:
    @pytest.mark.asyncio
    async def test_get_chat_log_from_cache_success(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE: Simulate a cache hit.
        mock_redis_service.get_value.return_value = (
            '[{"sender": "user1", "message": "hello"}]'
        )

        # ACT
        chat_log = await chat_service.get_chat_log(TEST_CHAT_ID)

        # ASSERT
        assert chat_log is not None
        assert len(chat_log) == 1
        assert chat_log[0].message == "hello"
        mock_cosmos_service.get_item.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_chat_log_from_db_on_cache_miss(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE: Simulate a cache miss and a database hit.
        mock_redis_service.get_value.return_value = None
        db_data = {"chat_log": [{"sender": "user1", "message": "hello from db"}]}
        mock_cosmos_service.get_item.return_value = db_data

        # ACT
        chat_log = await chat_service.get_chat_log(TEST_CHAT_ID)

        # ASSERT
        assert chat_log is not None
        assert len(chat_log) == 1
        assert chat_log[0].message == "hello from db"
        mock_cosmos_service.get_item.assert_awaited_once()


## Tests for add_message_to_chat
class TestAddMessageToChat:
    @pytest.mark.asyncio
    async def test_add_message_to_chat_success(self, chat_service, mock_redis_service):
        # ARRANGE
        from app.schemas import Chat

        chat_service.get_chat = AsyncMock(
            return_value=Chat(
                id=TEST_CHAT_ID,
                room_id=TEST_ROOM_ID,
                users={TEST_USER_ID},
                chat_log=[],
            )
        )
        message = "Hello, world!"

        # ACT
        chat_message = await chat_service.add_message_to_chat(
            TEST_CHAT_ID, TEST_USER_ID, message
        )

        # ASSERT
        assert chat_message.sender == TEST_USER_ID
        assert chat_message.message == message
        mock_redis_service.set_value.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_message_to_chat_fails_if_user_not_in_chat(self, chat_service):
        # ARRANGE
        from app.schemas import Chat

        chat_service.get_chat = AsyncMock(
            return_value=Chat(
                id=TEST_CHAT_ID,
                room_id=TEST_ROOM_ID,
                users={"another-user"},
                chat_log=[],
            )
        )
        message = "Hello, world!"

        # ACT & ASSERT
        with pytest.raises(HTTPException) as exc_info:
            await chat_service.add_message_to_chat(TEST_CHAT_ID, TEST_USER_ID, message)

        assert exc_info.value.status_code == 403


## Tests for leave_chat
class TestLeaveChat:
    @pytest.mark.asyncio
    async def test_leave_chat_success(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE
        from app.schemas import Chat

        chat_service.get_chat = AsyncMock(
            return_value=Chat(
                id=TEST_CHAT_ID,
                room_id=TEST_ROOM_ID,
                users={TEST_USER_ID, "another-user"},
                chat_log=[],
            )
        )
        mock_cosmos_service.get_item.return_value = {
            "users": [TEST_USER_ID, "another-user"]
        }

        # ACT
        await chat_service.leave_chat(TEST_CHAT_ID, TEST_USER_ID)

        # ASSERT
        mock_redis_service.set_remove.assert_awaited_once()
        mock_redis_service.delete_keys.assert_awaited_once()
        assert (
            mock_cosmos_service.patch_item.call_count == 2
        )  # once for chat, once for user

    @pytest.mark.asyncio
    async def test_leave_chat_deletes_chat_if_last_user(self, chat_service):
        # ARRANGE
        from app.schemas import Chat

        chat_service.get_chat = AsyncMock(
            return_value=Chat(
                id=TEST_CHAT_ID,
                room_id=TEST_ROOM_ID,
                users={TEST_USER_ID},
                chat_log=[],
            )
        )
        chat_service.delete_chat = AsyncMock()

        # ACT
        await chat_service.leave_chat(TEST_CHAT_ID, TEST_USER_ID)

        # ASSERT
        chat_service.delete_chat.assert_awaited_once_with(chat_id=TEST_CHAT_ID)


## Tests for delete_chat
class TestDeleteChat:
    @pytest.mark.asyncio
    async def test_delete_chat_success(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE
        chat_service.get_user_list = AsyncMock(return_value=[TEST_USER_ID])
        mock_redis_service.scan_keys.return_value = [f"chat:{TEST_CHAT_ID}:extra_key"]

        # ACT
        await chat_service.delete_chat(TEST_CHAT_ID)

        # ASSERT
        mock_redis_service.scan_keys.assert_awaited_once()
        mock_redis_service.delete_keys.assert_awaited_once()
        mock_cosmos_service.delete_item.assert_awaited_once()
        mock_cosmos_service.patch_item.assert_awaited_once()  # for the user


## Tests for get_user_chat
class TestGetUserChatroom:
    @pytest.mark.asyncio
    async def test_get_user_chat_from_cache(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE
        mock_redis_service.get_value.return_value = TEST_CHAT_ID

        # ACT
        chat_id = await chat_service.get_user_chat(TEST_USER_ID)

        # ASSERT
        assert chat_id == TEST_CHAT_ID
        mock_cosmos_service.get_item.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_user_chat_from_db(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE
        mock_redis_service.get_value.return_value = None
        mock_cosmos_service.get_item.return_value = {"chat": TEST_CHAT_ID}

        # ACT
        chat_id = await chat_service.get_user_chat(TEST_USER_ID)

        # ASSERT
        assert chat_id == TEST_CHAT_ID
        mock_redis_service.set_value.assert_awaited_once_with(
            key=f"user:{TEST_USER_ID}:chat", value=TEST_CHAT_ID
        )


## Tests for get_user_list
class TestGetUserList:
    @pytest.mark.asyncio
    async def test_get_user_list_from_cache(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE
        mock_redis_service.set_get.return_value = {TEST_USER_ID}

        # ACT
        user_list = await chat_service.get_user_list(TEST_CHAT_ID)

        # ASSERT
        assert user_list == {TEST_USER_ID}
        mock_cosmos_service.get_item.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_user_list_from_db(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE
        mock_redis_service.set_get.return_value = None
        mock_cosmos_service.get_item.return_value = {"users": [TEST_USER_ID]}

        # ACT
        user_list = await chat_service.get_user_list(TEST_CHAT_ID)

        # ASSERT
        assert user_list == [TEST_USER_ID]
        mock_redis_service.set_add.assert_awaited_once_with(
            key=f"chat:{TEST_CHAT_ID}:users", values=[TEST_USER_ID]
        )


## Tests for get_all_chats
class TestGetAllChats:
    @pytest.mark.asyncio
    async def test_get_all_chats_success(self, chat_service, mock_cosmos_service):
        # ARRANGE
        mock_cosmos_service.get_items_by_query.return_value = [{"id": TEST_CHAT_ID}]

        # ACT
        chat_list = await chat_service.get_all_chats()

        # ASSERT
        assert len(chat_list) == 1
        assert chat_list[0]["id"] == TEST_CHAT_ID
        mock_cosmos_service.get_items_by_query.assert_awaited_once()


## Tests for check_user_in_chat
class TestCheckUserInChat:
    @pytest.mark.asyncio
    async def test_check_user_in_chat_true(self, chat_service, mock_redis_service):
        # ARRANGE
        mock_redis_service.get_value.return_value = TEST_CHAT_ID

        # ACT
        is_in_chat = await chat_service.check_user_in_chat(TEST_USER_ID, TEST_CHAT_ID)

        # ASSERT
        assert is_in_chat is True

    @pytest.mark.asyncio
    async def test_check_user_in_chat_false(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE
        mock_redis_service.get_value.return_value = "another-chat-id"
        mock_cosmos_service.get_item.return_value = None

        # ACT
        is_in_chat = await chat_service.check_user_in_chat(TEST_USER_ID, TEST_CHAT_ID)

        # ASSERT
        assert is_in_chat is False


## Tests for join_chat
class TestJoinChat:
    @pytest.mark.asyncio
    async def test_join_chat_success(
        self, chat_service, mock_redis_service, mock_cosmos_service
    ):
        # ARRANGE
        joining_user_id = "user-456"
        chat_service.get_user_chat = AsyncMock(return_value=None)
        chat_service.get_user_list = AsyncMock(return_value=["user-123"])

        # ACT
        await chat_service.join_chat(TEST_CHAT_ID, joining_user_id)

        # ASSERT: Redis was updated
        mock_redis_service.set_add.assert_awaited_once_with(
            key=f"chat:{TEST_CHAT_ID}:users", values=[joining_user_id]
        )
        mock_redis_service.set_value.assert_awaited_once_with(
            key=f"user:{joining_user_id}:chat", value=TEST_CHAT_ID
        )

        # ASSERT: Cosmos was updated twice (once for the chat, once for the user)
        assert mock_cosmos_service.patch_item.call_count == 2

    @pytest.mark.asyncio
    async def test_join_chat_fails_if_user_already_in_room(self, chat_service):
        # ARRANGE
        chat_service.get_user_chat = AsyncMock(return_value="existing-chat")

        # ACT & ASSERT
        with pytest.raises(HTTPException) as exc_info:
            await chat_service.join_chat(TEST_CHAT_ID, TEST_USER_ID)

        assert exc_info.value.status_code == 409
