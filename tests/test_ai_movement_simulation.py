import unittest
import unittest.mock
from unittest.mock import MagicMock, PropertyMock

from MV_combat_system.tests.test_fixtures import BaseAITestCase, MockWeapon
from ecs.systems.ai import targeting, movement, utils
from ecs.systems.ai.main import BasicAISystem, AITurnContext

class TestAIMovementSimulation(BaseAITestCase):
    """
    Isolated test suite for AI movement simulation functionality.

    These tests use the BaseAITestCase to avoid test pollution
    issues that occur when run as part of the full test discovery.
    """

    def test_simulate_move_and_find_ranged_finds_shot(self):
        """AI should find a tile to move to if it provides a shot."""
        # Reset positions to default first
        self.reset_entity_positions()

        # Configure line of sight: only visible from tile (6,5)
        def mock_has_los(pos1, pos2):
            # Check if we're looking from (6,5) to (10,10)
            if (pos1 == (6, 5) and pos2 == (10, 10)):
                return True
            return False

        self.mock_los_manager.has_los.side_effect = mock_has_los

        # Ensure the character has a ranged weapon for this test
        self.entities["player_1"]["equipment"].weapons["ranged"] = MockWeapon(name="Test Ranged", weapon_range=35)

        # Create a completely fresh context
        ctx = self.create_fresh_context("player_1")

        # Mock the movement system to return our test tiles
        with unittest.mock.patch.object(ctx.movement_system, 'get_reachable_tiles', return_value=[(6, 5, 1), (5, 6, 1)]):
            result = movement.simulate_move_and_find_ranged(ctx)

        # Assert we got a valid move and target
        self.assertIsNotNone(result)
        move_tile, target_id = result
        self.assertEqual(move_tile, (6, 5))
        self.assertEqual(target_id, "enemy_1")

    def test_simulate_move_and_find_ranged_chooses_best_score(self):
        """AI should choose the move for a ranged attack with the best score."""
        # Setup: Two enemies, two possible move locations for a ranged shot.
        self.entities["enemy_1"]["position"] = (10, 10)
        self.entities["enemy_2_damaged"]["position"] = (10, 12) # Lower health, higher DPS target
        self.entities["player_1"]["position"] = (5, 5)

        # Ensure the character has a ranged weapon for this test
        self.entities["player_1"]["equipment"].weapons["ranged"] = MockWeapon(name="Test Ranged", weapon_range=35)

        # Configure LOS to always return True for this test
        self.mock_los_manager.has_los.return_value = True

        # Create a completely fresh context
        ctx = self.create_fresh_context("player_1")
        ctx.enemies = ["enemy_1", "enemy_2_damaged"]

        # Mock metrics with isolated scope
        def mock_dps(ctx_, weapon, target_id):
            return 11.0 if target_id == "enemy_2_damaged" else 10.0

        def mock_threats(ctx_, tile):
            # Simulate that moving to (8,8) is riskier
            return 2 if tile == (8, 8) else 0

        def mock_mobility(ctx_, tile):
            # Simulate that (2,2) offers more tactical options
            return 2 if tile == (8, 8) else 5

        # Use context managers to ensure proper cleanup
        with unittest.mock.patch.object(ctx.movement_system, 'get_reachable_tiles', return_value=[(8, 8, 1), (2, 2, 1)]), \
             unittest.mock.patch('ecs.systems.ai.utils.get_potential_dps', side_effect=mock_dps), \
             unittest.mock.patch('ecs.systems.ai.utils.count_future_threats', side_effect=mock_threats), \
             unittest.mock.patch('ecs.systems.ai.utils.count_free_adjacent_tiles', side_effect=mock_mobility):

            result = movement.simulate_move_and_find_ranged(ctx)

        self.assertIsNotNone(result)
        move_tile, target_id = result
        self.assertEqual(move_tile, (2, 2))
        # The target from this position would be the one that gives the best score.
        self.assertIn(target_id, ["enemy_1", "enemy_2_damaged"])

    def test_simulate_move_and_find_ranged_no_shot(self):
        """AI should return None if no move can provide a shot."""
        # No line of sight from anywhere
        self.mock_los_manager.has_los.return_value = False
        self.mock_movement_system.get_reachable_tiles.return_value = [(6, 5, 1)]

        ctx = self.create_fresh_context("player_1")
        result = movement.simulate_move_and_find_ranged(ctx)
        self.assertIsNone(result)
