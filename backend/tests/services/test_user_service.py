from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app.schemas import User, UserCreate
from app.services.user_service import UserService

# --- Fixtures for Mocking and Test Data ---


@pytest.fixture
def mock_cosmos_service() -> AsyncMock:
    """Provides a mock for the asynchronous CosmosService."""
    return AsyncMock()


@pytest.fixture
def user_service(mock_cosmos_service: AsyncMock) -> UserService:
    """Provides a UserService instance with a mocked CosmosService."""
    return UserService(cosmos_service=mock_cosmos_service)


@pytest.fixture
def sample_user_create() -> UserCreate:
    """Provides a valid UserCreate sample object for tests."""
    return UserCreate(
        username="testuser",
        email="test@example.com",
        password=SecretStr("a-strong-password"),
    )


# --- Test Cases ---


## Tests for create_user
class TestCreateUser:
    @pytest.mark.asyncio
    async def test_create_user_success(
        self, user_service, mock_cosmos_service, sample_user_create
    ):
        # ARRANGE: Mock the database to show that neither the email nor the username exists.
        mock_cosmos_service.get_items_by_query.return_value = []

        # ACT: Attempt to create the user. We patch uuid to get a predictable user ID.
        with patch("uuid.uuid4", return_value="test-uuid"):
            await user_service.create_user(sample_user_create)

        # ASSERT: Verify that the database was checked for both email and username.
        assert mock_cosmos_service.get_items_by_query.call_count == 2

        # ASSERT: Verify that the new user was added to the database.
        mock_cosmos_service.add_item.assert_awaited_once()

        # ASSERT: Check the contents of the item that was saved to the database.
        saved_item = mock_cosmos_service.add_item.call_args.kwargs["item"]
        assert saved_item["id"] == "test-uuid"
        assert saved_item["username"] == sample_user_create.username
        assert saved_item["email_lower"] == sample_user_create.email.lower()
        assert "password" in saved_item
        assert saved_item["password"] != sample_user_create.password.get_secret_value()

    @pytest.mark.asyncio
    async def test_create_user_fails_if_email_exists(
        self, user_service, mock_cosmos_service, sample_user_create
    ):
        # ARRANGE: Mock the database to return an existing user when checking the email.
        mock_cosmos_service.get_items_by_query.return_value = [
            {"email": "test@example.com"}
        ]

        # ACT & ASSERT: The call should raise a 409 Conflict error.
        with pytest.raises(HTTPException) as exc_info:
            await user_service.create_user(sample_user_create)

        assert exc_info.value.status_code == 409
        assert "Email already registered" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_user_fails_if_username_exists(
        self, user_service, mock_cosmos_service, sample_user_create
    ):
        # ARRANGE: Create a dictionary that looks like a full user record from the DB.
        existing_user_data = {
            "id": "existing-uuid",
            "user_id": "existing-uuid",
            "username": "testuser",
            "username_lower": "testuser",
            "email": "some-other-email@example.com",
            "email_lower": "some-other-email@example.com",
            "password": "a-real-hashed-password",
        }

        # ARRANGE: Mock a two-stage DB response with the complete user data.
        mock_cosmos_service.get_items_by_query.side_effect = [
            [],  # For the email check (it passes)
            [
                existing_user_data
            ],  # For the username check (it fails with complete data)
        ]

        # ACT & ASSERT: The call should raise a 409 Conflict error.
        with pytest.raises(HTTPException) as exc_info:
            await user_service.create_user(sample_user_create)

        assert exc_info.value.status_code == 409
        assert "Username already exists" in exc_info.value.detail

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "invalid_username",
        [
            "a",  # too short
            "ab",  # too short
            "a_very_long_username_that_is_over_20_chars",  # too long
            "invalid-username-!",  # invalid characters
            " spaces ",  # invalid characters
        ],
    )
    async def test_create_user_fails_with_invalid_username(
        self, user_service, sample_user_create, invalid_username
    ):
        # ARRANGE
        sample_user_create.username = invalid_username

        # ACT & ASSERT: The call should raise a 400 Bad Request error.
        with pytest.raises(HTTPException) as exc_info:
            await user_service.create_user(sample_user_create)

        assert exc_info.value.status_code == 400
        assert "Invalid username" in exc_info.value.detail


## Tests for get_user_by_username
class TestGetUserByUsername:
    @pytest.mark.asyncio
    async def test_get_user_by_username_success(
        self, user_service, mock_cosmos_service
    ):
        # ARRANGE: Mock the DB to return a single user.
        username = "found_user"
        user_data = {
            "id": "123",
            "user_id": "123",
            "username": username,
            "username_lower": username.lower(),
            "email": "a@b.com",
            "email_lower": "a@b.com",
            "password": "hashed_password",
        }
        mock_cosmos_service.get_items_by_query.return_value = [user_data]

        # ACT
        user = await user_service.get_user_by_username(username)

        # ASSERT
        assert user is not None
        assert isinstance(user, User)
        assert user.username == username

    @pytest.mark.asyncio
    async def test_get_user_by_username_not_found(
        self, user_service, mock_cosmos_service
    ):
        # ARRANGE: Mock the DB to return an empty list.
        mock_cosmos_service.get_items_by_query.return_value = []

        # ACT
        user = await user_service.get_user_by_username("not_found_user")

        # ASSERT
        assert user is None

    @pytest.mark.asyncio
    async def test_get_user_by_username_multiple_found_raises_error(
        self, user_service, mock_cosmos_service
    ):
        # ARRANGE: Mock the DB to return two users with the same username.
        mock_cosmos_service.get_items_by_query.return_value = [{}, {}]

        # ACT & ASSERT: Expect a 409 Conflict error.
        with pytest.raises(HTTPException) as exc_info:
            await user_service.get_user_by_username("multiple_user")

        assert exc_info.value.status_code == 409


## Tests for delete_user
class TestDeleteUser:
    @pytest.mark.asyncio
    async def test_delete_user_success(self, user_service, mock_cosmos_service):
        # ARRANGE
        user_id = "user-to-delete"

        # ACT
        await user_service.delete_user(user_id)

        # ASSERT: Verify that the delete method was called on the service with the correct parameters.
        mock_cosmos_service.delete_item.assert_awaited_once_with(
            item_id=user_id, partition_key=user_id, container_type="users"
        )
