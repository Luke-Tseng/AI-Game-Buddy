"""auth.py

This module provides user authentication, password hashing, JWT token management, and user identification for both HTTP
and WebSocket connections using Argon2 for secure password storage.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, HTTPException, Response, WebSocket, status
from jose import JWTError, jwt
from pydantic import SecretStr

from app.config import settings
from app.services.cosmos_service import CosmosService

logger = logging.getLogger(__name__)

# Initialize Argon2 PasswordHasher
ph = PasswordHasher()

# Dummy hash to prevent user enumeration via timing attacks
DUMMY_HASH = ph.hash("dummy_password_for_timing_attack_mitigation")


def verify_password(password: SecretStr, hashed_password: str) -> bool:
    """Verify a plain text password against an Argon2 hashed password.

    Args:
        password (SecretStr): The plain text password to verify.
        hashed_password (str): The Argon2 hash to verify against.

    Returns:
        bool: True if the password matches the hash, False otherwise.
    """
    try:
        return ph.verify(hashed_password, password.get_secret_value())
    except VerifyMismatchError:
        return False
    except Exception as e:
        logger.error(f"Unexpected error during password verification: {e}")
        return False


def get_password_hash(password: SecretStr) -> str:
    """Generate an Argon2 hash for a plain text password.

    Args:
        password (SecretStr): The plain text password to hash.

    Returns:
        str: The Argon2 hashed password string suitable for database storage.
    """
    return ph.hash(password.get_secret_value())


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """Create a JWT access token for user authentication."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=30)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode, settings.ACCESS_TOKEN_SECRET, algorithm=settings.ALGORITHM
    )


def verify_access_token(access_token: str) -> dict[str, Any]:
    """Verify and decode a JWT access token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            access_token, settings.ACCESS_TOKEN_SECRET, algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError as e:
        logger.error("Invalid or expired JWT")
        raise credentials_exception from e


def verify_refresh_token(refresh_token: str) -> dict[str, Any]:
    """Verify and decode a JWT refresh token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            refresh_token,
            settings.REFRESH_TOKEN_SECRET,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError as e:
        logger.error("Invalid or expired refresh token")
        raise credentials_exception from e


def create_refresh_token(data: dict, expires_delta: timedelta | None = None):
    """Create a JWT refresh token for token renewal."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(days=14)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode, settings.REFRESH_TOKEN_SECRET, algorithm=settings.ALGORITHM
    )


async def authenticate_user(
    identifier: str, password: SecretStr, cosmos_service: CosmosService
) -> dict | None:
    """Authenticate a user using email/username and password with timing attack protection."""
    query = "SELECT * FROM c WHERE c.email_lower = @identifier or c.username_lower = @identifier"
    parameters = [{"name": "@identifier", "value": identifier.lower()}]

    users = await cosmos_service.get_items_by_query(
        query=query, container_type="users", parameters=parameters
    )

    # Use the dummy hash if no user is found to maintain consistent response time
    target_hash = users[0]["password"] if users else DUMMY_HASH

    if not verify_password(password, target_hash):
        logger.warning(f"Failed login attempt for identifier: {identifier}")
        return None

    if not users:
        # verify_password returned True for dummy (impossible) or we found no user
        return None

    user = users[0]
    logger.info(f"User '{user['username']}' authenticated")
    return user


async def get_user_id_http(
    access_token: Annotated[str | None, Cookie()] = None,
) -> str | None:
    """Extract user ID from JWT access token in HTTP requests."""
    if access_token is None:
        logger.error("JWT access token not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated: Missing session cookie",
        )

    payload = verify_access_token(access_token=access_token)
    user_id = payload.get("sub")

    if user_id is None:
        logger.error("User ID not found in JWT")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


async def get_user_id_websocket(websocket: WebSocket) -> str | None:
    """Extract user ID from JWT access token in WebSocket connections."""
    access_token = websocket.cookies.get("access_token")
    if access_token is None:
        logger.error("JWT access token not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated: Missing session cookie",
        )

    payload = verify_access_token(access_token=access_token)
    user_id = payload.get("sub")

    if user_id is None:
        logger.error("User ID not found in JWT")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


def _set_auth_cookies(response: Response, user_id: str):
    """Generates access/refresh tokens and sets them as secure HTTPOnly cookies."""
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_id}, expires_delta=access_token_expires
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=int(access_token_expires.total_seconds()),
    )

    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = create_refresh_token(
        data={"sub": user_id}, expires_delta=refresh_token_expires
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=int(refresh_token_expires.total_seconds()),
    )
