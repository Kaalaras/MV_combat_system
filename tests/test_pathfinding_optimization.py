import unittest
import numpy as np
from core.pathfinding_optimization import OptimizedPathfinding

class DummyTerrain:
    def __init__(self, width, height, walls=None):
        self.width = width
        self.height = height
        self.walls = set(walls) if walls else set()
        self.entity_positions = {}
        self.walkable_cells = set((x, y) for x in range(width) for y in range(height) if (x, y) not in self.walls)
        self.path_cache = {}
        self.reachable_tiles_cache = {}

    def is_walkable(self, x, y, w=1, h=1):
        for dx in range(w):
            for dy in range(h):
                if (x+dx, y+dy) in self.walls:
                    return False
        return 0 <= x < self.width and 0 <= y < self.height

    def is_occupied(self, x, y, w=1, h=1, entity_id_to_ignore=None):
        return False

    def is_valid_position(self, x, y, w=1, h=1):
        return self.is_walkable(x, y, w, h)

    def move_entity(self, entity_id, x, y):
        self.entity_positions[entity_id] = (x, y)
        return True

    def _get_entity_size(self, entity_id):
        return (1, 1)

class TestPathfindingOptimization(unittest.TestCase):
    def test_portal_generation_open(self):
        terrain = DummyTerrain(20, 20)
        pf = OptimizedPathfinding(terrain)
        pf.min_region_size = 5  # Ensure subdivision for small test map
        pf._create_hierarchical_waypoints((0, 0, 20, 20))
        portals = set()
        for region in pf.regions.values():
            portals.update(region['portals'])
        self.assertGreater(len(portals), 0)

    def test_portal_generation_with_wall(self):
        walls = [(10, y) for y in range(20)]
        terrain = DummyTerrain(20, 20, walls=walls)
        pf = OptimizedPathfinding(terrain)
        pf._create_hierarchical_waypoints((0, 0, 20, 20))
        for region in pf.regions.values():
            for p in region['portals']:
                self.assertNotEqual(p[0], 10)

    def test_portal_graph_connectivity(self):
        terrain = DummyTerrain(10, 10)
        pf = OptimizedPathfinding(terrain)
        pf._create_hierarchical_waypoints((0, 0, 10, 10))
        for p1 in pf.portal_graph:
            for p2 in pf.portal_graph[p1]:
                self.assertGreaterEqual(pf.portal_graph[p1][p2], 1)

    def test_path_stitching(self):
        terrain = DummyTerrain(10, 10)
        pf = OptimizedPathfinding(terrain)
        pf.precompute_paths()
        path = pf._compute_path_astar((0, 0), (9, 9))
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (9, 9))
        self.assertTrue(all(terrain.is_walkable(x, y) for x, y in path))

    def test_fallback_to_global_astar(self):
        terrain = DummyTerrain(10, 10)
        pf = OptimizedPathfinding(terrain)
        pf.precompute_paths()
        pf.portal_graph.clear()
        pf.terrain.path_cache.clear()
        path = pf._compute_path_astar((0, 0), (9, 9))
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (9, 9))

    def test_portal_on_map_edge(self):
        terrain = DummyTerrain(10, 10)
        pf = OptimizedPathfinding(terrain)
        pf.min_region_size = 3
        pf._create_hierarchical_waypoints((0, 0, 10, 10))
        for region in pf.regions.values():
            for p in region['portals']:
                self.assertGreaterEqual(p[0], 0)
                self.assertLess(p[0], terrain.width)
                self.assertGreaterEqual(p[1], 0)
                self.assertLess(p[1], terrain.height)

    def test_single_tile_region(self):
        terrain = DummyTerrain(1, 1)
        pf = OptimizedPathfinding(terrain)
        pf.min_region_size = 1
        pf._create_hierarchical_waypoints((0, 0, 1, 1))
        for region in pf.regions.values():
            self.assertEqual(len(region['portals']), 0)

    def test_disconnected_regions(self):
        walls = [(5, y) for y in range(10)]
        terrain = DummyTerrain(10, 10, walls=walls)
        pf = OptimizedPathfinding(terrain)
        pf.min_region_size = 3
        pf._create_hierarchical_waypoints((0, 0, 10, 10))
        for region in pf.regions.values():
            for p in region['portals']:
                self.assertNotEqual(p[0], 5)

    def test_portal_overlap(self):
        walls = [(5, y) for y in range(10) if y != 5]
        terrain = DummyTerrain(10, 10, walls=walls)
        pf = OptimizedPathfinding(terrain)
        pf.min_region_size = 3
        pf._create_hierarchical_waypoints((0, 0, 10, 10))
        found = False
        for region in pf.regions.values():
            for p in region['portals']:
                if (p == (5, 5) or p == (4, 5)):
                    found = True
        self.assertTrue(found)

    def test_leaf_region_lookup_out_of_bounds(self):
        terrain = DummyTerrain(10, 10)
        pf = OptimizedPathfinding(terrain)
        pf.min_region_size = 3
        pf._create_hierarchical_waypoints((0, 0, 10, 10))
        self.assertIsNone(pf._get_leaf_region_for_position((-1, -1)))
        self.assertIsNone(pf._get_leaf_region_for_position((10, 10)))

if __name__ == '__main__':
    unittest.main()
