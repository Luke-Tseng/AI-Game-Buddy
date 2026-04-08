export type SmallBoard = (CellValue | null)[][];
export type CellValue = "X" | "O" | "-" | null;

// Corresponds to the backend's UltimateTicTacToePayload schema
export type UltimateTicTacToePayload = {
    board_row: number;
    board_col: number;
    row: number;
    col: number;
};

// Corresponds to the backend's UltimateTicTacToeAction schema
export type UltimateTicTacToeAction = {
    type: "PLACE_MARKER" | "RESIGN";
    payload: UltimateTicTacToePayload | null;
};

// Corresponds to the backend's UltimateTicTacToeState schema,
// including fields inherited from the base GameState.
export type UltimateTicTacToeState = {
    // --- Inherited from base GameState ---
    game_id: string;
    player_ids: string[];
    finished: boolean;
    curr_player_index: number;
    player_symbols: {
        [playerId: string]: "X" | "O"; // Maps a player ID to their symbol
    };
    winner: string | null; // Can be a player ID or null
    turn: number | null;

    // --- UltimateTicTacToe-specific state ---
    large_board: SmallBoard[][];
    meta_board: SmallBoard; // Tracks winners of the small boards
    active_board: [number, number] | null;
};
