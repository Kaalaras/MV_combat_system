"""Cover calculations for ECS-driven combat."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple, TYPE_CHECKING

from modules.maps.components import MapGrid
from modules.maps.resolver import ActiveMapResolver
from modules.maps.terrain_types import TerrainFlags

from ecs.components.cover import CoverComponent
from ecs.components.structure import StructureComponent
from ecs.components.position import PositionComponent

GridCoord = Tuple[int, int]

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ecs.ecs_manager import ECSManager
    from modules.los.system import LineOfSightSystem

DEFAULT_NO_COVER_BONUS = -2
_COVER_PRIORITY = (
    (TerrainFlags.FORTIFICATION, 1),
    (TerrainFlags.COVER_HEAVY, 0),
    (TerrainFlags.COVER_LIGHT, -1),
)


@dataclass
class _CoverAccumulator:
    manager: Optional["ECSManager"]
    game_state: Optional[object]

    def _get_cover_component(self, entity_id: str) -> Optional[CoverComponent]:
        if self.manager is not None:
            component = self.manager.get_component_for_entity(entity_id, CoverComponent)
            if component is not None:
                return component
        if self.game_state is not None:
            entity = getattr(self.game_state, "get_entity", lambda *_: None)(entity_id)
            if entity:
                return entity.get("cover")
        return None

    def _get_structure_component(self, entity_id: str) -> Optional[StructureComponent]:
        if self.manager is not None:
            component = self.manager.get_component_for_entity(entity_id, StructureComponent)
            if component is not None:
                return component
        if self.game_state is not None:
            entity = getattr(self.game_state, "get_entity", lambda *_: None)(entity_id)
            if entity:
                return entity.get("structure")
        return None

    def total_bonus(self, cover_ids: Sequence[str]) -> int:
        bonus = 0
        for cover_id in cover_ids:
            cover = self._get_cover_component(cover_id)
            if cover is None:
                continue
            structure = self._get_structure_component(cover_id)
            if structure is not None and getattr(structure, "destroyed", False):
                continue
            bonus += getattr(cover, "bonus", 0)
        return bonus


class CoverSystem:
    """Derive cover bonuses from terrain tiles and ECS entities."""

    def __init__(
        self,
        ecs_manager: Optional["ECSManager"],
        *,
        event_bus: Optional[object] = None,
        map_resolver: Optional[ActiveMapResolver] = None,
        default_no_cover_bonus: int = DEFAULT_NO_COVER_BONUS,
        los_system: Optional["LineOfSightSystem"] = None,
        terrain: Optional[object] = None,
        game_state: Optional[object] = None,
    ) -> None:
        self._ecs_manager = ecs_manager
        self._event_bus = event_bus
        self._terrain_provider = terrain
        self._game_state = game_state
        self._default_no_cover_bonus = default_no_cover_bonus
        self._los_system = los_system

        self._resolver = map_resolver
        if self._resolver is None and ecs_manager is not None and terrain is None:
            try:
                self._resolver = ActiveMapResolver(ecs_manager, event_bus=event_bus)
            except Exception:
                self._resolver = None

        self._cached_terrain_version: Optional[int] = None
        self._legacy_grid_cache: Optional[MapGrid] = None

    # ------------------------------------------------------------------
    # Map grid helpers
    # ------------------------------------------------------------------
    def _get_grid(self) -> MapGrid:
        if self._resolver is not None:
            resolution = self._resolver.get_active_map()
            return resolution.grid

        if self._terrain_provider is None:
            raise LookupError("No terrain information available to compute cover.")

        version = None
        if self._game_state is not None:
            version = getattr(self._game_state, "terrain_version", None)
        if version is None:
            version = getattr(self._terrain_provider, "terrain_version", None)

        if version is not None and version != self._cached_terrain_version:
            self._cached_terrain_version = version
            self._legacy_grid_cache = None

        if self._legacy_grid_cache is None:
            self._legacy_grid_cache = self._build_grid_from_terrain(self._terrain_provider)
        return self._legacy_grid_cache

    def _build_grid_from_terrain(self, terrain: object) -> MapGrid:
        raw_width = getattr(terrain, "width", 0)
        raw_height = getattr(terrain, "height", 0)
        raw_cell_size = getattr(terrain, "cell_size", 1)
        width = int(raw_width) if isinstance(raw_width, (int, float)) and raw_width > 0 else 0
        height = int(raw_height) if isinstance(raw_height, (int, float)) and raw_height > 0 else 0
        cell_size = int(raw_cell_size) if isinstance(raw_cell_size, (int, float)) and raw_cell_size > 0 else 1
        max_x = -1
        max_y = -1
        walls = getattr(terrain, "walls", None)
        if isinstance(walls, Iterable):
            for wx, wy in walls:
                max_x = max(max_x, int(wx))
                max_y = max(max_y, int(wy))
        grid_map = getattr(terrain, "grid", None)
        if isinstance(grid_map, dict):
            for gx, gy in grid_map.keys():
                max_x = max(max_x, int(gx))
                max_y = max(max_y, int(gy))
        if width <= 0:
            width = max(max_x + 1, 8) if max_x >= 0 else 8
        if height <= 0:
            height = max(max_y + 1, 8) if max_y >= 0 else 8
        if width <= 0:
            width = 1
        if height <= 0:
            height = 1
        grid = MapGrid(width, height, cell_size)
        if isinstance(walls, Iterable):
            for wx, wy in walls:
                x = int(wx)
                y = int(wy)
                if 0 <= x < width and 0 <= y < height:
                    grid.blocks_los_mask[y][x] = True
                    grid.blocks_move_mask[y][x] = True
                    grid.flags[y][x] |= int(
                        TerrainFlags.WALL | TerrainFlags.BLOCKS_LOS | TerrainFlags.BLOCKS_MOVE
                    )
        return grid

    # ------------------------------------------------------------------
    # Map-based cover queries
    # ------------------------------------------------------------------
    def tile_cover_bonus(self, x: int, y: int, *, default: Optional[int] = None) -> int:
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
        tx, ty = target
        bonuses = [self.tile_cover_bonus(tx, ty, default=default)]
        if edge_offsets:
            for dx, dy in edge_offsets:
                bonuses.append(self.tile_cover_bonus(tx + dx, ty + dy, default=default))
        return max(bonuses)

    # ------------------------------------------------------------------
    # Ranged combat integration
    # ------------------------------------------------------------------
    def compute_ranged_cover_bonus(self, attacker_id: str, defender_id: str) -> int:
        los_system = self._resolve_los_system()
        if los_system is None:
            return 0

        attacker_pos = self._get_entity_coord(attacker_id)
        defender_pos = self._get_entity_coord(defender_id)
        if attacker_pos is None or defender_pos is None:
            return 0

        entry = los_system.get_visibility_entry(attacker_pos, defender_pos)
        if not entry.cover_ids and not entry.partial_wall:
            return self._default_no_cover_bonus

        accumulator = _CoverAccumulator(self._ecs_manager, self._game_state)
        bonus = accumulator.total_bonus(entry.cover_ids)
        if entry.partial_wall:
            bonus += 2
        return bonus

    def _resolve_los_system(self) -> Optional["LineOfSightSystem"]:
        if self._los_system is not None:
            return self._los_system
        if self._game_state is not None:
            los = getattr(self._game_state, "los_manager", None)
            if los is not None:
                return los  # type: ignore[return-value]
        return None

    def _get_entity_coord(self, entity_id: str) -> Optional[GridCoord]:
        if self._ecs_manager is not None:
            position = self._ecs_manager.get_component_for_entity(entity_id, PositionComponent)
            if position is not None:
                return int(position.x), int(position.y)
        if self._game_state is not None:
            entity = getattr(self._game_state, "get_entity", lambda *_: None)(entity_id)
            if entity and "position" in entity:
                pos = entity["position"]
                return int(getattr(pos, "x", 0)), int(getattr(pos, "y", 0))
        return None


__all__ = ["CoverSystem"]
