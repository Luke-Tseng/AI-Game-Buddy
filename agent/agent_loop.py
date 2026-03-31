import asyncio

import google.generativeai as genai
from mcp.client.session import ClientSession

from schemas import AgentProfile, AgentSession


class AgentLoop:
    def __init__(
        self,
        profile: AgentProfile,
        session: AgentSession,
        mcp_session: ClientSession,
        model: genai.GenerativeModel,
    ):
        self.profile = profile
        self.session = session
        self.mcp_session = mcp_session
        self.model = model

        self.current_game_type = None
        self.model = None
        self.chat = None

    async def _observe_environment(self) -> dict:
        """
        Manually triggers MCP tools to get the current state before asking the LLM to act.
        Assumes your MCP server has tools named 'get_game_state' and 'get_new_chats'.
        """
        try:
            game_state = await self.mcp_session.call_tool(
                "get_game_state", {"room_id": self.session.room_id}
            )
            new_chats = await self.mcp_session.call_tool(
                "get_new_chats", {"room_id": self.session.room_id}
            )

            return {
                "game_state": game_state.content[0].text
                if game_state.content
                else "{}",
                "new_chats": new_chats.content[0].text if new_chats.content else "[]",
            }
        except Exception as e:
            print(f"Error observing environment: {e}")
            return {"game_state": "{}", "new_chats": "[]"}

    async def step(self):
        """A single iteration of the agentic loop."""

        # 1. OBSERVE
        env_state = await self._observe_environment()

        # For efficiency, if state is empty/no updates, you could return early here.
        # if env_state["game_state"] == "{}" and env_state["new_chats"] == "[]":
        #     return

        observation_msg = (
            f"Current Game State: {env_state['game_state']}\n"
            f"New Chat Messages: {env_state['new_chats']}\n"
            "Analyze the state. If it is your turn, use your game move tools. "
            "If there are chat messages, respond to them. You can do both."
        )

        # 2. DECIDE & 3. ACT (Gemini handles the tool calling loop internally when enabled)
        try:
            # send_message_async will automatically call the MCP tools mapped to Gemini
            # if the LLM decides to use them, because we registered them in the model!
            response = await self.chat.send_message_async(observation_msg)

            # 4. MEMORY
            # Gemini's chat object automatically keeps track of the history,
            # but we can sync it back to your Pydantic model for database storage.
            self.session.history.append({"role": "user", "content": observation_msg})
            self.session.history.append({"role": "agent", "content": response.text})

            # Print agent's text response (if any)
            if response.text:
                print(f"[{self.profile.name}]: {response.text}")

        except Exception as e:
            print(f"Error during agent step: {e}")

    async def start_loop(self, poll_interval: float = 2.0):
        print(f"Starting agent {self.profile.name} in room {self.session.room_id}...")
        try:
            while True:
                await self.step()
                await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            print(f"Agent {self.profile.name} shutting down.")

    async def _get_active_tools_for_game(mcp_session, game_type: str | None) -> list:
        """Filters MCP tools based on the active game type."""
        mcp_tools = await mcp_session.list_tools()

        active_tools = []
        for tool in mcp_tools.tools:
            if "get_room_manifest" in tool.name or "chat" in tool.name:
                # Always include lobby/general tools
                active_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                })
            elif game_type and game_type.lower() in tool.name.lower():
                # Only include game-specific tools if they match the current game
                active_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                })

        return [{"function_declarations": active_tools}]
