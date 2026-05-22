"""services/room_service.py

This module defines the RoomService, which is responsible for managing
the business logic and state of game rooms.
"""

import json
import logging
import uuid
from typing import Any

from fastapi import HTTPException

from app.schemas import Chat, ChatMessage
from app.services.cosmos_service import CosmosService
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        cosmos_service: CosmosService,
        redis_service: RedisService,
    ):
        self._cosmos_service = cosmos_service
        self._redis_service = redis_service

    async def create_chat(self, user_id: str, room_id: str | None = None) -> Chat:
        if not user_id:
            raise ValueError("User ID missing on chat creation")

        # Currently user can only be in one chat room at a time
        if await self.get_user_chat(user_id=user_id):
            logger.warning(f"User '{user_id}' currently in another chat room")
            raise HTTPException(
                status_code=409,
                detail="User already in another chat room",
            )

        chat_id = str(uuid.uuid4())
        chat = Chat(
            id=chat_id,
            room_id=room_id,
            users={user_id},  # Only user can create a chat room
        )

        cosmos_chat = chat.model_dump(mode="json")
        redis_chat = chat.model_dump(exclude={"users", "chat_log", "bots"}, mode="json")

        try:
            # Write new chat into redis
            await self._redis_service.dict_add(
                key=f"chat:{chat_id}", mapping=redis_chat
            )
            await self._redis_service.expire(f"chat:{chat_id}", 86400)

            await self._redis_service.set_add(
                key=f"chat:{chat_id}:users", values=chat.users
            )
            await self._redis_service.expire(f"chat:{chat_id}:users", 86400)

            await self._redis_service.set_add(
                key=f"chat:{chat_id}:bots", values=chat.bots
            )
            await self._redis_service.expire(f"chat:{chat_id}:bots", 86400)

            await self._redis_service.set_value(
                key=f"chat:{chat_id}:log", value=chat.chat_log
            )
            await self._redis_service.expire(f"chat:{chat_id}:log", 86400)

            # Write user into new chat room
            await self._redis_service.set_value(
                key=f"user:{user_id}:chat", value=chat_id
            )
        except HTTPException as e:
            logger.warning(f"Redis unavailable for creating chat room: {e}")

        # Write new chat room into cosmos
        await self._cosmos_service.add_item(item=cosmos_chat, container_type="chats")

        # Add current chat room to user information.
        # User can only be in one chat at a time for now
        patch_operation = [{"op": "add", "path": "/chat", "value": chat_id}]

        await self._cosmos_service.patch_item(
            item_id=user_id,
            partition_key=user_id,
            patch_operations=patch_operation,
            container_type="users",
        )

        return chat

    # Currently not supporting bots
    async def join_chat(self, chat_id: str, user_id: str):
        if not chat_id:
            raise ValueError("Chat ID missing on join chat room")
        if not user_id:
            raise ValueError("User ID missing on join chat room")

        if await self.get_user_chat(user_id=user_id):
            logger.warning(
                f"User '{user_id}' currently in another chat, unable to join {chat_id}"
            )
            raise HTTPException(
                status_code=409,
                detail="User already in another chat",
            )
        user_list = await self.get_user_list(chat_id=chat_id)

        # Sanity check to ensure chat room exists
        if user_list is None:
            logger.error("User list not found in redis and cosmos")
            raise ValueError("User list missing in redis and cosmos")
        try:
            await self._redis_service.set_add(
                key=f"chat:{chat_id}:users", values=[user_id]
            )
            await self._redis_service.set_value(
                key=f"user:{user_id}:chat", value=chat_id
            )
            await self._redis_service.expire(f"user:{user_id}:chat", 86400)
            await self._redis_service.expire(f"chat:{chat_id}:users", 86400)
        except HTTPException as e:
            logger.warning(f"Redis unavailable for joining room: {e}")

        # Add user to room list
        patch_operation = [{"op": "add", "path": "/users/-", "value": user_id}]

        await self._cosmos_service.patch_item(
            item_id=chat_id,
            partition_key=chat_id,
            patch_operations=patch_operation,
            container_type="chats",
        )

        # Add current chat to user information
        patch_operation = [{"op": "add", "path": "/chat", "value": chat_id}]

        await self._cosmos_service.patch_item(
            item_id=user_id,
            partition_key=user_id,
            patch_operations=patch_operation,
            container_type="users",
        )

    async def leave_chat(self, chat_id: str, user_id: str):
        if not chat_id:
            raise ValueError("Chat ID missing on leave chat")
        if not user_id:
            raise ValueError("User ID missing on leave chat")

        chat = await self.get_chat(chat_id=chat_id)

        # Only user in chat, delete chat
        if len(chat.users) == 1:
            logger.info(f"No more users in chat '{chat_id}', deleting chat")
            await self.delete_chat(chat_id=chat_id)
            return

        if chat is None:
            logger.warning(
                f"Chat '{chat_id}' not found when leaving for user '{user_id}'"
            )
            raise HTTPException(
                status_code=404,
                detail="Chat not found",
            )
        try:
            await self._redis_service.set_remove(
                key=f"chat:{chat_id}:users", values=[user_id]
            )

            await self._redis_service.delete_keys(keys=[f"user:{user_id}:chat"])
        except HTTPException as e:
            logger.warning(f"Redis unavailable for leaving chat: {e}")

        try:
            item = await self._cosmos_service.get_item(
                item=chat_id, partition_key=chat_id
            )
            user_list = item.get("users", [])

            if user_id in user_list:
                index_to_remove = user_list.index(user_id)

                patch_operation = [
                    {"op": "remove", "path": f"/users/{index_to_remove}"}
                ]

                await self._cosmos_service.patch_item(
                    item_id=chat_id,
                    partition_key=chat_id,
                    patch_operations=patch_operation,
                    container_type="chats",
                )
            else:
                logger.warning(f"User list not found in cosmos for chat '{chat_id}'")
                raise HTTPException(
                    status_code=404,
                    detail=f"User '{user_id}' not found in chat '{chat_id}'",
                )
        except ValueError:
            logger.warning(f"Tag '{chat_id}' not found in the list, no changes made.")
        except Exception as e:
            logger.error(f"An error occurred: {e}")

        patch_operation = [{"op": "remove", "path": "/chat"}]

        await self._cosmos_service.patch_item(
            item_id=user_id,
            partition_key=user_id,
            patch_operations=patch_operation,
            container_type="users",
        )

    async def get_chat(self, chat_id: str) -> Chat | None:
        try:
            chat_data = await self._redis_service.dict_get_all(key=f"chat:{chat_id}")
            if chat_data:
                await self._redis_service.expire(f"chat:{chat_id}", 86400)
            user_set = await self._redis_service.set_get(key=f"chat:{chat_id}:users")
            if user_set:
                await self._redis_service.expire(f"chat:{chat_id}:users", 86400)
            bot_set = await self._redis_service.set_get(key=f"chat:{chat_id}:bots")
            if bot_set is not None:
                await self._redis_service.expire(f"chat:{chat_id}:bots", 86400)
            chat_log = await self._redis_service.get_value(key=f"chat:{chat_id}:log")
            if chat_log is not None:
                await self._redis_service.expire(f"chat:{chat_id}:log", 86400)
            if chat_data and user_set is not None and chat_log is not None:
                # Combine the data into a single dictionary
                full_chat_data = chat_data | {
                    "users": user_set,
                    "bots": bot_set,
                    "chat_log": json.loads(chat_log),
                }
                return Chat.model_validate(full_chat_data)
        except HTTPException as e:
            logger.warning(f"Redis unavailable for getting chat: {e}")
        except Exception as e:
            logger.warning(
                f"Failed to reconstruct chat from Redis for '{chat_id}': {e}. Fetching from DB"
            )

        logger.info(f"Chat '{chat_id}' is incomplete in cache, checking database")

        chat_data_from_db = await self._cosmos_service.get_item(
            item_id=chat_id, partition_key=chat_id, container_type="chats"
        )

        if chat_data_from_db:
            try:
                chat_object = Chat.model_validate(chat_data_from_db)
                logger.info(f"Restoring chat '{chat_id}' to Redis cache.")

                # Separate the data for storage
                chat_data = chat_object.model_dump(
                    exclude={"users", "bots", "chat_log"}, mode="json"
                )
                try:
                    # Write to the separate Redis keys
                    await self._redis_service.dict_add(
                        key=f"chat:{chat_id}", mapping=chat_data
                    )
                    await self._redis_service.set_add(
                        key=f"chat:{chat_id}:users", values=chat_object.users
                    )
                    await self._redis_service.set_add(
                        key=f"chat:{chat_id}:bots", values=chat_object.bots
                    )
                    await self._redis_service.set_value(
                        key=f"chat:{chat_id}:log",
                        value=json.dumps(chat_object.chat_log),
                    )
                    await self._redis_service.expire(f"chat:{chat_id}", 86400)
                    await self._redis_service.expire(f"chat:{chat_id}:users", 86400)
                    await self._redis_service.expire(f"chat:{chat_id}:bots", 86400)
                    await self._redis_service.expire(f"chat:{chat_id}:log", 86400)
                except HTTPException as e:
                    logger.warning(f"Redis unavailable for writing new chat: {e}")

                return chat_object
            except Exception as e:
                logger.error(f"Invalid chat data in CosmosDB for '{chat_id}': {e}")
                return None

        logger.warning(f"Chat '{chat_id}' not found in any data source.")
        return None

    async def get_chat_log(self, chat_id: str) -> list[ChatMessage] | None:
        if not chat_id:
            raise ValueError("Chat ID missing on getting chat log")

        try:
            chat_log = await self._redis_service.get_value(key=f"chat:{chat_id}:log")
            if chat_log:
                await self._redis_service.expire(f"chat:{chat_id}:log", 86400)
                return [ChatMessage.model_validate(msg) for msg in json.loads(chat_log)]
        except HTTPException as e:
            logger.warning(f"Redis unavailable for getting chat log: {e}")

        logger.warning(f"Chat log for '{chat_id}' not found in redis, checking cosmos")
        chat_data = await self._cosmos_service.get_item(
            item_id=chat_id, partition_key=chat_id, container_type="chats"
        )

        if chat_data:
            return [
                ChatMessage.model_validate(msg) for msg in chat_data.get("chat_log", [])
            ]

        logger.warning(f"Chat log for '{chat_id}' not found in any data source.")
        return None

    async def delete_chat(self, chat_id: str):
        if not chat_id:
            raise ValueError("Chat ID missing on chat deletion")

        chat_key = f"chat:{chat_id}"

        keys_to_delete: list[str] = [chat_key]
        user_list = await self.get_user_list(chat_id=chat_id)

        # Getting all keys for user chat in redis
        for user_id in user_list:
            keys_to_delete.append(f"user:{user_id}:chat")
        try:
            # Get all chat keys in redis
            keys_to_delete += await self._redis_service.scan_keys(key=chat_key)

            # Deleting all keys in redis
            await self._redis_service.delete_keys(keys=keys_to_delete)
        except HTTPException as e:
            logger.warning(f"Redis unavailable for deleting chat: {e}")

        # Deleting chat in cosmos
        await self._cosmos_service.delete_item(
            item_id=chat_id, partition_key=chat_id, container_type="chats"
        )

        # Deleting chat from user information in cosmos
        for user_id in user_list:
            patch_operation = [{"op": "remove", "path": "/chat"}]

            await self._cosmos_service.patch_item(
                item_id=user_id,
                partition_key=user_id,
                patch_operations=patch_operation,
                container_type="users",
            )

        logger.info(f"Successfully deleted chat '{chat_id}' in database")

    async def get_user_chat(self, user_id: str) -> str | None:
        if not user_id:
            raise ValueError("User ID cannot be empty")
        try:
            chat_id = await self._redis_service.get_value(key=f"user:{user_id}:chat")
            if chat_id:
                await self._redis_service.expire(f"user:{user_id}:chat", 86400)
        except HTTPException as e:
            logger.warning(f"Redis unavailable for getting user chat: {e}")

        if chat_id:
            logger.info(f"User '{user_id}' chat found in redis: {chat_id}")
            return chat_id

        logger.warning("User chat not found in redis, checking cosmos")
        user_data = await self._cosmos_service.get_item(
            item_id=user_id, partition_key=user_id, container_type="users"
        )

        if user_data:
            chat_id = user_data.get("chat")

            if chat_id:
                logger.info("User chat found in cosmos, adding into redis")
                try:
                    await self._redis_service.set_value(
                        key=f"user:{user_id}:chat", value=chat_id
                    )
                    await self._redis_service.expire(f"user:{user_id}:chat", 86400)
                except HTTPException as e:
                    logger.warning(f"Redis unavailable for setting user chat: {e}")

                return chat_id

        logger.warning(
            f"User chat not found in both redis and cosmos for user '{user_id}'"
        )
        return None

    async def get_user_list(self, chat_id: str) -> set | None:
        """Gets the list of users in the chat room.

        Args:
            chat_id (str): The chat ID of the chat room to get the list of users of.

        Raises:
            ValueError: If the chat ID is missing.

        Returns:
            Optional[set]: The list of users in the chat room.
        """
        if not chat_id:
            raise ValueError("Chat ID missing on getting user list")
        try:
            user_list = await self._redis_service.set_get(key=f"chat:{chat_id}:users")
            if user_list is not None:
                await self._redis_service.expire(f"chat:{chat_id}:users", 86400)
        except HTTPException as e:
            logger.warning(f"Redis unavailable for getting user list: {e}")

        if user_list is not None:
            return user_list

        logger.warning("User list not found in redis, checking cosmos")
        chat_data = await self._cosmos_service.get_item(
            item_id=chat_id, partition_key=chat_id, container_type="chats"
        )

        if chat_data is not None:
            user_list = chat_data.get("users")

            if user_list is not None:
                logger.info("User list found in cosmos, adding into redis")
                try:
                    await self._redis_service.set_add(
                        key=f"chat:{chat_id}:users", values=user_list
                    )
                    await self._redis_service.expire(f"chat:{chat_id}:users", 86400)
                except HTTPException as e:
                    logger.warning(f"Redis unavailable for setting user list: {e}")

                return user_list

        logger.warning(
            f"User list not found in both redis and cosmos for chat '{chat_id}'"
        )
        return None

    async def get_all_chats(self) -> list[dict[str, Any]]:
        """Gets all the chats from the cosmos database.

        Returns:
            list[dict[str, Any]]: The list of all the chats.
        """
        query = "SELECT * FROM c"
        chat_list = await self._cosmos_service.get_items_by_query(
            query=query, container_type="chats"
        )
        return chat_list

    async def check_user_in_chat(self, user_id: str, chat_id: str) -> bool:
        """Check if user is in a chat.

        Args:
            chat_id (str): The chat ID of the chat to check.
            user_id (str): The user ID of the user to check.

        Raises:
            ValueError: If the chat ID or user ID is missing.
        """
        if not chat_id:
            raise ValueError("Chat ID missing on checking chat")
        if not user_id:
            raise ValueError("User ID missing on checking chat")

        try:
            chat = await self._redis_service.get_value(key=f"user:{user_id}:chat")
            if chat:
                await self._redis_service.expire(f"user:{user_id}:chat", 86400)
                return chat == chat_id
        except HTTPException as e:
            logger.warning(f"Redis unavailable for check user in chat: {e}")

        chat_data = await self._cosmos_service.get_item(
            item_id=chat_id, partition_key=chat_id, container_type="chats"
        )

        if chat_data is not None:
            user_list = chat_data.get("users")
            return user_id in user_list

        logger.warning(f"User not found in both redis and cosmos for chat '{chat_id}'")
        return False

    async def add_message_to_chat(
        self, chat_id: str, user_id: str, message: str
    ) -> ChatMessage:
        if not chat_id:
            raise ValueError("Chat ID missing on adding message")
        if not user_id:
            raise ValueError("User ID missing on adding message")
        if not message:
            raise ValueError("Message missing on adding message")

        chat_message = ChatMessage(sender=user_id, message=message)

        chat = await self.get_chat(chat_id=chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="Chat not found")

        # Verify user is in chat
        if user_id not in chat.users:
            raise HTTPException(status_code=403, detail="User not in chat")

        chat.chat_log.append(chat_message)
        try:
            # Convert chat_log to a list of dictionaries for JSON serialization
            chat_log_dict = [message.model_dump() for message in chat.chat_log]
            await self._redis_service.set_value(
                key=f"chat:{chat_id}:log",
                value=json.dumps(chat_log_dict, default=str),
            )
            await self._redis_service.expire(f"chat:{chat_id}:log", 86400)
        except HTTPException as e:
            logger.warning(f"Redis unavailable for adding message to chat: {e}")

        patch_operation = [
            {
                "op": "add",
                "path": "/chat_log/-",
                "value": chat_message.model_dump(mode="json"),
            }
        ]

        await self._cosmos_service.patch_item(
            item_id=chat_id,
            partition_key=chat_id,
            patch_operations=patch_operation,
            container_type="chats",
        )

        return chat_message

# TODO: Add function for adding agents to chat
