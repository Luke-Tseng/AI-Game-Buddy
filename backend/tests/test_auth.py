from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, WebSocket, status
from pydantic import SecretStr

from app import auth

# --- Test Password Hashing ---


def test_get_password_hash():
    """
    Tests that a password gets hashed into a non-empty string.
    """
    password = SecretStr("myStrongPassword123")
    hashed_password = auth.get_password_hash(password)
    assert isinstance(hashed_password, str)
    assert len(hashed_password) > 0


def test_verify_password():
    """
    Tests that password verification works for both correct and incorrect passwords.
    """
    password = SecretStr("myStrongPassword123")
    hashed_password = auth.get_password_hash(password)

    # Test with the correct password
    assert auth.verify_password(password, hashed_password) is True

    # Test with an incorrect password
    assert auth.verify_password(SecretStr("wrongPassword"), hashed_password) is False


# --- Test Token Creation and Verification ---


@pytest.fixture
def mock_settings():
    """A pytest fixture to provide a mock settings object for tests."""
    # Create a generic mock object instead of instantiating Settings
    mock = MagicMock()

    # Set the attributes that your auth functions will need
    mock.ACCESS_TOKEN_SECRET = "test_access_secret"
    mock.REFRESH_TOKEN_SECRET = "test_refresh_secret"
    mock.ALGORITHM = "HS256"

    return mock


def test_create_and_verify_access_token(mocker, mock_settings):
    """
    Tests creating a valid access token and then verifying it.
    """
    # Patch the settings object used inside the auth module
    mocker.patch.object(auth, "settings", mock_settings)

    user_id = "user-123"
    token = auth.create_access_token(data={"sub": user_id})
    payload = auth.verify_access_token(token)

    assert payload.get("sub") == user_id


def test_create_and_verify_refresh_token(mocker, mock_settings):
    """
    Tests creating a valid refresh token and then verifying it.
    """
    mocker.patch.object(auth, "settings", mock_settings)

    user_id = "user-123"
    token = auth.create_refresh_token(data={"sub": user_id})
    payload = auth.verify_refresh_token(token)

    assert payload.get("sub") == user_id


def test_verify_access_token_expired(mocker, mock_settings):
    """
    Tests that an expired token raises an HTTPException.
    """
    mocker.patch.object(auth, "settings", mock_settings)

    # Create a token that expired 1 minute ago
    expired_token = auth.create_access_token(
        data={"sub": "user-123"}, expires_delta=timedelta(minutes=-1)
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.verify_access_token(expired_token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_verify_access_token_invalid_signature(mocker, mock_settings):
    """
    Tests that a token with an invalid signature raises an HTTPException.
    """
    mocker.patch.object(auth, "settings", mock_settings)

    # Create a token with the correct secret
    token = auth.create_access_token(data={"sub": "user-123"})

    # Now, try to decode it with the WRONG secret
    mock_settings.ACCESS_TOKEN_SECRET = "a-different-secret"

    with pytest.raises(HTTPException):
        auth.verify_access_token(token)


# --- Test User Authentication ---


@pytest.fixture
def mock_cosmos_service():
    """A pytest fixture to provide a mock CosmosService."""
    return AsyncMock()


@pytest.mark.asyncio
async def test_authenticate_user_success(mock_cosmos_service):
    """
    Tests successful user authentication with correct credentials.
    """
    password = SecretStr("password123")
    hashed_password = auth.get_password_hash(password)
    mock_user = {
        "id": "user-123",
        "username": "testuser",
        "email_lower": "test@example.com",
        "username_lower": "testuser",
        "password": hashed_password,
    }

    # Configure the mock to return our test user
    mock_cosmos_service.get_items_by_query.return_value = [mock_user]

    authenticated_user = await auth.authenticate_user(
        identifier="testuser", password=password, cosmos_service=mock_cosmos_service
    )

    assert authenticated_user is not None
    assert authenticated_user["id"] == "user-123"
    mock_cosmos_service.get_items_by_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_authenticate_user_not_found(mock_cosmos_service):
    """
    Tests authentication failure when the user does not exist.
    """
    # Configure the mock to return an empty list (user not found)
    mock_cosmos_service.get_items_by_query.return_value = []

    result = await auth.authenticate_user(
        identifier="nouser",
        password=SecretStr("password123"),
        cosmos_service=mock_cosmos_service,
    )

    assert result is None


@pytest.mark.asyncio
async def test_authenticate_user_wrong_password(mock_cosmos_service):
    """
    Tests authentication failure with a correct username but wrong password.
    """
    hashed_password = auth.get_password_hash(SecretStr("correct_password"))
    mock_user = {"password": hashed_password}
    mock_cosmos_service.get_items_by_query.return_value = [mock_user]

    result = await auth.authenticate_user(
        identifier="testuser",
        password=SecretStr("wrong_password"),
        cosmos_service=mock_cosmos_service,
    )

    assert result is None


# --- Test User ID Extraction ---


@pytest.mark.asyncio
async def test_get_user_id_http_success(mocker, mock_settings):
    """
    Tests successfully getting a user ID from a valid HTTP token cookie.
    """
    mocker.patch.object(auth, "settings", mock_settings)
    token = auth.create_access_token(data={"sub": "http-user"})

    user_id = await auth.get_user_id_http(access_token=token)
    assert user_id == "http-user"


@pytest.mark.asyncio
async def test_get_user_id_http_no_token():
    """
    Tests that an exception is raised if the token cookie is missing.
    """
    with pytest.raises(HTTPException) as exc_info:
        await auth.get_user_id_http(access_token=None)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Missing session cookie" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_user_id_websocket_success(mocker, mock_settings):
    """
    Tests successfully getting a user ID from a valid WebSocket token cookie.
    """
    mocker.patch.object(auth, "settings", mock_settings)
    token = auth.create_access_token(data={"sub": "ws-user"})

    # Create a mock WebSocket object with the required cookie
    mock_websocket = MagicMock(spec=WebSocket)
    mock_websocket.cookies = {"access_token": token}

    user_id = await auth.get_user_id_websocket(websocket=mock_websocket)
    assert user_id == "ws-user"


@pytest.mark.asyncio
async def test_get_user_id_websocket_no_token():
    """
    Tests that an exception is raised if the WebSocket is missing the token cookie.
    """
    mock_websocket = MagicMock(spec=WebSocket)
    mock_websocket.cookies = {}  # No access_token cookie

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_user_id_websocket(websocket=mock_websocket)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
