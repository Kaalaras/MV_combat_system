
"""Line of sight helpers driven by :class:`MapComponent` data."""
from __future__ import annotations

from typing import Iterator, Optional, Sequence, Tuple

from modules.maps.components import MapGrid
from modules.maps.resolver import ActiveMapResolver, MapResolution
from modules.maps.terrain_types import TerrainFlags

GridCoord = Tuple[int, int]

DEFAULT_BLOCKING_FLAGS = (
    TerrainFlags.BLOCKS_LOS | TerrainFlags.IMPASSABLE | TerrainFlags.WALL
)


def _bresenham(start: GridCoord, end: GridCoord) -> Iterator[GridCoord]:
    """Yield integer coordinates between ``start`` and ``end`` (inclusive)."""

    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy

    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


class LineOfSightSystem:
    """Perform simple raycasts on the active map grid."""

    def __init__(
        self,
        ecs_manager: "ECSManager",
        *,
        event_bus: Optional[object] = None,
        map_resolver: Optional[ActiveMapResolver] = None,
        blocking_flags: Optional[TerrainFlags] = None,
    ) -> None:
        self._resolver = map_resolver or ActiveMapResolver(ecs_manager, event_bus=event_bus)
        self._blocking_flags = (
            blocking_flags if blocking_flags is not None else DEFAULT_BLOCKING_FLAGS
        )

    def _get_grid(self) -> MapGrid:
        resolution: MapResolution = self._resolver.get_active_map()
        return resolution.grid

    def has_line_of_sight(
        self,
        start: GridCoord,
        end: GridCoord,
        *,
        ignore_target_blocking: bool = False,
    ) -> bool:
        """Return ``True`` when ``start`` can see ``end``."""

        grid = self._get_grid()
        if not grid.in_bounds(*start) or not grid.in_bounds(*end):
            return False

        ray = iter(_bresenham(start, end))
        next(ray, None)  # Skip the origin tile.
        for x, y in ray:
            if not grid.in_bounds(x, y):
                return False

            if grid.blocks_los_mask[y][x]:
                if ignore_target_blocking and (x, y) == end:
                    continue
                return False

            flags = TerrainFlags(grid.flags[y][x])
            if flags & self._blocking_flags:
                if ignore_target_blocking and (x, y) == end:
                    continue
                return False

        return True

    def trace_ray(self, start: GridCoord, end: GridCoord) -> Sequence[GridCoord]:
        """Return the discrete coordinates followed by ``has_line_of_sight``."""

        return list(_bresenham(start, end))


__all__ = [
    "LineOfSightSystem",
]
