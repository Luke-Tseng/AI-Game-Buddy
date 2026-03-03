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
    async def join_game_room(room_id: str, user_id: str) -> dict:
        """
        Registers the agent as a participant in a specific room.
        The agent must be joined to a room before it can access game state.

        Use this to join a room when getting added by a user.

        Args:
            room_id (str): The ID provided by the user.
            user_id (str): The unique identifier for the agent.
        """
        try:
            room = await room_service.join_room(room_id, user_id)
            return {
                "status": "success",
                "room_id": room.room_id,
                "game_type": room.game_type,
                "active_players": room.users
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def get_room_manifest(room_id: str, user_id: str) -> dict:
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
                - player_ids (list[str]): The specific users assigned to the active game.
                - agent_role_index (int | None): The agent's position in the player list.
                - is_agent_turn (bool): Whether the game logic expects a move from this agent.
                - game_status (str): Current state (e.g., 'waiting', 'active').
        """
        room = await room_service.get_room(room_id)
        if not room:
            return {"error": "Room not found."}

        manifest = {
            "game_type": room.game_type,
            "users": room.users,
            "player_ids": [],
            "agent_role_index": None,
            "is_agent_turn": False,
            "game_status": "waiting" if not room.game_state else "active"
        }

        return manifest

    @mcp.tool()
    async def leave_game_room(room_id: str, user_id: str) -> dict:
        """
        Removes the agent from the room.

        Use this when the room is deleted or you are dismissed.

        Args:
            room_id (str): The unique ID of the room.
            user_id (str): The agent's unique identifier to leave room with.
        """
        await room_service.leave_room(room_id, user_id)
        return {"status": "success", "message": f"Left room {room_id}"}
