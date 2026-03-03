from functools import lru_cache

from app.mcp_server import create_mcp_server
from app.services.blob_service import BlobService
from app.services.chat_service import ChatService
from app.services.connection_service import ConnectionService
from app.services.cosmos_service import CosmosService
from app.services.game_service_factory import GameServiceFactory
from app.services.redis_service import RedisService
from app.services.room_service import RoomService
from app.services.user_service import UserService


@lru_cache
def get_cosmos_service() -> CosmosService:
    return CosmosService()


@lru_cache
def get_blob_service() -> BlobService:
    return BlobService()


@lru_cache
def get_redis_service() -> RedisService:
    return RedisService()


@lru_cache
def get_game_service_factory() -> GameServiceFactory:
    return GameServiceFactory()


@lru_cache
def get_connection_service() -> ConnectionService:
    return ConnectionService(redis_service=get_redis_service())


@lru_cache
def get_user_service() -> UserService:
    return UserService(cosmos_service=get_cosmos_service())


@lru_cache
def get_room_service() -> RoomService:
    return RoomService(
        cosmos_service=get_cosmos_service(),
        redis_service=get_redis_service(),
        connection_service=get_connection_service(),
    )


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(
        cosmos_service=get_cosmos_service(),
        redis_service=get_redis_service(),
    )


@lru_cache
def get_mcp_server():
    return create_mcp_server(
        room_service=get_room_service(), game_service_factory=get_game_service_factory
    )
