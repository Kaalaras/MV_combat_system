
"""Line-of-sight computations backed by ECS data and the active map grid."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Final, Iterable, Iterator, List, Optional, Sequence, Tuple

import numpy as np

from ecs.components.character_ref import CharacterRefComponent
from ecs.components.cover import CoverComponent
from ecs.components.position import PositionComponent
from modules.maps.components import MapGrid
from modules.maps.resolver import (
    ActiveMapResolver,
    MapResolution,
    CURRENT_MAP_CHANGED,
)
from modules.maps.terrain_types import TerrainFlags
from utils.condition_utils import INVISIBLE

GridCoord = Tuple[int, int]
EdgeCoord = Tuple[float, float]

# Masks that mark tiles as blocking line of sight during ray casting.
DEFAULT_BLOCKING_FLAGS: Final[TerrainFlags] = (
    TerrainFlags.BLOCKS_LOS | TerrainFlags.IMPASSABLE | TerrainFlags.WALL
)

EVT_WALL_ADDED = "wall_added"
EVT_WALL_REMOVED = "wall_removed"
EVT_ENTITY_MOVED = "entity_moved"
EVT_COVER_DESTROYED = "cover_destroyed"
EVT_VISIBILITY_STATE_CHANGED = "visibility_state_changed"


try:  # pragma: no cover - optional dependency
    import tcod  # type: ignore

    try:
        from tcod import libtcodpy as _libtcod  # type: ignore

        FOV_PERMISSIVE_8 = _libtcod.FOV_PERMISSIVE_8  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - tcod API variants
        try:
            from tcod import constants as _tcod_constants  # type: ignore

            FOV_PERMISSIVE_8 = _tcod_constants.FOV_PERMISSIVE_8  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - fallback attr
            FOV_PERMISSIVE_8 = getattr(tcod, "FOV_PERMISSIVE_8", 0)
    _HAS_TCOD = True
except Exception:  # pragma: no cover - tcod unavailable
    tcod = None  # type: ignore
    FOV_PERMISSIVE_8 = 0  # type: ignore
    _HAS_TCOD = False


@dataclass(frozen=True)
class VisibilityEntry:
    """Cached visibility/corresponding cover information for a coordinate pair."""

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
class _OccupantInfo:
    entity_id: str
    blocks_los: bool
    contributes_cover: bool
    cover_bonus: int


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
    """Perform advanced line-of-sight checks using ECS & map data."""

    def __init__(
        self,
        ecs_manager: "ECSManager",
        *,
        event_bus: Optional[object] = None,
        map_resolver: Optional[ActiveMapResolver] = None,
        blocking_flags: Optional[TerrainFlags] = None,
        los_granularity: int = 10,
        sampling_mode: str = "sparse",
        use_fov: bool = True,
    ) -> None:
        self._ecs = ecs_manager
        self._resolver = map_resolver or ActiveMapResolver(ecs_manager, event_bus=event_bus)
        self._blocking_flags = (
            blocking_flags if blocking_flags is not None else DEFAULT_BLOCKING_FLAGS
        )
        self._los_granularity = max(0, int(los_granularity))
        self.sampling_mode = sampling_mode
        self._edge_offsets: List[EdgeCoord] = self._build_edge_offsets(self._los_granularity)
        self._pair_cache: Dict[Tuple[GridCoord, GridCoord], VisibilityEntry] = {}
        self._terrain_version: int = 0
        self._blocker_version: int = 0
        self._blocker_index: Optional[Dict[GridCoord, List[_OccupantInfo]]] = None
        self._blocker_index_version: int = -1
        self._use_fov = _HAS_TCOD and use_fov
        self._fov_map: Optional[np.ndarray] = None
        self._fov_cache: Dict[GridCoord, Optional[np.ndarray]] = {}
        self._stats = {
            "pair_recomputes": 0,
            "rays_cast_total": 0,
            "cache_hits": 0,
            "fastpath_skips": 0,
        }
        self._event_bus = event_bus

        if event_bus is not None:
            subscribe = getattr(event_bus, "subscribe", None)
            if callable(subscribe):
                subscribe(EVT_WALL_ADDED, self._on_environment_changed)
                subscribe(EVT_WALL_REMOVED, self._on_environment_changed)
                subscribe(EVT_COVER_DESTROYED, self._on_blockers_changed)
                subscribe(EVT_ENTITY_MOVED, self._on_blockers_changed)
                subscribe(EVT_VISIBILITY_STATE_CHANGED, self._on_blockers_changed)
                subscribe(CURRENT_MAP_CHANGED, self._on_map_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def invalidate_cache(self) -> None:
        """Clear cached visibility entries."""

        self._pair_cache.clear()

    def reset_stats(self) -> None:
        for key in self._stats:
            self._stats[key] = 0

    def get_stats(self) -> Dict[str, int]:
        return dict(self._stats)

    def set_sampling_mode(self, mode: str) -> str:
        if mode in {"sparse", "full"}:
            self.sampling_mode = mode
        return self.sampling_mode

    def set_version_counters(
        self,
        *,
        terrain_version: Optional[int] = None,
        blocker_version: Optional[int] = None,
    ) -> None:
        """Synchronise internal cache versions with external counters."""

        if terrain_version is not None and int(terrain_version) != self._terrain_version:
            self._terrain_version = int(terrain_version)
            self.invalidate_cache()
            if self._use_fov:
                self._fov_map = None
                self._fov_cache.clear()
        if blocker_version is not None and int(blocker_version) != self._blocker_version:
            self._blocker_version = int(blocker_version)
            self.invalidate_cache()
            self._blocker_index = None
            self._blocker_index_version = -1

    def bump_terrain_version(self) -> None:
        self._terrain_version += 1
        self.invalidate_cache()
        if self._use_fov:
            self._fov_map = None
            self._fov_cache.clear()

    def bump_blocker_version(self) -> None:
        self._blocker_version += 1
        self.invalidate_cache()
        self._blocker_index = None
        self._blocker_index_version = -1

    def get_visibility_entry(
        self,
        start: object,
        end: object,
    ) -> VisibilityEntry:
        a = self._normalise_coord(start)
        b = self._normalise_coord(end)
        if a == b:
            return VisibilityEntry(
                self._terrain_version,
                self._blocker_version,
                True,
                False,
                0,
                0,
                0,
                0,
                0,
                tuple(),
                tuple(),
            )

        key = (a, b) if a <= b else (b, a)
        entry = self._pair_cache.get(key)
        if (
            entry
            and entry.terrain_v == self._terrain_version
            and entry.blocker_v == self._blocker_version
        ):
            self._stats["cache_hits"] += 1
            return entry

        entry = self._recompute_visibility_entry(a, b)
        self._pair_cache[key] = entry
        return entry

    def visibility_between_entities(
        self,
        attacker_id: str,
        defender_id: str,
    ) -> Optional[VisibilityEntry]:
        start = self._get_entity_anchor(attacker_id)
        end = self._get_entity_anchor(defender_id)
        if start is None or end is None:
            return None
        return self.get_visibility_entry(start, end)

    def visibility_profile(self, start: object, end: object) -> Tuple[int, int]:
        entry = self.get_visibility_entry(start, end)
        if entry.total_rays == 0:
            return 1, 1
        return entry.total_rays, entry.clear_rays

    def has_los(self, start: object, end: object) -> bool:
        return self.get_visibility_entry(start, end).has_los

    def has_line_of_sight(
        self,
        start: GridCoord,
        end: GridCoord,
        *,
        ignore_target_blocking: bool = False,
    ) -> bool:
        if not ignore_target_blocking:
            return self.has_los(start, end)

        grid = self._get_grid()
        if not grid.in_bounds(*start) or not grid.in_bounds(*end):
            return False

        ray = list(_bresenham(start, end))
        if not ray:
            return False
        blockers = self._get_blocker_index()
        attacker_cell = ray[0]
        for x, y in ray[1:]:
            if (x, y) == end:
                continue
            if not grid.in_bounds(x, y):
                return False
            if grid.blocks_los_mask[y][x]:
                return False
            flags = TerrainFlags(grid.flags[y][x])
            if flags & self._blocking_flags:
                return False
            for occ in blockers.get((x, y), ()):  # type: ignore[arg-type]
                if occ.blocks_los and (x, y) not in (attacker_cell, end):
                    return False
        return True

    def has_los_between_entities(self, attacker_id: str, defender_id: str) -> bool:
        entry = self.visibility_between_entities(attacker_id, defender_id)
        return bool(entry and entry.has_los)

    def trace_ray(self, start: GridCoord, end: GridCoord) -> Sequence[GridCoord]:
        return list(_bresenham(start, end))

    def benchmark_visibility(self, start: GridCoord, end: GridCoord, mode: str) -> VisibilityEntry:
        prev = self.sampling_mode
        self.sampling_mode = mode
        try:
            return self._recompute_visibility_entry(start, end)
        finally:
            self.sampling_mode = prev

    # ------------------------------------------------------------------
    # Event hooks
    # ------------------------------------------------------------------
    def _on_environment_changed(self, **_: object) -> None:
        self.bump_terrain_version()

    def _on_blockers_changed(self, **_: object) -> None:
        self.bump_blocker_version()

    def _on_map_changed(self, **_: object) -> None:
        self.bump_terrain_version()
        self.bump_blocker_version()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _normalise_coord(self, value: object) -> GridCoord:
        if isinstance(value, tuple) and len(value) == 2:
            return int(value[0]), int(value[1])
        if isinstance(value, PositionComponent):
            return int(value.x), int(value.y)
        if hasattr(value, "x") and hasattr(value, "y"):
            return int(getattr(value, "x")), int(getattr(value, "y"))
        raise TypeError(f"Unsupported coordinate type: {value!r}")

    def _get_entity_anchor(self, entity_id: str) -> Optional[GridCoord]:
        components = self._ecs.get_components_for_entity(entity_id, PositionComponent)
        if not components:
            return None
        position: PositionComponent = components[0]
        return int(position.x), int(position.y)

    def _get_grid(self) -> MapGrid:
        resolution: MapResolution = self._resolver.get_active_map()
        return resolution.grid

    def _build_edge_offsets(self, granularity: int) -> List[EdgeCoord]:
        if granularity == 0:
            return [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]

        points: List[EdgeCoord] = []
        corners: Sequence[EdgeCoord] = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        for idx in range(4):
            p1 = corners[idx]
            p2 = corners[(idx + 1) % 4]
            points.append(p1)
            points.append(p2)
            for j in range(1, granularity + 1):
                factor = j / (granularity + 1)
                points.append(
                    (
                        p1[0] + factor * (p2[0] - p1[0]),
                        p1[1] + factor * (p2[1] - p1[1]),
                    )
                )
        seen: set[EdgeCoord] = set()
        unique: List[EdgeCoord] = []
        for point in points:
            if point not in seen:
                seen.add(point)
                unique.append(point)
        return unique

    def _get_blocker_index(self) -> Dict[GridCoord, List[_OccupantInfo]]:
        if self._blocker_index_version == self._blocker_version and self._blocker_index is not None:
            return self._blocker_index

        blockers: Dict[GridCoord, List[_OccupantInfo]] = {}
        for entity_id, position in self._ecs.iter_with_id(PositionComponent):
            occupant = self._make_occupant_info(entity_id)
            if occupant is None:
                continue
            for dx in range(position.width):
                for dy in range(position.height):
                    cell = (position.x + dx, position.y + dy)
                    blockers.setdefault(cell, []).append(occupant)

        self._blocker_index = blockers
        self._blocker_index_version = self._blocker_version
        return blockers

    def _make_occupant_info(self, entity_id: str) -> Optional[_OccupantInfo]:
        cover = self._ecs.get_component_for_entity(entity_id, CoverComponent)
        if cover is not None:
            return _OccupantInfo(
                entity_id=entity_id,
                blocks_los=True,
                contributes_cover=True,
                cover_bonus=int(getattr(cover, "bonus", 0)),
            )

        char_ref = self._ecs.get_component_for_entity(entity_id, CharacterRefComponent)
        if char_ref is not None:
            character = getattr(char_ref, "character", None)
            states: Iterable[str] = getattr(character, "states", []) or []
            if INVISIBLE in set(states):
                return None
            return _OccupantInfo(
                entity_id=entity_id,
                blocks_los=True,
                contributes_cover=False,
                cover_bonus=0,
            )

        return None

    def _recompute_visibility_entry(self, start: GridCoord, end: GridCoord) -> VisibilityEntry:
        self._stats["pair_recomputes"] += 1
        grid = self._get_grid()
        if not grid.in_bounds(*start) or not grid.in_bounds(*end):
            return VisibilityEntry(
                self._terrain_version,
                self._blocker_version,
                False,
                False,
                0,
                0,
                0,
                0,
                0,
                tuple(),
                tuple(),
            )

        line = list(_bresenham(start, end))
        if len(line) <= 2:
            self._stats["fastpath_skips"] += 1
            return VisibilityEntry(
                self._terrain_version,
                self._blocker_version,
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

        blockers = self._get_blocker_index()
        walls_present = False
        clear_between = False
        cover_ids: List[str] = []
        seen_cover: set[str] = set()
        cover_sum = 0
        intervening: List[GridCoord] = []

        for cell in line[1:-1]:
            x, y = cell
            intervening.append(cell)
            if 0 <= y < grid.height and 0 <= x < grid.width and grid.blocks_los_mask[y][x]:
                walls_present = True
            else:
                clear_between = True

            for occ in blockers.get(cell, ()):  # type: ignore[arg-type]
                if occ.contributes_cover and occ.entity_id not in seen_cover:
                    seen_cover.add(occ.entity_id)
                    cover_ids.append(occ.entity_id)
                    cover_sum += occ.cover_bonus

        if self._use_fov and not walls_present:
            mask = self._get_fov_for_origin(start)
            if mask is not None:
                try:
                    if not mask[end[1], end[0]]:
                        total_cover = cover_sum
                        return VisibilityEntry(
                            self._terrain_version,
                            self._blocker_version,
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
                except Exception:
                    pass

        if walls_present and not clear_between:
            self._stats["fastpath_skips"] += 1
            total_cover = cover_sum
            return VisibilityEntry(
                self._terrain_version,
                self._blocker_version,
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

        if partial_wall_candidate:
            start_offsets = list(self._get_los_points(start))
            end_offsets = list(self._get_los_points(end))
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
                self._stats["rays_cast_total"] += total_rays
            else:
                attacker_corners = self._corner_subset(start_offsets, start)
                defender_corners = self._corner_subset(end_offsets, end)
                seen_blocked = False
                seen_clear = False
                for sp in attacker_corners:
                    for ep in defender_corners:
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
                    wall_bonus = 2
                    has_los = True
                elif seen_clear and not seen_blocked:
                    for sp in start_offsets:
                        if seen_blocked:
                            break
                        for ep in end_offsets:
                            if sp in attacker_corners and ep in defender_corners:
                                continue
                            total_rays += 1
                            if self._is_ray_clear(sp, ep):
                                clear_rays += 1
                            else:
                                seen_blocked = True
                                break
                    if seen_blocked:
                        wall_bonus = 2
                        has_los = True
                    else:
                        wall_bonus = 0
                        has_los = True
                        partial_wall_candidate = False
                elif seen_blocked and not seen_clear:
                    for sp in start_offsets:
                        if seen_clear:
                            break
                        for ep in end_offsets:
                            if sp in attacker_corners and ep in defender_corners:
                                continue
                            total_rays += 1
                            if self._is_ray_clear(sp, ep):
                                clear_rays += 1
                                seen_clear = True
                                break
                    if seen_clear:
                        wall_bonus = 2
                        has_los = True
                    else:
                        has_los = False
                        partial_wall_candidate = False
                else:
                    has_los = True
                    partial_wall_candidate = False
                self._stats["rays_cast_total"] += total_rays

        if not partial_wall_candidate:
            self._stats["fastpath_skips"] += 1

        partial_wall = partial_wall_candidate and has_los
        if partial_wall_candidate and not has_los:
            has_los = True
            partial_wall = True
            wall_bonus = 2
        if not partial_wall:
            wall_bonus = 0

        total_cover = cover_sum + wall_bonus
        return VisibilityEntry(
            self._terrain_version,
            self._blocker_version,
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

    def _corner_subset(self, points: Sequence[EdgeCoord], origin: GridCoord) -> List[EdgeCoord]:
        ox, oy = origin
        corners = {(ox, oy), (ox + 1, oy), (ox + 1, oy + 1), (ox, oy + 1)}
        subset = [p for p in points if (int(p[0]), int(p[1])) in corners]
        if subset:
            return subset
        return list(points[:4])

    def _get_los_points(self, pos: GridCoord) -> set[EdgeCoord]:
        x, y = pos
        return {(x + dx, y + dy) for dx, dy in self._edge_offsets}

    def _is_ray_clear(self, start_coord: EdgeCoord, end_coord: EdgeCoord) -> bool:
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
        grid = self._get_grid()
        blockers = self._get_blocker_index()

        while True:
            if (ix1, iy1) not in (attacker_cell, target_cell):
                if not grid.in_bounds(ix1, iy1):
                    return False
                if grid.blocks_los_mask[iy1][ix1]:
                    return False
                flags = TerrainFlags(grid.flags[iy1][ix1])
                if flags & self._blocking_flags:
                    return False
                for occ in blockers.get((ix1, iy1), ()):  # type: ignore[arg-type]
                    if occ.blocks_los:
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

    def _get_fov_for_origin(self, origin: GridCoord) -> Optional[np.ndarray]:
        if not self._use_fov:
            return None

        grid = self._get_grid()
        width = int(getattr(grid, "width", 0))
        height = int(getattr(grid, "height", 0))
        if width <= 0 or height <= 0:
            return None

        if self._fov_map is None:
            self._fov_map = self._build_fov_map(grid)
            self._fov_cache.clear()
            if self._fov_map is None:
                return None

        cached = self._fov_cache.get(origin)
        if cached is not None:
            return cached

        try:
            mask = tcod.map.compute_fov(
                self._fov_map, (origin[1], origin[0]), 0, True, FOV_PERMISSIVE_8
            )  # type: ignore[arg-type]
        except Exception:
            mask = None
        self._fov_cache[origin] = mask
        return mask

    def _build_fov_map(self, grid: MapGrid) -> Optional[np.ndarray]:
        try:
            width = int(grid.width)
            height = int(grid.height)
        except Exception:
            return None

        transparency = np.ones((height, width), dtype=bool)
        for y in range(height):
            for x in range(width):
                if grid.blocks_los_mask[y][x]:
                    transparency[y, x] = False
        return transparency


__all__ = [
    "LineOfSightSystem",
    "VisibilityEntry",
    "EVT_ENTITY_MOVED",
    "EVT_WALL_ADDED",
    "EVT_WALL_REMOVED",
    "EVT_COVER_DESTROYED",
    "EVT_VISIBILITY_STATE_CHANGED",
]
