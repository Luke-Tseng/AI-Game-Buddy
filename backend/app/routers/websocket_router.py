"""routers/websocket_router.py

This module provides WebSocket endpoints for real-time communication.
It handles WebSocket connections, message routing, and manages real-time game interactions between clients.

All WebSocket operations are asynchronous and include proper error handling and logging.
"""

import json
import logging

from fastapi import APIRouter, WebSocket
from pydantic import ValidationError
from starlette.endpoints import WebSocketEndpoint

from app import auth
from app.dependencies import (
    get_chat_service,
    get_connection_service,
    get_game_service_factory,
    get_room_service,
)
from app.schemas import GameUpdate
from app.services.connection_service import ConnectionService

router = APIRouter(tags=["Websocket"])
logger = logging.getLogger(__name__)


@router.websocket_route("/ws")
class ConnectionEndpoint(WebSocketEndpoint):
    """WebSocket endpoint for real-time client-server communication.

    Attributes:
        encoding (str): Message encoding format (JSON).
        connection_service (ConnectionService): Service for managing WebSocket connections.
        user_id (str): Authenticated user ID for the current connection.
        room_service: Service for managing game rooms and state.

    Message Format:
        Expected message structure:
        {
            "type": "message_type",
            "room_id": "room_identifier",
            "payload": { ... message data ... }
        }

    Supported Message Types:
        - "game_action": Process game moves and actions
        - "chat_message": Handle chat communication
    """

    encoding = "json"

    async def on_connect(self, websocket: WebSocket):
        """Handle new WebSocket connection establishment.

        This method is called when a client attempts to establish a WebSocket connection.
        It performs the following operations:
        1. Accepts the WebSocket connection
        2. Authenticates the user
        3. Initializes required services
        4. Registers the connection with the connection service

        Args:
            websocket (WebSocket): The WebSocket connection object.

        Raises:
            Exception: If authentication fails or service initialization encounters errors.
                      Connection failures are logged but don't raise exceptions to the client.
        """
        await websocket.accept()

        try:
            # Authenticate user
            self.user_id = await auth.get_user_id_websocket(websocket=websocket)

            # Initialize services
            self.connection_service: ConnectionService = get_connection_service()
            self.room_service = get_room_service()
            self.game_service_factory = get_game_service_factory()
            self.chat_service = get_chat_service()

            # Handler map for mapping message type to handler function
            self.handler_map = {
                "game_action": self.handle_game_action,
                "chat_message": self.handle_chat_message,
            }

            await self.connection_service.connect(
                websocket=websocket, user_id=self.user_id
            )

            self.is_authenticated = True
            logger.info(f"User '{self.user_id}' connected to websocket endpoint")

            # Send connection acceptance message
            await websocket.send_json({
                "message": "Successfully connected to websocket endpoint"
            })
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            # Send error message to client before closing
            try:
                await websocket.send_json({
                    "error": str(e),
                    "message": "Unable to establish connection",
                })
            except Exception:
                pass

            # Close the connection
            await websocket.close(code=1008, reason="Authentication failed")

    async def on_receive(self, websocket: WebSocket, data: dict):
        """Handle incoming WebSocket messages from clients.

        Message Processing Flow:
        1. Extract message type and payload from received data
        2. Route message based on type:
           - "game_action": Process game moves/actions through game service
           - "chat_message": Handle chat communication
        3. Send appropriate responses or error messages back to client

        Args:
            websocket (WebSocket): The WebSocket connection object.
            data (dict): The received message data containing:
                - type (str): Message type identifier
                - payload (dict): Message-specific data

        Raises:
            ValidationError: If the message format is invalid. Sends error response to client.
            Exception: For other processing errors. Sends generic error response to client.

        Note:
            All errors are caught and handled gracefully, sending error responses to the client rather than terminating the connection.
        """
        if not self.is_authenticated or not self.user_id:
            await websocket.send_json({
                "error": "Not authenticated",
                "message": "Please establish a valid connection first",
            })
            return

        try:
            message_type = data.get("type")
            payload = data.get("payload", {})

            handler = self.handler_map.get(message_type, self.handle_unknown)

            await handler(payload)
        except ValueError as e:
            error_payload = {"type": "Error", "payload": {"message": str(e)}}
            await websocket.send_json(error_payload)
        except ValidationError as e:
            logger.error(f"Invalid message format from '{self.user_id}': {e}")
            error_details = json.loads(e.json())
            await websocket.send_json({
                "error": "Invalid message format",
                "details": error_details,
            })
        except Exception as e:
            logger.exception(f"Error processing message from '{self.user_id}': {e}")
            await websocket.send_json({
                "error": "Failed to process message.",
                "details": e,
            })

    async def on_disconnect(self, websocket: WebSocket, close_code: int):
        """Handle WebSocket connection termination.

        Args:
            websocket (WebSocket): The WebSocket connection object being closed.
            close_code (int): The WebSocket close code indicating the reason for closure.

        """
        if hasattr(self, "user_id"):
            self.connection_service.disconnect(user_id=self.user_id)
            logger.info(
                f"User '{self.user_id}' disconnected from websocket endpoint: {close_code}"
            )

    async def handle_game_action(self, payload: dict):
        """Handler for game action.

        Args:
            payload (dict): Contains room_id and action for the game.

        Payload example:
        {
            "type": "game_action",
            "payload": {
                "room_id": "room_id",
                "game_type": "chess",
                "action": {
                    "type": "MAKE_MOVE",
                    "payload": {
                        "move": "e2e4"
                    }
                }
            }
        }

        """
        room_id = payload.get("room_id")
        # Verify room exists and user is in room
        if room_id and await self.room_service.check_user_in_room(
            user_id=self.user_id, room_id=room_id
        ):
            # Get current game state in database
            game_state = await self.room_service.get_game_state(room_id=room_id)

            action = payload.get("action")

            game_type = payload.get("game_type")
            game_service = self.game_service_factory.get_service(game_type=game_type)

            # Make action given from user to current game state
            new_game_state = game_service.make_action(
                state=game_state, player_id=self.user_id, action=action
            )

            # Set new game state after action is processed
            await self.room_service.set_game_state(
                room_id=room_id, game_state=new_game_state.model_dump()
            )

            user_list = await self.room_service.get_user_list(room_id=room_id)
            game_update = GameUpdate(
                room_id=room_id,
                game_state=new_game_state.model_dump(),
            )
            await self.connection_service.publish_event(
                channel="game_update",
                user_list=user_list,
                message_data=game_update.model_dump(),
            )

    async def handle_chat_message(self, payload: dict):
        """Handler for chat messages.

        Args:
            payload (dict): Contains room_id and message for the chat.

        Payload example:
        {
            "type": "chat_message",
            "payload": {
                "chat_id": "chat_id",
                "sender": "user_id",
                "message": "Hello, world!"
            }
        }

        """
        chat_id = payload.get("chat_id")
        sender = payload.get("sender")
        message = payload.get("message")

        if chat_id and sender and message:
            # Verify chat exists and user is in chat
            if not await self.chat_service.check_user_in_chat(
                user_id=self.user_id, chat_id=chat_id
            ):
                logger.warning(f"Unauthorized chat attempt by user {self.user_id}")
                return

            # Send chat message to chat service
            chat_message = await self.chat_service.add_message_to_chat(
                chat_id=chat_id, user_id=self.user_id, message=message
            )

            user_list = await self.chat_service.get_user_list(chat_id=chat_id)
            await self.connection_service.publish_event(
                channel="chat_message",
                user_list=user_list,
                message_data=chat_message.model_dump(),
            )
        else:
            logger.warning(f"Invalid chat message payload: {payload}")

    async def handle_unknown(self, _payload: dict):
        """Handler for unknown message type"""
        logger.warning("Received unknown message type.")
