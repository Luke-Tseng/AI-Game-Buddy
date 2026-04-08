# main.py
import os
import sys

# Add the game directory to the Python path to find the modules
# This might not be necessary depending on your setup, but it's robust.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from games.ulttt.ultimate_tic_tac_toe import UltimateTicTacToeSystem
from games.ulttt.ulttt_interface import (
    UltimateTicTacToeAction,
    UltimateTicTacToePayload,
    UltimateTicTacToeState,
)


def print_board(state: UltimateTicTacToeState):
    """Renders the entire game state to the console."""
    os.system("cls" if os.name == "nt" else "clear")
    print("--- Ultimate Tic-Tac-Toe ---")
    print()

    # Board and Meta Board characters
    markers = {"X": "X", "O": "O", None: "."}
    meta_markers = {"X": "X", "O": "O", "-": "#", None: " "}

    # Print board row by row, including meta board status on the side
    for board_r in range(3):
        for r in range(3):
            line = ""
            # Print a small board row
            for board_c in range(3):
                for c in range(3):
                    line += f" {markers[state.large_board[board_r][board_c][r][c]]}"
                line += " |"

            # Add meta board info for the middle row of each large board row
            if r == 1:
                line += "   Meta: |"
                for meta_c in range(3):
                    line += f" {meta_markers[state.meta_board[board_r][meta_c]]}"
                line += " |"

            print(line[:-1])  # Print line without the last '|'

        if board_r < 2:
            print("---------+---------+---------")

    print("\n" + "=" * 30 + "\n")


def get_player_input(player_marker: str) -> tuple[int, int, int, int]:
    """Gets and validates move input from the command line."""
    while True:
        try:
            prompt = f"Player '{player_marker}', enter move (BoardRow BoardCol CellRow CellCol) or RESIGN to forfeit: "
            parts = input(prompt).split()
            if len(parts) == 1 and parts[0].upper() == "RESIGN":
                return -1, -1, -1, -1  # Special value indicating resignation
            if len(parts) != 4:
                print("Invalid input. Please enter 4 numbers separated by spaces.")
                continue

            coords = [int(p) for p in parts]
            if not all(0 <= c <= 2 for c in coords):
                print("Invalid input. All numbers must be between 0 and 2.")
                continue

            return coords[0], coords[1], coords[2], coords[3]
        except ValueError:
            print("Invalid input. Please enter numbers only.")


def main():
    """Main game loop."""
    system = UltimateTicTacToeSystem()
    state = system.initialize_game(player_ids=["Player 1", "Player 2"])

    while not state.finished:
        print_board(state)

        curr_player_index = state.current_player_index
        player_id = state.player_ids[curr_player_index]
        player_marker = "X" if curr_player_index == 0 else "O"

        if state.active_board:
            br, bc = state.active_board
            print(f"--- {player_id}'s Turn ({player_marker}) ---")
            print(f"You MUST play in board ({br}, {bc})")
        else:
            print(f"--- {player_id}'s Turn ({player_marker}) ---")
            print("You have a FREE MOVE (play in any non-finished board).")

        # Loop until the player provides a valid move according to game rules
        while True:
            try:
                board_r, board_c, r, c = get_player_input(player_marker)
                if board_r == -1:  # Player chose to resign
                    action = UltimateTicTacToeAction(
                        type="RESIGN",
                        payload=None,  # No payload needed for resignation
                    )
                    state = system.make_action(
                        state, player_id=player_id, action=action
                    )
                    break  # Exit the input loop after resignation
                action = UltimateTicTacToeAction(
                    type="PLACE_MARKER",
                    payload=UltimateTicTacToePayload(
                        board_row=board_r, board_col=board_c, row=r, col=c
                    ),
                )
                state = system.make_action(state, player_id=player_id, action=action)
                break  # Move was successful, break the input loop
            except ValueError as e:
                print(f"Invalid Move: {e}. Please try again.")

    # Game Over
    print_board(state)
    winner = state.winner
    if winner == "Draw":
        print("It's a draw! The game is over.")
    elif winner:
        print(f"Congratulations {winner}! You have won the game! 🏆")


if __name__ == "__main__":
    main()
