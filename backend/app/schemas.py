import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, SecretStr, model_validator


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: SecretStr = Field(
        json_schema_extra={"format": "password"},
    )


class User(BaseModel):
    id: str
    user_id: str
    username: str
    username_lower: str
    email: EmailStr
    email_lower: str
    password: str


class UserResponse(BaseModel):
    user_id: str = Field(alias="id")
    username: str
    email: EmailStr
    room: str | None = (
        None  # TODO: Possibly make this a list if we want users to be able to join multiple rooms at once
    )


class UserLogin(BaseModel):
    identifier: str
    password: SecretStr = Field(
        json_schema_extra={"format": "password"},
    )


class Room(BaseModel):
    id: str
    room_id: str
    name: str
    creator_id: str
    game_type: str
    status: str = "waiting"
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    users: set[str]
    game_state: dict = Field(default_factory=dict)


class RoomCreate(BaseModel):
    room_name: str
    game_type: str


class BroadcastPayload(BaseModel):
    user_list: set[str]
    message: dict[str, Any]

    @model_validator(mode="after")
    def validate_payload_state(self) -> "BroadcastPayload":
        # user_list and message must not be empty
        if len(self.user_list) == 0:
            raise ValueError(
                f"User list was empty while validating BroadcastPayload {self}"
            )
        elif len(self.message) == 0:
            raise ValueError(
                f"Message was empty while validating BroadcastPayload {self}"
            )

        return self


class PubSubMessage(BaseModel):
    channel: str
    payload: BroadcastPayload


class GameUpdate(BaseModel):
    room_id: str
    game_state: dict


# ---------- Chat Service------------------
class ChatMessage(BaseModel):
    sender: str
    message: str
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class Chat(BaseModel):
    id: str  # chat id
    room_id: str | None = None
    users: set[str] = Field(default_factory=set)
    agents: set[str] = Field(default_factory=set)
    chat_log: list[ChatMessage] = Field(default_factory=list)


# ---------- Agents ------------------
class AgentProfile(BaseModel):
    id: str  # profile id
    name: str
    system_prompt: str  # Initial prompt for agent
    difficulty_level: int = Field(
        default=5, gt=0, le=10
    )  # playing difficulty from 1-10
    traits: list[str] = []


class AgentSession(BaseModel):
    id: str  # session id
    room_id: str
    profile_id: str  # profile selected for session
    history: list[dict] = []
