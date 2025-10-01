import unittest

from core.event_bus import EventBus
from core.game_state import GameState
from core.terrain_manager import Terrain
from core.movement_system import MovementSystem
from ecs.components.position import PositionComponent
from ecs.ecs_manager import ECSManager

class TestMovementIntegration(unittest.TestCase):
    def setUp(self):
        self.event_bus = EventBus()
        self.ecs_manager = ECSManager(self.event_bus)
        self.game_state = GameState(self.ecs_manager)
        self.game_state.set_event_bus(self.event_bus)
        self.terrain = Terrain(width=10, height=10, game_state=self.game_state)
        self.movement_system = MovementSystem(
            self.game_state,
            self.ecs_manager,
            event_bus=self.event_bus,
        )
        self.game_state.set_terrain(self.terrain)

    def test_move_1x1_entity_success(self):
        entity_id = "player"
        entity_data = {"position": PositionComponent(x=0, y=0)}
        self.game_state.add_entity(entity_id, entity_data)
        self.terrain.add_entity(entity_id, 0, 0)

        result = self.movement_system.move(entity_id, (1, 1))

        self.assertTrue(result)
        self.assertEqual(self.terrain.get_entity_position(entity_id), (1, 1))
        self.assertEqual(entity_data["position"].x, 1)

    def test_move_2x2_entity_fail_wall(self):
        entity_id = "golem"
        entity_data = {"position": PositionComponent(x=0, y=0, width=2, height=2)}
        self.game_state.add_entity(entity_id, entity_data)
        self.terrain.add_entity(entity_id, 0, 0)
        self.terrain.add_wall(1, 1) # Wall that blocks the 2x2 footprint

        result = self.movement_system.move(entity_id, (0, 0))
        self.assertFalse(result, "Should not be able to move to its own spot if a wall is there now")

        result_blocked = self.movement_system.move(entity_id, (1,0))
        self.assertFalse(result_blocked, "Move should be blocked by the wall in its footprint")
        self.assertEqual(self.terrain.get_entity_position(entity_id), (0, 0))

    def test_get_reachable_tiles_with_entities_and_walls(self):
        # Player at (0,0)
        player_id = "player"
        player_data = {"position": PositionComponent(x=0, y=0)}
        self.game_state.add_entity(player_id, player_data)
        self.terrain.add_entity(player_id, 0, 0)

        # Enemy at (2,0)
        enemy_id = "enemy"
        enemy_data = {"position": PositionComponent(x=2, y=0)}
        self.game_state.add_entity(enemy_id, enemy_data)
        self.terrain.add_entity(enemy_id, 2, 0)

        # Wall at (1,1)
        self.terrain.add_wall(1, 1)

        reachable = self.movement_system.get_reachable_tiles(player_id, max_distance=2)
        reachable_coords = [(x, y) for x, y, cost in reachable]

        self.assertIn((0, 0), reachable_coords)
        self.assertIn((1, 0), reachable_coords)
        self.assertNotIn((2, 0), reachable_coords) # Blocked by enemy
        self.assertNotIn((1, 1), reachable_coords) # Blocked by wall
        self.assertIn((0, 1), reachable_coords)

if __name__ == '__main__':
    unittest.main()

