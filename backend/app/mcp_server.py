from fastmcp import FastMCP

from app.services.games.chess.chess_tools import chess_tools
from app.services.room_service import RoomService


def create_mcp_server(room_service: RoomService) -> FastMCP:
    """
    Initializes the FastMCP server and registers all game tools.
    """
    mcp = FastMCP("AI-Game-Buddy-MCP-Server")

    # Register game tools
    chess_tools(mcp, room_service)

    return mcp
