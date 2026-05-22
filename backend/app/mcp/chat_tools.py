import logging

from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)


def chat_tools(mcp, chat_service: ChatService):
    @mcp.tool()
    async def send_chat_message(chat_id: str, agent_id: str, message: str) -> dict:
        # Verify agent is allowed in this chat
        if not await chat_service.check_user_in_chat(user_id=agent_id, chat_id=chat_id):
            return {"error": f"Agent {agent_id} is not authorized in this chat."}

        chat_message = await chat_service.add_message_to_chat(
            chat_id=chat_id, user_id=agent_id, message=message
        )

        return chat_message

    @mcp.tool()
    async def get_recent_chat_messages(chat_id: str) -> dict:
        chat = await chat_service.get_chat(chat_id)
        if not chat:
            return {"error": "Chat not found."}

        return chat
