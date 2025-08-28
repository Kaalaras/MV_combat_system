import numpy as np
import unittest
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
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        for dx in range(w):
            for dy in range(h):
                if (x+dx, y+dy) in self.walls:
                    return False
        return True

# --- UNIT TESTS ---
class TestPathFindingOptimizationUnit(unittest.TestCase):
    def _build(self, width, height, walls=None, min_region_size=5):
        terrain = DummyTerrain(width, height, walls=walls)
        pf = OptimizedPathfinding(terrain)
        pf.min_region_size = min_region_size
        pf.precompute_paths()
        return terrain, pf

    def test_portal_generation_open(self):
        _, pf = self._build(20, 20, min_region_size=5)
        total_portals = sum(len(v) for v in pf.cluster_portals.values())
        self.assertGreater(total_portals, 0)

    def test_portal_generation_with_wall(self):
        walls = {(10, y) for y in range(20)}
        _, pf = self._build(20, 20, walls=walls, min_region_size=5)
        for plist in pf.cluster_portals.values():
            for p in plist:
                self.assertNotIn(p, walls)

    def test_portal_graph_connectivity(self):
        _, pf = self._build(10, 10, min_region_size=3)
        for node, edges in pf.portal_graph.items():
            for nb, (cost, path) in edges.items():
                self.assertGreaterEqual(cost, 1)
                self.assertGreaterEqual(len(path), 2 if cost == 1 else 1)

    def test_path_stitching(self):
        terrain, pf = self._build(10, 10, min_region_size=3)
        path = pf._compute_path_astar((0, 0), (9, 9))
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (9, 9))
        self.assertTrue(all(terrain.is_walkable(x, y) for x, y in path))
        self.assertEqual(len(path), pf.manhattan_distance((0,0),(9,9)) + 1)

    def test_fallback_to_global_astar(self):
        terrain, pf = self._build(10, 10, min_region_size=20)
        pf.portal_graph.clear()
        path = pf._compute_path_astar((0, 0), (9, 9))
        self.assertEqual(len(path), pf.manhattan_distance((0,0),(9,9)) + 1)

    def test_portal_on_map_edge(self):
        _, pf = self._build(10, 10, min_region_size=3)
        for plist in pf.cluster_portals.values():
            for x, y in plist:
                self.assertTrue(0 <= x < pf.width)
                self.assertTrue(0 <= y < pf.height)

    def test_single_tile_region(self):
        _, pf = self._build(1, 1, min_region_size=1)
        total_portals = sum(len(v) for v in pf.cluster_portals.values())
        self.assertEqual(total_portals, 0)

    def test_disconnected_regions(self):
        walls = {(5, y) for y in range(10)}
        terrain, pf = self._build(10, 10, walls=walls, min_region_size=3)
        path = pf._compute_path_astar((0,5),(9,5))
        self.assertEqual(path, [])

    def test_portal_overlap(self):
        walls = {(5, y) for y in range(10) if y != 5}
        terrain, pf = self._build(10, 10, walls=walls, min_region_size=3)
        path = pf._compute_path_astar((0,5),(9,5))
        self.assertTrue(any(p[0] == 5 for p in path))

    def test_leaf_region_lookup_out_of_bounds(self):
        _, pf = self._build(10, 10, min_region_size=3)
        self.assertIsNone(pf._cluster_id_for_position((-1,-1)))
        self.assertIsNone(pf._cluster_id_for_position((10,10)))

if __name__ == '__main__':
    unittest.main()
