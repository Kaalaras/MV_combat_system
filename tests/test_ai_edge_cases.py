import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from MV_combat_system.tests.test_fixtures import BaseAITestCase, MockCharacter
from ecs.systems.ai import movement, targeting, utils
from ecs.systems.ai.main import BasicAISystem, AITurnContext

class TestScoringMultiCriteria(BaseAITestCase):
    def test_melee_scoring_tiebreak_on_distance(self):
        """Two tiles with same dps, threat, mobility but one closer"""
        # Create fresh context with test enemies
        ctx = self.create_fresh_context("player_1")

        # Position enemy at (0,0) so (0,1) is closer than (1,2)
        self.entities["enemy_1"]["position"] = (0, 0)

        # Mock reachable tiles
        self.mock_movement_system.get_reachable_tiles.return_value = [(0,1,1),(1,2,1)]

        # Mock distance calculation to return proper values
        def mock_calculate_distance(pos1, pos2):
            if pos1 == (0, 1) and pos2 == (0, 0):
                return 1  # Closer
            elif pos1 == (1, 2) and pos2 == (0, 0):
                return 3  # Further
            return 5  # Default

        # Simulate is_in_range True and mock scoring functions
        with patch.object(utils, 'is_in_range', return_value=True), \
             patch.object(utils, 'get_potential_dps', return_value=5), \
             patch.object(utils, 'count_future_threats', return_value=1), \
             patch.object(utils, 'count_free_adjacent_tiles', return_value=2), \
             patch.object(utils, 'calculate_distance', side_effect=mock_calculate_distance):

            result = movement.simulate_move_and_find_melee(ctx)

        # Should prefer the closer tile (0,1) over (1,2)
        self.assertIsNotNone(result)
        move_tile, target_id = result
        self.assertEqual(move_tile, (0, 1))

    def test_ranged_scoring_prioritizes_dps(self):
        """Test that ranged targeting prioritizes higher DPS targets"""
        # Create fresh context
        ctx = self.create_fresh_context("player_1")

        # Mock reachable tiles
        self.mock_movement_system.get_reachable_tiles.return_value = [(6,6,1), (7,7,1)]

        # Mock different DPS for different enemies
        def mock_dps(ctx, weapon, target_id):
            return 10.0 if target_id == "enemy_2_damaged" else 5.0

        # Mock LOS and range checks
        with patch.object(utils, 'is_in_range_tiles', return_value=True), \
             patch.object(ctx.los_manager, 'has_los', return_value=True), \
             patch.object(utils, 'get_potential_dps', side_effect=mock_dps), \
             patch.object(utils, 'count_future_threats', return_value=0), \
             patch.object(utils, 'count_free_adjacent_tiles', return_value=3):

            result = movement.simulate_move_and_find_ranged(ctx)

        # Should target the higher DPS enemy
        self.assertIsNotNone(result)
        move_tile, target_id = result
        self.assertEqual(target_id, "enemy_2_damaged")

class TestReservedTilesHandling(BaseAITestCase):
    def test_reserved_tiles_blocks_movement(self):
        """Test that reserved tiles are properly excluded from movement options"""
        # Create context first
        ctx = self.create_fresh_context("player_1")

        # Add a tile to reserved tiles in the context's turn order system
        ctx.turn_order_system.reserved_tiles.add((6, 6))

        # Mock movement system to properly handle reserved tiles parameter
        def mock_get_reachable_tiles(char_id, max_distance, reserved_tiles=None):
            all_tiles = [(5, 6, 1), (6, 6, 1), (7, 7, 1)]
            # If reserved_tiles is provided, filter them out
            if reserved_tiles:
                filtered_tiles = []
                for x, y, cost in all_tiles:
                    if (x, y) not in reserved_tiles:
                        filtered_tiles.append((x, y, cost))
                return filtered_tiles
            return all_tiles

        self.mock_movement_system.get_reachable_tiles.side_effect = mock_get_reachable_tiles

        # Get filtered tiles - this should exclude the reserved tile
        filtered = movement.get_reachable_tiles(
            ctx.movement_system,
            ctx.char_id,
            7,
            reserved_tiles=ctx.turn_order_system.reserved_tiles
        )

        # Should exclude the reserved tile
        tile_coords = [(x, y) for x, y, cost in filtered]
        self.assertNotIn((6, 6), tile_coords)
        self.assertIn((5, 6), tile_coords)
        self.assertIn((7, 7), tile_coords)

    def test_reserved_tiles_cleared_on_round_start(self):
        """Test that reserved tiles are cleared when a new round starts"""
        # Add tiles to reserved set
        self.mock_turn_order_system.reserved_tiles.add((3, 3))
        self.assertEqual(len(self.mock_turn_order_system.reserved_tiles), 1)

        # Create context (which wraps the turn order system)
        ctx = self.create_fresh_context("player_1")

        # Simulate round start
        ctx.turn_order_system.start_new_round()

        # Reserved tiles should be cleared
        self.assertEqual(len(ctx.turn_order_system.reserved_tiles), 0)

class TestAIContextEdgeCases(BaseAITestCase):
    def test_context_with_no_enemies(self):
        """Test AI context creation when no enemies are present"""
        # Remove all enemies from entities AND update both references
        self.entities = {
            "player_1": self.entities["player_1"],
            "ally_1": self.entities["ally_1"]
        }

        # Update BOTH the PropertyMock AND the get_entity side_effect
        type(self.mock_game_state).entities = PropertyMock(return_value=self.entities)

        def safe_get_entity(eid):
            if eid in self.entities:
                return self.entities[eid]
            # Return a default mock entity for missing entities (but mark as dead)
            mock_character = MockCharacter(team="B", health_damage=(0, 0), is_dead=True)
            return {
                "position": (0, 0),
                "character_ref": MagicMock(character=mock_character),
                "equipment": MagicMock(weapons={})
            }

        self.mock_game_state.get_entity.side_effect = safe_get_entity

        # Ensure the mock game state reflects the new entities immediately
        self.mock_game_state.entities = self.entities

        # Create context
        ctx = self.create_fresh_context("player_1")

        # Should handle empty enemy list gracefully
        self.assertEqual(len(ctx.enemies), 0)
        self.assertEqual(len(ctx.adjacent_enemies), 0)
        self.assertEqual(len(ctx.engaged_enemies), 0)

    def test_context_with_mock_turn_order_system(self):
        """Test that context works with mock turn order systems"""
        # Create context with our mock system
        ctx = self.create_fresh_context("player_1")

        # Should have reserved_tiles attribute
        self.assertTrue(hasattr(ctx.turn_order_system, 'reserved_tiles'))
        self.assertIsNotNone(ctx.turn_order_system.reserved_tiles)

        # Should be able to add and clear tiles
        ctx.turn_order_system.reserved_tiles.add((1, 1))
        self.assertEqual(len(ctx.turn_order_system.reserved_tiles), 1)

        ctx.turn_order_system.reserved_tiles.clear()
        self.assertEqual(len(ctx.turn_order_system.reserved_tiles), 0)
