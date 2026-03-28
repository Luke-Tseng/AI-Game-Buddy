import pytest
from pydantic import ValidationError

from app.services.games.ulttt.ulttt_interface import UltimateTicTacToeState


@pytest.fixture
def player_ids() -> list[str]:
    """Provides a standard list of player IDs."""
    return ["player1", "player2"]


@pytest.fixture
def valid_state(player_ids: list[str]) -> UltimateTicTacToeState:
    """Provides a basic, valid game state."""
    return UltimateTicTacToeState(player_ids=player_ids, meta={"curr_player_index": 0})


class TestUltimateTicTacToeStateValidation:
    def test_valid_initial_state_passes(self, valid_state: UltimateTicTacToeState):
        # Should not raise an error
        assert valid_state is not None

    def test_mismatched_meta_board_raises_error(
        self, valid_state: UltimateTicTacToeState
    ):
        # Manually create an invalid state
        valid_state.large_board[0][0][0][0] = "X"
        valid_state.large_board[0][0][0][1] = "X"
        valid_state.large_board[0][0][0][2] = "X"
        # meta_board[0][0] is still None, which is incorrect
        with pytest.raises(ValidationError, match="Mismatched meta_board"):
            UltimateTicTacToeState.model_validate(valid_state.model_dump())

    def test_active_board_pointing_to_finished_board_raises_error(
        self, valid_state: UltimateTicTacToeState
    ):
        # Win a board
        valid_state.large_board[0][0][0][0] = "X"
        valid_state.large_board[0][0][0][1] = "X"
        valid_state.large_board[0][0][0][2] = "X"
        valid_state.meta_board[0][0] = "X"
        # Set active_board to point to the won board
        valid_state.active_board = (0, 0)
        with pytest.raises(
            ValidationError, match="active_board .* points to a finished board"
        ):
            UltimateTicTacToeState.model_validate(valid_state.model_dump())

    def test_invalid_turn_order_raises_error(self, valid_state: UltimateTicTacToeState):
        # X's turn (p_index=0), but O has more pieces
        valid_state.large_board[0][0][0][0] = "O"
        valid_state.large_board[0][0][0][1] = "O"
        with pytest.raises(ValidationError, match="Invalid turn order"):
            UltimateTicTacToeState.model_validate(valid_state.model_dump())

    def test_finished_game_without_winner_raises_error(
        self, valid_state: UltimateTicTacToeState
    ):
        valid_state.finished = True
        # No winner is set in meta
        with pytest.raises(
            ValidationError,
            match="Game is marked as finished, but there is no winner or draw.",
        ):
            UltimateTicTacToeState.model_validate(valid_state.model_dump())

    def test_unfinished_game_with_winner_raises_error(
        self, valid_state: UltimateTicTacToeState
    ):
        # Create an inconsistent state where meta_board has a winner, but large_board is empty
        valid_state.meta_board[0][0] = "X"
        valid_state.meta["winner"] = "player1"

        # Game is not marked as finished. The validator should catch the inconsistency.
        with pytest.raises(ValidationError, match="Mismatched meta_board"):
            UltimateTicTacToeState.model_validate(valid_state.model_dump())
