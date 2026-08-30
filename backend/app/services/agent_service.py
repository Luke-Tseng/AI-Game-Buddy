"""services/agent_service.py

This module defines the AgentService, which orchestrates the lifecycle of
AI agents in game rooms by communicating with the agent microservice.
"""

import logging

import httpx

from app.config import settings
from app.schemas import AgentProfile, AgentSession

logger = logging.getLogger(__name__)


class AgentService:
    """Manages connecting/disconnecting agents to the agent microservice.

    The backend acts as the orchestrator: when a user invites an agent to a
    room/chat, the backend persists the agent (room_service/chat_service) and
    tells the agent microservice to start its loop by calling /connect. The
    agent microservice then connects back to this backend's MCP SSE endpoint
    to observe game state and take actions.
    """

    def __init__(self, mcp_sse_url: str | None = None):
        self._mcp_sse_url = mcp_sse_url or settings.MCP_SSE_URL
        self._agent_service_url = settings.AGENT_SERVICE_URL.rstrip("/")

    async def connect_agent(
        self, profile: AgentProfile, session: AgentSession, timeout: float = 10.0
    ) -> None:
        """Starts an agent's loop in the agent microservice for the given session.

        Args:
            profile (AgentProfile): The agent's personality profile.
            session (AgentSession): The session (room) the agent should join.
            timeout (float): HTTP request timeout in seconds.

        Raises:
            httpx.HTTPError: If the agent microservice is unreachable or errors.
        """
        payload = {
            "profile": profile.model_dump(mode="json"),
            "session": session.model_dump(mode="json"),
            "mcp_sse_url": self._mcp_sse_url,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self._agent_service_url}/connect", json=payload
            )
            response.raise_for_status()

        logger.info(
            f"Connected agent '{session.profile_id}' session '{session.id}' "
            f"to room '{session.room_id}'."
        )

    async def disconnect_agent(
        self, room_id: str, agent_id: str, timeout: float = 10.0
    ) -> None:
        """Stops an agent's loop in the agent microservice.

        Args:
            room_id (str): The room ID the agent was connected to.
            agent_id (str): The agent's unique identifier (session id).
            timeout (float): HTTP request timeout in seconds.

        Raises:
            httpx.HTTPError: If the agent microservice is unreachable or errors.
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self._agent_service_url}/disconnect",
                params={"room_id": room_id, "profile_id": agent_id},
            )
            response.raise_for_status()

        logger.info(f"Disconnected agent '{agent_id}' from room '{room_id}'.")
