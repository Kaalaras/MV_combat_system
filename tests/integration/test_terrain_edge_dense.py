"""
Integration tests for edge/corner placement and dense map scenarios.
"""
import unittest
from unittest.mock import MagicMock
from core.terrain_manager import Terrain
from core.game_state import GameState
from ecs.components.position import PositionComponent

class TestTerrainEdgeAndDenseIntegration(unittest.TestCase):
    def setUp(self):
        self.game_state = GameState()
        self.terrain = Terrain(width=6, height=6, game_state=self.game_state)
        self.event_bus = MagicMock()
        self.game_state.event_bus = self.event_bus
        self.terrain.event_bus = self.event_bus

    def test_simultaneous_actions(self):
        # Place two entities
        a = {"position": PositionComponent(x=0, y=0, width=2, height=2)}
        b = {"position": PositionComponent(x=4, y=0, width=2, height=2)}
        self.game_state.add_entity("A", a)
        self.game_state.add_entity("B", b)
        self.assertTrue(self.terrain.add_entity("A", 0, 0))
        self.assertTrue(self.terrain.add_entity("B", 4, 0))
        # Add a wall between them
        self.assertTrue(self.terrain.add_wall(2, 1))
        # Move A to (2,2), B to (2,4), remove wall, add new wall
        self.assertTrue(self.terrain.move_entity("A", 2, 2))
        self.assertTrue(self.terrain.move_entity("B", 2, 4))
        self.assertTrue(self.terrain.remove_wall(2, 1))
        self.assertTrue(self.terrain.add_wall(3, 3))
        # Check occupation and walkability
        self.assertTrue(self.terrain.is_occupied(2, 2, 2, 2))
        self.assertTrue(self.terrain.is_occupied(2, 4, 2, 2))
        self.assertFalse(self.terrain.is_walkable(3, 3, 1, 1))
        self.assertTrue(self.terrain.is_walkable(0, 0, 1, 1))

    def test_dense_map_placement(self):
        # Fill the map with 1x1 entities except (5,5)
        for x in range(6):
            for y in range(6):
                if (x, y) == (5, 5):
                    continue
                eid = f"E_{x}_{y}"
                ent = {"position": PositionComponent(x=x, y=y)}
                self.game_state.add_entity(eid, ent)
                self.assertTrue(self.terrain.add_entity(eid, x, y))
        # (0,0) is occupied, but walkable (no wall). (5,5) is not occupied and walkable.
        self.assertTrue(self.terrain.is_occupied(0, 0, 1, 1))
        self.assertTrue(self.terrain.is_walkable(0, 0, 1, 1))
        self.assertFalse(self.terrain.is_occupied(5, 5, 1, 1))
        self.assertTrue(self.terrain.is_walkable(5, 5, 1, 1))
        # Place a wall at (5,5), now nowhere is walkable
        self.assertTrue(self.terrain.add_wall(5, 5))
        self.assertFalse(self.terrain.is_walkable(5, 5, 1, 1))
        # Remove an entity and check that cell is now not occupied and still walkable
        self.terrain.remove_entity("E_0_0")
        self.assertFalse(self.terrain.is_occupied(0, 0, 1, 1))
        self.assertTrue(self.terrain.is_walkable(0, 0, 1, 1))

if __name__ == "__main__":
    unittest.main()
