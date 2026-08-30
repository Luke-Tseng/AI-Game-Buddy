import asyncio
import json
import logging

import google.generativeai as genai

from schemas import AgentProfile, AgentSession

logger = logging.getLogger(__name__)


class MicroserviceAgentLoop:
    def __init__(self, profile: AgentProfile, session: AgentSession, mcp_session):
        self.profile = profile
        self.session = session
        self.mcp_session = mcp_session

        self.current_game_type = None
        self.model = None
        self.chat = None
        self._max_tool_calls = 10

    async def _get_active_tools_for_game(self, game_type: str | None) -> list:
        mcp_tools = await self.mcp_session.list_tools()
        gemini_declarations = []
        for tool in mcp_tools.tools:
            if "manifest" in tool.name or "chat" in tool.name:
                gemini_declarations.append({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                })
            elif game_type and game_type.lower() in tool.name.lower():
                gemini_declarations.append({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                })
        return [{"function_declarations": gemini_declarations}]

    async def _update_llm_tools(self, game_type: str | None):
        logger.info(f"Equipping tools for game type: {game_type}")
        active_tools = await self._get_active_tools_for_game(game_type)

        system_instruction = (
            f"You are {self.profile.name}. Persona: {self.profile.system_prompt} "
            f"Difficulty: {self.profile.difficulty_level}/10. "
            f"You are currently playing: {game_type if game_type else 'Waiting in lobby'}."
        )

        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            tools=active_tools,
            system_instruction=system_instruction,
        )

        history = self.chat.history if self.chat else []
        self.chat = self.model.start_chat(history=history)
        self.current_game_type = game_type

    async def step(self):
        try:
            manifest_response = await self.mcp_session.call_tool(
                "get_room_manifest",
                {"room_id": self.session.room_id, "agent_id": self.session.id},
            )
            if not manifest_response.content or not manifest_response.content[0].text:
                logger.warning("Empty manifest response received.")
                return
            manifest = json.loads(manifest_response.content[0].text)
        except Exception as e:
            logger.error(f"Failed to get room manifest: {e}")
            return

        # Manifest may return an error dict (e.g. room not found)
        if "error" in manifest:
            logger.warning(f"Manifest error: {manifest.get('error')}")
            return

        active_game_type = manifest.get("game_type")
        is_my_turn = manifest.get("is_agent_turn", False)

        if active_game_type != self.current_game_type:
            await self._update_llm_tools(active_game_type)

        if is_my_turn:
            observation_msg = "It is your turn. Check the board state and use your game tools to make a move."
            try:
                response = await self.chat.send_message_async(observation_msg)
                await self.handle_tool_calls(response, depth=0)
            except Exception as e:
                logger.error(f"Error during agent action step: {e}")

    async def handle_tool_calls(self, response, depth: int = 0) -> bool:
        if not response.function_calls:
            return False

        if depth >= self._max_tool_calls:
            logger.warning(
                f"Max tool call depth ({self._max_tool_calls}) reached; stopping tool chain."
            )
            return False

        for call in response.function_calls:
            logger.info(f"LLM requested tool: {call.name} with args: {dict(call.args)}")
            try:
                mcp_result = await self.mcp_session.call_tool(
                    call.name, dict(call.args)
                )
                result_text = (
                    mcp_result.content[0].text if mcp_result.content else "Success"
                )

                next_response = await self.chat.send_message_async(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=call.name, response={"result": result_text}
                        )
                    )
                )
                await self.handle_tool_calls(next_response, depth=depth + 1)

            except Exception as e:
                logger.error(f"Error executing tool {call.name}: {e}")
                await self.chat.send_message_async(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=call.name, response={"error": str(e)}
                        )
                    )
                )
        return True

    async def start_loop(self, poll_interval: float = 2.0):
        """Starts the continuous loop."""
        logger.info(
            f"Starting Agent Loop for {self.profile.name} in Room {self.session.room_id}..."
        )
        try:
            while True:
                await self.step()
                await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            logger.info(f"Agent {self.profile.name} shutting down gracefully.")
