import uuid
from abc import ABC, abstractmethod
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, Field, computed_field, model_validator


# --- Generic Phase ---
class Phase(BaseModel):
    current: str  # Current phase of the game
    available_phases: Annotated[
        list[str], Field(min_length=1)
    ]  # List of all available phases

    @model_validator(mode="before")
    @classmethod
    def set_current_if_missing(cls, values: dict) -> dict:
        if "current" not in values or not values["current"]:
            if "available_phases" in values and values["available_phases"]:
                # Set 'current' to the first available phase
                values["current"] = values["available_phases"][0]
            else:
                raise ValueError(
                    "'current' is missing and cannot be defaulted from 'available_phases'"
                )
        return values

    @model_validator(mode="after")
    def validate_current_index(self):
        if self.current not in self.available_phases:
            raise ValueError(
                f"Current phase '{self.current}' is not in available phases {self.available_phases}"
            )
        return self

    # Index of the current phase in available_phases
    @computed_field
    def _current_index(self) -> int:
        return self.available_phases.index(self.current)

    def next_phase(self):
        # Calculate the next index, looping back to 0 if at the end
        next_index = (self._current_index + 1) % len(self.available_phases)

        return self.model_copy(
            update={"current": self.available_phases[next_index]}, deep=True
        )


# --- Type Variables for Components ---
PrivateStateT = TypeVar("PrivateStateT")


# --- Generic Components ---
class PrivateStates(BaseModel, Generic[PrivateStateT]):
    """Represents the private state of a player or group of players in a game."""

    states: dict[str, PrivateStateT]


# --- Generic GameState ---
class GameState(BaseModel):
    game_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )  # Unique identifier for each game
    player_ids: list[str]  # Player identifications
    finished: bool = False  # Set True when game is finished

    # Simple Optional Features
    turn: int | None = None
    phase: Phase | None = None

    # Complex Optional Features
    private_state: PrivateStates | None = None


# --- Generic Action ---
class Action(BaseModel):
    type: str  # Type
    payload: dict[str, Any] | None


# --- Type Variables for GameSystem ---
StateType = TypeVar("StateType", bound=GameState)
ActionType = TypeVar("ActionType", bound=Action)


# --- Generic GameSystem ---
class GameSystem(ABC, Generic[StateType, ActionType]):
    @abstractmethod
    def initialize_game(self, player_ids: list[str]) -> StateType:
        """Returns the starting state for a new game."""
        pass

    @abstractmethod
    def make_action(
        self, state: StateType, player_id: str, action: ActionType
    ) -> StateType:
        """Processes a player's action and returns the new game state."""
        pass

    @abstractmethod
    def get_valid_actions(self, state: StateType, player_id: str) -> list[ActionType]:
        """Returns all valid actions for a given player"""
        pass

    @abstractmethod
    def is_action_valid(
        self, state: StateType, player_id: str, action: ActionType
    ) -> bool:
        """Raises an ValueError if move is invalid. Else returns True."""
        pass
