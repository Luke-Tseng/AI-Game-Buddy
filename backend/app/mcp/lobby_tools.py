import logging

from app.services.room_service import RoomService

logger = logging.getLogger(__name__)


def lobby_tools(mcp, room_service: RoomService):
    """
    Registers lobby tools that allows agents to join

    Args:
        mcp (_type_): _description_
        room_service (RoomService): _description_
    """

    @mcp.tool()
    async def get_room_manifest(room_id: str) -> dict:
        """
        Retrieves the room's current activity and the agent's role within it.

        Use this to synchronize state after joining or when the game type changes.

        Args:
            room_id (str): The unique ID of the room.
            user_id (str): The agent's unique identifier to check role/turn.

        Returns:
            dict: A manifest containing:
                - game_type (str): The identifier for the active game (e.g., 'chess').
                - users (list[str]): All users currently present in the room lobby.
                - is_agent_turn (bool): Whether the game logic expects a move from this agent.
                - game_status (str): Current state (e.g., 'waiting', 'active').
        """
        room = await room_service.get_room(room_id)
        if not room:
            return {"error": "Room not found."}

        manifest = {
            "game_type": room.game_type,
            "users": room.users,
            "is_agent_turn": False,
            "game_status": "waiting" if not room.game_state else "active"
        }

        return manifest
