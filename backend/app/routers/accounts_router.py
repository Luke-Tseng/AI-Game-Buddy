from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from jose import JWTError

from app import auth
from app.config import settings
from app.dependencies import get_cosmos_service, get_user_service
from app.schemas import UserCreate, UserLogin, UserResponse
from app.services.cosmos_service import CosmosService
from app.services.user_service import UserService

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.post("/register", status_code=201, response_model=UserResponse)
async def create_account(
    response: Response,
    user: UserCreate,
    user_service: UserService = Depends(get_user_service),
):
    new_user = await user_service.create_user(user=user)

    auth._set_auth_cookies(response=response, user_id=new_user["id"])

    return new_user


@router.post("/login", response_model=UserResponse)
async def login_account(
    response: Response,
    user_login: UserLogin,
    cosmos_service: CosmosService = Depends(get_cosmos_service),
):
    user = await auth.authenticate_user(
        identifier=user_login.identifier,
        password=user_login.password,
        cosmos_service=cosmos_service,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth._set_auth_cookies(response=response, user_id=user["id"])

    user.pop("password", None)

    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_account(response: Response):
    response.delete_cookie(
        key="access_token", httponly=True, secure=True, samesite="none"
    )

    response.delete_cookie(
        key="refresh_token", httponly=True, secure=True, samesite="none"
    )

    return


# Call refresh endpoint if jwt/cookie is expired
@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
async def refresh_access_token(
    response: Response, refresh_token: Annotated[str | None, Cookie()] = None
):
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )
    try:
        # Validate the refresh token
        payload = auth.verify_refresh_token(refresh_token=refresh_token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth.create_access_token(
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
        return
    except JWTError as e:
        raise HTTPException(
            status_code=401, detail="Invalid or expired refresh token"
        ) from e


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    response: Response,
    user_id: str = Depends(auth.get_user_id_http),
    user_service: UserService = Depends(get_user_service),
):
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")
    await user_service.delete_user(user_id=user_id)

    # TODO: Check if user is in any rooms before deleting, don't want any stale data

    response.delete_cookie(
        key="access_token", httponly=True, secure=True, samesite="none"
    )

    response.delete_cookie(
        key="refresh_token", httponly=True, secure=True, samesite="none"
    )

    return


@router.get("/me", response_model=UserResponse)
async def get_user(
    user_id: str = Depends(auth.get_user_id_http),
    cosmos_service: CosmosService = Depends(get_cosmos_service),
):
    """
    Retrieves information about the current authenticated user.
    This endpoint requires a valid JWT access token.
    """

    user_data = await cosmos_service.get_item(
        item_id=user_id, partition_key=user_id, container_type="users"
    )

    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    user_data.pop("password", None)  # Don't send hashed password back

    return user_data
