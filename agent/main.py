import asyncio
import logging
import os
from contextlib import asynccontextmanager

import google.generativeai as genai
from fastapi import FastAPI, HTTPException, status
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from agent_loop import AgentLoop
from schemas import ConnectAgentRequest

logger = logging.getLogger(__name__)

active_agents: dict[str, asyncio.Task] = {}
mcp_sessions: dict[str, ClientSession] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup on container startup
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    yield
    # Cleanup on container shutdown
    for task in active_agents.values():
        task.cancel()


app = FastAPI(lifespan=lifespan)


@app.post("/connect", status_code=status.HTTP_204_NO_CONTENT)
async def connect_agent(req: ConnectAgentRequest):
    """Allows backend to connect agent to the room"""
    session_id = req.session.id
    room_id = req.session.room_id
    session_key = f"{room_id}_{session_id}"

    if session_key in active_agents:
        raise HTTPException(status_code=400, detail="Agent is already in this room.")

    # Connecting agent to mcp server through sse
    async def run_agent_session():
        try:
            async with sse_client(req.mcp_sse_url) as streams:
                async with ClientSession(streams[0], streams[1]) as mcp_session:
                    await mcp_session.initialize()

                    # Store session if we need to close it manually later
                    mcp_sessions[session_key] = mcp_session

                    # Initialize agent loop
                    agent_loop = AgentLoop(
                        profile=req.profile,
                        session=req.session,
                        mcp_session=mcp_session,
                    )

                    # Start agent loop
                    await agent_loop.start_loop(poll_interval=3.0)
        except asyncio.CancelledError:
            logger.info(f"Agent {session_key} session was cancelled.")
        except Exception as e:
            logger.error(f"Agent {session_key} crashed: {e}")
        finally:
            # Cleanup when loop ends or crashes
            active_agents.pop(session_key, None)
            mcp_sessions.pop(session_key, None)

    task = asyncio.create_task(run_agent_session())
    active_agents[session_key] = task

    return


@app.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_agent(
    room_id: str, profile_id: str
):
    """Allows backend to disconnect agent out of the room."""
    task_key = f"{room_id}_{profile_id}"
    if task_key in active_agents:
        active_agents[task_key].cancel()  # Triggers asyncio.CancelledError in the loop
        return
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found."
    )
