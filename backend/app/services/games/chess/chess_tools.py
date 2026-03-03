import logging

from app.schemas import GameUpdate
from app.services.game_service_factory import GameServiceFactory
from app.services.room_service import RoomService

from .chess_interface import ChessAction, ChessMovePayload, ChessState

logger = logging.getLogger(__name__)


def chess_tools(
    mcp, room_service: RoomService, game_service_factory: GameServiceFactory
):
    """
    Registers Chess tools that gets and sets game states via RoomService.
    """

    @mcp.tool()
    async def get_chess_board_representation(room_id: str) -> dict:
        """
        Returns a dictionary representation of the current chess game state

        Use this tool to synchronize your understanding of the board. It provides
        both machine-readable FEN and human-readable ASCII formats.

        Args:
            room_id (str): Room ID of where the game state is in.

        Returns:
            dict: Dictionary representation of the current chess game state.
                - fen (str): The standard Forsyth-Edwards Notation of the board.
                - ascii (str): A 2D text-based visual of the board. Pieces are
                  represented by letters (Uppercase=White, Lowercase=Black).
                - turn (str): 'white' or 'black', indicating whose turn it is.
                - castling_rights (dict): Boolean flags for 'white_kingside',
                  'white_queenside', 'black_kingside', and 'black_queenside'.
                - en_passant (str | None): The square coordinate if an en passant
                  capture is available (e.g., 'e3').
                - halfmove_clock (int): Number of halfmoves since the last capture
                  or pawn advance (used for the 50-move rule).
                - fullmove_number (int): The count of the full turns in the game.
                - is_check (bool): True if the current player's king is under attack.
                - is_checkmate (bool): True if the game has ended via checkmate.
                - is_stalemate (bool): True if the game is a draw due to no legal moves.
        """

        room = await room_service.get_room(room_id)
        if not room:
            logger.error(f"Error in get_chess_board_representation: Room {room_id} not found")
            return {"error": f"Room {room_id} not found."}

        # Check if game_state exists
        if not room.game_state or room.game_state == {}:
            logger.error("Error in get_chess_board_representation: Game has not been initialized yet")
            return {"error": "Game has not been initialized yet."}

        chess_system = game_service_factory.get_service(game_type="chess")

        state = ChessState.model_validate(room.game_state)
        return chess_system.get_board_representation(state)

    @mcp.tool()
    async def list_legal_chess_moves(room_id: str) -> dict:
        """
        Retrieves all valid moves for the player whose turn it is in a specific room.

        This tool connects to the room service, fetches the current state, and
        calculates legal moves based on the FEN board position. It prevents
        out-of-turn move attempts by checking the internal turn counter.

        Args:
            room_id (str): The unique identifier for the game room.

        Returns:
            dict: Dictionary containing legal move of the current player.
                - current_player_id (str): The ID of the user who must move next.
                - turn_color (str): Either 'white' or 'black'.
                - legal_moves (list[str]): A list of moves in UCI format
                  (e.g., 'e2e4', 'g1f3'). If empty, the game may be over.
                - error (str, optional): Detailed message if the room or game state
                  is missing/uninitialized.
        """

        room = await room_service.get_room(room_id)
        if not room:
            logger.error(f"Error in list_legal_chess_moves: Room {room_id} not found")
            return {"error": f"Room {room_id} not found."}
        # Check if game_state exists
        if not room.game_state or room.game_state == {}:
            logger.error("Error in list_legal_chess_moves: Game has not been initialized yet")
            return {"error": "Game has not been initialized yet."}

        chess_system = game_service_factory.get_service(game_type="chess")

        state = ChessState.model_validate(room.game_state)
        current_player_index = state.current_player_index
        current_player = state.player_ids[current_player_index]
        actions = chess_system.get_valid_actions(state, current_player)

        moves = [a.payload.move for a in actions if a.type == "MAKE_MOVE"]

        return {
            "room_id": room_id,
            "current_turn": "white" if current_player_index == 0 else "black",
            "legal_moves": moves,
        }

    @mcp.tool()
    async def play_chess_move(room_id: str, move_uci: str) -> dict:
        """
        Executes a legal chess move in the specified room and updates the persistent database.

        This is a state-changing tool. It identifies the current player, validates
        the move against chess rules, updates the board FEN, increments the turn
        counter, and saves the result to the Room Service.

        Args:
            room_id (str): The unique identifier for the game room.
            move_uci (str): The move to play in Universal Chess Interface format
                           (e.g., 'e2e4', 'e7e5', 'e1g1' for castling).

        Returns:
            dict: A status report of the action:
                - status (str): 'success' if the move was applied, 'error' otherwise.
                - new_fen (str): The updated board state in FEN format after the move.
                - game_over (bool): True if this move resulted in checkmate,
                  stalemate, or a draw.
                - result (str | None): If game_over is True, this contains the
                  outcome (e.g., 'white_wins', 'black_wins', 'draw').
                  Remains null during active play.
                - message (str, optional): A descriptive error message if the
                  move was illegal or the room was not found.
        """

        room = await room_service.get_room(room_id)
        if not room:
            logger.error(f"Error in play_chess_move: Room {room_id} not found")
            return {"error": f"Room {room_id} not found."}

        if not room.game_state or room.game_state == {}:
            logger.error("Error in play_chess_move: Game has not been initialized yet")
            return {"error": "Game has not been initialized yet."}

        chess_system = game_service_factory.get_service(game_type="chess")

        state = ChessState.model_validate(room.game_state)
        current_player_index = state.meta["current_player_index"]
        current_player_id = state.player_ids[current_player_index]

        action = ChessAction(type="MAKE_MOVE", payload=ChessMovePayload(move=move_uci))

        try:
            # Create new state from action
            new_state = chess_system.make_action(state, current_player_id, action)
            new_state_dict = new_state.model_dump(mode="json")

            # Update databases on move made
            await room_service.set_game_state(room_id, new_state_dict)

            # Broadcast to WebSockets via ConnectionService
            user_list = await room_service.get_user_list(room_id)
            game_update = GameUpdate(room_id=room_id, game_state=new_state_dict)

            await room_service._connection_service.publish_event(
                channel="game_update",
                user_list=user_list,
                message_data=game_update.model_dump(),
            )

            return {"status": "success", "new_fen": new_state.board_fen}
        except Exception as e:
            logger.error(f"Error in play_chess_move: {e}")
            return {"status": "error", "message": str(e)}
