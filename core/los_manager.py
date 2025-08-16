import functools
from typing import Set, Tuple, List

from core.event_bus import EventBus
from core.game_state import GameState
from core.terrain_manager import Terrain

EVT_WALL_ADDED = "wall_added"
EVT_ENTITY_MOVED = "entity_moved"


class LineOfSightManager:
    """
    Manages Line of Sight (LOS) calculations with caching.

    This system uses a multi-ray, corner-to-corner casting method for accuracy
    and aggressive caching for performance. The cache is automatically invalidated
    when walls are added to the terrain.
    """

    def __init__(self, game_state: GameState, terrain_manager: Terrain, event_bus: EventBus, los_granularity: int = 10):
        self.game_state = game_state
        self.terrain = terrain_manager
        self.event_bus = event_bus
        self.event_bus.subscribe(EVT_WALL_ADDED, self.invalidate_cache)
        self.event_bus.subscribe(EVT_ENTITY_MOVED, self.invalidate_cache)
        self.los_cache = {}
        self.los_granularity = los_granularity

    def invalidate_cache(self, **kwargs):
        """Clears the LOS cache. Called when terrain changes."""
        self.los_cache.clear()

    def has_los(self, start_pos, end_pos) -> bool:
        """
        Check if there's a clear line of sight between start_pos and end_pos.
        Both positions can be either tuples (x,y) or objects with x,y attributes.

        Returns True if there's a clear line, False if obstructed.
        """
        # Convert positions to tuples if they're objects with x,y attributes
        if hasattr(start_pos, 'x') and hasattr(start_pos, 'y'):
            start_pos = (start_pos.x, start_pos.y)

        if hasattr(end_pos, 'x') and hasattr(end_pos, 'y'):
            end_pos = (end_pos.x, end_pos.y)

        # Convert to immutable tuples for caching
        start_pos = tuple(start_pos)
        end_pos = tuple(end_pos)

        # Ensure consistent ordering for cache (always start with lower position)
        cache_key = (start_pos, end_pos)
        if (start_pos > end_pos):  # Now this comparison works because both are tuples
            cache_key = (end_pos, start_pos)

        # Check cache first
        if cache_key in self.los_cache:
            return self.los_cache[cache_key]

        # Perform detailed LOS check and cache the result
        result = self._check_los(start_pos, end_pos)
        self.los_cache[cache_key] = result
        return result

    def _check_los(self, start_pos: Tuple[int, int], end_pos: Tuple[int, int]) -> bool:
        """
        Performs the actual LOS check by casting rays between cell boundary points.
        Returns True if any ray is unobstructed.
        """
        start_points = self._get_los_points(start_pos)
        end_points = self._get_los_points(end_pos)

        for sp in start_points:
            for ep in end_points:
                if self._is_ray_clear(sp, ep):
                    return True
        return False

    def _get_los_points(self, pos: Tuple[int, int]) -> Set[Tuple[float, float]]:
        """
        Returns a set of points on the cell's border for LOS checks,
        based on the configured granularity.
        """
        x, y = pos
        points = set()
        corners = [(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)]

        if self.los_granularity == 0:
            return set(corners)

        # Iterate over the four edges of the cell
        for i in range(4):
            p1 = corners[i]
            p2 = corners[(i + 1) % 4]
            points.add(p1)
            points.add(p2)

            # Add intermediate points
            for j in range(1, self.los_granularity + 1):
                fraction = j / (self.los_granularity + 1)
                ix = p1[0] + fraction * (p2[0] - p1[0])
                iy = p1[1] + fraction * (p2[1] - p1[1])
                points.add((ix, iy))

        return points

    def _is_ray_clear(self, start_coord: Tuple[float, float], end_coord: Tuple[float, float]) -> bool:
        """
        Checks if a single ray is obstructed by walls using Bresenham's algorithm.
        """
        x1, y1 = start_coord
        x2, y2 = end_coord

        # Use integer positions for cell checking
        ix1, iy1 = int(x1), int(y1)
        ix2, iy2 = int(x2), int(y2)

        dx = abs(ix2 - ix1)
        dy = -abs(iy2 - iy1)
        sx = 1 if ix1 < ix2 else -1
        sy = 1 if iy1 < iy2 else -1
        err = dx + dy

        while True:
            # Check for wall at the current integer cell position
            if self.terrain.is_wall(ix1, iy1):
                # Don't block on the start/end cells themselves
                if (ix1, iy1) != self.terrain.world_to_cell(start_coord) and \
                   (ix1, iy1) != self.terrain.world_to_cell(end_coord):
                    return False

            if ix1 == ix2 and iy1 == iy2:
                break

            e2 = 2 * err
            if e2 >= dy:
                err += dy
                ix1 += sx
            if e2 <= dx:
                err += dx
                iy1 += sy
        return True

    def _bresenham_line(self, x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
        """
        Implementation of Bresenham's line algorithm to determine all cells that form a line.
        Used for line of sight calculations.

        Args:
            x0, y0: Starting coordinates
            x1, y1: Ending coordinates

        Returns:
            List of (x,y) coordinates forming the line
        """
        points = []
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy

        while True:
            points.append((x0, y0))
            if x0 == x1 and y0 == y1:
                break

            e2 = 2 * err
            if e2 >= dy:
                if x0 == x1:
                    break
                err += dy
                x0 += sx
            if e2 <= dx:
                if y0 == y1:
                    break
                err += dx
                y0 += sy

        return points
