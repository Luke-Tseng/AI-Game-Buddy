from fastmcp import FastMCP

from app.services.game_service_factory import GameServiceFactory
from app.services.games.chess.chess_tools import chess_tools
from app.services.lobby_tools import lobby_tools
from app.services.room_service import RoomService


class MCPService:
    """
    Service to manage the FastMCP server instance and tool registrations.
    """

    def __init__(self, room_service: RoomService, game_service_factory: GameServiceFactory):
        self.mcp = FastMCP("AI-Game-Buddy-MCP-Server")
        self.room_service = room_service
        self.game_service_factory = game_service_factory

        # Register all tools on initialization
        self._register_tools()

    def _register_tools(self):
        """Passes the service instances to the game-specific tool modules."""
        lobby_tools(self.mcp, self.room_service)
        chess_tools(self.mcp, self.room_service, self.game_service_factory)

    def get_app(self):
        """Returns the SSE-ready application for mounting in FastAPI."""
        return self.mcp.http_app()
