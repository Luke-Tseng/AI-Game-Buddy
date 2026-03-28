from unittest.mock import AsyncMock, MagicMock

import pytest
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError
from fastapi import HTTPException

from app.services import cosmos_service

# --- Mocks for Azure SDK objects ---


@pytest.fixture
def mock_container_client() -> AsyncMock:
    """Provides a fully asynchronous mock for a container client."""
    mock = AsyncMock()

    # query_items needs to return an async iterator. We create a simple
    # async generator to mock this behavior.
    async def mock_async_iterator(items_to_return=None):
        if items_to_return is None:
            items_to_return = []
        for item in items_to_return:
            yield item

    mock.query_items.return_value = mock_async_iterator()
    return mock


@pytest.fixture
def mock_db_client(mock_container_client: AsyncMock) -> MagicMock:
    """Provides a mock for a database client. Its methods are synchronous."""
    mock = MagicMock()
    mock.get_container_client.return_value = mock_container_client
    return mock


@pytest.fixture
def mock_cosmos_client(mock_db_client: MagicMock) -> MagicMock:
    """
    Provides a mock for the main CosmosClient. Its setup methods are synchronous.
    """
    mock = MagicMock()
    mock.get_database_client.return_value = mock_db_client
    return mock


# --- Tests for the __init__ method ---


class TestCosmosServiceInitialization:
    def test_init_with_endpoint_and_credential(
        self, mocker, mock_cosmos_client, monkeypatch
    ):
        # ARRANGE
        monkeypatch.setattr(cosmos_service.settings, "COSMOS_ENDPOINT", "test_endpoint")
        # Patch the credential and client classes
        mocker.patch("app.services.cosmos_service.DefaultAzureCredential")
        mocker.patch(
            "app.services.cosmos_service.CosmosClient", return_value=mock_cosmos_client
        )

        # ACT
        service = cosmos_service.CosmosService()

        # ASSERT
        cosmos_service.CosmosClient.assert_called_once()
        assert service.client is not None
        service.client.get_database_client.assert_called_once()

    def test_init_no_config_raises_error(self, monkeypatch):
        monkeypatch.setattr(cosmos_service.settings, "COSMOS_ENDPOINT", None)
        with pytest.raises(ValueError, match="Database configuration missing"):
            cosmos_service.CosmosService()


# --- Tests for the public service methods ---


class TestCosmosServiceMethods:
    @pytest.fixture(autouse=True)
    def setup_service(self, mocker, mock_cosmos_client, monkeypatch):
        """
        This fixture bypasses the real __init__ and injects our mocks directly,
        providing a clean service instance for each test.
        """
        # ARRANGE
        monkeypatch.setattr(cosmos_service.settings, "COSMOS_ENDPOINT", "test_endpoint")
        # Patch the credential and client classes
        mocker.patch("app.services.cosmos_service.DefaultAzureCredential")
        mocker.patch(
            "app.services.cosmos_service.CosmosClient", return_value=mock_cosmos_client
        )

        self.service = cosmos_service.CosmosService()
        self.mock_users_container = self.service.users_container_client
        self.mock_rooms_container = self.service.rooms_container_client

    @pytest.mark.asyncio
    async def test_add_item_succeeds(self):
        item = {"id": "user123"}
        await self.service.add_item(item, "users")
        self.mock_users_container.create_item.assert_awaited_once_with(body=item)

    @pytest.mark.asyncio
    async def test_get_item_succeeds(self):
        self.mock_rooms_container.read_item.return_value = {"id": "room123"}
        result = await self.service.get_item("room123", "room123", "rooms")
        assert result == {"id": "room123"}

    @pytest.mark.asyncio
    async def test_get_item_returns_none_when_not_found(self):
        self.mock_users_container.read_item.side_effect = CosmosResourceNotFoundError()
        result = await self.service.get_item("123", "123", "users")
        assert result is None

    @pytest.mark.asyncio
    async def test_patch_item_raises_404_when_not_found(self):
        self.mock_users_container.patch_item.side_effect = CosmosResourceNotFoundError()
        with pytest.raises(HTTPException) as exc_info:
            await self.service.patch_item("123", "123", {}, "users")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_item_raises_http_exception_on_cosmos_error(self):
        self.mock_users_container.delete_item.side_effect = CosmosHttpResponseError()
        with pytest.raises(HTTPException) as exc_info:
            await self.service.delete_item("123", "123", "users")
        assert exc_info.value.status_code == 500
