import unittest
from unittest.mock import MagicMock
from core.los_manager import LineOfSightManager, EVT_WALL_ADDED, EVT_ENTITY_MOVED, EVT_WALL_REMOVED

class TestLineOfSightManager(unittest.TestCase):
    def setUp(self):
        self.mock_game_state = MagicMock()
        # minimal version attributes
        self.mock_game_state.terrain_version = 0
        self.mock_game_state.blocker_version = 0
        self.mock_terrain = MagicMock()
        self.mock_terrain.walls = set()
        self.mock_terrain.grid = {}
        self.mock_terrain.is_wall.side_effect = lambda x,y: (x,y) in self.mock_terrain.walls
        self.mock_event_bus = MagicMock()
        self.los_manager = LineOfSightManager(
            self.mock_game_state, self.mock_terrain, self.mock_event_bus, los_granularity=2
        )

    def test_event_bus_subscription(self):
        subs = [c.args for c in self.mock_event_bus.subscribe.call_args_list]
        expected_topics = {EVT_WALL_ADDED, EVT_WALL_REMOVED, EVT_ENTITY_MOVED}
        topics = {a[0] for a in subs}
        self.assertTrue(expected_topics.issubset(topics))

    def test_cache_hit_counts(self):
        a=(0,0); b=(5,0)
        # first compute
        self.los_manager.reset_stats()
        self.los_manager.get_visibility_entry(a,b)
        stats1 = self.los_manager.get_stats()
        self.assertEqual(stats1['pair_recomputes'],1)
        # second should be cached
        self.los_manager.get_visibility_entry(a,b)
        stats2 = self.los_manager.get_stats()
        self.assertEqual(stats2['pair_recomputes'],1)
        self.assertEqual(stats2['cache_hits'],1)

    def test_invalidation_clears_cache(self):
        a=(0,0); b=(2,0)
        self.los_manager.get_visibility_entry(a,b)
        self.assertEqual(len(self.los_manager._pair_cache),1)
        self.los_manager.invalidate_cache()
        self.assertEqual(len(self.los_manager._pair_cache),0)

    def test_has_los_basic_clear_line(self):
        a=(0,0); b=(3,0)
        self.assertTrue(self.los_manager.has_los(a,b))

    def test_partial_wall_sparse_vs_full(self):
        a=(0,0); b=(5,0)
        # add a single wall cell between to force partial
        self.mock_terrain.walls.add((2,0))
        sparse_entry = self.los_manager.benchmark_visibility(a,b,'sparse')
        full_entry = self.los_manager.benchmark_visibility(a,b,'full')
        self.assertTrue(sparse_entry.partial_wall)
        self.assertTrue(full_entry.partial_wall)
        self.assertEqual(sparse_entry.has_los, full_entry.has_los)
        self.assertLessEqual(sparse_entry.total_rays, full_entry.total_rays)

    def test_set_sampling_mode(self):
        self.los_manager.set_sampling_mode('full')
        self.assertEqual(self.los_manager.sampling_mode, 'full')
        self.los_manager.set_sampling_mode('sparse')
        self.assertEqual(self.los_manager.sampling_mode, 'sparse')

    def test_get_los_points_zero_granularity(self):
        mgr0 = LineOfSightManager(self.mock_game_state, self.mock_terrain, self.mock_event_bus, los_granularity=0)
        pts = mgr0._get_los_points((5,5))
        self.assertEqual(pts, {(5,5),(6,5),(6,6),(5,6)})

if __name__ == '__main__':
    unittest.main()
