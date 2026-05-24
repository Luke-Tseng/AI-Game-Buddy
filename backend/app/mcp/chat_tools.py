import logging

from app.services.chat_service import ChatService
from app.services.connection_service import ConnectionService

logger = logging.getLogger(__name__)


def chat_tools(mcp, chat_service: ChatService, connection_service: ConnectionService):
    @mcp.tool()
    async def send_chat_message(chat_id: str, agent_id: str, message: str) -> dict:
        try:
            # Verify agent is allowed in this chat
            if not await chat_service.check_user_in_chat(
                user_id=agent_id, chat_id=chat_id
            ):
                return {"error": f"Agent {agent_id} is not authorized in this chat."}

            chat_message = await chat_service.add_message_to_chat(
                chat_id=chat_id, user_id=agent_id, message=message
            )

            # Get user list of room and broadcast chat message via connection service
            user_list = await chat_service.get_user_list(chat_id=chat_id)

            await connection_service.publish_event(
                channel="chat_message",
                user_list=user_list,
                message_data=chat_message.model_dump(),
            )

            return {"status": "success", "message": "Chat sent successfully."}
        except Exception as e:
            logger.error(f"Error in send_chat_message tool: {e}")
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def get_recent_chat_messages(chat_id: str, limit: int = 10) -> dict:
        try:
            chat = await chat_service.get_chat(chat_id)
            if not chat:
                return {"error": "Chat not found."}

            messages = [msg.model_dump(mode="json") for msg in chat.chat_log[-limit:]]

            return {"messages": messages}

        except Exception as e:
            logger.error(f"Error in get_recent_chat_messages tool: {e}")
            return {"status": "error", "message": str(e)}
