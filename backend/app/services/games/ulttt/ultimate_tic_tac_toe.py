import logging

from pydantic import validate_call

from ..game_interface import GameSystem
from .ulttt_interface import (
    UltimateTicTacToeAction,
    UltimateTicTacToePayload,
    UltimateTicTacToeState,
)

logger = logging.getLogger(__name__)


class UltimateTicTacToeSystem(
    GameSystem[UltimateTicTacToeState, UltimateTicTacToeAction]
):
    """
    Implements the game logic for Ultimate Tic-Tac-Toe.
    """

    @validate_call  # Check type constraints for parameters
    def initialize_game(self, player_ids: list[str]) -> UltimateTicTacToeState:
        if len(player_ids) != 2:
            raise ValueError("Ultimate Tic-Tac-Toe requires exactly 2 players.")
        return UltimateTicTacToeState(
            player_ids=player_ids,
            winner=None,
            current_player_index=0,
        )

    @validate_call
    def make_action(
        self,
        state: UltimateTicTacToeState,
        player_id: str,
        action: UltimateTicTacToeAction,
    ) -> UltimateTicTacToeState:
        # Validate the action before proceeding.
        self.is_action_valid(state, player_id, action)

        new_state = state.model_copy(deep=True)
        if action.type == "RESIGN":
            new_state.winner = new_state.player_ids[
                1 - new_state.current_player_index
            ]
            new_state.finished = True
            return new_state

        p = action.payload
        marker = "X" if new_state.current_player_index == 0 else "O"

        # Apply the move to the board.
        new_state.large_board[p.board_row][p.board_col][p.row][p.col] = marker

        # Check if this move won the small board.
        small_board = new_state.large_board[p.board_row][p.board_col]
        board_status = UltimateTicTacToeState._check_board_status(
            small_board
        )  # 'X', 'O', '-', or None

        if board_status:
            new_state.meta_board[p.board_row][p.board_col] = board_status

            # If a small board was won, check if that wins the whole game.
            game_status = UltimateTicTacToeState._check_board_status(
                new_state.meta_board
            )
            if game_status:
                new_state.winner = player_id if game_status != "-" else "Draw"
                new_state.finished = True
                return new_state  # Game Over

        # Determine the next active board based on the inner cell played.
        next_board_status = new_state.meta_board[p.row][p.col]
        if next_board_status:
            # If the next board is already won/drawn, the player can go anywhere.
            new_state.active_board = None
        else:
            new_state.active_board = (p.row, p.col)

        # Switch to the next player.
        new_state.current_player_index = 1 - new_state.current_player_index

        return new_state

    @validate_call
    def get_valid_actions(
        self, state: UltimateTicTacToeState, player_id: str
    ) -> list[UltimateTicTacToeAction]:
        if (
            state.finished
            or state.player_ids[state.current_player_index] != player_id
        ):
            return []

        actions = [UltimateTicTacToeAction(type="RESIGN", payload=None)]

        # If active_board is set, player is forced to play there.
        if state.active_board:
            board_r, board_c = state.active_board
            small_board = state.large_board[board_r][board_c]
            for r in range(3):
                for c in range(3):
                    if small_board[r][c] is None:
                        actions.append(
                            UltimateTicTacToeAction(
                                payload=UltimateTicTacToePayload(
                                    board_row=board_r, board_col=board_c, row=r, col=c
                                )
                            )
                        )
        # Otherwise, player can play in any non-finished board.
        else:
            for board_r in range(3):
                for board_c in range(3):
                    # Check if the board is already won/drawn
                    if state.meta_board[board_r][board_c] is None:
                        small_board = state.large_board[board_r][board_c]
                        for r in range(3):
                            for c in range(3):
                                if small_board[r][c] is None:
                                    actions.append(
                                        UltimateTicTacToeAction(
                                            payload=UltimateTicTacToePayload(
                                                board_row=board_r,
                                                board_col=board_c,
                                                row=r,
                                                col=c,
                                            )
                                        )
                                    )
        return actions

    @validate_call
    def is_action_valid(
        self,
        state: UltimateTicTacToeState,
        player_id: str,
        action: UltimateTicTacToeAction,
    ) -> bool:
        if state.finished:
            raise ValueError("Game is already finished.")

        if player_id not in state.player_ids:
            raise ValueError("Invalid player ID.")

        if state.player_ids.index(player_id) != state.current_player_index:
            raise ValueError("It's not your turn.")

        if action.type == "PLACE_MARKER":
            p = action.payload

            if state.active_board and state.active_board != (p.board_row, p.board_col):
                raise ValueError(f"You must play in board {state.active_board}.")

            if state.meta_board[p.board_row][p.board_col] is not None:
                raise ValueError("This board is already finished.")

            if state.large_board[p.board_row][p.board_col][p.row][p.col] is not None:
                raise ValueError("This cell is already occupied.")

        return True
