from fastmcp import FastMCP

from app.services.game_service_factory import GameServiceFactory
from app.services.games.chess.chess_tools import chess_tools
from app.services.lobby_tools import lobby_tools
from app.services.room_service import RoomService


def create_mcp_server(
    room_service: RoomService, game_service_factory: GameServiceFactory
) -> FastMCP:
    """
    Initializes the FastMCP server and registers all game tools.
    """
    mcp = FastMCP("AI-Game-Buddy-MCP-Server")

    # Register lobby tools
    lobby_tools(mcp, room_service)

    # Register game tools
    chess_tools(mcp, room_service, game_service_factory)

    return mcp
