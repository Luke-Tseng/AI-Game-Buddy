from fastmcp import FastMCP

from app.services.chat_service import ChatService
from app.services.connection_service import ConnectionService
from app.services.game_service_factory import GameServiceFactory
from app.services.room_service import RoomService

from .chat_tools import chat_tools
from .chess_tools import chess_tools
from .lobby_tools import lobby_tools


class MCPService:
    """
    Service to manage the FastMCP server instance and tool registrations.
    """

    def __init__(
        self,
        room_service: RoomService,
        game_service_factory: GameServiceFactory,
        chat_service: ChatService,
        connection_service: ConnectionService,
    ):
        self.mcp = FastMCP("AI-Game-Buddy-MCP-Server")
        self.room_service = room_service
        self.game_service_factory = game_service_factory
        self.chat_service = chat_service
        self.connection_service = connection_service

        # Register all tools on initialization
        self._register_tools()

    def _register_tools(self):
        """Passes the service instances to the game-specific tool modules."""
        lobby_tools(self.mcp, self.room_service)
        chess_tools(self.mcp, self.room_service, self.game_service_factory)
        chat_tools(self.mcp, self.chat_service, self.connection_service)

    def get_app(self):
        """Returns the SSE-ready application for mounting in FastAPI."""
        return self.mcp.sse_app()
