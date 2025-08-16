import unittest
from unittest.mock import MagicMock
from ecs.systems.ai.main import BasicAISystem, AITurnContext
from ecs.systems.ai import utils, movement
from tests.test_fixtures import BaseAITestCase

class TestAIRetreatAndCover(BaseAITestCase):
    def test_find_best_retreat_tile_basic(self):
        """Test that AI can find a retreat tile with better future score."""
        # Mock reachable tiles
        self.mock_movement_system.get_reachable_tiles.return_value = [(1, 1, 1), (3, 3, 2)]

        # Create fresh context
        ctx = self.create_fresh_context("player_1")

        # Mock the _calculate_future_score method
        def mock_future_score(ctx, tile):
            # (3,3) has better score than (1,1)
            return 5.0 if tile == (3, 3) else 2.0

        # Test the retreat tile finding
        with unittest.mock.patch.object(BasicAISystem, '_calculate_future_score', side_effect=mock_future_score):
            ai_system = BasicAISystem(
                self.mock_game_state,
                self.mock_movement_system,
                self.mock_action_system,
                self.mock_event_bus,
                self.mock_los_manager
            )

            result = ai_system._find_best_retreat_tile(ctx)

        self.assertEqual(result, (3, 3))

    def test_find_best_cover_tile_avoids_los(self):
        """Test that AI finds cover tiles that avoid line of sight from enemies."""
        # Mock reachable tiles
        self.mock_movement_system.get_reachable_tiles.return_value = [(1, 1, 1), (2, 2, 1), (3, 3, 1)]

        # Create fresh context
        ctx = self.create_fresh_context("player_1")

        # Mock LOS - only (3,3) provides cover from enemies
        def mock_has_los(pos1, pos2):
            if pos2 == (3, 3):  # Target tile has cover
                return False
            return True  # Other tiles are visible

        self.mock_los_manager.has_los.side_effect = mock_has_los

        # Mock utility functions
        with unittest.mock.patch('ecs.systems.ai.utils.count_free_adjacent_tiles', return_value=2), \
             unittest.mock.patch('ecs.systems.ai.utils.find_closest_cover', return_value=1):

            ai_system = BasicAISystem(
                self.mock_game_state,
                self.mock_movement_system,
                self.mock_action_system,
                self.mock_event_bus,
                self.mock_los_manager
            )

            result = ai_system._find_best_cover_tile(ctx)

        self.assertEqual(result, (3, 3))
