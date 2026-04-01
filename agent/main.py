import asyncio
import logging
import os
from contextlib import asynccontextmanager

import google.generativeai as genai
from fastapi import FastAPI, HTTPException, status
from mcp.client.session import ClientSession

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


@app.post("/connect")
async def connect_agent(req: ConnectAgentRequest):
    """Allows backend to connect agent to the room"""
    return


@app.post("/disconnect")
async def disconnect_agent(
    room_id: str, profile_id: str, status_code=status.HTTP_204_NO_CONTENT
):
    """Allows backend to disconnect agent out of the room."""
    task_key = f"{room_id}_{profile_id}"
    if task_key in active_agents:
        active_agents[task_key].cancel()  # Triggers asyncio.CancelledError in the loop
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
