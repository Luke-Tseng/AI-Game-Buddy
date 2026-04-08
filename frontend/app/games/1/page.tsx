"use client";

import { useState } from "react";

import { UltimateBoard } from "@/components/tic-tac-toe/ultimate-board";
import {
    UltimateTicTacToeAction,
    UltimateTicTacToeState,
} from "@/types/games/ulttt.types";

// This is an interactive demonstration page for the UltimateBoard component.
// It shows how a parent "Game Room" would manage state.
// The logic in `handleMakeMove` is a simplified simulation of a backend response.

const initialGameState: UltimateTicTacToeState = {
    game_id: "sample-game-123",
    player_ids: ["player-1", "player-2"],
    finished: false,
    curr_player_index: 0,
    player_symbols: { "player-1": "X", "player-2": "O" },
    winner: null,
    turn: 1,
    large_board: Array(3)
        .fill(null)
        .map(() =>
            Array(3)
                .fill(null)
                .map(() =>
                    Array(3)
                        .fill(null)
                        .map(() => Array(3).fill(null))
                )
        ),
    meta_board: Array(3)
        .fill(null)
        .map(() => Array(3).fill(null)),
    active_board: null, // Start with any board being active
};

export default function UltimateTicTacToePage() {
    const [gameState, setGameState] = useState(initialGameState);

    // This handler simulates a parent component's response after a move is made.
    // It computes the next state, just as a backend would.
    const handleMakeMove = (action: UltimateTicTacToeAction) => {
        if (gameState.finished || !action.payload) return;

        const { board_row, board_col, row, col } = action.payload;

        // Create a deep copy to avoid direct state mutation.
        const newState: UltimateTicTacToeState = JSON.parse(
            JSON.stringify(gameState)
        );
        const currentPlayerSymbol =
            newState.player_symbols[
                newState.player_ids[newState.curr_player_index]
            ];

        // 1. Place the piece on the board.
        newState.large_board[board_row][board_col][row][col] =
            currentPlayerSymbol;

        // 2. For demonstration, we'll set the next active board.
        // The real backend logic would also check for local and global winners here.
        newState.active_board = [row, col];

        // 3. Switch the current player index for the next turn.
        newState.curr_player_index =
            (newState.curr_player_index + 1) % newState.player_ids.length;
        newState.turn = (newState.turn ?? 0) + 1;

        // Update the state to re-render the component.
        setGameState(newState);
    };

    const handleReset = () => {
        setGameState(initialGameState);
    };

    const currentPlayerSymbol =
        gameState.player_symbols?.[
            gameState.player_ids[gameState.curr_player_index]
        ] || "Unknown";

    return (
        <div className="flex flex-col items-center p-4">
            <h1 className="text-4xl font-bold mb-4">Ultimate Tic Tac Toe</h1>
            <div className="text-2xl mb-4">
                Turn {gameState.turn}: Player {currentPlayerSymbol}&apos;s move
            </div>
            <UltimateBoard gameState={gameState} onMakeMove={handleMakeMove} />
            <button
                onClick={handleReset}
                className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
            >
                Reset Game
            </button>
            <div className="mt-4 text-sm text-gray-500">
                <p>
                    Clickable cells are now derived directly from the game
                    state.
                </p>
            </div>
        </div>
    );
}
