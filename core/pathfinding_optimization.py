import numpy as np
import heapq
from functools import lru_cache
from collections import defaultdict, deque
from typing import List, Tuple, Dict, Set, Optional, Any
import numba
from tqdm import tqdm
import multiprocessing


def _calculate_reachable_for_position(args):
    """Helper function for multiprocessing pool to compute reachable tiles."""
    start_pos, move_distance, wall_matrix, width, height = args
    # This function is called in a separate process, so it cannot use instance methods directly.
    # We pass all necessary data from the main process.
    reachable = OptimizedPathfinding._compute_reachable_bfs_static(start_pos, move_distance, wall_matrix, width, height)
    return start_pos, move_distance, reachable


class OptimizedPathfinding:
    """
    Advanced pathfinding optimization class for terrain navigation using spatial partitioning
    and hierarchical approaches.

    This class implements optimized pathfinding algorithms to improve performance in large grid-based
    terrain maps, using techniques such as:
    - Spatial partitioning to divide the map into manageable regions
    - Path caching with hierarchical waypoints
    - NumPy optimizations for grid operations
    - Floyd-Warshall algorithm for all-pairs shortest paths
    - A* search with optimizations
    - Pre-computation of commonly used paths and reachable tiles

    Attributes:
        terrain: The terrain object containing grid data and entity positions
        wall_matrix: NumPy boolean array representing wall positions for fast lookups

    Example usage:
    ```python
    # Create and initialize terrain
    terrain = TerrainGrid(100, 100)
    terrain.load_from_file("desert_map.json")

    # Apply optimizations
    optimizer = OptimizedPathfinding(terrain)

    # Precompute paths and reachable tiles for performance
    optimizer.precompute_paths()
    optimizer.precompute_reachable_tiles()

    # Find path between positions
    path = optimizer._compute_path_astar((10, 10), (50, 50))

    # Get all tiles reachable within 7 movement points
    reachable = optimizer._compute_reachable_bfs((10, 10), 7)
    ```
    """

    def __init__(self, terrain: Any) -> None:
        """
        Initialize the pathfinding optimizer with a terrain instance.

        Creates a NumPy boolean matrix of walls for efficient collision detection.

        Args:
            terrain: The terrain object to optimize, typically a grid-based map

        Example:
            ```python
            terrain = TerrainGrid(100, 100)
            optimizer = OptimizedPathfinding(terrain)
            ```
        """
        self.terrain = terrain
        self.wall_matrix = np.zeros((terrain.width, terrain.height), dtype=np.bool_)
        for x, y in terrain.walls:
            if 0 <= x < terrain.width and 0 <= y < terrain.height:
                self.wall_matrix[x, y] = True

        # New attributes for hierarchical pathfinding
        self.regions: Dict[Any, Any] = {}
        self.portal_graph: Dict[Tuple[int, int], Dict[Tuple[int, int], int]] = defaultdict(dict)
        self.min_region_size: int = 50
        self.leaf_regions: Dict[Tuple[int, int], Any] = {}  # Cache for position to leaf region

    @lru_cache(maxsize=1024)
    def manhattan_distance(self, a: Tuple[int, int], b: Tuple[int, int]) -> int:
        """
        Calculate Manhattan distance between two points with caching.

        Uses Python's lru_cache for memoization to avoid recalculating
        frequently used distances.

        Args:
            a: First position as (x, y) tuple
            b: Second position as (x, y) tuple

        Returns:
            Integer distance (sum of x and y differences)

        Example:
            ```python
            # Calculate distance between two points
            dist = optimizer.manhattan_distance((10, 5), (15, 8))
            print(f"Distance: {dist}")  # Output: Distance: 8
            ```
        """
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def precompute_paths(self) -> None:
        """
        Precomputes paths using a hierarchical, recursive approach.
        1. Recursively subdivides the map into regions (quadtree).
        2. Identifies "portals" (walkable connections) between regions.
        3. Precomputes paths between all portals.
        This avoids the N^2 problem of the flat waypoint system on large maps.
        """
        self.regions = {}
        self.portal_graph = defaultdict(dict)
        self.terrain.path_cache = {}
        map_bounds = (0, 0, self.terrain.width, self.terrain.height)

        print("[Terrain] Starting hierarchical waypoint creation...")
        self._create_hierarchical_waypoints(map_bounds)

        all_portals = list(self.portal_graph.keys())
        print(f"[Terrain] Found {len(all_portals)} portals. Precomputing paths between them...")

        if all_portals:
            self._compute_paths_floyd_warshall(all_portals)

        print("[Terrain] Hierarchical path precomputation complete.")

    def _create_hierarchical_waypoints(self, bounds: Tuple[int, int, int, int], level: int = 0) -> None:
        """
        Recursively subdivides the map, finds portals, and builds the portal graph.
        """
        x, y, width, height = bounds
        region_id = bounds

        self.regions[region_id] = {'bounds': bounds, 'children': [], 'portals': set()}

        # Base Case: If region is small enough, stop subdividing.
        if width <= self.min_region_size or height <= self.min_region_size:
            # When we reach a leaf, we can map all its cells to it for quick lookup
            for i in range(x, x + width):
                for j in range(y, y + height):
                    self.leaf_regions[(i, j)] = region_id
            return

        # Recursive Step: Subdivide into four quadrants.
        mid_x = x + width // 2
        mid_y = y + height // 2

        child_bounds_nw = (x, y, mid_x - x, mid_y - y)
        child_bounds_ne = (mid_x, y, x + width - mid_x, mid_y - y)
        child_bounds_sw = (x, mid_y, mid_x - x, y + height - mid_y)
        child_bounds_se = (mid_x, mid_y, x + width - mid_x, y + height - mid_y)

        children = [child_bounds_nw, child_bounds_ne, child_bounds_sw, child_bounds_se]
        self.regions[region_id]['children'] = children

        for child_bound in children:
            self._create_hierarchical_waypoints(child_bound, level + 1)

        # Find Portals between child regions
        # Vertical border between NW/SW and NE/SE
        portals_v1 = self._find_portals_between(child_bounds_nw, child_bounds_ne)
        portals_v2 = self._find_portals_between(child_bounds_sw, child_bounds_se)
        # Horizontal border between NW/NE and SW/SE
        portals_h1 = self._find_portals_between(child_bounds_nw, child_bounds_sw)
        portals_h2 = self._find_portals_between(child_bounds_ne, child_bounds_se)

        all_new_portals = set(portals_v1 + portals_v2 + portals_h1 + portals_h2)
        self.regions[region_id]['portals'].update(all_new_portals)

        # Add portals to the graph and connect them with local paths
        for p1 in all_new_portals:
            for p2 in all_new_portals:
                if p1 != p2:
                    # Path is constrained to the current region's bounds
                    path = self._astar_search(p1, p2, bounds=bounds)
                    if path:
                        self.portal_graph[p1][p2] = len(path) - 1
                        self.portal_graph[p2][p1] = len(path) - 1 # Assuming symmetric paths

    def _find_portals_between(self, bounds1: Tuple[int, int, int, int], bounds2: Tuple[int, int, int, int]) -> List[Tuple[int, int]]:
        """
        Finds walkable connections (portals) on the border of two adjacent regions.
        Groups contiguous walkable tiles into single portals at their center.
        """
        portals = []
        x1, y1, w1, h1 = bounds1
        x2, y2, w2, h2 = bounds2

        # Determine shared border
        # Vertical border
        if x1 + w1 == x2:
            border_x = x1 + w1 - 1
            border_y_start = max(y1, y2)
            border_y_end = min(y1 + h1, y2 + h2)

            current_segment = []
            for y in range(border_y_start, border_y_end):
                if not self.wall_matrix[border_x, y] and not self.wall_matrix[border_x + 1, y]:
                    current_segment.append((border_x, y))
                else:
                    if current_segment:
                        portal_pos = current_segment[len(current_segment) // 2]
                        portals.append(portal_pos)
                        current_segment = []
            if current_segment:
                portals.append(current_segment[len(current_segment) // 2])

        # Horizontal border
        elif y1 + h1 == y2:
            border_y = y1 + h1 - 1
            border_x_start = max(x1, x2)
            border_x_end = min(x1 + w1, x2 + w2)

            current_segment = []
            for x in range(border_x_start, border_x_end):
                if not self.wall_matrix[x, border_y] and not self.wall_matrix[x, border_y + 1]:
                    current_segment.append((x, border_y))
                else:
                    if current_segment:
                        portal_pos = current_segment[len(current_segment) // 2]
                        portals.append(portal_pos)
                        current_segment = []
            if current_segment:
                portals.append(current_segment[len(current_segment) // 2])

        return portals

    def _identify_key_waypoints(self, region_size: int) -> List[Tuple[int, int]]:
        """
        DEPRECATED: This method is no longer used in the hierarchical system.
        It is replaced by _create_hierarchical_waypoints.
        """
        pass

    def _compute_paths_floyd_warshall(self, waypoints: List[Tuple[int, int]]) -> None:
        """
        Compute all-pairs shortest paths using the Floyd-Warshall algorithm.

        Efficiently finds the shortest path between all pairs of waypoints and
        stores them in the terrain's path cache. This is most efficient when
        the number of waypoints is relatively small (< 300).

        Args:
            waypoints: List of waypoint positions as (x, y) tuples

        Example:
            ```python
            waypoints = optimizer._identify_key_waypoints(10)
            optimizer._compute_paths_floyd_warshall(waypoints)

            # Now paths are available in the cache
            print(f"Cached {len(terrain.path_cache)} paths")
            ```
        """
        # Initialize distance matrix
        n = len(waypoints)
        dist = {}
        next_node = {}

        waypoint_map = {wp: i for i, wp in enumerate(waypoints)}

        # Build the initial graph from the portal_graph or direct A*
        for i in range(n):
            for j in range(n):
                if i == j:
                    dist[(i, j)] = 0
                    continue

                p1 = waypoints[i]
                p2 = waypoints[j]

                # Check if a direct path exists in the pre-computed portal graph
                if p1 in self.portal_graph and p2 in self.portal_graph[p1]:
                    dist[(i, j)] = self.portal_graph[p1][p2]
                    next_node[(i, j)] = j
                else:
                    # Fallback to A* for portals that are not directly connected
                    # This might happen for portals in non-adjacent sub-regions
                    path = self._astar_search(p1, p2) # Search without bounds for global connectivity
                    if path:
                        dist[(i, j)] = len(path) - 1
                        next_node[(i, j)] = j
                    else:
                        dist[(i, j)] = float('inf')

        # Floyd-Warshall main loop
        for k in tqdm(range(n), desc="Floyd-Warshall on Portals"):
            for i in range(n):
                for j in range(n):
                    if (i, k) in dist and (k, j) in dist:
                        if (i, j) not in dist or dist[(i, k)] + dist[(k, j)] < dist[(i, j)]:
                            dist[(i, j)] = dist[(i, k)] + dist[(k, j)]
                            if (i, k) in next_node:
                                next_node[(i, j)] = next_node[(i, k)]

        # Store all paths in the cache
        for i in range(n):
            for j in range(n):
                if i != j and (i, j) in dist and dist[(i, j)] < float('inf'):
                    # Reconstruct path
                    path = [waypoints[i]]
                    current_i = i
                    while current_i != j:
                        next_i = next_node.get((current_i, j))
                        if next_i is None:
                            # This path is impossible, break
                            path = []
                            break
                        # To reconstruct the full path, we need to A* between intermediate portals
                        # For now, we store the sequence of portals. The full path is stitched together on-demand.
                        path.append(waypoints[next_i])
                        current_i = next_i

                    if path:
                        # Store in cache
                        self.terrain.path_cache[(waypoints[i], waypoints[j])] = path

    def _get_leaf_region_for_position(self, pos: Tuple[int, int]) -> Optional[Any]:
        """Finds the leaf region containing a given position."""
        if pos in self.leaf_regions:
            return self.leaf_regions[pos]

        # Fallback for positions not in cache (should be rare)
        for region_id, region_data in self.regions.items():
            if not region_data['children']: # It's a leaf
                x, y, w, h = region_data['bounds']
                if x <= pos[0] < x + w and y <= pos[1] < y + h:
                    self.leaf_regions[pos] = region_id
                    return region_id
        return None

    def _compute_path_astar(self, start: Tuple[int, int], end: Tuple[int, int]) -> List[Tuple[int, int]]:
        """
        Compute optimal path using the hierarchical portal system.
        """
        # --- FIX: Return [] if start or end is not walkable ---
        if not self.terrain.is_walkable(*start) or not self.terrain.is_walkable(*end):
            return []

        if start == end:
            return [start]

        # Check if path is already cached
        if (start, end) in self.terrain.path_cache:
            return self.terrain.path_cache[(start, end)]

        start_region_id = self._get_leaf_region_for_position(start)
        end_region_id = self._get_leaf_region_for_position(end)

        # Case 1: Path is within a single leaf region
        if start_region_id == end_region_id and start_region_id is not None:
            bounds = self.regions[start_region_id]['bounds']
            path = self._astar_search(start, end, bounds=bounds)
            if path:
                self.terrain.path_cache[(start, end)] = path
            return path

        # Case 2: Path crosses region boundaries
        # Find all portals of the parent regions until a common ancestor is found
        start_portals = self._get_portals_up_to_common_ancestor(start_region_id, end_region_id)
        end_portals = self._get_portals_up_to_common_ancestor(end_region_id, start_region_id)

        if not start_portals or not end_portals:
            # Fallback to a global A* if portal pathfinding fails
            return self._astar_search(start, end)

        # Find best entry and exit portals
        best_entry_portal, path_to_entry = self._find_best_path_to_portal(start, start_portals, self.regions[start_region_id]['bounds'])
        best_exit_portal, path_from_exit = self._find_best_path_to_portal(end, end_portals, self.regions[end_region_id]['bounds'])

        if not best_entry_portal or not best_exit_portal:
            return self._astar_search(start, end) # Fallback

        # Look up the high-level path between the entry and exit portals
        inter_portal_sequence = self.terrain.path_cache.get((best_entry_portal, best_exit_portal))

        if not inter_portal_sequence:
             # If the direct portal path isn't cached, something is wrong with the portal graph.
             # Fallback to a global A* search as a last resort.
             return self._astar_search(start, end)

        # --- Path Stitching Logic ---
        # 1. Start with the path from the starting point to the first portal.
        final_path = path_to_entry

        # 2. Stitch together the path between the portals in the sequence.
        # The inter_portal_sequence is a list of portal coordinates, e.g., [p1, p2, p3].
        # We need to run A* between each consecutive pair (p1-p2, p2-p3, etc.).
        for i in range(len(inter_portal_sequence) - 1):
            p1 = inter_portal_sequence[i]
            p2 = inter_portal_sequence[i+1]

            # Find a common ancestor to bound the search, making it faster.
            p1_region_id = self._get_leaf_region_for_position(p1)
            p2_region_id = self._get_leaf_region_for_position(p2)
            ancestor_id = self._find_common_ancestor(p1_region_id, p2_region_id)
            search_bounds = self.regions[ancestor_id]['bounds'] if ancestor_id else None

            segment = self._astar_search(p1, p2, bounds=search_bounds)
            if not segment:
                # If a segment can't be found, the portal graph is inconsistent. Fallback.
                return self._astar_search(start, end)

            # Append the segment, removing the first element to avoid duplicating the portal node.
            final_path.extend(segment[1:])

        # 3. Stitch the final segment from the last portal to the destination.
        last_portal = inter_portal_sequence[-1]

        # We already calculated the path from the end to the exit portal.
        # We just need to reverse it and append.
        path_from_exit.reverse()
        final_path.extend(path_from_exit[1:])

        if final_path:
            self.terrain.path_cache[(start, end)] = final_path
        return final_path

    def _find_common_ancestor(self, r1_id, r2_id):
        """Finds the lowest common ancestor region for two given regions."""
        if not r1_id or not r2_id:
            return self.regions.keys()[0] if self.regions else None # Return root if cant find

        path1 = []
        curr = r1_id
        while curr is not None:
            path1.append(curr)
            curr = self._get_parent_region(curr)

        curr = r2_id
        while curr is not None:
            if curr in path1:
                return curr
            curr = self._get_parent_region(curr)

        return self.regions.keys()[0] if self.regions else None # Fallback to root

    def _get_portals_up_to_common_ancestor(self, r1_id, r2_id):
        """Helper to collect all portals from a region up to the common ancestor with another region."""
        portals = set()

        # Find path of regions from r1_id up to the root
        path1 = []
        curr = r1_id
        while curr is not None:
            path1.append(curr)
            curr = self._get_parent_region(curr)

        # Find path of regions from r2_id up to the root
        path2 = []
        curr = r2_id
        while curr is not None:
            path2.append(curr)
            curr = self._get_parent_region(curr)

        # Find common ancestor
        common_ancestor = None
        for r in path1:
            if r in path2:
                common_ancestor = r
                break

        if common_ancestor:
            # Collect portals from r1_id up to the child of the common ancestor
            curr = r1_id
            while curr and curr != common_ancestor:
                portals.update(self.regions[curr]['portals'])
                # Also add portals of the parent, as they are entry/exit points for the level above
                parent = self._get_parent_region(curr)
                if parent:
                    portals.update(self.regions[parent]['portals'])
                curr = parent

        return list(portals)

    def _get_parent_region(self, region_id):
        """Find the parent of a given region."""
        for pid, data in self.regions.items():
            if region_id in data['children']:
                return pid
        return None

    def _find_best_path_to_portal(self, start_pos, portals, bounds):
        """Finds the shortest path from a position to any of the given portals."""
        best_portal = None
        shortest_path = []
        min_len = float('inf')

        for portal in portals:
            path = self._astar_search(start_pos, portal, bounds=bounds)
            if path and len(path) < min_len:
                min_len = len(path)
                shortest_path = path
                best_portal = portal

        return best_portal, shortest_path

    @numba.njit
    def _astar_search_numba(self, start_x: int, start_y: int, goal_x: int, goal_y: int,
                            wall_matrix: np.ndarray, width: int, height: int) -> List[Tuple[int, int]]:
        """
        JIT-compiled A* search implementation using Numba for performance optimization.

        This method would contain a Numba-optimized version of the A* algorithm.
        Currently a placeholder for the JIT-compiled function.

        Args:
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            goal_x: Destination X coordinate
            goal_y: Destination Y coordinate
            wall_matrix: Boolean NumPy array of wall positions
            width: Width of the terrain grid
            height: Height of the terrain grid

        Returns:
            List of (x, y) tuples representing the path
        """
        # This is a placeholder for the JIT-compiled function
        # The actual implementation would be similar to _astar_search but optimized for Numba
        pass

    def _astar_search(self, start: Tuple[int, int], end: Tuple[int, int], bounds: Optional[Tuple[int, int, int, int]] = None) -> List[Tuple[int, int]]:
        """
        A* search algorithm implementation using a heap queue for performance.
        Can be constrained to a bounding box.
        Args:
            start: Starting position as (x, y) tuple
            end: Destination position as (x, y) tuple
            bounds: Optional (x, y, width, height) tuple to constrain the search area.
        Returns:
            List of (x, y) tuples representing the path from start to end,
            or an empty list if no path exists
        """
        if bounds:
            min_x, min_y, width, height = bounds
            max_x = min_x + width
            max_y = min_y + height
        else:
            min_x, min_y = 0, 0
            max_x, max_y = self.terrain.width, self.terrain.height

        open_set = []
        heapq.heappush(open_set, (0, start))

        came_from = {}
        g_score = {start: 0}
        f_score = {start: self.manhattan_distance(start, end)}

        open_set_hash = {start}

        while open_set:
            _, current = heapq.heappop(open_set)
            open_set_hash.remove(current)

            if current == end:
                # Reconstruct path
                path = []
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                path.append(start)
                path.reverse()
                return path

            x, y = current
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                neighbor = (x + dx, y + dy)
                nx, ny = neighbor

                if not (min_x <= nx < max_x and min_y <= ny < max_y):
                    continue  # Out of bounds (either map or region)

                if self.wall_matrix[nx, ny]:
                    continue  # Wall

                tentative_g = g_score[current] + 1

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + self.manhattan_distance(neighbor, end)

                    if neighbor not in open_set_hash:
                        heapq.heappush(open_set, (f_score[neighbor], neighbor))
                        open_set_hash.add(neighbor)

        return []  # No path found

    def precompute_reachable_tiles(self, move_distances: Tuple[int, ...] = (7, 15)) -> None:
        """
        Precompute and cache reachable tiles for common movement distances using multiprocessing.

        For performance optimization, this method:
        1. Identifies important positions (entity positions and surrounding areas)
        2. Computes reachable tiles from these positions for given movement distances in parallel
        3. Stores results in the terrain's reachable_tiles_cache

        Args:
            move_distances: Tuple of movement distances to precompute
                           (default: (7, 15) for standard and sprint moves)

        Example:
            ```python
            # Precompute reachable tiles for standard movement (7) and sprint (15)
            optimizer.precompute_reachable_tiles()

            # Precompute for custom movement distances
            optimizer.precompute_reachable_tiles((5, 10, 20))

            # Later, retrieve precomputed reachable tiles
            reachable = terrain.reachable_tiles_cache.get((entity_pos, 7), set())
            ```
        """
        width, height = self.terrain.width, self.terrain.height

        self.terrain.reachable_tiles_cache = {}
        print("[Terrain] Precomputing reachable tiles...")

        # Focus on key positions (entity positions + surrounding areas)
        important_positions = set()

        # Add entity positions
        for entity_pos in self.terrain.entity_positions.values():
            important_positions.add(entity_pos)

            # Add surrounding area (20 squares radius)
            x, y = entity_pos
            for dx in range(-20, 21):
                for dy in range(-20, 21):
                    nx, ny = x + dx, y + dy
                    if (0 <= nx < width and 0 <= ny < height and
                            not self.wall_matrix[nx, ny] and
                            (nx, ny) in self.terrain.walkable_cells):
                        important_positions.add((nx, ny))

        # Add regular grid points for complete coverage
        for x in range(0, width, 10):
            for y in range(0, height, 10):
                if (x, y) not in self.terrain.walls and (x, y) in self.terrain.walkable_cells:
                    important_positions.add((x, y))

        tasks = []
        for move_distance in move_distances:
            for start_pos in important_positions:
                tasks.append((start_pos, move_distance, self.wall_matrix, width, height))

        # Use multiprocessing Pool
        print(f"[Terrain] Starting parallel computation for {len(tasks)} tasks...")
        with multiprocessing.Pool() as pool:
            results = list(tqdm(pool.imap(_calculate_reachable_for_position, tasks), total=len(tasks), desc="Computing Reachable Tiles"))

        for start_pos, move_distance, reachable in results:
            self.terrain.reachable_tiles_cache[(start_pos, move_distance)] = reachable

        print("[Terrain] Finished precomputing reachable tiles.")

    def _compute_reachable_numba(self, start_x: int, start_y: int, move_distance: int) -> Set[Tuple[int, int]]:
        """
        Compute reachable tiles using optimized BFS with Numba JIT compilation.

        This method is a wrapper that calls either a Numba-optimized implementation
        or falls back to the Python implementation if Numba is not available.

        Args:
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            move_distance: Maximum movement distance from starting position

        Returns:
            Set of (x, y) tuples representing reachable positions

        Example:
            ```python
            # Find tiles reachable within 7 movement points from position (10, 15)
            reachable_tiles = optimizer._compute_reachable_numba(10, 15, 7)
            print(f"Can reach {len(reachable_tiles)} tiles")
            ```
        """
        # Fall back to Python implementation if Numba is not available
        return self._compute_reachable_bfs((start_x, start_y), move_distance)

    def _compute_reachable_bfs(self, start: Tuple[int, int], move_distance: int) -> Set[Tuple[int, int]]:
        """
        Calculate tiles reachable from a starting position using breadth-first search.

        Uses BFS algorithm to find all grid cells within the specified movement distance,
        accounting for walls and terrain boundaries.

        Args:
            start: Starting position as (x, y) tuple
            move_distance: Maximum movement distance from starting position

        Returns:
            Set of (x, y) tuples representing reachable positions

        Example:
            ```python
            # Find tiles reachable in a standard move (distance 7) from position (15, 20)
            start_pos = (15, 20)
            reachable = optimizer._compute_reachable_bfs(start_pos, 7)

            # Show how many positions are reachable
            print(f"Can reach {len(reachable)} positions within 7 steps")
            ```
        """
        return self._compute_reachable_bfs_static(start, move_distance, self.wall_matrix, self.terrain.width, self.terrain.height)

    @staticmethod
    def _compute_reachable_bfs_static(start: Tuple[int, int], move_distance: int, wall_matrix: np.ndarray, width: int, height: int) -> Set[Tuple[int, int]]:
        """
        Static version of BFS for reachable tiles, suitable for multiprocessing.
        """
        reachable = set()
        visited = np.zeros((width, height), dtype=np.bool_)

        queue = deque([(start, 0)])
        reachable.add(start)
        visited[start[0], start[1]] = True

        while queue:
            (x, y), dist = queue.popleft()

            if dist >= move_distance:
                continue

            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy

                if not (0 <= nx < width and 0 <= ny < height):
                    continue  # Out of bounds

                if visited[nx, ny] or wall_matrix[nx, ny]:
                    continue

                visited[nx, ny] = True
                reachable.add((nx, ny))
                queue.append(((nx, ny), dist + 1))

        return reachable


def optimize_terrain(terrain: Any) -> Any:
    """
    Apply optimized pathfinding algorithms to a terrain instance.

    This function:
    1. Creates an OptimizedPathfinding instance for the terrain
    2. Replaces the terrain's original pathfinding methods with optimized versions
    3. Adds new methods for path lookup with A* fallback

    Args:
        terrain: Terrain instance to optimize

    Returns:
        The optimized terrain instance with enhanced pathfinding capabilities

    Example:
        ```python
        # Create terrain
        terrain = TerrainGrid(100, 100)
        terrain.load_map("large_battlefield.json")

        # Apply optimizations
        optimized_terrain = optimize_terrain(terrain)

        # Precompute paths and reachable tiles
        optimized_terrain.precompute_paths()
        optimized_terrain.precompute_reachable_tiles()
        ```
    """
    # Convert walls to numpy array for faster operations
    optimizer = OptimizedPathfinding(terrain)

    # Replace the original methods with optimized ones
    terrain.precompute_paths = lambda: optimizer.precompute_paths()
    terrain.precompute_reachable_tiles = lambda move_distances=(7, 15): optimizer.precompute_reachable_tiles(
        move_distances)

    # Add path lookup with fallback to A* when needed
    original_get_entity_position = terrain.get_entity_position

    def get_path(self, start, end):
        """Get path between two points, computing on demand if needed"""
        if (start, end) in self.path_cache:
            return self.path_cache[(start, end)]

        # Path not in cache - compute on demand with A*
        path = optimizer._compute_path_astar(start, end)
        return path

    terrain.get_path = get_path.__get__(terrain)

    return terrain