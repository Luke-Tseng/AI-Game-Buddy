import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app import auth
from app.dependencies import get_agent_service, get_room_service
from app.schemas import AgentProfile, AgentSession
from app.services.agent_service import AgentService
from app.services.room_service import RoomService

router = APIRouter(prefix="/rooms", tags=["Agents"])
logger = logging.getLogger(__name__)


@router.post(
    "/{room_id}/agents",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentSession,
)
async def add_agent_to_room(
    room_id: str,
    profile: AgentProfile,
    user_id: str = Depends(auth.get_user_id_http),
    room_service: RoomService = Depends(get_room_service),
    agent_service: AgentService = Depends(get_agent_service),
):
    """Adds an AI agent to a room and starts its agent loop."""
    try:
        room = await room_service.get_room(room_id=room_id)
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")

        # Only the room creator (or a member) can invite agents
        if user_id not in room.users:
            raise HTTPException(status_code=403, detail="Not a member of this room")

        session_id = str(uuid.uuid4())
        agent_session = AgentSession(
            id=session_id,
            room_id=room_id,
            profile_id=profile.id,
        )

        # Persist the agent into the room so it becomes a game participant
        await room_service.add_agent(room_id=room_id, agent_id=session_id)

        # Start the agent loop in the agent microservice
        await agent_service.connect_agent(profile=profile, session=agent_session)

        return agent_session
    except HTTPException as e:
        raise e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in add_agent_to_room: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.delete(
    "/{room_id}/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_agent_from_room(
    room_id: str,
    agent_id: str,
    user_id: str = Depends(auth.get_user_id_http),
    room_service: RoomService = Depends(get_room_service),
    agent_service: AgentService = Depends(get_agent_service),
):
    """Removes an AI agent from a room and stops its agent loop."""
    try:
        room = await room_service.get_room(room_id=room_id)
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")

        # Only the room creator (or a member) can remove agents
        if user_id not in room.users:
            raise HTTPException(status_code=403, detail="Not a member of this room")

        # Stop the agent loop in the agent microservice
        try:
            await agent_service.disconnect_agent(
                room_id=room_id, agent_id=agent_id
            )
        except Exception as e:
            logger.warning(f"Failed to disconnect agent '{agent_id}': {e}")

        # Persist the removal from the room
        await room_service.remove_agent(room_id=room_id, agent_id=agent_id)

        return
    except HTTPException as e:
        raise e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in remove_agent_from_room: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e
