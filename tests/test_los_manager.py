import unittest
from unittest.mock import MagicMock
from core.los_manager import LineOfSightManager, EVT_WALL_ADDED, EVT_ENTITY_MOVED

class TestLineOfSightManager(unittest.TestCase):
    def setUp(self):
        self.mock_game_state = MagicMock()
        self.mock_terrain = MagicMock()
        self.mock_event_bus = MagicMock()
        self.los_manager = LineOfSightManager(
            self.mock_game_state, self.mock_terrain, self.mock_event_bus, los_granularity=5
        )

    def test_cache_invalidation_on_wall_added(self):
        self.los_manager.los_cache = {((0, 0), (1, 1)): True}
        self.los_manager.invalidate_cache()
        self.assertEqual(self.los_manager.los_cache, {})

    def test_event_bus_subscription(self):
        # Check that subscriptions are set up
        calls = [
            unittest.mock.call(EVT_WALL_ADDED, self.los_manager.invalidate_cache),
            unittest.mock.call(EVT_ENTITY_MOVED, self.los_manager.invalidate_cache)
        ]
        self.mock_event_bus.subscribe.assert_has_calls(calls, any_order=True)

    def test_has_los_cache_usage(self):
        # Simulate cache hit
        self.los_manager.los_cache[((1, 1), (2, 2))] = True
        result = self.los_manager.has_los((1, 1), (2, 2))
        self.assertTrue(result)

    def test_has_los_calls_terrain(self):
        # Simulate cache miss, should call _check_los
        self.los_manager.los_cache = {}
        self.los_manager._check_los = MagicMock(return_value=True)
        result = self.los_manager.has_los((0, 0), (1, 1))
        self.assertTrue(result)
        self.los_manager._check_los.assert_called_once_with((0, 0), (1, 1))

    # Integration-like test
    def test_integration_event_triggers_cache_clear(self):
        self.los_manager.los_cache[((0, 0), (1, 1))] = True
        # Simulate event callback
        self.los_manager.invalidate_cache()
        self.assertEqual(self.los_manager.los_cache, {})

    def test_has_los_normalizes_input(self):
        # Ensure cache keys are normalized
        self.los_manager._check_los = MagicMock(return_value=True)
        result = self.los_manager.has_los((2, 3), (1, 1))
        self.assertTrue(result)
        self.assertIn(((1, 1), (2, 3)), self.los_manager.los_cache)

    def test_negative_los_cached(self):
        # Ensure False results are cached and not recomputed
        mock_check = MagicMock(return_value=False)
        self.los_manager._check_los = mock_check
        res1 = self.los_manager.has_los((0, 0), (1, 0))
        res2 = self.los_manager.has_los((0, 0), (1, 0))
        self.assertFalse(res1)
        self.assertFalse(res2)
        mock_check.assert_called_once()

    def test_get_los_points_zero_granularity(self):
        # granularity=0 should return only corners
        mgr0 = LineOfSightManager(self.mock_game_state, self.mock_terrain, self.mock_event_bus, los_granularity=0)
        pts = mgr0._get_los_points((5, 5))
        self.assertEqual(pts, {(5, 5), (6, 5), (6, 6), (5, 6)})

    def test_is_ray_clear_blocked_midpoint(self):
        # Setup a wall strictly between start and end
        self.mock_terrain.is_wall = lambda x, y: (x, y) == (1, 0)
        self.mock_terrain.world_to_cell = lambda coord: (int(coord[0]), int(coord[1]))
        self.assertFalse(self.los_manager._is_ray_clear((0.5, 0.5), (2.5, 0.5)))

    def test_is_ray_clear_allows_start_and_end_walls(self):
        # Walls on start/end must not block
        self.mock_terrain.is_wall = lambda x, y: (x, y) in [(0, 0), (2, 2)]
        self.mock_terrain.world_to_cell = lambda coord: (int(coord[0]), int(coord[1]))
        self.assertTrue(self.los_manager._is_ray_clear((0.1, 0.1), (2.9, 2.9)))

    def test_has_los_caches_result(self):
        # _check_los should only run once per key
        mock_check = MagicMock(return_value=True)
        self.los_manager._check_los = mock_check
        _ = self.los_manager.has_los((1, 2), (3, 4))
        _ = self.los_manager.has_los((1, 2), (3, 4))
        mock_check.assert_called_once()

if __name__ == '__main__':
    unittest.main()
