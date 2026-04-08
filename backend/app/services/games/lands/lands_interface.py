from typing import Literal

from pydantic import BaseModel, Field

from ..game_interface import Action, GameState, Phase, PrivateStates

# A type alias for clarity

# length 5, fixed-size lists, each index corresponding to # of 'grass', 'lightning', 'fire', 'darkness', 'water'
hand = list[int]
board = list[int]
discard = list[int]

# Each element in the list represents the card, 0 = grass, 1 = lightning, 2 = fire, 3 = darkness, 4 = water
deck = list[int]


class LandsPrivateState(BaseModel):
    """
    Represents the private state of a player in a Lands game.
    """

    hand: hand
    deck: deck
    top_card: int | None = None  # The card revealed by playing a water card


class LandsState(GameState):
    """
    Represents the complete state of a Lands game at any point in time.
    """

    # Public game areas
    boards: dict[str, board]
    discard: dict[str, discard]
    phase: Phase = Field(
        default_factory=lambda: Phase(
            current="MAIN_PHASE",
            available_phases=[
                "DRAW_PHASE",
                "MAIN_PHASE",
                "COUNTER_PHASE",
                "RESOLUTION_PHASE",
            ],
        )
    )
    winner: int | None
    main_player_index: int
    countered: int

    # Player-specific game areas
    private_state: PrivateStates[LandsPrivateState]

    # A place to hold the card being played before it resolves
    pending_card: int | None = None

    # A place to hold selections for resolution of the effects of cards
    # 0 (keep it top), 1 (put it on bottom) when a water is successfully played
    # non-main player's hand when a darkness is successfully played
    # selection of card(s) picked by non-main player if darkness is successfully played and opponent has cards
    # cards on opponent's board when a fire is successfully played
    # cards in player's discard when a grass is successfully played
    selection: list[int] | None = None


class LandsPayload(BaseModel):
    """
    Defines the data needed for a player's move.
    """

    # The card being played from the hand
    target: int | list[int] | None = None


class LandsAction(Action):
    """
    Represents an action a player can take, such as playing a card or resigning.
    """

    type: Literal["PLAY_ENERGY", "COUNTER", "CHOOSE_TARGET", "RESIGN"]
    # If type is "PLAY_ENERGY", "COUNTER", or "CHOOSE_TARGET", payload must be provided
    # If type is "PLAY_ENERGY", payload.target is the card being played from the hand
    # If type is "COUNTER", payload.target[0] is either 0 (don't counter) or 1 (counter)
    # If type is "CHOOSE_TARGET", it must be a legal target from the selection
    payload: LandsPayload | None = None
