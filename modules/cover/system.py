"""Cover computations driven by the ECS and :class:`MapComponent` data."""
from __future__ import annotations

from typing import Final, Optional, Sequence, Tuple

from ecs.components.position import PositionComponent
from modules.los.system import LineOfSightSystem, VisibilityEntry
from modules.maps.components import MapGrid
from modules.maps.resolver import ActiveMapResolver, MapResolution
from modules.maps.terrain_types import TerrainFlags

GridCoord = Tuple[int, int]

# Default modifier used when no cover applies. ``-2`` mirrors the combat rules
# documented in ``docs/combat.md`` and represents the penalty for being exposed.
DEFAULT_NO_COVER_BONUS: Final[int] = -2
_COVER_PRIORITY = (
    (TerrainFlags.FORTIFICATION, 1),
    (TerrainFlags.COVER_HEAVY, 0),
    (TerrainFlags.COVER_LIGHT, -1),
)


class CoverSystem:
    """Derive cover bonuses from terrain tiles and ECS cover entities."""

    def __init__(
        self,
        ecs_manager: "ECSManager",
        *,
        event_bus: Optional[object] = None,
        map_resolver: Optional[ActiveMapResolver] = None,
        los_system: Optional[LineOfSightSystem] = None,
        default_no_cover_bonus: int = DEFAULT_NO_COVER_BONUS,
    ) -> None:
        resolver = map_resolver or ActiveMapResolver(ecs_manager, event_bus=event_bus)
        self._resolver = resolver
        self._los = los_system or LineOfSightSystem(
            ecs_manager,
            event_bus=event_bus,
            map_resolver=resolver,
        )
        self._default_no_cover_bonus = default_no_cover_bonus
        self._ecs = ecs_manager

    # ------------------------------------------------------------------
    # Tile-based helpers (used by map integration tests and editor tooling)
    # ------------------------------------------------------------------
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
        """Return the best cover modifier available to a defender tile."""

        tx, ty = target
        bonuses = [self.tile_cover_bonus(tx, ty, default=default)]

        if edge_offsets:
            for dx, dy in edge_offsets:
                bonuses.append(self.tile_cover_bonus(tx + dx, ty + dy, default=default))

        return max(bonuses)

    # ------------------------------------------------------------------
    # ECS-driven ranged cover calculations
    # ------------------------------------------------------------------
    def compute_ranged_cover_bonus(self, attacker_id: str, defender_id: str) -> int:
        """Return the cumulative cover modifier between two entities."""

        entry = self._visibility_for_entities(attacker_id, defender_id)
        if entry is None:
            return 0
        if not entry.cover_ids and not entry.partial_wall:
            return self._default_no_cover_bonus
        return entry.cover_sum + entry.wall_bonus

    def _visibility_for_entities(
        self, attacker_id: str, defender_id: str
    ) -> Optional[VisibilityEntry]:
        entry = self._los.visibility_between_entities(attacker_id, defender_id)
        if entry is not None:
            return entry
        start = self._get_entity_anchor(attacker_id)
        end = self._get_entity_anchor(defender_id)
        if start is None or end is None:
            return None
        return self._los.get_visibility_entry(start, end)

    def _get_entity_anchor(self, entity_id: str) -> Optional[GridCoord]:
        components = self._ecs.get_components_for_entity(entity_id, PositionComponent)
        if not components:
            return None
        position: PositionComponent = components[0]
        return int(position.x), int(position.y)


__all__ = [
    "CoverSystem",
    "DEFAULT_NO_COVER_BONUS",
]
