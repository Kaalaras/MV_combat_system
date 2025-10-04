
"""Grid-aware movement helpers that operate on :class:`MapComponent` data."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

from modules.maps.components import MapGrid
from modules.maps.resolver import ActiveMapResolver, MapResolution
from modules.maps.terrain_types import TerrainFlags

GridCoord = Tuple[int, int]


class MovementError(RuntimeError):
    """Base exception raised by :class:`MovementSystem`."""


class TileBlockedError(MovementError):
    """Raised when attempting to move through an impassable tile."""


@dataclass(frozen=True)
class TileInfo:
    """Snapshot of a single grid cell."""

    x: int
    y: int
    move_cost: int
    flags: TerrainFlags
    blocks_movement: bool

    @property
    def is_walkable(self) -> bool:
        return not self.blocks_movement and TerrainFlags.IMPASSABLE not in self.flags


class MovementSystem:
    """Movement utilities backed by a :class:`~modules.maps.components.MapGrid`."""

    def __init__(
        self,
        ecs_manager: "ECSManager",
        *,
        event_bus: Optional[object] = None,
        map_resolver: Optional[ActiveMapResolver] = None,
    ) -> None:
        self._resolver = map_resolver or ActiveMapResolver(ecs_manager, event_bus=event_bus)

    def _get_resolution(self) -> MapResolution:
        return self._resolver.get_active_map()

    def get_grid(self) -> MapGrid:
        """Return the currently active map grid."""

        return self._get_resolution().grid

    def describe_tile(self, x: int, y: int) -> TileInfo:
        """Return a :class:`TileInfo` view of the requested coordinates."""

        grid = self.get_grid()
        if not grid.in_bounds(x, y):
            raise IndexError(f"coordinates ({x}, {y}) are outside the grid bounds")

        flags = TerrainFlags(grid.flags[y][x])
        blocks = bool(grid.blocks_move_mask[y][x]) or bool(flags & TerrainFlags.IMPASSABLE)
        move_cost = int(grid.move_cost[y][x])
        return TileInfo(x=x, y=y, move_cost=move_cost, flags=flags, blocks_movement=blocks)

    def can_enter(self, x: int, y: int) -> bool:
        """Return ``True`` when the tile can be traversed."""

        try:
            info = self.describe_tile(x, y)
        except IndexError:
            return False
        return info.is_walkable

    def get_move_cost(self, x: int, y: int, *, require_walkable: bool = True) -> int:
        """Return the terrain movement cost for ``(x, y)``."""

        info = self.describe_tile(x, y)
        if require_walkable and not info.is_walkable:
            raise TileBlockedError(f"Tile ({x}, {y}) blocks movement: {info.flags!r}")
        return info.move_cost

    def path_cost(self, path: Sequence[GridCoord]) -> int:
        """Return the cumulative cost of traversing ``path``."""

        total = 0
        for x, y in path:
            total += self.get_move_cost(x, y)
        return total

    def validate_path(self, path: Iterable[GridCoord]) -> None:
        """Ensure every tile within ``path`` is traversable."""

        for x, y in path:
            self.get_move_cost(x, y, require_walkable=True)


__all__ = [
    "MovementError",
    "MovementSystem",
    "TileBlockedError",
    "TileInfo",
]
