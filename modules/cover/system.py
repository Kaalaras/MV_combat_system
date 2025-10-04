"""Cover calculations based on :class:`MapComponent` tiles."""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

from modules.maps.components import MapGrid
from modules.maps.resolver import ActiveMapResolver, MapResolution
from modules.maps.terrain_types import TerrainFlags

GridCoord = Tuple[int, int]

# Default modifier used when no cover applies.  ``-2`` mirrors the existing
# combat balance rules documented in ``docs/combat.md`` and represents a
# defensive penalty for being exposed.
DEFAULT_NO_COVER_BONUS = -2
_COVER_PRIORITY = (
    (TerrainFlags.FORTIFICATION, 1),
    (TerrainFlags.COVER_HEAVY, 0),
    (TerrainFlags.COVER_LIGHT, -1),
)


class CoverSystem:
    """Derive cover bonuses directly from map tiles."""

    def __init__(
        self,
        ecs_manager: "ECSManager",
        *,
        event_bus: Optional[object] = None,
        map_resolver: Optional[ActiveMapResolver] = None,
        default_no_cover_bonus: int = DEFAULT_NO_COVER_BONUS,
    ) -> None:
        self._resolver = map_resolver or ActiveMapResolver(ecs_manager, event_bus=event_bus)
        self._default_no_cover_bonus = default_no_cover_bonus

    def _get_grid(self) -> MapGrid:
        resolution: MapResolution = self._resolver.get_active_map()
        return resolution.grid

    def tile_cover_bonus(self, x: int, y: int, *, default: Optional[int] = None) -> int:
        """Return the cover modifier supplied by the tile at ``(x, y)``."""

        grid = self._get_grid()
        if default is None:
            default = self._default_no_cover_bonus

        if not grid.in_bounds(x, y):
            return default

        flags = TerrainFlags(grid.flags[y][x])
        for mask, bonus in _COVER_PRIORITY:
            if flags & mask:
                return bonus
        return default

    def cover_bonus(
        self,
        target: GridCoord,
        *,
        edge_offsets: Optional[Sequence[GridCoord]] = None,
        default: Optional[int] = None,
    ) -> int:
        """Return the best cover modifier available to a defender.

        ``target`` is the tile occupied by the defender.  ``edge_offsets`` can be
        used to sample neighbouring tiles (for example, half-height walls or
        adjacent barricades) – the highest bonus encountered is returned.
        """

        tx, ty = target
        bonuses = [self.tile_cover_bonus(tx, ty, default=default)]

        if edge_offsets:
            for dx, dy in edge_offsets:
                bonuses.append(self.tile_cover_bonus(tx + dx, ty + dy, default=default))

        return max(bonuses)


__all__ = [
    "CoverSystem",
]
