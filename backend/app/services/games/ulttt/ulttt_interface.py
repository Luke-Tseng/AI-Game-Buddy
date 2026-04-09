from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..game_interface import Action, GameState

# A type alias for clarity
SmallBoard = list[list[str | None]]  # Represents a single 3x3 board


class UltimateTicTacToeState(GameState):
    # The entire board
    large_board: list[list[SmallBoard]] = Field(
        default_factory=lambda: [
            [[[None, None, None] for _ in range(3)] for _ in range(3)] for _ in range(3)
        ]
    )

    # Tracks the winner of each small board ('O', 'X', or 'Draw')
    meta_board: SmallBoard = Field(
        default_factory=lambda: [[None] * 3 for _ in range(3)]
    )

    # Determines which small board the next player must play in.
    # None indicates the player can choose any board.
    active_board: tuple[int, int] | None = None
    winner: str | None = None

    @model_validator(mode="after")
    def check_legal_state(self) -> "UltimateTicTacToeState":
        # 1. Check meta_board consistency with large_board
        for r in range(3):
            for c in range(3):
                expected_status = self._check_board_status(self.large_board[r][c])
                if self.meta_board[r][c] != expected_status:
                    raise ValueError(
                        f"Mismatched meta_board at ({r},{c}). "
                        f"Expected {expected_status}, got {self.meta_board[r][c]}"
                    )

        # 2. Check active_board consistency
        if self.active_board:
            r, c = self.active_board
            if self.meta_board[r][c] is not None:
                raise ValueError(
                    f"active_board {self.active_board} points to a finished board."
                )

        # 3. Check turn order and number of pieces
        if not self.finished:
            x_count = sum(
                cell == "X"
                for large_row in self.large_board
                for small_board in large_row
                for small_row in small_board
                for cell in small_row
            )
            o_count = sum(
                cell == "O"
                for large_row in self.large_board
                for small_board in large_row
                for small_row in small_board
                for cell in small_row
            )

            player_index = self.current_player_index

            if player_index == 0 and x_count != o_count:  # X's turn
                raise ValueError("Invalid turn order")
            elif player_index == 1 and x_count != o_count + 1:  # O's turn
                raise ValueError("Invalid turn order")

        # 4. Check finished flag consistency
        game_status = self._check_board_status(self.meta_board)
        if self.finished:
            if not game_status:
                raise ValueError(
                    "Game is marked as finished, but there is no winner or draw."
                )
            if self.winner is None:
                raise ValueError("Game is marked as finished, but winner is not set.")
        else:
            if game_status and self.winner is not None:
                raise ValueError(
                    "Game is not marked as finished, but there is a winner."
                )
        return self

    @staticmethod
    def _check_board_status(board: SmallBoard) -> str | None:
        """
        Checks a 3x3 board for a winner or a draw.
        Returns 'X', 'O', '-', or None if the game is ongoing.
        """
        # Check rows and columns
        for i in range(3):
            if (
                board[i][0] == board[i][1] == board[i][2]
                and board[i][0] is not None
                and board[i][0] != "-"
            ):
                return board[i][0]
            if (
                board[0][i] == board[1][i] == board[2][i]
                and board[0][i] is not None
                and board[0][i] != "-"
            ):
                return board[0][i]

        # Check diagonals
        if (
            board[0][0] == board[1][1] == board[2][2]
            and board[0][0] is not None
            and board[0][0] != "-"
        ):
            return board[0][0]
        if (
            board[0][2] == board[1][1] == board[2][0]
            and board[0][2] is not None
            and board[0][2] != "-"
        ):
            return board[0][2]

        # Check for a draw (all cells filled, no winner)
        if all(cell for row in board for cell in row):
            return "-"

        return None


class UltimateTicTacToePayload(BaseModel):
    # Row and column of the large board
    board_row: int = Field(..., ge=0, le=2)
    board_col: int = Field(..., ge=0, le=2)

    # Row and column of the small board
    row: int = Field(..., ge=0, le=2)
    col: int = Field(..., ge=0, le=2)


# Action type would be either "PLACE_MARKER" or "RESIGN"
class UltimateTicTacToeAction(Action):
    type: Literal["PLACE_MARKER", "RESIGN"] = "PLACE_MARKER"
    payload: UltimateTicTacToePayload | None = None
