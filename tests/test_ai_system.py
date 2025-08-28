import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from MV_combat_system.tests.test_fixtures import BaseAITestCase, MockWeapon
from ecs.systems.ai.main import BasicAISystem, AITurnContext
from ecs.systems.ai import utils, targeting, movement

class TestAISystem(BaseAITestCase):

    # --- Unit Tests for Targeting ---

    def test_choose_ranged_target_prefers_isolated(self):
        """The AI should target the enemy that is furthest from any allies."""
        # Position ally closer to enemy_2_damaged to make enemy_3 more isolated
        self.entities["ally_1"]["position"] = (14, 14)

        # Create a context with these positions
        ctx = self.create_fresh_context("player_1")

        # Run the targeting function
        target = targeting.choose_ranged_target(ctx)
        self.assertEqual(target, "enemy_3_isolated")

    def test_choose_ranged_target_prefers_most_damaged(self):
        """When no target is isolated, the AI should prefer the most damaged one."""
        # Force isolation detection to return empty list for this test
        original_get_isolated = targeting.get_isolated_targets
        targeting.get_isolated_targets = lambda ctx, ids: []  # Always return empty list

        try:
            # Position ally equally distant from all enemies
            self.entities["ally_1"]["position"] = (0, 0)

            # Create a context with these positions
            ctx = self.create_fresh_context("player_1")

            target = targeting.choose_ranged_target(ctx)
            self.assertEqual(target, "enemy_2_damaged")
        finally:
            # Restore original function
            targeting.get_isolated_targets = original_get_isolated

    def test_choose_melee_target_prefers_engaged(self):
        """The AI should prioritize melee targets that are already engaged with an ally."""
        # Set up melee scenario: two enemies adjacent to player
        self.entities["enemy_1"]["position"] = (5, 4)        # Adjacent to player
        self.entities["enemy_2_damaged"]["position"] = (4, 5) # Adjacent to player
        self.entities["ally_1"]["position"] = (5, 3)         # Ally adjacent to enemy_1

        # Create context with this scenario
        ctx = self.create_fresh_context("player_1")

        target = targeting.choose_melee_target(ctx)
        self.assertEqual(target, "enemy_1")

    # --- Unit Tests for Movement ---

    def test_simulate_move_and_find_ranged_no_shot(self):
        """AI should return None if no move can provide a shot."""
        # No line of sight from anywhere
        self.mock_los_manager.has_los.return_value = False
        self.mock_movement_system.get_reachable_tiles.return_value = [(6, 5, 1)]

        ctx = self.create_fresh_context("player_1")
        result = movement.simulate_move_and_find_ranged(ctx)
        self.assertIsNone(result)

    # --- Integration Tests for BasicAISystem ---

    def test_choose_action_fires_ranged_if_clear_shot(self):
        """If a valid ranged target exists, the AI should choose to attack."""
        # Temporarily patch the get_isolated_targets function to ensure consistent behavior
        original_get_isolated = targeting.get_isolated_targets
        targeting.get_isolated_targets = lambda ctx, ids: []  # Always return empty list to force damaged target selection

        try:
            # Ensure all enemies are in range
            self.mock_los_manager.has_los.return_value = True
            self.mock_action_system.can_perform_action.return_value = True

            ai_system = BasicAISystem(self.mock_game_state, self.mock_movement_system, self.mock_action_system,
                                     self.mock_event_bus, self.mock_los_manager)
            ai_system.choose_action("player_1")

            # Check that the attack event was published with the damaged enemy as target
            self.mock_event_bus.publish.assert_called_with(
                "action_requested",
                entity_id="player_1",
                action_name="Attack",
                target_id="enemy_2_damaged",  # Prefers most damaged when none are isolated
                weapon=unittest.mock.ANY
            )
        finally:
            # Restore original function
            targeting.get_isolated_targets = original_get_isolated

    def test_choose_action_moves_for_ranged_shot(self):
        """If no shot is available, but one can be made by moving, AI should move."""
        # No LOS from current position, but can see enemy_1 from (6,5)
        player_pos = self.entities["player_1"]["position"]
        enemy_pos = self.entities["enemy_1"]["position"]

        # Create a more sophisticated side_effect that prevents shooting from current position
        def mock_has_los(pos1, pos2):
            # No line of sight from current position to any enemy
            if pos1 == player_pos:
                return False
            # But can see enemy from the target move tile
            if pos1 == (6, 5) and pos2 == enemy_pos:
                return True
            return False

        self.mock_los_manager.has_los.side_effect = mock_has_los

        # Can reach (6,5)
        self.mock_movement_system.get_reachable_tiles.return_value = [(6, 5, 1)]

        # Make sure we can move but NOT attack after moving (for this test)
        def can_perform_action(char_id, action, **kwargs):
            if action.name == "Standard Move":
                return True
            if action.name == "Attack" and "target_id" in kwargs:
                return False  # Can't attack after moving in this test
            return True

        self.mock_action_system.can_perform_action.side_effect = can_perform_action

        ai_system = BasicAISystem(self.mock_game_state, self.mock_movement_system, self.mock_action_system,
                                 self.mock_event_bus, self.mock_los_manager)
        ai_system.choose_action("player_1")

        # Should move to get a shot
        self.mock_event_bus.publish.assert_called_with(
            "action_requested",
            entity_id="player_1",
            action_name="Standard Move",
            target_tile=(6, 5)
        )

    def test_choose_action_ends_turn_if_no_options(self):
        """If no enemies are visible and no moves improve the situation, end turn."""
        # Setup an empty battlefield with no enemies visible
        self.entities = {
            "player_1": self.entities["player_1"]  # Keep only player
        }
        type(self.mock_game_state).entities = PropertyMock(return_value=self.entities)

        # No moves possible
        self.mock_movement_system.get_reachable_tiles.return_value = []
        self.mock_action_system.can_perform_action.return_value = True

        ai_system = BasicAISystem(self.mock_game_state, self.mock_movement_system, self.mock_action_system,
                                 self.mock_event_bus, self.mock_los_manager)
        ai_system.choose_action("player_1")

        # Should end turn as there are no other options
        self.mock_event_bus.publish.assert_called_with(
            "action_requested",
            entity_id="player_1",
            action_name="End Turn"
        )

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
