import random
from typing import Any

import chess
from chess import InvalidMoveError
from pydantic import validate_call

from ..game_interface import GameSystem
from .chess_interface import (
    ChessAction,
    ChessMovePayload,
    ChessState,
)


class ChessSystem(GameSystem[ChessState, ChessAction]):
    @validate_call
    def initialize_game(self, player_ids: list[str]) -> ChessState:
        if len(player_ids) < 2:
            raise ValueError("Chess requires 2 players.")

        selected_players = random.sample(player_ids, 2)
        return ChessState(
            player_ids=selected_players,
            turn=1,
            current_player_index=0,
        )

    def _create_board_from_state(self, state: ChessState) -> chess.Board:
        """Creates a chess board from current state"""
        return chess.Board(fen=state.board_fen)

    @validate_call  # validate that ChessState and ChessAction
    def make_action(
        self, state: ChessState, player_id: str, action: ChessAction
    ) -> ChessState:
        self.is_action_valid(state, player_id, action)

        board = self._create_board_from_state(state=state)

        if action.type == "RESIGN":
            current_player_index = state.current_player_index
            winner = "white" if board.turn == chess.BLACK else "black"
            game_result = f"{winner}_wins"
            new_state = state.model_copy(
                update={
                    "game_result": game_result,
                    "finished": True,
                },
                deep=True,
            )
            return new_state

        move = chess.Move.from_uci(action.payload.move)
        board.push(move)

        new_move_history = state.move_history + [action.payload.move]

        current_player_index = state.current_player_index
        next_player_index = 1 - current_player_index

        game_result = None
        if board.is_checkmate():
            winner = "white" if board.turn == chess.BLACK else "black"
            game_result = f"{winner}_wins"
        elif (
            board.is_stalemate()
            or board.is_insufficient_material()
            or board.is_seventyfive_moves()
            or board.is_fivefold_repetition()
        ):
            game_result = "draw"

        new_state = ChessState(
            finished=game_result is not None,
            game_id=state.game_id,
            player_ids=state.player_ids,
            turn=state.turn + 1,
            current_player_index=next_player_index,
            board_fen=board.fen(),
            game_result=game_result,
            move_history=new_move_history,
        )

        return new_state

    @validate_call  # validate ChessState
    def get_valid_actions(self, state: ChessState, player_id: str) -> list[ChessAction]:
        board = self._create_board_from_state(state=state)

        if state.finished:
            return []

        current_player_index = state.current_player_index
        if state.player_ids[current_player_index] != player_id:
            return []

        valid_moves = [ChessAction(type="RESIGN", payload=None)]
        for move in board.legal_moves:
            valid_moves.append(ChessAction(payload=ChessMovePayload(move=move.uci())))

        return valid_moves

    @validate_call
    def is_action_valid(
        self,
        state: ChessState,
        player_id: str,
        action: ChessAction,
    ) -> bool:
        if state.finished:
            raise ValueError("Game is already finished.")

        current_player_index = state.current_player_index
        if state.player_ids[current_player_index] != player_id:
            raise ValueError("It's not your turn.")

        if action.type == "MAKE_MOVE":
            try:
                board = self._create_board_from_state(state=state)
                move = chess.Move.from_uci(action.payload.move)
                if move not in board.legal_moves:
                    raise ValueError("Move is invalid.")
            except InvalidMoveError as e:
                raise ValueError("Move is invalid.") from e

        return True

    @validate_call
    def get_board_representation(self, state: ChessState) -> dict[str, Any]:
        """Returns a dictionary representation of the current board state"""
        board = self._create_board_from_state(state=state)
        return {
            "fen": board.fen(),
            "ascii": str(board),
            "turn": "white" if board.turn else "black",
            "castling_rights": {
                "white_kingside": board.has_kingside_castling_rights(chess.WHITE),
                "white_queenside": board.has_queenside_castling_rights(chess.WHITE),
                "black_kingside": board.has_kingside_castling_rights(chess.BLACK),
                "black_queenside": board.has_queenside_castling_rights(chess.BLACK),
            },
            "en_passant": board.ep_square if board.ep_square else None,
            "halfmove_clock": board.halfmove_clock,
            "fullmove_number": board.fullmove_number,
            "is_check": board.is_check(),
            "is_checkmate": board.is_checkmate(),
            "is_stalemate": board.is_stalemate(),
        }
