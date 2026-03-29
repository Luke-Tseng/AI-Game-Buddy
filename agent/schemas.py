from pydantic import BaseModel, Field

class AgentProfile(BaseModel):
    id: str  # profile id
    name: str
    system_prompt: str  # Initial prompt for agent
    difficulty_level: int = Field(
        default=5, gt=0, le=10
    )  # playing difficulty from 1-10
    traits: list[str] = []


class AgentSession(BaseModel):
    id: str  # session id
    room_id: str
    profile_id: str  # profile selected for session
    history: list[dict] = []
