import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app import auth
from app.dependencies import get_chat_service
from app.schemas import Chat, ChatMessage
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)


# Create a chat room independent of game room
@router.post("", status_code=201, response_model=Chat)
async def create_chat(
    user_id: str = Depends(auth.get_user_id_http),
    chat_service: ChatService = Depends(get_chat_service),
):
    try:
        chat = await chat_service.create_chat(user_id=user_id)
        if not chat:
            raise HTTPException(status_code=500, detail="Failed to create chat room")

        return chat
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in create_chat: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.post("/{chat_id}/join", status_code=status.HTTP_204_NO_CONTENT)
async def join_chat(
    chat_id: str,
    user_id: str = Depends(auth.get_user_id_http),
    chat_service: ChatService = Depends(get_chat_service),
):
    try:
        await chat_service.join_chat(chat_id=chat_id, user_id=user_id)
        # Return no content, new users will only see new messages of the chat
        return
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in join_chat: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.post("/{chat_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_chat(
    chat_id: str,
    user_id: str = Depends(auth.get_user_id_http),
    chat_service: ChatService = Depends(get_chat_service),
):
    try:
        await chat_service.leave_chat(chat_id=chat_id, user_id=user_id)
        return
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in leave_chat: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: str,
    chat_service: ChatService = Depends(get_chat_service),
):
    try:
        await chat_service.delete_chat(chat_id=chat_id)
        return
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"An unexpected error occurred in delete_chat: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.get("/{chat_id}", response_model=Chat)
async def get_chat(
    chat_id: str,
    chat_service: ChatService = Depends(get_chat_service),
):
    try:
        chat = await chat_service.get_chat(chat_id=chat_id)
        return chat
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in get_chat: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e


@router.get("/{chat_id}/log", response_model=list[ChatMessage])
async def get_chat_log(
    chat_id: str,
    chat_service: ChatService = Depends(get_chat_service),
):
    try:
        chat_log = await chat_service.get_chat_log(chat_id=chat_id)
        return chat_log
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"An unexpected error occurred in get_chat_log: {e}")
        raise HTTPException(
            status_code=500, detail="An internal error occurred."
        ) from e
