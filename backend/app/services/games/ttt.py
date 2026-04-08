from typing import Literal

from pydantic import BaseModel, Field

from app.services.games.game_interface import Action, GameState, GameSystem


class TicTacToeState(GameState):
    board: list[list[str | None]] = Field(
        default_factory=lambda: [[None, None, None] for _ in range(3)]
    )
    winner: int | None


class TicTacToeMovePayload(BaseModel):
    row: int = Field(..., ge=0, le=2)
    col: int = Field(..., ge=0, le=2)


class TicTacToeAction(Action):
    type: Literal["PLACE_MARKER"] = "PLACE_MARKER"
    payload: TicTacToeMovePayload


# --- TicTacToe Specific GameSystem ---
class TicTacToeSystem(GameSystem):
    def initialize_game(self, player_ids: list[str]) -> TicTacToeState:
        if len(player_ids) != 2:
            raise ValueError("TicTacToe requires exactly 2 players.")
        return TicTacToeState(
            player_ids=player_ids,
            winner=None,
            current_player_index=0,
        )

    def make_action(
        self, state: TicTacToeState, action: TicTacToeAction
    ) -> TicTacToeState:
        # Validate the move
        if self.is_game_finished(state):
            raise ValueError("Game is already finished")

        self.is_action_valid(state, action.player_id, action)

        row, col = action.payload.row, action.payload.col

        # Apply the move
        marker = "X" if state.current_player_index == 1 else "O"
        state.board[row][col] = marker

        # Check for a winner
        if self.is_win(row, col):
            state.winner = action.player_id

        # Update whose turn it is
        state.current_player_index = (
            1 - state.current_player_index
        )  # Toggles between 0 and 1

        return state

    def get_valid_actions(
        self, state: TicTacToeState, player_id: str
    ) -> list[TicTacToeAction]:
        actions = []
        for row in range(3):
            for col in range(3):
                if state.board[row][col] is None:
                    actions.append(
                        TicTacToeAction(
                            player_id=player_id,
                            payload=TicTacToeMovePayload(row=row, col=col),
                        )
                    )
        return actions

    def is_action_valid(
        self, state: TicTacToeState, player_id: str, action: TicTacToeAction
    ):
        # Invalid Player
        if player_id not in state.player_ids:
            raise ValueError("Invalid player ID.")

        # Not player's turn
        if state.player_ids.index(player_id) != state.current_player_index:
            raise ValueError("It's not your turn.")

        row, col = action.payload.row, action.payload.col
        if state.board[row][col] is not None:
            raise ValueError("Cell is already occupied.")

    def is_game_finished(self, state: TicTacToeState) -> bool:
        """Returns whether the game is finished"""
        return state.winner is not None

    def is_win(self, row: int, col: int, state: TicTacToeState) -> bool:
        """Check if the current player has won with last move"""
        board = state.board
        marker = board[row][col]

        # Check current row for a win
        if all(board[row][j] == marker for j in range(3)):
            return True

        # Check current column for a win
        if all(board[i][col] == marker for i in range(3)):
            return True

        # Check diagonal (top-left to bottom-right) for a win
        if all(board[i][i] == marker for i in range(3)):
            return True

        # Check diagonal (top-right to bottom-left) for a win
        if all(board[i][2 - i] == marker for i in range(3)):
            return True

        return False
