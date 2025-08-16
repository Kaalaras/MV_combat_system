"""
Integration tests for TerrainManager with multiple entities, walls, and events.
"""
import unittest
from unittest.mock import MagicMock
from core.terrain_manager import Terrain, EVT_ENTITY_MOVED, EVT_WALL_ADDED, EVT_WALL_REMOVED
from core.game_state import GameState
from ecs.components.position import PositionComponent

class TestTerrainIntegration(unittest.TestCase):
    def setUp(self):
        self.game_state = GameState()
        self.terrain = Terrain(width=8, height=8, game_state=self.game_state)
        self.event_bus = MagicMock()
        self.game_state.event_bus = self.event_bus
        self.terrain.event_bus = self.event_bus

    def test_complex_scenario(self):
        # Place a 2x2 entity
        entity_a = {"position": PositionComponent(x=1, y=1, width=2, height=2)}
        self.game_state.add_entity("A", entity_a)
        self.assertTrue(self.terrain.add_entity("A", 1, 1))
        self.assertTrue(self.terrain.is_occupied(1, 1, 2, 2))

        # Place a 3x1 entity, non-overlapping
        entity_b = {"position": PositionComponent(x=4, y=1, width=3, height=1)}
        self.game_state.add_entity("B", entity_b)
        self.assertTrue(self.terrain.add_entity("B", 4, 1))
        self.assertTrue(self.terrain.is_occupied(4, 1, 3, 1))

        # Try to place a 1x1 entity overlapping A (should fail)
        entity_c = {"position": PositionComponent(x=2, y=2)}
        self.game_state.add_entity("C", entity_c)
        self.assertFalse(self.terrain.add_entity("C", 2, 2))

        # Add a wall and check walkability
        self.assertTrue(self.terrain.add_wall(6, 6))
        self.assertFalse(self.terrain.is_walkable(6, 6, 1, 1))
        self.event_bus.publish.assert_any_call(EVT_WALL_ADDED, position=(6, 6))

        # Move entity A to a new valid position
        self.assertTrue(self.terrain.move_entity("A", 2, 4))
        self.event_bus.publish.assert_any_call(EVT_ENTITY_MOVED,
            entity_id="A",
            old_position=(1, 1),
            new_position=(2, 4),
            size=(2, 2)
        )
        self.assertTrue(self.terrain.is_occupied(2, 4, 2, 2))
        self.assertFalse(self.terrain.is_occupied(1, 1, 2, 2))

        # Remove the wall and check walkability
        self.assertTrue(self.terrain.remove_wall(6, 6))
        self.assertTrue(self.terrain.is_walkable(6, 6, 1, 1))
        self.event_bus.publish.assert_any_call(EVT_WALL_REMOVED, position=(6, 6))

        # Check that an area overlapping with A is correctly identified as occupied.
        # Entity A (2x2) is at (2,4), so this check for a 3x1 entity at (2,4) should be True.
        self.assertTrue(self.terrain.is_occupied(2, 4, 3, 1))  # Partial overlap is still occupied

        # Try to move entity B to a valid, non-overlapping position.
        self.assertTrue(self.terrain.move_entity("B", 0, 0))
        self.assertTrue(self.terrain.is_occupied(0, 0, 3, 1))

        # Remove entity A and check occupation
        self.assertTrue(self.terrain.remove_entity("A"))
        self.assertFalse(self.terrain.is_occupied(2, 4, 2, 2))

if __name__ == "__main__":
    unittest.main()
