import unittest
import importlib.util
import os

# Attempt to import the OptimizedPathfinding class from various common locations.
# We do not modify sys.path to avoid interfering with other tests.  If all
# import attempts fail, we load the module directly from the file path
# relative to this test file.
try:
    # Package layout: MV_combat_system.core.pathfinding_optimization
    from MV_combat_system.core.pathfinding_optimization import OptimizedPathfinding  # type: ignore
except ImportError:
    try:
        # Package layout: core.pathfinding_optimization
        from core.pathfinding_optimization import OptimizedPathfinding  # type: ignore
    except ImportError:
        try:
            # Direct import if module is on PYTHONPATH
            from pathfinding_optimization import OptimizedPathfinding  # type: ignore
        except ImportError:
            # Fallback: load module from path relative to this file
            current_dir = os.path.dirname(__file__)
            project_root = os.path.abspath(os.path.join(current_dir, os.pardir))
            module_path = os.path.join(project_root, "pathfinding_optimization.py")
            spec = importlib.util.spec_from_file_location("pathfinding_optimization", module_path)
            if spec is None or spec.loader is None:
                raise
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore
            OptimizedPathfinding = module.OptimizedPathfinding  # type: ignore


class DummyTerrain:
    """
    Minimal stand‑in for the Terrain class used by OptimizedPathfinding.

    The dummy terrain exposes just the properties and methods accessed by
    OptimizedPathfinding: width, height, walls, walkable_cells,
    entity_positions, path_cache, and is_walkable.  Movement cost is
    assumed to be uniform (1 per step).
    """

    def __init__(self, width: int, height: int, walls: set[tuple[int, int]] | None = None) -> None:
        self.width = width
        self.height = height
        self.walls = set(walls or [])
        # Precompute the set of walkable cells for convenience
        self.walkable_cells = {
            (x, y)
            for x in range(width)
            for y in range(height)
            if (x, y) not in self.walls
        }
        # Entity positions are unused in these tests but must exist
        self.entity_positions: dict[str, tuple[int, int]] = {}
        # Caches populated by the optimizer
        self.path_cache: dict[tuple[tuple[int, int], tuple[int, int]], list[tuple[int, int]]] = {}
        self.reachable_tiles_cache: dict[tuple[tuple[int, int], int], set[tuple[int, int]]] = {}

    def is_walkable(self, x: int, y: int, entity_width: int = 1, entity_height: int = 1) -> bool:
        """Return True if the given position is not a wall and within bounds."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        # Check footprint of the entity (for now always 1×1 in tests)
        for dx in range(entity_width):
            for dy in range(entity_height):
                if (x + dx, y + dy) in self.walls:
                    return False
        return True

    # For MovementSystem compatibility (not used directly in tests)
    def get_movement_cost(self, x: int, y: int) -> int:
        return 1


def assert_valid_path(testcase: unittest.TestCase, path: list[tuple[int, int]], start: tuple[int, int], end: tuple[int, int], walls: set[tuple[int, int]]) -> None:
    """
    Validate that a path is correctly formed.

    The path must start at ``start`` and end at ``end``.  Each move must
    change the x or y coordinate by exactly one in the four cardinal
    directions.  No step may land on a wall.
    """
    testcase.assertEqual(path[0], start, f"Path does not start at {start}: {path}")
    testcase.assertEqual(path[-1], end, f"Path does not end at {end}: {path}")
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        testcase.assertTrue((dx, dy) in ((1, 0), (0, 1)), f"Invalid step from {(x1, y1)} to {(x2, y2)}")
        testcase.assertTrue((x2, y2) not in walls, f"Step lands on wall at {(x2, y2)}")


class TestHierarchicalPathfinding(unittest.TestCase):
    def test_simple_straight_line(self) -> None:
        """Path on an open grid should follow a straight line."""
        terrain = DummyTerrain(5, 5)
        optimizer = OptimizedPathfinding(terrain)
        # Prevent subdivision to keep a single region
        optimizer.min_region_size = 10
        optimizer.precompute_paths()

        start = (0, 0)
        end = (4, 0)
        path = optimizer._compute_path_astar(start, end)
        expected = [(x, 0) for x in range(5)]
        self.assertEqual(path, expected)
        assert_valid_path(self, path, start, end, terrain.walls)

    def test_path_around_obstacle(self) -> None:
        """Pathfinder should navigate around a simple obstacle barrier."""
        # Vertical barrier with a single opening at (2, 2)
        walls = {(2, 0), (2, 1), (2, 3), (2, 4)}
        terrain = DummyTerrain(5, 5, walls)
        optimizer = OptimizedPathfinding(terrain)
        optimizer.min_region_size = 2  # Force subdivision into multiple regions
        optimizer.precompute_paths()

        start = (0, 0)
        end = (4, 4)
        path = optimizer._compute_path_astar(start, end)
        # The Manhattan distance ignoring the obstacle is 8; the detour adds one extra step (total length 9).
        self.assertEqual(len(path), 9)
        assert_valid_path(self, path, start, end, walls)

    def test_unreachable_due_to_walls(self) -> None:
        """If walls block all possible routes, the path should be empty."""
        # Impassable vertical wall splitting the map
        walls = {(1, y) for y in range(5)}
        terrain = DummyTerrain(5, 5, walls)
        optimizer = OptimizedPathfinding(terrain)
        optimizer.min_region_size = 2
        optimizer.precompute_paths()

        start = (0, 2)
        end = (4, 2)
        path = optimizer._compute_path_astar(start, end)
        self.assertEqual(path, [])

    def test_start_end_same(self) -> None:
        """Start and end at the same coordinate should yield a single‑element path."""
        terrain = DummyTerrain(3, 3)
        optimizer = OptimizedPathfinding(terrain)
        optimizer.precompute_paths()
        pos = (1, 1)
        path = optimizer._compute_path_astar(pos, pos)
        self.assertEqual(path, [pos])

    def test_non_walkable_start_or_end(self) -> None:
        """If either start or end is a wall, path should be empty."""
        walls = {(0, 0), (2, 2)}
        terrain = DummyTerrain(3, 3, walls)
        optimizer = OptimizedPathfinding(terrain)
        optimizer.precompute_paths()
        # Start is a wall
        self.assertEqual(optimizer._compute_path_astar((0, 0), (2, 1)), [])
        # End is a wall
        self.assertEqual(optimizer._compute_path_astar((1, 1), (2, 2)), [])

    def test_portal_creation_on_clean_grid(self) -> None:
        """Verify that portals are created correctly between child regions.

        With a 6x6 grid and min_region_size=3 we get four 3x3 clusters:
        (0,0) (1,0)
        (0,1) (1,1)
        Each shared border produces one portal segment whose midpoint yields
        TWO portal nodes (one per cluster side). We therefore expect eight
        portal nodes (4 borders * 2 sides). The coordinate pairs are:
          Vertical border (x=2 / x=3, y=0..2)  -> (2,1) & (3,1)
          Vertical border (x=2 / x=3, y=3..5)  -> (2,4) & (3,4)
          Horizontal border (y=2 / y=3, x=0..2)-> (1,2) & (1,3)
          Horizontal border (y=2 / y=3, x=3..5)-> (4,2) & (4,3)
        We validate that these eight (x,y) coordinates exist among the
        portal graph nodes and that each has at least one connection.
        """
        terrain = DummyTerrain(6, 6)
        optimizer = OptimizedPathfinding(terrain)
        optimizer.min_region_size = 3
        optimizer.precompute_paths()
        expected_positions = {(2,1),(3,1),(2,4),(3,4),(1,2),(1,3),(4,2),(4,3)}
        portal_positions = { (x,y) for (_cx,_cy,x,y) in optimizer.portal_graph.keys() }
        self.assertTrue(expected_positions.issubset(portal_positions))
        # Each expected portal position should have at least one outgoing edge
        for node, edges in optimizer.portal_graph.items():
            cx, cy, x, y = node
            if (x,y) in expected_positions:
                self.assertTrue(edges, f"Portal node {(x,y)} has no connections")

    def test_cross_cluster_path_length(self) -> None:
        """Path length across clusters should remain optimal."""
        terrain = DummyTerrain(6, 6)
        optimizer = OptimizedPathfinding(terrain)
        # Split into four regions of size 3x3
        optimizer.min_region_size = 3
        optimizer.precompute_paths()

        start = (0, 0)
        end = (5, 5)
        path = optimizer._compute_path_astar(start, end)
        # The Manhattan distance between start and end is 10; path includes both endpoints => length 11
        self.assertEqual(len(path), optimizer.manhattan_distance(start, end) + 1)
        assert_valid_path(self, path, start, end, terrain.walls)

    def test_fallback_global_astar_when_no_portals(self) -> None:
        """When no portals exist, the algorithm should use global A* for pathfinding."""
        terrain = DummyTerrain(4, 4)
        optimizer = OptimizedPathfinding(terrain)
        # Force the entire map to be treated as a single region (no subdivisions)
        optimizer.min_region_size = 10
        optimizer.precompute_paths()
        # No portals should be created on a single region map
        self.assertEqual(dict(optimizer.portal_graph), {})
        start = (0, 0)
        end = (3, 3)
        path = optimizer._compute_path_astar(start, end)
        # Global A* should return the straight Manhattan path
        expected_len = optimizer.manhattan_distance(start, end) + 1
        self.assertEqual(len(path), expected_len)
        assert_valid_path(self, path, start, end, terrain.walls)

    def test_compute_reachable_bfs(self) -> None:
        """Reachable BFS should return all positions within the given distance, avoiding walls."""
        # 3x3 grid with a wall in the center
        walls = {(1, 1)}
        terrain = DummyTerrain(3, 3, walls)
        optimizer = OptimizedPathfinding(terrain)
        # Use direct BFS method (static version to avoid side effects)
        start = (0, 0)
        reachable = optimizer._compute_reachable_bfs(start, 2)
        # Expected reachable: (0,0),(1,0),(0,1),(2,0),(0,2)
        expected = {(0, 0), (1, 0), (0, 1), (2, 0), (0, 2)}
        self.assertEqual(reachable, expected)

    def test_path_caching(self) -> None:
        """Repeated path queries should utilize the path cache."""
        terrain = DummyTerrain(5, 5)
        optimizer = OptimizedPathfinding(terrain)
        # Prevent subdivision to simplify caching behaviour
        optimizer.min_region_size = 10
        optimizer.precompute_paths()
        start = (0, 0)
        end = (4, 4)
        # First call computes and caches
        path1 = optimizer._compute_path_astar(start, end)
        self.assertIn((start, end), terrain.path_cache)
        # Modify wall matrix to ensure second call would otherwise produce a different path
        # (if it weren't cached).  Add a wall somewhere along the path.
        optimizer.wall_matrix[2, 2] = True
        # Second call should return the cached path regardless of the new wall
        path2 = optimizer._compute_path_astar(start, end)
        self.assertEqual(path1, path2)
        assert_valid_path(self, path2, start, end, terrain.walls)


if __name__ == '__main__':
    unittest.main()