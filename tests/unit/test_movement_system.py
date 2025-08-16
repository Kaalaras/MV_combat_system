import unittest
from unittest.mock import MagicMock
from core.movement_system import MovementSystem
from ecs.components.position import PositionComponent

class TestMovementSystem(unittest.TestCase):
    def setUp(self):
        self.game_state = MagicMock()
        self.movement_system = MovementSystem(self.game_state)
        self.terrain = self.game_state.terrain

    def test_get_reachable_tiles_1x1_entity(self):
        # Entity is at (0,0), wants to move, max_distance=2
        entity_id = "player"
        entity_data = {
            "position": PositionComponent(x=0, y=0, width=1, height=1)
        }
        self.game_state.get_entity.return_value = entity_data

        # Mock terrain: (1,0) is a wall, (0,1) is occupied
        self.terrain.is_walkable.side_effect = lambda x, y, w, h: (x, y) != (1, 0)
        self.terrain.is_occupied.side_effect = lambda x, y, w, h, entity_id_to_ignore: (x, y) == (0, 1)

        # With max_distance = 1
        reachable = self.movement_system.get_reachable_tiles(entity_id, max_distance=1)
        reachable_coords = [(x, y) for x, y, cost in reachable]

        self.assertIn((0, 0), reachable_coords)
        self.assertIn((-1, 0), reachable_coords)
        self.assertIn((0, -1), reachable_coords)
        self.assertNotIn((1, 0), reachable_coords) # Wall
        self.assertNotIn((0, 1), reachable_coords) # Occupied
        self.assertEqual(len(reachable), 3) # (0,0), (-1,0), (0,-1)

    def test_get_reachable_tiles_2x2_entity_blocked(self):
        # 2x2 Entity is at (0,0), wants to move, max_distance=1
        entity_id = "player_2x2"
        entity_data = {
            "position": PositionComponent(x=0, y=0, width=2, height=2)
        }
        self.game_state.get_entity.return_value = entity_data

        # A wall at (2,1) should block a 2x2 entity at (1,0) because its footprint (1,0 -> 3,2) would overlap the wall.
        self.terrain.is_walkable.side_effect = lambda x, y, w, h: not (x <= 2 < x + w and y <= 1 < y + h)
        self.terrain.is_occupied.return_value = False # No other entities

        reachable = self.movement_system.get_reachable_tiles(entity_id, max_distance=1)
        reachable_coords = [(x, y) for x, y, cost in reachable]

        # Cannot move to (1,0) because footprint would hit the wall.
        self.assertNotIn((1,0), reachable_coords)

    def test_move_success(self):
        entity_id = "player"
        entity_data = {"position": PositionComponent(x=0, y=0)}
        self.game_state.get_entity.return_value = entity_data
        self.terrain._get_entity_size.return_value = (1, 1)
        self.terrain.is_valid_position.return_value = True
        self.terrain.is_occupied.return_value = False
        self.terrain.is_walkable.return_value = True
        self.terrain.move_entity.return_value = True

        result = self.movement_system.move(entity_id, (1, 1))

        self.assertTrue(result)
        self.terrain.move_entity.assert_called_once_with(entity_id, 1, 1)
        self.assertEqual(entity_data["position"].x, 1)
        self.assertEqual(entity_data["position"].y, 1)

    def test_move_fail_occupied(self):
        entity_id = "player"
        entity_data = {"position": PositionComponent(x=0, y=0)}
        self.game_state.get_entity.return_value = entity_data
        self.terrain._get_entity_size.return_value = (1, 1)
        self.terrain.is_valid_position.return_value = True
        self.terrain.is_occupied.return_value = True  # Destination is occupied
        self.terrain.is_walkable.return_value = True
        self.terrain.move_entity.return_value = False

        result = self.movement_system.move(entity_id, (1, 1))

        self.assertFalse(result)
        self.terrain.is_occupied.assert_called_once_with(1, 1, 1, 1, entity_id_to_ignore=entity_id)
        self.assertEqual(entity_data["position"].x, 0) # Position should not change
        self.assertEqual(entity_data["position"].y, 0)

    def test_move_fail_invalid_position(self):
        entity_id = "player"
        entity_data = {"position": PositionComponent(x=0, y=0)}
        self.game_state.get_entity.return_value = entity_data
        self.terrain._get_entity_size.return_value = (1, 1)
        self.terrain.is_valid_position.return_value = False # Invalid destination
        self.terrain.is_occupied.return_value = False
        self.terrain.is_walkable.return_value = True

        result = self.movement_system.move(entity_id, (100, 100))

        self.assertFalse(result)
        self.assertEqual(entity_data["position"].x, 0)

    def test_move_fail_not_walkable(self):
        entity_id = "player"
        entity_data = {"position": PositionComponent(x=0, y=0)}
        self.game_state.get_entity.return_value = entity_data
        self.terrain._get_entity_size.return_value = (1, 1)
        self.terrain.is_valid_position.return_value = True
        self.terrain.is_occupied.return_value = False
        self.terrain.is_walkable.return_value = False # Wall

        result = self.movement_system.move(entity_id, (1, 0))

        self.assertFalse(result)
        self.assertEqual(entity_data["position"].x, 0)

if __name__ == '__main__':
    unittest.main()
