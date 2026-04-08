from unittest.mock import patch

import pytest

from app.services.games.chess.chess_game import ChessSystem
from app.services.games.chess.chess_interface import (
    ChessAction,
    ChessMovePayload,
    ChessState,
)

# --- Fixtures ---


@pytest.fixture
def chess_system() -> ChessSystem:
    """Provides a fresh instance of the ChessSystem class."""
    return ChessSystem()


@pytest.fixture
def player_ids() -> list[str]:
    """Provides a standard list of player IDs."""
    return ["player1", "player2"]


@pytest.fixture
def initial_state(chess_system: ChessSystem, player_ids: list[str]) -> ChessState:
    """Provides a predictable, initialized game state for tests."""
    # We patch random.sample to ensure player1 is always white for consistent tests
    with patch("random.sample", return_value=player_ids):
        return chess_system.initialize_game(player_ids)


# --- Test Classes ---


class TestInitializeGame:
    def test_initialization_success(
        self, chess_system: ChessSystem, player_ids: list[str], mocker
    ):
        # ARRANGE: Mock random.sample for a predictable player order.
        mocker.patch("random.sample", return_value=["player1", "player2"])

        # ACT
        state = chess_system.initialize_game(player_ids)

        # ASSERT
        assert state.player_ids == ["player1", "player2"]
        assert state.current_player_index == 0
        assert (
            state.board_fen
            == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        )

    def test_initialization_fails_with_too_few_players(self, chess_system: ChessSystem):
        with pytest.raises(ValueError, match="Chess requires 2 players."):
            chess_system.initialize_game(["player1"])


class TestMakeAction:
    def test_make_valid_move(
        self, chess_system: ChessSystem, initial_state: ChessState
    ):
        action = ChessAction(payload=ChessMovePayload(move="e2e4"))
        new_state = chess_system.make_action(initial_state, "player1", action)

        assert new_state.turn == 2
        assert new_state.current_player_index == 1
        assert new_state.move_history == ["e2e4"]
        assert new_state.finished is False

    def test_make_move_causes_checkmate(self, chess_system: ChessSystem):
        fools_mate_fen = "rnbqkbnr/pppp1ppp/8/4p3/5PP1/8/PPPPP2P/RNBQKBNR b KQkq - 0 2"
        state = ChessState(
            player_ids=["p1", "p2"],
            current_player_index=1,
            board_fen=fools_mate_fen,
            turn=3,
        )
        action = ChessAction(payload=ChessMovePayload(move="d8h4"))

        new_state = chess_system.make_action(state, "p2", action)

        assert new_state.finished is True
        assert new_state.game_result == "black_wins"

    def test_resign_action_ends_game(
        self, chess_system: ChessSystem, initial_state: ChessState
    ):
        # ARRANGE: Player1 (White) decides to resign on their first turn.
        action = ChessAction(type="RESIGN")

        # ACT
        new_state = chess_system.make_action(initial_state, "player1", action)

        # ASSERT
        assert new_state.finished is True
        # Since White (player1) resigned, Black (player2) is the winner.
        assert new_state.game_result == "black_wins"
        assert new_state.board_fen == initial_state.board_fen  # Board is unchanged

    def test_make_invalid_move_raises_error(
        self, chess_system: ChessSystem, initial_state: ChessState
    ):
        action = ChessAction(payload=ChessMovePayload(move="e2e5"))  # Illegal move
        with pytest.raises(ValueError, match="Move is invalid."):
            chess_system.make_action(initial_state, "player1", action)


class TestValidActions:
    def test_get_valid_actions_for_current_player(
        self, chess_system: ChessSystem, initial_state: ChessState
    ):
        actions = chess_system.get_valid_actions(initial_state, "player1")

        # There are 20 possible opening moves + 1 RESIGN action.
        assert len(actions) == 21
        assert actions[0].type == "RESIGN"
        assert actions[1].type == "MAKE_MOVE"

    def test_get_valid_actions_for_other_player_is_empty(
        self, chess_system: ChessSystem, initial_state: ChessState
    ):
        actions = chess_system.get_valid_actions(initial_state, "player2")
        assert len(actions) == 0

    def test_is_action_valid_for_legal_move(
        self, chess_system: ChessSystem, initial_state: ChessState
    ):
        # A valid move for the correct player should return True and not raise an error.
        action = ChessAction(payload=ChessMovePayload(move="g1f3"))
        assert chess_system.is_action_valid(initial_state, "player1", action) is True

    def test_is_action_valid_for_resign(
        self, chess_system: ChessSystem, initial_state: ChessState
    ):
        # A RESIGN action for the correct player should return True.
        action = ChessAction(type="RESIGN")
        assert chess_system.is_action_valid(initial_state, "player1", action) is True

    def test_is_action_valid_raises_error_for_illegal_move(
        self, chess_system: ChessSystem, initial_state: ChessState
    ):
        action = ChessAction(
            payload=ChessMovePayload(move="g1f4")
        )  # Illegal knight move
        with pytest.raises(ValueError, match="Move is invalid."):
            chess_system.is_action_valid(initial_state, "player1", action)

    def test_is_action_valid_raises_error_for_wrong_player(
        self, chess_system: ChessSystem, initial_state: ChessState
    ):
        action = ChessAction(payload=ChessMovePayload(move="e7e5"))
        with pytest.raises(ValueError, match="It's not your turn."):
            chess_system.is_action_valid(initial_state, "player2", action)


class TestChessStateValidation:
    @pytest.mark.parametrize(
        "invalid_fen, error_msg",
        [
            ("invalid fen", "Invalid FEN string"),
            (
                "rnbqkbnr/pppppppp/9/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "Invalid FEN string",
            ),  # Invalid piece count
        ],
    )
    def test_invalid_fen_string_raises_error(self, invalid_fen: str, error_msg: str):
        with pytest.raises(ValueError, match=error_msg):
            ChessState(
                player_ids=["p1", "p2"],
                board_fen=invalid_fen,
                current_player_index=0,
            )

    def test_illegal_position_raises_error(self):
        # This FEN has a pawn on the 1st rank, which is illegal.
        illegal_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNP w KQkq - 0 1"
        with pytest.raises(ValueError, match="Invalid board position"):
            ChessState(
                player_ids=["p1", "p2"],
                board_fen=illegal_fen,
                current_player_index=0,
            )

    def test_inconsistent_finished_flag_raises_error(self):
        with pytest.raises(
            ValueError, match="If game_result is set, finished must be True"
        ):
            ChessState(
                player_ids=["p1", "p2"],
                game_result="white_wins",
                finished=False,
                current_player_index=0,
            )

    def test_inconsistent_turn_white_raises_error(self):
        # FEN is white's turn, but index is 1 (black)
        with pytest.raises(
            ValueError,
            match="FEN indicates white's turn, but current_player_index is not 0",
        ):
            ChessState(
                player_ids=["p1", "p2"],
                board_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                current_player_index=1,
            )

    def test_inconsistent_turn_black_raises_error(self):
        # FEN is black's turn, but index is 0 (white)
        with pytest.raises(
            ValueError,
            match="FEN indicates black's turn, but current_player_index is not 1",
        ):
            ChessState(
                player_ids=["p1", "p2"],
                board_fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                current_player_index=0,
            )
