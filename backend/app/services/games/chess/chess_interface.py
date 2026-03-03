from typing import Literal

import chess
from pydantic import BaseModel, Field, model_validator

from ..game_interface import Action, GameState


class ChessState(GameState):
    """
    Represents the state of a chess game.

    The `move_history` is not validated for performance reasons. The primary source of truth
    for the board state is `board_fen`.
    """

    board_fen: str = Field(
        default="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    )
    game_result: str | None = None
    move_history: list[str] = Field(default_factory=list)
    current_player_index: Literal[0, 1]

    @model_validator(mode="after")
    def validate_chess_state(self) -> "ChessState":
        try:
            board = chess.Board(self.board_fen)
        except ValueError as e:
            raise ValueError("Invalid FEN string") from e

        if not board.is_valid():
            raise ValueError("Invalid board position")

        if self.game_result is not None and not self.finished:
            raise ValueError("If game_result is set, finished must be True")

        # White's turn corresponds to current_player_index 0, Black's to 1
        is_white_turn = board.turn == chess.WHITE
        current_player_index = self.meta.get("current_player_index")

        if is_white_turn and current_player_index != 0:
            raise ValueError(
                "FEN indicates white's turn, but current_player_index is not 0"
            )
        if not is_white_turn and current_player_index != 1:
            raise ValueError(
                "FEN indicates black's turn, but current_player_index is not 1"
            )

        return self


class ChessMovePayload(BaseModel):
    move: str = Field(..., description="Move in UCI format (e.g., 'e2e4', 'e1g1')")


class ChessAction(Action):
    type: Literal["MAKE_MOVE", "RESIGN"] = "MAKE_MOVE"
    payload: ChessMovePayload | None = None
