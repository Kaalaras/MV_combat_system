"""Line-of-sight system driven by ECS components and optional legacy terrain."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, TYPE_CHECKING

import numpy as np

from modules.maps.components import MapGrid
from modules.maps.resolver import ActiveMapResolver, CURRENT_MAP_CHANGED
from modules.maps.terrain_types import TerrainFlags

from ecs.components.cover import CoverComponent
from ecs.components.facing import FacingComponent
from ecs.components.position import PositionComponent
from ecs.components.structure import StructureComponent
from ecs.components.character_ref import CharacterRefComponent
from ecs.components.condition_tracker import ConditionTrackerComponent
from ecs.helpers import occupancy

from utils.condition_utils import (
    INVISIBLE,
    SEE_INVISIBLE,
    NIGHT_VISION_PARTIAL,
    NIGHT_VISION_TOTAL,
)

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from ecs.ecs_manager import ECSManager

# Optional tcod integration ---------------------------------------------------
try:  # pragma: no cover - tcod optional dependency
    import tcod  # type: ignore[import]

    try:
        from tcod import libtcodpy as _libtcod  # type: ignore[import]

        FOV_PERMISSIVE_8 = _libtcod.FOV_PERMISSIVE_8  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - fallbacks for new tcod layouts
        try:
            from tcod import constants as _tcod_constants  # type: ignore[import]

            FOV_PERMISSIVE_8 = _tcod_constants.FOV_PERMISSIVE_8  # type: ignore[attr-defined]
        except Exception:
            FOV_PERMISSIVE_8 = getattr(tcod, "FOV_PERMISSIVE_8", 0)  # type: ignore[attr-defined]
    _TcodMap: Any = None
    _HAS_TCOD: bool = True
except Exception:  # pragma: no cover - tcod unavailable
    tcod = None  # type: ignore[assignment]  # noqa: F401
    FOV_PERMISSIVE_8 = 0  # type: ignore[assignment]  # noqa: F401
    _TcodMap = None  # noqa: F401
    _HAS_TCOD = False

# Event topics ----------------------------------------------------------------
EVT_WALL_ADDED = "wall_added"
EVT_ENTITY_MOVED = "entity_moved"
EVT_WALL_REMOVED = "wall_removed"
EVT_COVER_DESTROYED = "cover_destroyed"
EVT_VISIBILITY_CHANGED = "visibility_state_changed"

GridCoord = Tuple[int, int]


@dataclass(frozen=True)
class VisibilityEntry:
    """Cached visibility information between two grid coordinates."""

    terrain_v: int
    blocker_v: int
    has_los: bool
    partial_wall: bool
    cover_sum: int
    wall_bonus: int
    total_cover: int
    total_rays: int
    clear_rays: int
    cover_ids: Tuple[str, ...]
    intervening_cells: Tuple[GridCoord, ...]


@dataclass(frozen=True)
class _Occupant:
    entity_id: str
    cover: Optional[CoverComponent]
    structure: Optional[StructureComponent]
    facing: Optional[FacingComponent]
    states: Set[str]
    has_character_ref: bool

    @property
    def is_cover_destroyed(self) -> bool:
        return self.is_structure_destroyed

    @property
    def is_structure_destroyed(self) -> bool:
        return bool(self.structure and getattr(self.structure, "destroyed", False))

    def blocks_visibility(self) -> bool:
        if INVISIBLE in self.states:
            return False
        if self.has_character_ref:
            return True
        if self.cover is not None and not self.is_cover_destroyed:
            return True
        if self.structure is not None and not self.is_structure_destroyed:
            return True
        return False


class LineOfSightSystem:
    """Compute line-of-sight information using ECS components."""

    def __init__(
        self,
        ecs_manager: Optional["ECSManager"],
        *,
        event_bus: Optional[object] = None,
        map_resolver: Optional[ActiveMapResolver] = None,
        los_granularity: int = 10,
        sampling_mode: str = "sparse",
        terrain: Optional[object] = None,
        game_state: Optional[object] = None,
    ) -> None:
        self._ecs_manager = ecs_manager
        self._event_bus = event_bus
        self._resolver = map_resolver
        if self._resolver is None and ecs_manager is not None and terrain is None:
            # Only attempt automatic resolver creation when no legacy terrain is supplied.
            try:
                self._resolver = ActiveMapResolver(ecs_manager, event_bus=event_bus)
            except Exception:
                self._resolver = None
        self._terrain_provider = terrain
        self._game_state = game_state

        self.los_granularity = los_granularity
        self.sampling_mode = sampling_mode
        self._edge_offsets = self._build_edge_offsets(los_granularity)

        self._pair_cache: Dict[Tuple[GridCoord, GridCoord], VisibilityEntry] = {}
        self.stats: Dict[str, int] = {
            "pair_recomputes": 0,
            "rays_cast_total": 0,
            "cache_hits": 0,
            "fastpath_skips": 0,
        }

        self._terrain_revision: int = 0
        self._blocker_revision: int = 0
        self._active_map_id: Optional[str] = None
        self._active_map_component: Optional[object] = None
        self._cached_terrain_version: Optional[int] = None
        self._external_terrain_version: Optional[int] = (
            getattr(game_state, "terrain_version", None) if game_state is not None else None
        )
        self._external_blocker_version: Optional[int] = (
            getattr(game_state, "blocker_version", None) if game_state is not None else None
        )

        self._grid_cache: Optional[MapGrid] = None
        self._legacy_grid_cache: Optional[MapGrid] = None

        self._tile_occupants_cache: Optional[Dict[GridCoord, List[_Occupant]]] = None
        self._tile_cache_blocker_v: int = -1
        self._current_tile_occupants: Optional[Dict[GridCoord, List[_Occupant]]] = None

        # tcod FOV state
        self._fov_map: Optional[np.ndarray] = None
        self._fov_cache: Dict[Tuple[int, int], Optional[np.ndarray]] = {}

        self._subscribe_events()
    # ------------------------------------------------------------------
    # Event handling & cache management
    # ------------------------------------------------------------------
    def _subscribe_events(self) -> None:
        bus = self._event_bus
        if not bus:
            return

        subscribe = getattr(bus, "subscribe", None)
        if not callable(subscribe):
            return

        subscribe(EVT_WALL_ADDED, self._on_static_changed)
        subscribe(EVT_WALL_REMOVED, self._on_static_changed)
        subscribe(EVT_ENTITY_MOVED, self._on_blockers_changed)
        subscribe(EVT_COVER_DESTROYED, self._on_blockers_changed)
        subscribe(EVT_VISIBILITY_CHANGED, self._on_blockers_changed)
        subscribe(CURRENT_MAP_CHANGED, self._on_static_changed)

    def _on_static_changed(self, **_: object) -> None:
        self._mark_static_changed()

    def _on_blockers_changed(self, **_: object) -> None:
        self._mark_blockers_changed()

    def _mark_static_changed(self) -> None:
        self._terrain_revision += 1
        self._fov_map = None
        self._fov_cache.clear()
        self._legacy_grid_cache = None
        self.invalidate_cache()

    def _mark_blockers_changed(self) -> None:
        self._blocker_revision += 1
        self._fov_cache.clear()
        self._tile_occupants_cache = None
        self.invalidate_cache()

    def _sync_external_versions(self) -> None:
        if self._game_state is None:
            return

        terrain_version = getattr(self._game_state, "terrain_version", None)
        if isinstance(terrain_version, int) and terrain_version != self._external_terrain_version:
            self._external_terrain_version = terrain_version
            self._mark_static_changed()

        blocker_version = getattr(self._game_state, "blocker_version", None)
        if isinstance(blocker_version, int) and blocker_version != self._external_blocker_version:
            self._external_blocker_version = blocker_version
            self._mark_blockers_changed()

    def invalidate_cache(self, **_: object) -> None:
        self._pair_cache.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_visibility_entry(
        self,
        a: GridCoord | object,
        b: GridCoord | object,
    ) -> VisibilityEntry:
        origin = self._coerce_coord(a)
        target = self._coerce_coord(b)
        if origin == target:
            gv = self._terrain_revision
            bv = self._blocker_revision
            return VisibilityEntry(
                gv,
                bv,
                True,
                False,
                0,
                0,
                0,
                0,
                0,
                tuple(),
                (origin,),
            )

        key = (origin, target) if origin <= target else (target, origin)
        self._sync_external_versions()
        self._refresh_grid_if_needed()
        gv = self._terrain_revision
        bv = self._blocker_revision
        entry = self._pair_cache.get(key)
        if entry and entry.terrain_v == gv and entry.blocker_v == bv:
            self.stats["cache_hits"] += 1
            return entry

        entry = self._recompute_visibility_entry(origin, target, gv, bv)
        self._pair_cache[key] = entry
        return entry

    def has_line_of_sight(self, start: GridCoord, end: GridCoord, *, ignore_target_blocking: bool = False) -> bool:
        entry = self.get_visibility_entry(start, end)
        if ignore_target_blocking and not entry.has_los:
            self._refresh_grid_if_needed()
            self._current_tile_occupants = self._get_tile_occupants()
            try:
                return self._is_ray_clear(
                    (float(start[0]) + 0.5, float(start[1]) + 0.5),
                    (float(end[0]) + 0.5, float(end[1]) + 0.5),
                    ignore_target_blocking=True,
                )
            finally:
                self._current_tile_occupants = None
        return entry.has_los

    def trace_ray(self, start: GridCoord, end: GridCoord) -> Sequence[GridCoord]:
        return list(self._bresenham_line(start[0], start[1], end[0], end[1]))

    def visibility_profile(self, start_pos: GridCoord, end_pos: GridCoord) -> Tuple[int, int]:
        entry = self.get_visibility_entry(start_pos, end_pos)
        if entry.total_rays == 0:
            return (1, 1)
        return (entry.total_rays, entry.clear_rays)

    def has_los(self, start_pos: GridCoord | object, end_pos: GridCoord | object) -> bool:
        """Legacy alias forwarding to :meth:`has_line_of_sight`."""

        origin = self._coerce_coord(start_pos)
        target = self._coerce_coord(end_pos)
        return self.has_line_of_sight(origin, target)

    def can_see(self, attacker_id: str, defender_id: str) -> bool:
        attacker_pos = self._get_entity_coord(attacker_id)
        defender_pos = self._get_entity_coord(defender_id)
        if not attacker_pos or not defender_pos:
            return False

        att_states = self._collect_entity_states(attacker_id)
        def_states = self._collect_entity_states(defender_id)

        if self._has_terrain_effect(attacker_pos, "dark_total") and NIGHT_VISION_TOTAL not in att_states:
            return False
        if self._has_terrain_effect(defender_pos, "dark_total") and NIGHT_VISION_TOTAL not in att_states:
            return False

        if not self.has_line_of_sight(attacker_pos, defender_pos):
            return False

        if INVISIBLE in def_states and SEE_INVISIBLE not in att_states:
            return False
        return True

    def get_darkness_attack_modifier(self, attacker_id: str, defender_id: str) -> int:
        vision_system = getattr(self._game_state, "vision_system", None)
        if vision_system and hasattr(vision_system, "get_attack_modifier"):
            try:
                modifier = vision_system.get_attack_modifier(attacker_id, defender_id)
                if modifier:
                    return int(modifier)
            except Exception:
                pass

        defender_pos = self._get_entity_coord(defender_id)
        if not defender_pos:
            return 0

        attacker_states = self._collect_entity_states(attacker_id)
        if self._has_terrain_effect(defender_pos, "dark_total"):
            return 0
        if self._has_terrain_effect(defender_pos, "dark_low"):
            if NIGHT_VISION_PARTIAL in attacker_states or NIGHT_VISION_TOTAL in attacker_states:
                return 0
            return -1
        return 0

    def benchmark_visibility(self, a: GridCoord, b: GridCoord, mode: str) -> VisibilityEntry:
        previous = self.sampling_mode
        self.sampling_mode = mode
        self._sync_external_versions()
        self._refresh_grid_if_needed()
        gv = self._terrain_revision
        bv = self._blocker_revision
        entry = self._recompute_visibility_entry(a, b, gv, bv)
        self.sampling_mode = previous
        return entry

    def reset_stats(self) -> None:
        for key in self.stats:
            self.stats[key] = 0

    def get_stats(self) -> Dict[str, int]:
        return dict(self.stats)

    def set_sampling_mode(self, mode: str) -> str:
        if mode in ("sparse", "full"):
            self.sampling_mode = mode
        return self.sampling_mode

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _refresh_grid_if_needed(self) -> None:
        if self._resolver is not None:
            resolution = self._resolver.get_active_map()
            if (
                self._active_map_id != resolution.entity_id
                or self._active_map_component is not resolution.component
            ):
                self._active_map_id = resolution.entity_id
                self._active_map_component = resolution.component
                self._grid_cache = resolution.grid
                self._mark_static_changed()
            else:
                self._grid_cache = resolution.grid
            return

        terrain = self._terrain_provider
        if terrain is None:
            return

        version = None
        if self._game_state is not None:
            version = getattr(self._game_state, "terrain_version", None)
        if version is None:
            version = getattr(terrain, "terrain_version", None)
        if version is None and self._game_state is not None:
            version = getattr(self._game_state, "terrain_version", None)

        if version is not None and version != self._cached_terrain_version:
            self._cached_terrain_version = version
            self._legacy_grid_cache = None
            self._mark_static_changed()

        if self._legacy_grid_cache is None:
            self._legacy_grid_cache = self._build_grid_from_terrain(terrain)
        self._grid_cache = self._legacy_grid_cache

    def _get_grid(self) -> MapGrid:
        self._refresh_grid_if_needed()
        if self._grid_cache is None:
            raise LookupError("No active map grid available for line of sight computation.")
        return self._grid_cache

    def _coerce_coord(self, coord: GridCoord | object) -> GridCoord:
        if isinstance(coord, tuple) and len(coord) == 2:
            return int(coord[0]), int(coord[1])
        if hasattr(coord, "x") and hasattr(coord, "y"):
            return int(getattr(coord, "x")), int(getattr(coord, "y"))
        raise TypeError(f"Invalid coordinate {coord!r}; expected tuple or object with x/y attributes.")

    def _get_entity_coord(self, entity_id: str) -> Optional[GridCoord]:
        manager = self._ecs_manager
        if manager is not None:
            position = manager.get_component_for_entity(entity_id, PositionComponent)
            if position is not None:
                return int(position.x), int(position.y)
        if self._game_state is not None:
            entity = getattr(self._game_state, "get_entity", lambda *_: None)(entity_id)
            if entity and "position" in entity:
                pos = entity["position"]
                return int(getattr(pos, "x", 0)), int(getattr(pos, "y", 0))
        return None

    def _collect_entity_states(self, entity_id: str) -> Set[str]:
        states: Set[str] = set()
        manager = self._ecs_manager
        if manager is not None:
            tracker = manager.get_component_for_entity(entity_id, ConditionTrackerComponent)
            if tracker is not None:
                try:
                    states.update(tracker.active_states())
                except Exception:
                    pass
            char_ref = manager.get_component_for_entity(entity_id, CharacterRefComponent)
            if char_ref is not None:
                character = getattr(char_ref, "character", None)
                if character is not None:
                    char_states = getattr(character, "states", None)
                    if isinstance(char_states, Iterable):
                        states.update(char_states)
        if self._game_state is not None:
            entity = getattr(self._game_state, "get_entity", lambda *_: None)(entity_id)
            if entity and "character_ref" in entity:
                char_ref = entity["character_ref"]
                character = getattr(char_ref, "character", None)
                if character is not None:
                    char_states = getattr(character, "states", None)
                    if isinstance(char_states, Iterable):
                        states.update(char_states)
        return states

    def _has_terrain_effect(self, coord: GridCoord, effect_name: str) -> bool:
        terrain = self._terrain_provider
        if not terrain:
            return False
        effect_key = {
            "dark_total": "dark_total",
            "dark_low": "dark_low",
        }.get(effect_name, effect_name)
        checker = getattr(terrain, "has_effect", None)
        if callable(checker):
            try:
                return bool(checker(coord[0], coord[1], effect_key))
            except Exception:
                return False
        return False

    def _get_tile_occupants(self) -> Dict[GridCoord, List[_Occupant]]:
        if self._tile_occupants_cache is not None and self._tile_cache_blocker_v == self._blocker_revision:
            return self._tile_occupants_cache

        occupants: Dict[GridCoord, List[_Occupant]] = {}
        manager = self._ecs_manager
        if manager is not None:
            for entity_id, tiles in occupancy.iter_entity_tiles(manager):
                occupant = self._build_occupant(entity_id)
                if occupant is None:
                    continue
                for tile in tiles:
                    occupants.setdefault(tile, []).append(occupant)
        elif self._terrain_provider is not None and hasattr(self._terrain_provider, "grid"):
            grid_map: Mapping[GridCoord, str] = getattr(self._terrain_provider, "grid", {})
            if isinstance(grid_map, Mapping):
                for tile, entity_id in grid_map.items():
                    occupant = self._build_occupant(entity_id)
                    if occupant is None:
                        continue
                    occupants.setdefault((int(tile[0]), int(tile[1])), []).append(occupant)

        self._tile_occupants_cache = occupants
        self._tile_cache_blocker_v = self._blocker_revision
        return occupants

    def _build_occupant(self, entity_id: str) -> Optional[_Occupant]:
        manager = self._ecs_manager
        cover = None
        structure = None
        facing = None
        states: Set[str] = set()
        has_character_ref = False

        if manager is not None:
            cover = manager.get_component_for_entity(entity_id, CoverComponent)
            structure = manager.get_component_for_entity(entity_id, StructureComponent)
            facing = manager.get_component_for_entity(entity_id, FacingComponent)
            has_character_ref = (
                manager.get_component_for_entity(entity_id, CharacterRefComponent) is not None
            )
            states.update(self._collect_entity_states(entity_id))
        elif self._game_state is not None:
            entity = getattr(self._game_state, "get_entity", lambda *_: None)(entity_id)
            if entity:
                cover = entity.get("cover")
                structure = entity.get("structure")
                facing = entity.get("facing")
                char_ref = entity.get("character_ref")
                if char_ref is not None:
                    has_character_ref = True
                    character = getattr(char_ref, "character", None)
                    if character is not None:
                        char_states = getattr(character, "states", None)
                        if isinstance(char_states, Iterable):
                            states.update(char_states)
        return _Occupant(
            entity_id=entity_id,
            cover=cover,
            structure=structure,
            facing=facing,
            states=states,
            has_character_ref=has_character_ref,
        )

    def _build_grid_from_terrain(self, terrain: object) -> MapGrid:
        if terrain is None:
            raise LookupError("Legacy terrain is required to build a grid.")
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
        if isinstance(grid_map, Mapping):
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

    def _build_edge_offsets(self, granularity: int) -> List[Tuple[float, float]]:
        if granularity == 0:
            return [(0, 0), (1, 0), (1, 1), (0, 1)]
        points: List[Tuple[float, float]] = []
        corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        for i in range(4):
            p1 = corners[i]
            p2 = corners[(i + 1) % 4]
            points.append(p1)
            points.append(p2)
            for j in range(1, granularity + 1):
                f = j / (granularity + 1)
                points.append((p1[0] + f * (p2[0] - p1[0]), p1[1] + f * (p2[1] - p1[1])))
        unique: List[Tuple[float, float]] = []
        seen: Set[Tuple[float, float]] = set()
        for point in points:
            if point not in seen:
                seen.add(point)
                unique.append(point)
        return unique

    # ------------------------------------------------------------------
    # Visibility computation internals
    # ------------------------------------------------------------------
    def _recompute_visibility_entry(
        self,
        origin: GridCoord,
        target: GridCoord,
        terrain_v: int,
        blocker_v: int,
    ) -> VisibilityEntry:
        self.stats["pair_recomputes"] += 1
        grid = self._get_grid()
        line = self._bresenham_line(origin[0], origin[1], target[0], target[1])
        if len(line) <= 2:
            self.stats["fastpath_skips"] += 1
            return VisibilityEntry(
                terrain_v,
                blocker_v,
                True,
                False,
                0,
                0,
                0,
                0,
                0,
                tuple(),
                tuple(line),
            )

        tile_occupants = self._get_tile_occupants()
        self._current_tile_occupants = tile_occupants
        cover_ids: List[str] = []
        cover_sum = 0
        cover_seen: Set[str] = set()
        intervening: List[GridCoord] = []
        walls_present = False
        clear_between = False

        try:
            for cell in line[1:-1]:
                intervening.append(cell)
                cx, cy = cell
                if not (0 <= cy < grid.height and 0 <= cx < grid.width):
                    continue
                if grid.blocks_los_mask[cy][cx]:
                    walls_present = True
                else:
                    clear_between = True

                for occupant in tile_occupants.get(cell, []):
                    if (
                        occupant.entity_id not in cover_seen
                        and occupant.cover is not None
                        and not occupant.is_cover_destroyed
                    ):
                        cover_seen.add(occupant.entity_id)
                        cover_ids.append(occupant.entity_id)
                        cover_sum += getattr(occupant.cover, "bonus", 0)
                    if not grid.blocks_los_mask[cy][cx]:
                        clear_between = True
        finally:
            self._current_tile_occupants = None

        if walls_present and not clear_between:
            self.stats["fastpath_skips"] += 1
            total_cover = cover_sum
            return VisibilityEntry(
                terrain_v,
                blocker_v,
                False,
                False,
                cover_sum,
                0,
                total_cover,
                0,
                0,
                tuple(cover_ids),
                tuple(intervening),
            )

        partial_wall_candidate = walls_present and clear_between
        wall_bonus = 0
        has_los = True
        total_rays = 0
        clear_rays = 0

        start_offsets = list(self._get_los_points(origin))
        end_offsets = list(self._get_los_points(target))

        if partial_wall_candidate:
            tile_occupants = self._get_tile_occupants()
            self._current_tile_occupants = tile_occupants
            try:
                if self.sampling_mode == "full":
                    for sp in start_offsets:
                        for ep in end_offsets:
                            total_rays += 1
                            if self._is_ray_clear(sp, ep):
                                clear_rays += 1
                    has_los = clear_rays > 0
                    wall_bonus = 2 if has_los and clear_rays < total_rays else 0
                    if wall_bonus == 0 and has_los and clear_rays == total_rays:
                        partial_wall_candidate = False
                else:  # sparse sampling
                    origin_set = self._corner_set(start_offsets, origin)
                    target_set = self._corner_set(end_offsets, target)
                    seen_blocked = False
                    seen_clear = False
                    for sp in origin_set:
                        for ep in target_set:
                            total_rays += 1
                            if self._is_ray_clear(sp, ep):
                                clear_rays += 1
                                seen_clear = True
                            else:
                                seen_blocked = True
                            if seen_blocked and seen_clear:
                                break
                        if seen_blocked and seen_clear:
                            break
                    if seen_blocked and seen_clear:
                        has_los = True
                        wall_bonus = 2
                    elif seen_clear and not seen_blocked:
                        for sp in start_offsets:
                            if seen_blocked:
                                break
                            for ep in end_offsets:
                                if sp in origin_set and ep in target_set:
                                    continue
                                total_rays += 1
                                if self._is_ray_clear(sp, ep):
                                    clear_rays += 1
                                else:
                                    seen_blocked = True
                                    break
                        if seen_blocked:
                            has_los = True
                            wall_bonus = 2
                        else:
                            has_los = True
                            partial_wall_candidate = False
                    elif seen_blocked and not seen_clear:
                        for sp in start_offsets:
                            if seen_clear:
                                break
                            for ep in end_offsets:
                                if sp in origin_set and ep in target_set:
                                    continue
                                total_rays += 1
                                if self._is_ray_clear(sp, ep):
                                    clear_rays += 1
                                    seen_clear = True
                                    break
                        if seen_clear:
                            has_los = True
                            wall_bonus = 2
                        else:
                            has_los = False
                            partial_wall_candidate = False
                    else:
                        has_los = True
                        partial_wall_candidate = False
            finally:
                self._current_tile_occupants = None
            self.stats["rays_cast_total"] += total_rays
        else:
            self.stats["fastpath_skips"] += 1

        partial_wall = partial_wall_candidate and has_los
        if partial_wall_candidate and not has_los:
            has_los = True
            partial_wall = True
            wall_bonus = 2
        if not partial_wall:
            wall_bonus = 0
        total_cover = cover_sum + wall_bonus
        return VisibilityEntry(
            terrain_v,
            blocker_v,
            has_los,
            partial_wall,
            cover_sum,
            wall_bonus,
            total_cover,
            total_rays,
            clear_rays,
            tuple(cover_ids),
            tuple(intervening),
        )

    def _corner_set(self, offsets: Sequence[Tuple[float, float]], origin: GridCoord) -> List[Tuple[float, float]]:
        ox, oy = origin
        targets = {(ox + dx, oy + dy) for dx, dy in [(0, 0), (1, 0), (1, 1), (0, 1)]}
        subset = [p for p in offsets if p in targets]
        return subset or list(offsets[:4])

    def _get_los_points(self, pos: GridCoord) -> Set[Tuple[float, float]]:
        x, y = pos
        return {(x + dx, y + dy) for dx, dy in self._edge_offsets}

    def _is_ray_clear(
        self,
        start_coord: Tuple[float, float],
        end_coord: Tuple[float, float],
        *,
        ignore_target_blocking: bool = False,
    ) -> bool:
        grid = self._get_grid()
        tile_occupants = self._current_tile_occupants or self._get_tile_occupants()
        x1, y1 = start_coord
        x2, y2 = end_coord
        ix1, iy1 = int(x1), int(y1)
        ix2, iy2 = int(x2), int(y2)
        dx = abs(ix2 - ix1)
        dy = -abs(iy2 - iy1)
        sx = 1 if ix1 < ix2 else -1
        sy = 1 if iy1 < iy2 else -1
        err = dx + dy

        attacker_cell = (int(start_coord[0]), int(start_coord[1]))
        target_cell = (int(end_coord[0]), int(end_coord[1]))

        while True:
            if 0 <= iy1 < grid.height and 0 <= ix1 < grid.width:
                if grid.blocks_los_mask[iy1][ix1] and (ix1, iy1) not in (attacker_cell, target_cell):
                    return False
            occupants = tile_occupants.get((ix1, iy1), [])
            if occupants and (ix1, iy1) not in (attacker_cell, target_cell):
                blocking = any(occupant.blocks_visibility() for occupant in occupants)
                if blocking:
                    return False
            if ix1 == ix2 and iy1 == iy2:
                break
            e2 = 2 * err
            if e2 >= dy:
                if ix1 == ix2:
                    break
                err += dy
                ix1 += sx
            if e2 <= dx:
                if iy1 == iy2:
                    break
                err += dx
                iy1 += sy
        return True

    def _bresenham_line(self, x0: int, y0: int, x1: int, y1: int) -> List[GridCoord]:
        pts: List[GridCoord] = []
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            pts.append((x0, y0))
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
        return pts

    # ------------------------------------------------------------------
    # FOV helpers (tcod integration)
    # ------------------------------------------------------------------
    def _build_fov_map(self) -> Optional[np.ndarray]:
        try:
            grid = self._get_grid()
        except LookupError:
            return None
        transparency = np.ones((grid.height, grid.width), dtype=bool)
        for y in range(grid.height):
            row = grid.blocks_los_mask[y]
            for x in range(grid.width):
                if row[x]:
                    transparency[y, x] = False
        return transparency

    def _get_fov_for_origin(self, origin: GridCoord) -> Optional[np.ndarray]:
        if not _HAS_TCOD:
            return None
        self._refresh_grid_if_needed()
        grid = self._get_grid()
        if self._fov_map is None:
            self._fov_map = self._build_fov_map()
            if self._fov_map is None:
                return None
            self._fov_cache.clear()
        cached = self._fov_cache.get(origin)
        if cached is not None:
            return cached
        ox, oy = origin
        try:
            vis_mask = tcod.map.compute_fov(self._fov_map, (oy, ox), 0, True, FOV_PERMISSIVE_8)  # type: ignore[arg-type]
        except Exception:
            vis_mask = None
        self._fov_cache[origin] = vis_mask
        return vis_mask


__all__ = [
    "LineOfSightSystem",
    "VisibilityEntry",
    "EVT_WALL_ADDED",
    "EVT_ENTITY_MOVED",
    "EVT_WALL_REMOVED",
    "EVT_COVER_DESTROYED",
    "EVT_VISIBILITY_CHANGED",
]
