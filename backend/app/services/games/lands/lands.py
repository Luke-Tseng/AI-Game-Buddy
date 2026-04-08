import logging
import random

from pydantic import validate_call

from ..game_interface import GameSystem, PrivateStates
from . import lands_vars as lv
from .lands_interface import LandsAction, LandsPayload, LandsPrivateState, LandsState

logger = logging.getLogger(__name__)


class LandsSystem(GameSystem[LandsState, LandsAction]):
    """
    Implements the game logic for Lands.
    """

    @validate_call  # Check type constraints for parameters
    def initialize_game(self, player_ids: list[str]) -> LandsState:
        if len(player_ids) != 2:
            raise ValueError("Lands requires exactly 2 players.")

        new_state = LandsState(
            turn=1,
            boards={pid: [0, 0, 0, 0, 0] for pid in player_ids},
            discard={pid: [0, 0, 0, 0, 0] for pid in player_ids},
            player_ids=player_ids,
            winner=None,
            main_player_index=0,
            countered=0,
            current_player_index=0,
            private_state=PrivateStates(
                states={
                    pid: LandsPrivateState(
                        hand=[0, 0, 0, 0, 0], deck=self._initialize_deck()
                    )
                    for pid in player_ids
                }
            ),
        )

        for pid in player_ids:
            new_state = self._draw_cards(new_state, pid, 5)

        return new_state

    @validate_call
    def make_action(
        self, state: LandsState, player_id: str, action: LandsAction
    ) -> LandsState:
        self.is_action_valid(state, player_id, action)

        new_state = state.model_copy(deep=True)
        match action.type:
            case "RESIGN":
                new_state.winner = new_state.player_ids[
                    1 - new_state.current_player_index
                ]
                new_state.finished = True
            case "PLAY_ENERGY":
                card_type = action.payload.target
                new_state.private_state.states[player_id].hand[card_type] -= 1
                new_state.pending_card = card_type
                new_state.current_player_index = 1 - new_state.current_player_index
                new_state.phase = new_state.phase.next_phase()
            case "COUNTER":
                # Counter change stopped
                if action.payload.target == 0:
                    # Move to resolution phase
                    new_state.phase = new_state.phase.next_phase()
                    if (
                        new_state.countered % 2 == 0
                    ):  # Not countered or countered the counter
                        # Card goes to the board
                        main_player_id = state.player_ids[state.main_player_index]
                        new_state.current_player_index = new_state.main_player_index
                        card_type = state.pending_card
                        if card_type is not None:
                            new_state.boards[main_player_id][card_type] += 1

                        # Check for the winner
                        new_state = self._check_win_condition(new_state, main_player_id)
                        if new_state.winner:
                            return new_state

                        new_state = self._resolve_after_counter_fail(new_state)
                    else:
                        # Counter went through, so main player loses their card
                        main_player_id = state.player_ids[state.main_player_index]
                        card_type = state.pending_card
                        if card_type is not None:
                            new_state.discard[main_player_id][card_type] += 1
                        new_state = self._end_turn(new_state)
                        new_state = self._start_turn(new_state)
                else:  # Countering
                    # If it is an initial counter
                    if new_state.countered == 0:
                        pending_card = state.pending_card
                        if pending_card is not None:
                            new_state.private_state.states[player_id].hand[
                                lv.WATER
                            ] -= 1
                            new_state.discard[player_id][lv.WATER] += 1
                            new_state.private_state.states[player_id].hand[
                                pending_card
                            ] -= 1
                            new_state.discard[player_id][pending_card] += 1
                            new_state.countered += 1
                    else:  # If it is a counter to a counter
                        new_state.private_state.states[player_id].hand[lv.WATER] -= 2
                        new_state.discard[player_id][lv.WATER] += 2
                        new_state.countered += 1
                    # Switch the turn. The other player can counter again
                    new_state.current_player_index = 1 - new_state.current_player_index
            case "CHOOSE_TARGET":  # Resolving the effect of a card
                new_state = self._resolve_target_choice(
                    new_state, player_id, action.payload.target
                )
        return new_state

    @validate_call
    def get_valid_actions(self, state: LandsState, player_id: str) -> list[LandsAction]:
        valid_actions = []
        # If the game is finished or it's not the player's turn, they cannot act
        if state.finished or player_id != state.player_ids[state.current_player_index]:
            return valid_actions

        # Always possible to resign for the current player
        valid_actions.append(LandsAction(type="RESIGN", payload=None))

        match state.phase.current:
            case "MAIN_PHASE":
                # Only allowed action is to play a card from hand
                for card_type, count in enumerate(
                    state.private_state.states[player_id].hand
                ):
                    if count > 0:
                        valid_actions.append(
                            LandsAction(
                                type="PLAY_ENERGY",
                                payload=LandsPayload(target=card_type),
                            )
                        )
            case "COUNTER_PHASE":
                # player can choose to counter or not
                valid_actions.append(
                    LandsAction(type="COUNTER", payload=LandsPayload(target=0))
                )  # Don't counter

                # Check if can counter
                pending_card = state.pending_card

                if pending_card is not None:
                    hand = state.private_state.states[player_id].hand
                    # If it is the first counter
                    if state.countered == 0:
                        # Need 1 water and 1 matching card
                        if hand[lv.WATER] > 0 and hand[pending_card] > 0:
                            # Special case: if pending card is water, need 2 water cards
                            if pending_card == lv.WATER and hand[lv.WATER] < 2:
                                pass
                            else:
                                valid_actions.append(
                                    LandsAction(
                                        type="COUNTER", payload=LandsPayload(target=1)
                                    )
                                )  # Counter
                    else:  # If it is a counter to a counter, need two water cards
                        if hand[lv.WATER] > 1:
                            valid_actions.append(
                                LandsAction(
                                    type="COUNTER", payload=LandsPayload(target=1)
                                )
                            )  # Counter
            case "RESOLUTION_PHASE":
                # player can only choose a target from the selection
                if state.selection:
                    if (
                        state.pending_card == lv.DARKNESS
                        and state.current_player_index == 1 - state.main_player_index
                    ):
                        # If it is opponent's turn, they have to choose three cards from their hand to reveal
                        hand = state.private_state.states[player_id].hand
                        if sum(hand) <= 3:
                            # If they have 3 or fewer cards, they have to reveal all of them
                            entire_hand = []
                            for card_type, count in enumerate(hand):
                                entire_hand.extend([card_type] * count)
                            valid_actions.append(
                                LandsAction(
                                    type="CHOOSE_TARGET",
                                    payload=LandsPayload(target=entire_hand),
                                )
                            )
                        # Otherwise, they can choose any combination of 3 cards from their hand, including duplicates
                        else:
                            from itertools import combinations_with_replacement

                            unique_cards = [
                                card_type
                                for card_type, count in enumerate(hand)
                                if count > 0
                            ]
                            possible_combinations = set(
                                combinations_with_replacement(unique_cards, 3)
                            )
                            for combo in possible_combinations:
                                # Check if the player has enough cards to make this combination
                                temp_hand = hand.copy()
                                valid_combo = True
                                for card in combo:
                                    if temp_hand[card] > 0:
                                        temp_hand[card] -= 1
                                    else:
                                        valid_combo = False
                                        break
                                if valid_combo:
                                    valid_actions.append(
                                        LandsAction(
                                            type="CHOOSE_TARGET",
                                            payload=LandsPayload(target=list(combo)),
                                        )
                                    )
                    else:
                        for target in state.selection:
                            valid_actions.append(
                                LandsAction(
                                    type="CHOOSE_TARGET",
                                    payload=LandsPayload(target=target),
                                )
                            )
                else:
                    # Edge case: no valid targets (e.g. opponent has no cards on board for fire)
                    # Allow player to choose no target, which will effectively skip the effect
                    valid_actions.append(
                        LandsAction(
                            type="CHOOSE_TARGET", payload=LandsPayload(target=None)
                        )
                    )

        return valid_actions

    @validate_call
    def is_action_valid(
        self, state: LandsState, player_id: str, action: LandsAction
    ) -> bool:
        valid_actions = self.get_valid_actions(state, player_id)
        if action not in valid_actions:
            raise ValueError("Invalid action.")
        return True

    # --- Helper methods ---

    # Handles the turn logic after a counter has been fizzled
    def _resolve_after_counter_fail(self, state: LandsState) -> LandsState:
        main_player_id = state.player_ids[state.main_player_index]
        opponent_id = state.player_ids[1 - state.main_player_index]
        card_type = state.pending_card

        match card_type:
            case lv.GRASS:
                state.current_player_index = state.main_player_index
                state.selection = [
                    i
                    for i, count in enumerate(state.discard[main_player_id])
                    if count > 0
                ]
            case lv.LIGHTNING:
                state = self._draw_cards(state, main_player_id, 1)
                state = self._end_turn(state)
                state = self._start_turn(state)
            case lv.FIRE:
                state.current_player_index = state.main_player_index
                state.selection = [
                    i for i, count in enumerate(state.boards[opponent_id]) if count > 0
                ]
            case lv.DARKNESS:
                # Opponent has to choose a card from their hand if they have any
                state.current_player_index = 1 - state.main_player_index
                # Put copy of opponent's hand into selection
                state.selection = list(state.private_state.states[opponent_id].hand)
            case lv.WATER:
                state.current_player_index = state.main_player_index
                state.selection = [0, 1]  # 0: keep on top, 1: move to bottom
                state.private_state.states[
                    main_player_id
                ].top_card = state.private_state.states[main_player_id].deck[0]
        return state

    def _check_win_condition(self, state: LandsState, player_id: str) -> LandsState:
        board = state.boards[player_id]

        # Check for 5 of the same type of energy
        if any(count >= 5 for count in board):
            state.winner = player_id
            state.finished = True
            return state

        # Check for 1 of each type of energy
        if all(count >= 1 for count in board):
            state.winner = player_id
            state.finished = True
            return state

        return state

    # Start a draw phase for the main player
    def _start_turn(self, state: LandsState) -> LandsState:
        state.turn += 1

        # Draw one Card, but not on the first turn
        if state.turn > 1:
            player_id = state.player_ids[state.main_player_index]
            state = self._draw_cards(state, player_id, 1)

        # Move to Main Phase
        state.phase = state.phase.next_phase()
        return state

    def _end_turn(self, state: LandsState) -> LandsState:
        # switch main player
        state.main_player_index = 1 - state.main_player_index
        state.current_player_index = state.main_player_index

        # Reset turn-specific variables
        state.countered = 0
        state.pending_card = None
        state.selection = None
        state.phase = state.phase.next_phase()  # Back to draw phase

        return state

    def _resolve_target_choice(
        self, state: LandsState, player_id: str, target: int
    ) -> LandsState:
        active_player_id = player_id
        opponent_id = state.player_ids[1 - state.current_player_index]
        card_type = state.pending_card

        match card_type:
            case lv.GRASS:
                if target is not None:
                    state.discard[active_player_id][target] -= 1
                    state.private_state.states[active_player_id].hand[target] += 1
                state = self._end_turn(state)
                state = self._start_turn(state)
            case lv.FIRE:
                if target is not None:
                    state.boards[opponent_id][target] -= 1
                    state.discard[opponent_id][target] += 1
                state = self._end_turn(state)
                state = self._start_turn(state)
            case lv.DARKNESS:
                # If it is opponent's turn, target is a chosen selection of cards from their hand to reveal
                if state.current_player_index == 1 - state.main_player_index:
                    state.selection = list(target)
                    state.current_player_index = state.main_player_index
                else:  # If it is main player's turn, target is a card to discard from opponent's hand
                    if target is not None:
                        state.private_state.states[opponent_id].hand[target] -= 1
                        state.discard[opponent_id][target] += 1
                    state = self._end_turn(state)
                    state = self._start_turn(state)
            case lv.WATER:
                if target is not None:
                    # target is either 0 (keep it top) or 1 (move to bottom)
                    if target == 1:  # Move to bottom
                        top_card = state.private_state.states[
                            active_player_id
                        ].deck.pop(0)
                        state.private_state.states[active_player_id].deck.append(
                            top_card
                        )
                    # Hide top card
                    state.private_state.states[active_player_id].top_card = None

                state = self._end_turn(state)
                state = self._start_turn(state)
        return state

    # Create a deck with 5 of each type of card (0-4)
    def _initialize_deck(self) -> list[int]:
        deck = [i for i in range(5) for _ in range(5)]
        random.shuffle(deck)
        return deck

    # Draw num_cards from the player's deck to their hand
    def _draw_cards(
        self, state: LandsState, player_id: str, num_cards: int
    ) -> LandsState:
        drawn_cards = []
        for _ in range(num_cards):
            if not state.private_state.states[player_id].deck:
                state = self._reshuffle_discard_into_deck(state, player_id)
                if not state.private_state.states[player_id].deck:
                    # No cards left to draw
                    break

            card = state.private_state.states[player_id].deck.pop(0)
            drawn_cards.append(card)

        for card in drawn_cards:
            state.private_state.states[player_id].hand[card] += 1

        return state

    # shuffle the player's discard pile back into their deck
    def _reshuffle_discard_into_deck(
        self, state: LandsState, player_id: str
    ) -> LandsState:
        discard_pile_cards = []
        for card_type, count in enumerate(state.discard[player_id]):
            discard_pile_cards.extend([card_type] * count)

        state.private_state.states[player_id].deck.extend(discard_pile_cards)
        random.shuffle(state.private_state.states[player_id].deck)
        state.discard[player_id] = [0, 0, 0, 0, 0]
        return state
