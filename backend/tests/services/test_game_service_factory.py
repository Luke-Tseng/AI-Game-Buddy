import pytest

from app.services.game_service_factory import GameServiceFactory
from app.services.games.game_interface import GameSystem

# --- Test Setup ---


# Create dummy classes that mimic the real game systems for isolated testing.
# We only care about their type, not their implementation.
class DummyChessSystem(GameSystem):
    def initialize_game(self, player_ids):
        pass

    def make_action(self, state, player_id, action):
        pass

    def get_valid_actions(self, state, player_id):
        pass

    def is_action_valid(self, state, player_id, action):
        pass


class DummyUltimateTicTacToeSystem(GameSystem):
    def initialize_game(self, player_ids):
        pass

    def make_action(self, state, player_id, action):
        pass

    def get_valid_actions(self, state, player_id):
        pass

    def is_action_valid(self, state, player_id, action):
        pass


@pytest.fixture
def game_factory() -> GameServiceFactory:
    """
    Provides a GameServiceFactory instance for testing.

    We override the internal service map to use our dummy classes. This decouples
    the factory test from the actual game logic classes, which is a best practice.
    """
    factory = GameServiceFactory()
    factory._service_map = {
        "chess": DummyChessSystem,
        "ultimate_tic_tac_toe": DummyUltimateTicTacToeSystem,
    }
    return factory


# --- Test Cases ---


def test_get_service_returns_correct_instance_type(game_factory: GameServiceFactory):
    """
    Tests if the factory returns an instance of the correct class for a given game type.
    """
    # ARRANGE & ACT
    chess_service = game_factory.get_service("chess")
    ulttt_service = game_factory.get_service("ultimate_tic_tac_toe")

    # ASSERT
    assert isinstance(chess_service, DummyChessSystem)
    assert isinstance(ulttt_service, DummyUltimateTicTacToeSystem)


def test_get_service_caches_instances(game_factory: GameServiceFactory):
    """
    Tests if the factory returns the exact same instance on subsequent calls
    for the same game type, verifying the caching mechanism.
    """
    # ARRANGE & ACT
    instance1 = game_factory.get_service("chess")
    instance2 = game_factory.get_service("chess")

    # ASSERT: We use 'is' to check that they are the same object in memory.
    assert instance1 is instance2


def test_get_service_creates_different_instances_for_different_games(
    game_factory: GameServiceFactory,
):
    """
    Tests if the factory creates unique instances for different game types.
    """
    # ARRANGE & ACT
    chess_service = game_factory.get_service("chess")
    ulttt_service = game_factory.get_service("ultimate_tic_tac_toe")

    # ASSERT
    assert chess_service is not ulttt_service


def test_get_service_raises_error_for_unknown_game_type(
    game_factory: GameServiceFactory,
):
    """
    Tests if the factory raises a ValueError for a game type that is not in its map.
    """
    # ARRANGE, ACT, & ASSERT
    with pytest.raises(ValueError, match="Unknown game type: checkers"):
        game_factory.get_service("checkers")
