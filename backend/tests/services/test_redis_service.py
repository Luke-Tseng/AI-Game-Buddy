import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError, RedisError

from app.services.redis_service import RedisService


# --- Tests for the __init__ method ---
class TestRedisServiceInitialization:
    @patch("app.services.redis_service.aioredis")
    def test_init_success(self, mock_aioredis, monkeypatch):
        """
        Tests that the Redis client is created successfully when a URL is provided.
        """
        # ARRANGE
        monkeypatch.setattr(
            "app.services.redis_service.settings.REDIS_CONNECTION_URL",
            "redis://localhost",
        )

        # ACT
        service = RedisService()

        # ASSERT
        mock_aioredis.from_url.assert_called_once_with(
            "redis://localhost", decode_responses=True
        )
        assert service.r is not None

    @patch("app.services.redis_service.aioredis")
    def test_init_no_url(self, mock_aioredis, monkeypatch):
        """
        Tests that the Redis client is None when the URL is missing.
        """
        # ARRANGE
        monkeypatch.setattr(
            "app.services.redis_service.settings.REDIS_CONNECTION_URL", None
        )

        # ACT
        service = RedisService()

        # ASSERT
        mock_aioredis.from_url.assert_not_called()
        assert service.r is None

    @patch("app.services.redis_service.aioredis")
    def test_init_connection_error(self, mock_aioredis, monkeypatch):
        """
        Tests that the client is None if the connection fails during initialization.
        """
        # ARRANGE
        monkeypatch.setattr(
            "app.services.redis_service.settings.REDIS_CONNECTION_URL",
            "redis://localhost",
        )
        mock_aioredis.from_url.side_effect = ConnectionError("Failed to connect")

        # ACT
        service = RedisService()

        # ASSERT
        assert service.r is None


# --- Tests for the public service methods ---
class TestRedisServiceMethods:
    @pytest.fixture(autouse=True)
    def setup_service(self, monkeypatch):
        """
        This fixture automatically runs before each test in this class.
        It patches aioredis, injects a mock client, and creates a service instance.
        """
        self.mock_redis_client = AsyncMock()
        # Patch the aioredis library within the redis_service module
        with patch("app.services.redis_service.aioredis") as mock_aioredis:
            monkeypatch.setattr(
                "app.services.redis_service.settings.REDIS_CONNECTION_URL",
                "redis://localhost",
            )
            mock_aioredis.from_url.return_value = self.mock_redis_client
            self.redis_service = RedisService()

    @pytest.mark.asyncio
    async def test_publish_message(self):
        message = {"data": "test"}
        await self.redis_service.publish_message("my-channel", message)
        self.mock_redis_client.publish.assert_awaited_once_with(
            channel="my-channel", message=json.dumps(message)
        )

    @pytest.mark.asyncio
    async def test_set_value(self):
        await self.redis_service.set_value("my_key", "my_value")
        self.mock_redis_client.set.assert_awaited_once_with("my_key", "my_value")

    @pytest.mark.asyncio
    async def test_get_value(self):
        self.mock_redis_client.get.return_value = "expected_value"
        result = await self.redis_service.get_value("my_key")
        assert result == "expected_value"
        self.mock_redis_client.get.assert_awaited_once_with("my_key")

    @pytest.mark.asyncio
    async def test_dict_add(self):
        mapping = {"field1": "value1"}
        await self.redis_service.dict_add("my_hash", mapping)
        self.mock_redis_client.hset.assert_awaited_once_with("my_hash", mapping=mapping)

    @pytest.mark.asyncio
    async def test_dict_get_all(self):
        self.mock_redis_client.hgetall.return_value = {"field1": "value1"}
        result = await self.redis_service.dict_get_all("my_hash")
        assert result == {"field1": "value1"}
        self.mock_redis_client.hgetall.assert_awaited_once_with("my_hash")

    @pytest.mark.asyncio
    async def test_set_add(self):
        values = {"member1", "member2"}
        await self.redis_service.set_add("my_set", values)

        # ASSERT: Check the call without demanding a specific order for the members.
        self.mock_redis_client.sadd.assert_awaited_once()

        # Get the actual arguments the mock was called with
        call_args = self.mock_redis_client.sadd.call_args.args

        # Check the key is correct
        assert call_args[0] == "my_set"

        # Compare the passed members as a set to ignore their order
        assert set(call_args[1:]) == values

    @pytest.mark.asyncio
    async def test_set_get(self):
        self.mock_redis_client.smembers.return_value = {"member1", "member2"}
        result = await self.redis_service.set_get("my_set")
        assert result == {"member1", "member2"}
        self.mock_redis_client.smembers.assert_awaited_once_with("my_set")

    @pytest.mark.asyncio
    async def test_set_is_member(self):
        self.mock_redis_client.sismember.return_value = True
        result = await self.redis_service.set_is_member("my_set", "member1")
        assert result is True
        self.mock_redis_client.sismember.assert_awaited_once_with("my_set", "member1")

    @pytest.mark.asyncio
    async def test_set_remove(self):
        values = {"member1", "member2"}
        await self.redis_service.set_remove("my_set", values)

        # ASSERT: Check the call without demanding a specific order.
        self.mock_redis_client.srem.assert_awaited_once()
        call_args = self.mock_redis_client.srem.call_args.args
        assert call_args[0] == "my_set"
        assert set(call_args[1:]) == values

    @pytest.mark.asyncio
    async def test_expire(self):
        await self.redis_service.expire("my_key", 3600)
        self.mock_redis_client.expire.assert_awaited_once_with("my_key", 3600)

    @pytest.mark.asyncio
    async def test_delete_keys(self):
        keys = ["key1", "key2"]
        await self.redis_service.delete_keys(keys)
        self.mock_redis_client.delete.assert_awaited_once_with("key1", "key2")

    @pytest.mark.asyncio
    async def test_scan_keys(self):
        # ARRANGE: Create an async generator that will act as our mock iterator.
        async def mock_iterator():
            yield "my_pattern:key1"
            yield "my_pattern:key2"

        # ARRANGE: Replace the `scan_iter` method on our mock client with a
        # standard MagicMock that returns the async generator directly.
        self.mock_redis_client.scan_iter = MagicMock(return_value=mock_iterator())

        # ACT
        result = await self.redis_service.scan_keys("my_pattern")

        # ASSERT
        self.mock_redis_client.scan_iter.assert_called_once_with("my_pattern:*")
        assert result == ["my_pattern:key1", "my_pattern:key2"]

    @pytest.mark.asyncio
    async def test_method_raises_on_redis_error(self):
        """
        Tests that RedisError is correctly re-raised by the service methods.
        """
        self.mock_redis_client.get.side_effect = RedisError("Something went wrong")

        with pytest.raises(RedisError):
            await self.redis_service.get_value("my_key")

    @pytest.mark.asyncio
    async def test_method_fails_if_client_is_unavailable(self):
        """
        Tests that a 503 HTTPException is raised if the client is not initialized.
        """
        # ARRANGE: Create a service instance where self.r is None
        service_no_client = RedisService()
        service_no_client.r = None

        # ACT & ASSERT
        with pytest.raises(HTTPException) as exc_info:
            await service_no_client.get_value("any_key")

        assert exc_info.value.status_code == 503
        assert "Redis service unavailable" in exc_info.value.detail
