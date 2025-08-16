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

class TestPathfindingOptimizationIntegration(unittest.TestCase):
    def test_pathfinding_small_open_map(self):
        terrain = DummyTerrain(10, 10)
        pf = OptimizedPathfinding(terrain)
        pf.precompute_paths()
        path = pf._compute_path_astar((0, 0), (5, 5))
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (5, 5))
        self.assertTrue(all(terrain.is_walkable(x, y) for x, y in path))

    def test_pathfinding_large_open_map(self):
        terrain = DummyTerrain(100, 100)
        pf = OptimizedPathfinding(terrain)
        pf.precompute_paths()
        path = pf._compute_path_astar((0, 0), (99, 99))
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (99, 99))
        self.assertTrue(all(terrain.is_walkable(x, y) for x, y in path))

    def test_no_path_exists(self):
        walls = [(x, 5) for x in range(10)]
        terrain = DummyTerrain(10, 10, walls=walls)
        pf = OptimizedPathfinding(terrain)
        pf.precompute_paths()
        path = pf._compute_path_astar((0, 0), (9, 9))
        self.assertEqual(path, [])

    def test_maze_map(self):
        """Test pathfinding in a maze structure."""
        walls = set()
        for x in range(7):
            for y in range(7):
                if (x, y) not in [(0,0),(1,0),(1,1),(1,2),(2,2),(3,2),(3,3),(3,4),(4,4),(5,4),(5,5),(6,5),(6,6)]:
                    walls.add((x, y))
        terrain = DummyTerrain(7, 7, walls=walls)
        pf = OptimizedPathfinding(terrain)
        pf.precompute_paths()
        path = pf._compute_path_astar((0, 0), (6, 6))
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (6, 6))
        self.assertTrue(all(terrain.is_walkable(x, y) for x, y in path))
        self.assertGreater(len(path), 7)  # Should not be a straight line

    def test_dynamic_obstacle(self):
        """Test that adding a wall after precomputation triggers fallback or fails gracefully."""
        terrain = DummyTerrain(10, 10)
        pf = OptimizedPathfinding(terrain)
        pf.precompute_paths()
        for i in range(10):
            terrain.walls.add((5, i))
            terrain.walkable_cells.discard((5, i))
            pf.wall_matrix[5, i] = True
        path = pf._compute_path_astar((0, 0), (9, 9))
        self.assertEqual(path, [])

    def test_multiple_disconnected_areas(self):
        """Test that no path is found between disconnected areas."""
        walls = [(x, 5) for x in range(10)]
        terrain = DummyTerrain(10, 10, walls=walls)
        pf = OptimizedPathfinding(terrain)
        pf.precompute_paths()
        path = pf._compute_path_astar((0, 0), (0, 9))
        self.assertEqual(path, [])

    def test_large_map_sparse_portals(self):
        """Test a large map with only a narrow passage between two halves."""
        walls = [(50, y) for y in range(100) if y != 50]
        terrain = DummyTerrain(100, 100, walls=walls)
        pf = OptimizedPathfinding(terrain)
        pf.precompute_paths()
        path = pf._compute_path_astar((0, 0), (99, 99))
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (99, 99))
        self.assertIn((50, 50), path)

    def test_start_or_end_on_wall(self):
        """Test that no path is found if start or end is a wall."""
        walls = [(0, 0), (9, 9)]
        terrain = DummyTerrain(10, 10, walls=walls)
        pf = OptimizedPathfinding(terrain)
        pf.precompute_paths()
        path1 = pf._compute_path_astar((0, 0), (5, 5))
        path2 = pf._compute_path_astar((5, 5), (9, 9))
        self.assertEqual(path1, [])
        self.assertEqual(path2, [])

if __name__ == "__main__":
    unittest.main()
