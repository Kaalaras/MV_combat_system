"""
Efficient hierarchical pathfinding with local BFS and LRU caching.

This module implements a hierarchical pathfinding algorithm suitable for large
grid‑based maps.  The map is divided into rectangular clusters based on a
configurable `min_region_size`.  Portals are automatically detected along
cluster boundaries wherever contiguous run(s) of walkable tiles exist.
Within each cluster, the shortest paths between all pairs of portals are
computed using a flood‑fill (breadth‑first search) constrained to that
cluster.  A high‑level graph of portals is constructed without computing
all‑pairs shortest paths globally (no Floyd–Warshall), and A* search over
this graph stitches together a complete path between clusters.

To control memory usage when many paths are requested, two LRU caches are
employed:

* ``path_cache`` stores recently computed paths between arbitrary start and
  end positions.  When its size exceeds ``MAX_CACHE_SIZE``, the least
  recently used entry is evicted.
* ``reachable_cache`` stores recently computed reachable tile sets for
  given starting positions and movement distances.  Its size is limited by
  ``MAX_REACH_CACHE_SIZE``.

The public API consists of:

* ``precompute_paths()`` – Build the cluster structure, detect portals, and
  precompute local portal paths.  Must be called before any pathfinding.
* ``_compute_path_astar(start, end)`` – Return a list of coordinates
  representing the optimal path from ``start`` to ``end``.  If ``start``
  equals ``end``, a single‑element list is returned.  Out‑of‑bounds or
  blocked start/end points yield an empty list.
* ``_compute_reachable_bfs(start, move_distance)`` – Return the set of
  positions reachable from ``start`` within ``move_distance`` steps using
  four‑directional movement.  Does not consult or update the reachable
  cache; call ``_update_reachable_cache`` afterwards to cache results.
* ``_update_reachable_cache(key, reachable)`` – Insert a reachable set into
  the LRU cache, evicting old entries if necessary.
* ``_cluster_id_for_position(pos)`` – Return the cluster identifier for a
  position, or ``None`` if out of bounds.
* ``_bfs_path_within_cluster(start, end, cluster_id)`` – Compute a path
  within a single cluster from ``start`` to ``end`` using BFS.

This implementation does not include expensive global preprocessing like
Floyd–Warshall.  Instead, it computes portal‑to‑portal routes lazily on
demand via A* over the high‑level portal graph.  Consequently, it scales
better to large maps and dynamic usage patterns typical of game AI systems.
"""

from __future__ import annotations

from collections import defaultdict, deque, OrderedDict
from typing import Any, Dict, List, Optional, Tuple, Set
import heapq
import numpy as np


class OptimizedPathfinding:
    """Hierarchical pathfinding with local BFS and LRU caches."""

    # Maximum number of entries to retain in the path cache.  When this
    # threshold is exceeded, the least recently used entry is dropped.  Tests
    # override this value to exercise eviction logic.
    MAX_CACHE_SIZE: int = 1000
    # Maximum number of entries to retain in the reachable tiles cache.
    MAX_REACH_CACHE_SIZE: int = 1000

    def __init__(self, terrain: Any) -> None:
        """Initialise the optimiser for a given terrain.

        Parameters
        ----------
        terrain : Any
            A terrain object providing at least the following attributes:
            ``width``, ``height``, ``walls`` (an iterable of (x, y) tuples),
            and ``is_walkable(x, y)``.
        """
        self.terrain: Any = terrain
        self.width: int = terrain.width
        self.height: int = terrain.height
        # Build a wall matrix for O(1) walkability checks
        self.wall_matrix: np.ndarray = np.zeros((self.width, self.height), dtype=np.bool_)
        for (wx, wy) in getattr(terrain, "walls", []):
            if 0 <= wx < self.width and 0 <= wy < self.height:
                self.wall_matrix[wx, wy] = True

        # Cluster configuration; can be adjusted before calling precompute_paths
        self.min_region_size: int = 50

        # Data structures for hierarchical decomposition
        # Map cluster id (cx, cy) → (x_start, y_start, w, h)
        self.cluster_bounds: Dict[Tuple[int, int], Tuple[int, int, int, int]] = {}
        # Map cluster id → list of portal positions (x, y)
        self.cluster_portals: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        # Local paths between portals inside a cluster; keyed by cluster id
        # mapping (pos_a, pos_b) → list of (x, y)
        self.local_portal_paths: Dict[Tuple[int, int], Dict[Tuple[Tuple[int, int], Tuple[int, int]], List[Tuple[int, int]]]] = {}
        # High‑level graph of portals: node→{neighbour: (cost, path_list)}
        # Node is (cx, cy, x, y)
        self.portal_graph: Dict[Tuple[int, int, int, int], Dict[Tuple[int, int, int, int], Tuple[int, List[Tuple[int, int]]]]] = defaultdict(dict)

        # Path cache (LRU).  Keys are ((start_x, start_y), (end_x, end_y)) and
        # values are lists of coordinates representing the path.  The cache is
        # shared with terrain.path_cache for backwards compatibility.
        self.path_cache: OrderedDict[Tuple[Tuple[int, int], Tuple[int, int]], List[Tuple[int, int]]] = OrderedDict()
        # Ensure terrain.path_cache refers to this LRU cache
        try:
            self.terrain.path_cache = self.path_cache
        except Exception:
            # If terrain does not allow attribute assignment, ignore
            pass

        # Reachable tiles cache (LRU).  Keys are ((x, y), move_distance) and
        # values are sets of reachable positions.
        self.reachable_cache: OrderedDict[Tuple[Tuple[int, int], int], Set[Tuple[int, int]]] = OrderedDict()
        # Also mirror into terrain.reachable_tiles_cache if available
        try:
            self.terrain.reachable_tiles_cache = self.reachable_cache
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Distance helper
    #
    @staticmethod
    def manhattan_distance(a: Tuple[int, int], b: Tuple[int, int]) -> int:
        """Return the Manhattan distance between two points."""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    # ------------------------------------------------------------------
    # Precomputation
    #
    def precompute_paths(self) -> None:
        """Prepare cluster structure and portal graph for pathfinding.

        This method must be called before requesting any paths.  It divides
        the terrain into clusters of size at most ``min_region_size`` along
        each axis, detects portals along cluster borders, computes local
        paths between portals inside clusters, and builds a high‑level
        portal graph.  It also resets the caches.
        """
        # Reset caches and data structures
        self.path_cache.clear()
        self.reachable_cache.clear()
        self.portal_graph.clear()
        self.cluster_bounds.clear()
        self.cluster_portals.clear()
        self.local_portal_paths.clear()

        # Determine cluster grid
        size = max(1, self.min_region_size)
        cluster_cols = (self.width + size - 1) // size
        cluster_rows = (self.height + size - 1) // size

        # Create cluster bounds
        for cy in range(cluster_rows):
            for cx in range(cluster_cols):
                x_start = cx * size
                y_start = cy * size
                w = min(size, self.width - x_start)
                h = min(size, self.height - y_start)
                cid = (cx, cy)
                self.cluster_bounds[cid] = (x_start, y_start, w, h)
                self.cluster_portals[cid] = []
                self.local_portal_paths[cid] = {}

        # Detect portals along borders
        for (cx, cy), bounds in self.cluster_bounds.items():
            x_start, y_start, w, h = bounds
            # Left border: cluster to the left
            if x_start > 0:
                nb = (cx - 1, cy)
                if nb in self.cluster_bounds:
                    self._find_portals_between_clusters((cx, cy), nb, vertical=True, at_left=True)
            # Right border
            if x_start + w < self.width:
                nb = (cx + 1, cy)
                if nb in self.cluster_bounds:
                    self._find_portals_between_clusters((cx, cy), nb, vertical=True, at_left=False)
            # Top border
            if y_start > 0:
                nb = (cx, cy - 1)
                if nb in self.cluster_bounds:
                    self._find_portals_between_clusters((cx, cy), nb, vertical=False, at_left=True)
            # Bottom border
            if y_start + h < self.height:
                nb = (cx, cy + 1)
                if nb in self.cluster_bounds:
                    self._find_portals_between_clusters((cx, cy), nb, vertical=False, at_left=False)

        # Deduplicate portal lists per cluster
        for cid, plist in self.cluster_portals.items():
            # Use dict.fromkeys to preserve order but remove duplicates
            self.cluster_portals[cid] = list(dict.fromkeys(plist))
        # Compute local portal paths for each cluster
        for cid, portals in self.cluster_portals.items():
            if portals:
                self._compute_local_portal_paths(cid, portals)
        # Build portal graph by adding local edges
        self._build_portal_graph()

    # ------------------------------------------------------------------
    # Portal detection
    #
    def _find_portals_between_clusters(
        self,
        cid_a: Tuple[int, int],
        cid_b: Tuple[int, int],
        *,
        vertical: bool,
        at_left: bool
    ) -> None:
        """Detect portals along the border between two adjacent clusters.

        Parameters
        ----------
        cid_a : Tuple[int, int]
            Cluster id on one side of the border.
        cid_b : Tuple[int, int]
            Cluster id on the other side of the border.
        vertical : bool
            ``True`` if the border is vertical (clusters side by side).  ``False`` if horizontal.
        at_left : bool
            When ``vertical`` is True, indicates whether cluster_b is to the left of cluster_a.
            When ``vertical`` is False (horizontal border), indicates whether cluster_b is above
            cluster_a.

        For each contiguous run of walkable tiles along the border where movement between
        clusters is possible, a portal is created at the midpoint of the segment.  Two
        portal nodes are recorded (one in each cluster) and a cross edge of cost 1 is
        added to the portal graph.  Portal positions are appended to the portal list
        for each cluster.
        """
        bounds_a = self.cluster_bounds[cid_a]
        bounds_b = self.cluster_bounds[cid_b]
        x_a, y_a, w_a, h_a = bounds_a
        x_b, y_b, w_b, h_b = bounds_b
        segment: List[Tuple[int, int]] = []

        if vertical:
            # Shared vertical border: y ranges overlap, x border is between clusters
            if at_left:
                # cluster_b is to the left of cluster_a
                border_x_a = x_a
                border_x_b = x_a - 1
            else:
                # cluster_b is to the right of cluster_a
                border_x_a = x_a + w_a - 1
                border_x_b = border_x_a + 1
            y_start = max(y_a, y_b)
            y_end = min(y_a + h_a, y_b + h_b)
            for yy in range(y_start, y_end):
                cell_a = (border_x_a, yy)
                cell_b = (border_x_b, yy)
                if (
                    0 <= cell_a[0] < self.width and 0 <= cell_a[1] < self.height
                    and 0 <= cell_b[0] < self.width and 0 <= cell_b[1] < self.height
                    and not self.wall_matrix[cell_a]
                    and not self.wall_matrix[cell_b]
                ):
                    segment.append(cell_a)
                else:
                    if segment:
                        self._add_portal_pair(segment, cid_a, cid_b, vertical, at_left)
                        segment = []
            if segment:
                self._add_portal_pair(segment, cid_a, cid_b, vertical, at_left)
        else:
            # Shared horizontal border: x ranges overlap, y border is between clusters
            if at_left:
                # cluster_b is above cluster_a
                border_y_a = y_a
                border_y_b = y_a - 1
            else:
                # cluster_b is below cluster_a
                border_y_a = y_a + h_a - 1
                border_y_b = border_y_a + 1
            x_start = max(x_a, x_b)
            x_end = min(x_a + w_a, x_b + w_b)
            for xx in range(x_start, x_end):
                cell_a = (xx, border_y_a)
                cell_b = (xx, border_y_b)
                if (
                    0 <= cell_a[0] < self.width and 0 <= cell_a[1] < self.height
                    and 0 <= cell_b[0] < self.width and 0 <= cell_b[1] < self.height
                    and not self.wall_matrix[cell_a]
                    and not self.wall_matrix[cell_b]
                ):
                    segment.append(cell_a)
                else:
                    if segment:
                        self._add_portal_pair(segment, cid_a, cid_b, vertical, at_left)
                        segment = []
            if segment:
                self._add_portal_pair(segment, cid_a, cid_b, vertical, at_left)

    def _add_portal_pair(
        self,
        segment: List[Tuple[int, int]],
        cid_a: Tuple[int, int],
        cid_b: Tuple[int, int],
        vertical: bool,
        at_left: bool
    ) -> None:
        """Create portal nodes for a contiguous open segment.

        The portal is placed at the midpoint of ``segment``. Two portal nodes are
        recorded (one in each cluster) using the *adjacent* walkable cells that
        sit on either side of the border. A cross edge with cost 1 (one step to
        move across the boundary) together with its explicit two‑cell path is
        added to the portal graph. Portal positions (cluster‑local entry cells)
        are appended to the ``cluster_portals`` list for each cluster.

        Previous logic attempted to *unify* the coordinate across both clusters
        (so tests could compare raw positions). That collapsed the actual step
        required to cross a cluster boundary, producing paths that were shorter
        than the true Manhattan distance (missing one step per boundary
        crossing). Keeping distinct cells per side preserves correct path
        length accounting.
        """
        if not segment:
            return
        mid_idx = len(segment) // 2
        cell_a = segment[mid_idx]  # Cell inside cluster A
        x_a, y_a = cell_a
        # Determine the adjacent cell inside cluster B
        if vertical:
            if at_left:
                x_b, y_b = x_a - 1, y_a
            else:
                x_b, y_b = x_a + 1, y_a
        else:
            if at_left:
                x_b, y_b = x_a, y_a - 1
            else:
                x_b, y_b = x_a, y_a + 1
        # Guard: ensure adjacent cell is in bounds & walkable
        if not (0 <= x_b < self.width and 0 <= y_b < self.height):
            return
        if self.wall_matrix[x_b, y_b]:
            return
        cell_b = (x_b, y_b)
        # Record portal entry cells separately for each cluster
        self.cluster_portals[cid_a].append(cell_a)
        self.cluster_portals[cid_b].append(cell_b)
        # Create portal nodes (cluster id + concrete cell)
        node_a = (cid_a[0], cid_a[1], x_a, y_a)
        node_b = (cid_b[0], cid_b[1], x_b, y_b)
        # Cross edge path: explicit two cells (inside A then inside B)
        path_ab = [cell_a, cell_b]
        existing = self.portal_graph[node_a].get(node_b)
        if existing is None or existing[0] > 1:
            self.portal_graph[node_a][node_b] = (1, path_ab)
            self.portal_graph[node_b][node_a] = (1, path_ab[::-1])

    # ------------------------------------------------------------------
    # Local portal paths
    #
    def _compute_local_portal_paths(self, cid: Tuple[int, int], portals: List[Tuple[int, int]]) -> None:
        """Compute shortest paths between portal pairs inside a cluster via BFS.

        For each portal, a BFS is run within the cluster bounds to compute
        shortest paths to all other portals.  The results are stored in
        ``self.local_portal_paths[cid]`` as lists of coordinates.
        """
        bounds = self.cluster_bounds[cid]
        x_start, y_start, w, h = bounds
        min_x, min_y = x_start, y_start
        max_x, max_y = x_start + w, y_start + h

        for p_idx, p_start in enumerate(portals):
            # BFS from p_start within cluster
            queue: deque[Tuple[Tuple[int, int], int]] = deque()
            queue.append((p_start, 0))
            visited: Dict[Tuple[int, int], int] = {p_start: 0}
            parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
            while queue:
                (cx, cy), dist = queue.popleft()
                # Expand neighbours
                for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                    nx, ny = cx + dx, cy + dy
                    if not (min_x <= nx < max_x and min_y <= ny < max_y):
                        continue
                    if self.wall_matrix[nx, ny]:
                        continue
                    if (nx, ny) in visited:
                        continue
                    visited[(nx, ny)] = dist + 1
                    parent[(nx, ny)] = (cx, cy)
                    queue.append(((nx, ny), dist + 1))
            # Reconstruct paths to other portals
            for p_end in portals:
                if p_end == p_start or p_end not in visited:
                    continue
                # Build path from p_start to p_end
                path: List[Tuple[int, int]] = []
                cur = p_end
                while cur != p_start:
                    path.append(cur)
                    cur = parent[cur]
                path.append(p_start)
                path.reverse()
                self.local_portal_paths[cid][(p_start, p_end)] = path

    def _build_portal_graph(self) -> None:
        """Populate portal_graph with local intra‑cluster edges."""
        for cid, path_map in self.local_portal_paths.items():
            cx, cy = cid
            for (p_start, p_end), path in path_map.items():
                cost = len(path) - 1
                node_start = (cx, cy, p_start[0], p_start[1])
                node_end = (cx, cy, p_end[0], p_end[1])
                existing = self.portal_graph[node_start].get(node_end)
                if existing is None or cost < existing[0]:
                    self.portal_graph[node_start][node_end] = (cost, path)
                    # reverse path for opposite direction
                    self.portal_graph[node_end][node_start] = (cost, path[::-1])

    # ------------------------------------------------------------------
    # Cluster helpers
    #
    def _cluster_id_for_position(self, pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Return the cluster identifier containing ``pos`` or ``None`` if out of bounds."""
        x, y = pos
        if not (0 <= x < self.width and 0 <= y < self.height):
            return None
        size = max(1, self.min_region_size)
        cx = x // size
        cy = y // size
        cid = (cx, cy)
        return cid if cid in self.cluster_bounds else None

    # ------------------------------------------------------------------
    # BFS within cluster
    #
    def _bfs_path_within_cluster(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        cluster_id: Tuple[int, int]
    ) -> List[Tuple[int, int]]:
        """Return a path within a cluster using BFS, or empty if unreachable."""
        if start == end:
            return [start]
        bounds = self.cluster_bounds.get(cluster_id)
        if bounds is None:
            return []
        x_start, y_start, w, h = bounds
        min_x, min_y = x_start, y_start
        max_x, max_y = x_start + w, y_start + h
        sx, sy = start
        ex, ey = end
        if not (min_x <= sx < max_x and min_y <= sy < max_y):
            return []
        if not (min_x <= ex < max_x and min_y <= ey < max_y):
            return []
        if self.wall_matrix[sx, sy] or self.wall_matrix[ex, ey]:
            return []
        queue: deque[Tuple[Tuple[int, int], int]] = deque()
        queue.append(((sx, sy), 0))
        visited: Set[Tuple[int, int]] = {(sx, sy)}
        parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
        while queue:
            (cx, cy), dist = queue.popleft()
            if (cx, cy) == (ex, ey):
                # reconstruct
                path: List[Tuple[int, int]] = []
                cur = (cx, cy)
                while cur != (sx, sy):
                    path.append(cur)
                    cur = parent[cur]
                path.append((sx, sy))
                path.reverse()
                return path
            for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                nx, ny = cx + dx, cy + dy
                if not (min_x <= nx < max_x and min_y <= ny < max_y):
                    continue
                if self.wall_matrix[nx, ny]:
                    continue
                if (nx, ny) in visited:
                    continue
                visited.add((nx, ny))
                parent[(nx, ny)] = (cx, cy)
                queue.append(((nx, ny), dist + 1))
        return []

    # ------------------------------------------------------------------
    # Reachable tiles
    #
    def _compute_reachable_bfs(self, start: Tuple[int, int], move_distance: int) -> Set[Tuple[int, int]]:
        """Compute reachable tiles within ``move_distance`` using BFS (no cache update)."""
        reachable: Set[Tuple[int, int]] = set()
        sx, sy = start
        if move_distance < 0:
            return reachable
        if not (0 <= sx < self.width and 0 <= sy < self.height):
            return reachable
        if self.wall_matrix[sx, sy]:
            return reachable
        visited = np.zeros((self.width, self.height), dtype=bool)
        queue: deque[Tuple[Tuple[int, int], int]] = deque()
        queue.append(((sx, sy), 0))
        visited[sx, sy] = True
        reachable.add((sx, sy))
        while queue:
            (cx, cy), dist = queue.popleft()
            if dist >= move_distance:
                continue
            for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < self.width and 0 <= ny < self.height):
                    continue
                if visited[nx, ny] or self.wall_matrix[nx, ny]:
                    continue
                visited[nx, ny] = True
                reachable.add((nx, ny))
                queue.append(((nx, ny), dist + 1))
        return reachable

    def _update_reachable_cache(self, key: Tuple[Tuple[int, int], int], reachable: Set[Tuple[int, int]]) -> None:
        """Insert a reachable set into the LRU cache, evicting if necessary."""
        # If already present, move to end (most recent)
        if key in self.reachable_cache:
            self.reachable_cache.move_to_end(key)
            return
        # Insert new
        self.reachable_cache[key] = reachable
        # Evict oldest if over capacity
        if len(self.reachable_cache) > self.MAX_REACH_CACHE_SIZE:
            self.reachable_cache.popitem(last=False)

    # ------------------------------------------------------------------
    # Pathfinding
    #
    def _update_path_cache(self, key: Tuple[Tuple[int, int], Tuple[int, int]], path: List[Tuple[int, int]]) -> None:
        """Insert a path into the LRU path cache, with eviction."""
        if key in self.path_cache:
            # Move to end to mark as recently used
            self.path_cache.move_to_end(key)
            return
        self.path_cache[key] = path
        if len(self.path_cache) > self.MAX_CACHE_SIZE:
            self.path_cache.popitem(last=False)

    def _astar_search_global(self, start: Tuple[int, int], end: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Fallback global A* search across entire terrain."""
        if not (0 <= start[0] < self.width and 0 <= start[1] < self.height):
            return []
        if not (0 <= end[0] < self.width and 0 <= end[1] < self.height):
            return []
        if self.wall_matrix[start] or self.wall_matrix[end]:
            return []
        if start == end:
            return [start]
        open_set: List[Tuple[int, Tuple[int, int]]] = []
        heapq.heappush(open_set, (self.manhattan_distance(start, end), start))
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], int] = {start: 0}
        open_hash: Set[Tuple[int, int]] = {start}
        while open_set:
            _, current = heapq.heappop(open_set)
            open_hash.discard(current)
            if current == end:
                # reconstruct path
                path: List[Tuple[int, int]] = []
                cur = current
                while cur in came_from:
                    path.append(cur)
                    cur = came_from[cur]
                path.append(start)
                path.reverse()
                return path
            cx, cy = current
            for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < self.width and 0 <= ny < self.height):
                    continue
                if self.wall_matrix[nx, ny]:
                    continue
                tentative_g = g_score[current] + 1
                neighbour = (nx, ny)
                if neighbour not in g_score or tentative_g < g_score[neighbour]:
                    came_from[neighbour] = current
                    g_score[neighbour] = tentative_g
                    f = tentative_g + self.manhattan_distance(neighbour, end)
                    if neighbour not in open_hash:
                        heapq.heappush(open_set, (f, neighbour))
                        open_hash.add(neighbour)
        return []

    def _compute_path_astar(self, start: Tuple[int, int], end: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Compute a path from ``start`` to ``end`` using hierarchical A* and caching."""
        # Reject out of bounds
        if not (0 <= start[0] < self.width and 0 <= start[1] < self.height):
            return []
        if not (0 <= end[0] < self.width and 0 <= end[1] < self.height):
            return []
        # Reject blocked start or end
        if self.wall_matrix[start] or self.wall_matrix[end]:
            return []
        # Trivial case
        if start == end:
            return [start]
        key = (start, end)
        # Check cache
        if key in self.path_cache:
            # Update recency and return cached path
            self.path_cache.move_to_end(key)
            return self.path_cache[key]
        # Determine clusters
        start_cid = self._cluster_id_for_position(start)
        end_cid = self._cluster_id_for_position(end)
        # Fallback if out of cluster
        if start_cid is None or end_cid is None:
            path = self._astar_search_global(start, end)
            if path:
                self._update_path_cache(key, path)
            return path
        # Same cluster → BFS within cluster
        if start_cid == end_cid:
            path = self._bfs_path_within_cluster(start, end, start_cid)
            if path:
                self._update_path_cache(key, path)
            return path
        # Hierarchical search across clusters
        # Identify reachable portals in start and end clusters
        portals_start: List[Tuple[int, int]] = self.cluster_portals.get(start_cid, [])
        portals_end: List[Tuple[int, int]] = self.cluster_portals.get(end_cid, [])
        if not portals_start or not portals_end:
            # If no portals exist, fallback to global A*
            path = self._astar_search_global(start, end)
            if path:
                self._update_path_cache(key, path)
            return path
        # BFS from start to portals in start cluster
        start_paths = self._bfs_all_paths_from(start, start_cid)
        start_portal_nodes: List[Tuple[int, int, int, int]] = []
        start_portal_paths: Dict[Tuple[int, int, int, int], List[Tuple[int, int]]] = {}
        for p in portals_start:
            if p in start_paths:
                node = (start_cid[0], start_cid[1], p[0], p[1])
                start_portal_nodes.append(node)
                start_portal_paths[node] = start_paths[p]
        if not start_portal_nodes:
            # fallback
            path = self._astar_search_global(start, end)
            if path:
                self._update_path_cache(key, path)
            return path
        # BFS from end to portals in end cluster (reverse to build portal→end path)
        end_paths = self._bfs_all_paths_from(end, end_cid)
        end_portal_nodes: List[Tuple[int, int, int, int]] = []
        end_portal_paths: Dict[Tuple[int, int, int, int], List[Tuple[int, int]]] = {}
        end_costs: Dict[Tuple[int, int, int, int], int] = {}
        for p in portals_end:
            if p in end_paths:
                node = (end_cid[0], end_cid[1], p[0], p[1])
                # path from end to portal → reverse to portal→end
                p_to_end = list(reversed(end_paths[p]))
                end_portal_nodes.append(node)
                end_portal_paths[node] = p_to_end
                end_costs[node] = len(p_to_end) - 1
        if not end_portal_nodes:
            path = self._astar_search_global(start, end)
            if path:
                self._update_path_cache(key, path)
            return path
        # A* search on portal graph
        # Precompute minimal end cost for heuristic
        min_end_cost = min(end_costs.values()) if end_costs else 0
        def heuristic(node: Tuple[int, int, int, int]) -> int:
            _, _, px, py = node
            return abs(px - end[0]) + abs(py - end[1]) + min_end_cost
        open_heap: List[Tuple[int, Tuple[int, int, int, int]]] = []
        g_score: Dict[Tuple[int, int, int, int], int] = {}
        f_score: Dict[Tuple[int, int, int, int], int] = {}
        came_from_portal: Dict[Tuple[int, int, int, int], Optional[Tuple[int, int, int, int]]] = {}
        # initialise open set
        for node in start_portal_nodes:
            cost_to_start = len(start_portal_paths[node]) - 1
            g_score[node] = cost_to_start
            f_val = cost_to_start + heuristic(node)
            f_score[node] = f_val
            heapq.heappush(open_heap, (f_val, node))
            came_from_portal[node] = None
        goal_node: Optional[Tuple[int, int, int, int]] = None
        goal_set = set(end_portal_nodes)
        visited_portals: Set[Tuple[int, int, int, int]] = set()
        while open_heap:
            f_current, current = heapq.heappop(open_heap)
            if current in visited_portals:
                continue
            visited_portals.add(current)
            if current in goal_set:
                goal_node = current
                break
            # Explore neighbours
            for neighbour, (edge_cost, edge_path) in self.portal_graph.get(current, {}).items():
                tentative_g = g_score[current] + edge_cost
                if neighbour not in g_score or tentative_g < g_score[neighbour]:
                    g_score[neighbour] = tentative_g
                    came_from_portal[neighbour] = current
                    f_n = tentative_g + heuristic(neighbour)
                    f_score[neighbour] = f_n
                    heapq.heappush(open_heap, (f_n, neighbour))
        if goal_node is None:
            # Fallback global search
            path = self._astar_search_global(start, end)
            if path:
                self._update_path_cache(key, path)
            return path
        # Reconstruct portal sequence
        portal_sequence: List[Tuple[int, int, int, int]] = []
        cur = goal_node
        while cur is not None:
            portal_sequence.append(cur)
            cur = came_from_portal.get(cur)
        portal_sequence.reverse()
        # Build final path from segments
        final_path: List[Tuple[int, int]] = []
        # start to first portal
        entry_portal = portal_sequence[0]
        final_path.extend(start_portal_paths[entry_portal])
        # between portals in sequence
        for i in range(len(portal_sequence) - 1):
            p1 = portal_sequence[i]
            p2 = portal_sequence[i + 1]
            cx1, cy1, x1, y1 = p1
            cx2, cy2, x2, y2 = p2
            if (cx1, cy1) == (cx2, cy2):
                # intra‑cluster path
                cid = (cx1, cy1)
                seg = self.local_portal_paths[cid].get(((x1, y1), (x2, y2)))
                if seg:
                    final_path.extend(seg[1:])
                else:
                    bfs_seg = self._bfs_path_within_cluster((x1, y1), (x2, y2), cid)
                    final_path.extend(bfs_seg[1:] if bfs_seg else [])
            else:
                # cross cluster; use stored edge path (contains the two boundary cells)
                edge = self.portal_graph.get(p1, {}).get(p2)
                if edge:
                    _, edge_path = edge
                    final_path.extend(edge_path[1:])  # avoid duplicating last of previous
                else:
                    # fallback: direct adjacency (should not normally happen)
                    final_path.append((x2, y2))
        # final portal to end
        exit_portal = portal_sequence[-1]
        final_path.extend(end_portal_paths[exit_portal][1:])
        # Cache and return
        if final_path:
            self._update_path_cache(key, final_path)
        return final_path

    def _bfs_all_paths_from(
        self,
        start: Tuple[int, int],
        cluster_id: Tuple[int, int]
    ) -> Dict[Tuple[int, int], List[Tuple[int, int]]]:
        """Return BFS paths from ``start`` to each reachable portal in the cluster."""
        bounds = self.cluster_bounds.get(cluster_id)
        if bounds is None:
            return {}
        x_start, y_start, w, h = bounds
        min_x, min_y = x_start, y_start
        max_x, max_y = x_start + w, y_start + h
        sx, sy = start
        if not (min_x <= sx < max_x and min_y <= sy < max_y):
            return {}
        if self.wall_matrix[sx, sy]:
            return {}
        queue: deque[Tuple[Tuple[int, int], int]] = deque()
        queue.append(((sx, sy), 0))
        visited: Dict[Tuple[int, int], int] = {(sx, sy): 0}
        parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
        while queue:
            (cx, cy), dist = queue.popleft()
            for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                nx, ny = cx + dx, cy + dy
                if not (min_x <= nx < max_x and min_y <= ny < max_y):
                    continue
                if self.wall_matrix[nx, ny]:
                    continue
                if (nx, ny) in visited:
                    continue
                visited[(nx, ny)] = dist + 1
                parent[(nx, ny)] = (cx, cy)
                queue.append(((nx, ny), dist + 1))
        # Reconstruct paths to portals
        paths: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        for portal_pos in self.cluster_portals.get(cluster_id, []):
            if portal_pos not in visited:
                continue
            path: List[Tuple[int, int]] = []
            cur = portal_pos
            while cur != (sx, sy):
                path.append(cur)
                cur = parent[cur]
            path.append((sx, sy))
            path.reverse()
            paths[portal_pos] = path
        return paths


def optimize_terrain(terrain: Any) -> Any:
    """Attach an OptimizedPathfinding instance to the given terrain.

    This helper constructs an ``OptimizedPathfinding`` and installs proxy
    methods on the terrain for ``precompute_paths``, ``precompute_reachable_tiles``
    and ``get_path``.  It ensures that caching occurs within the optimiser.
    """
    optimizer = OptimizedPathfinding(terrain)
    def precompute_paths_proxy() -> None:
        optimizer.precompute_paths()
    terrain.precompute_paths = precompute_paths_proxy
    def precompute_reachable_tiles_proxy(move_distances: Tuple[int, ...] = (7, 15)) -> None:
        # Precompute reachable tiles for each distance; update reachable cache accordingly
        for dist in move_distances:
            for x in range(terrain.width):
                for y in range(terrain.height):
                    if not optimizer.wall_matrix[x, y]:
                        reachable = optimizer._compute_reachable_bfs((x, y), dist)
                        optimizer._update_reachable_cache(((x, y), dist), reachable)
    terrain.precompute_reachable_tiles = precompute_reachable_tiles_proxy
    def get_path_proxy(start: Tuple[int, int], end: Tuple[int, int]) -> List[Tuple[int, int]]:
        return optimizer._compute_path_astar(start, end)
    terrain.get_path = get_path_proxy
    return terrain
