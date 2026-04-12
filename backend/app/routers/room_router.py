import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app import auth
from app.dependencies import get_game_service_factory, get_room_service
from app.schemas import Room, RoomCreate
from app.services.game_service_factory import GameServiceFactory
from app.services.games.chess.chess_interface import ChessState
from app.services.games.lands.lands_interface import LandsState
from app.services.games.ulttt.ulttt_interface import UltimateTicTacToeState
from app.services.room_service import RoomService

router = APIRouter(prefix="/rooms", tags=["Rooms"])
logger = logging.getLogger(__name__)

# All states value for using as response model
all_states = ChessState | UltimateTicTacToeState | LandsState


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Room)
async def create_room(
    room_data: RoomCreate,
    user_id: str = Depends(auth.get_user_id_http),
    room_service: RoomService = Depends(get_room_service),
):
    try:
        room = await room_service.create_room(room_data=room_data, user_id=user_id)
        if not room:
            raise HTTPException(status_code=500, detail="Failed to create room")

        return room
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in create_room: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.post("/{room_id}/join", response_model=Room)
async def join_room(
    room_id: str,
    user_id: str = Depends(auth.get_user_id_http),
    room_service: RoomService = Depends(get_room_service),
):
    try:
        room = await room_service.join_room(room_id=room_id, user_id=user_id)
        return room
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in join_room: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.post("/{room_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_room(
    room_id: str,
    user_id: str = Depends(auth.get_user_id_http),
    room_service: RoomService = Depends(get_room_service),
):
    try:
        await room_service.leave_room(room_id=room_id, user_id=user_id)
        return
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in leave_room: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: str,
    room_service: RoomService = Depends(get_room_service),
):
    try:
        await room_service.delete_room(room_id=room_id)
        return
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in delete_room: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.get("/{room_id}", response_model=Room)
async def get_room(
    room_id: str,
    room_service: RoomService = Depends(get_room_service),
):
    try:
        room = await room_service.get_room(room_id=room_id)
        if room is None:
            raise HTTPException(status_code=400, detail="Room not found")
        return room
    except Exception as e:
        logger.error(f"An unexpected error occurred in get_room: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.get("", response_model=list[dict[str, Any]])
async def list_rooms(room_service: RoomService = Depends(get_room_service)):
    try:
        rooms = await room_service.get_all_rooms()
        return rooms
    except Exception as e:
        logger.error(f"Failed to list rooms: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while fetching rooms.",
        ) from e


@router.post("/{room_id}/game", response_model=all_states)
async def start_game(
    room_id: str,
    room_service: RoomService = Depends(get_room_service),
    game_service_factory: GameServiceFactory = Depends(get_game_service_factory),
):
    try:
        room = await room_service.get_room(room_id=room_id)

        if room is None:
            logger.error(f"Room '{room_id}' not found in database")
            raise HTTPException(status_code=500, detail="Room not found")

        # Get game service based on game type of room
        game_type = room.model_dump().get("game_type")
        game_service = game_service_factory.get_service(game_type=game_type)

        user_list = list(await room_service.get_user_list(room_id=room_id))

        game_state = game_service.initialize_game(player_ids=user_list)

        await room_service.set_game_state(
            room_id=room_id, game_state=game_state.model_dump()
        )

        return game_state
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in create_game: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.delete("/{room_id}/game", status_code=status.HTTP_204_NO_CONTENT)
async def end_game(
    room_id: str,
    user_id: str = Depends(auth.get_user_id_http),
    room_service: RoomService = Depends(get_room_service),
):
    try:
        await room_service.delete_game_state(room_id=room_id)
        return
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in end_game: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.get("/{room_id}/game", response_model=all_states)
async def get_game(
    room_id: str,
    room_service: RoomService = Depends(get_room_service),
):
    try:
        game_state = await room_service.get_game_state(room_id=room_id)
        if game_state is None:
            raise HTTPException(status_code=404, detail="Game not found")
        return game_state
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in get_game: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


# TODO: Add endpoint for updating room information (status, name)
