"""Deprecated adapter bridging legacy imports to the new LOS system."""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

from modules.los.system import (
    EVT_COVER_DESTROYED,
    EVT_ENTITY_MOVED,
    EVT_VISIBILITY_STATE_CHANGED,
    EVT_WALL_ADDED,
    EVT_WALL_REMOVED,
    LineOfSightSystem as _LineOfSightSystem,
    VisibilityEntry,
)
from modules.maps.components import MapGrid
from modules.maps.resolver import MapResolution
from modules.maps.terrain_types import TerrainFlags
from utils.condition_utils import (
    INVISIBLE,
    NIGHT_VISION_PARTIAL,
    NIGHT_VISION_TOTAL,
    SEE_INVISIBLE,
)

from core.terrain_manager import EFFECT_DARK_LOW, EFFECT_DARK_TOTAL

_DEPRECATION_MESSAGE = (
    "`core.los_manager.LineOfSightManager` is deprecated. "
    "Use `modules.los.system.LineOfSightSystem` instead."
)


@dataclass
class _LegacyMapResolution:
    entity_id: str
    grid: MapGrid


class _LegacyTerrainResolver:
    """Adapts :class:`core.terrain_manager.Terrain` into a map resolver API."""

    def __init__(self, terrain: Any) -> None:
        self._terrain = terrain

    def get_active_map(self) -> MapResolution:
        grid = self._build_grid()
        return _LegacyMapResolution(entity_id="legacy_terrain", grid=grid)  # type: ignore[return-value]

    def invalidate(self) -> None:  # pragma: no cover - API parity hook
        """Provided for compatibility with :class:`ActiveMapResolver`."""

    def _build_grid(self) -> MapGrid:
        terrain = self._terrain
        raw_walls: Iterable[Tuple[int, int]] = getattr(terrain, "walls", []) or []
        walls = list(raw_walls)

        def _coerce(value: Any, fallback: int) -> int:
            if isinstance(value, (int, float)):
                coerced = int(value)
                return coerced if coerced > 0 else fallback
            if isinstance(value, str):
                try:
                    coerced = int(value)
                except ValueError:
                    return fallback
                return coerced if coerced > 0 else fallback
            return fallback

        inferred_width = max((x for x, _ in walls), default=0) + 5
        inferred_height = max((y for _, y in walls), default=0) + 5

        width = _coerce(getattr(terrain, "width", None), max(inferred_width, 32))
        height = _coerce(getattr(terrain, "height", None), max(inferred_height, 32))
        cell_size = _coerce(getattr(terrain, "cell_size", None), 1)
        flags = [[0 for _ in range(width)] for _ in range(height)]
        blocks_los = [[False for _ in range(width)] for _ in range(height)]

        for x, y in walls:
            if 0 <= x < width and 0 <= y < height:
                blocks_los[y][x] = True
                flags[y][x] = int(
                    TerrainFlags.BLOCKS_LOS | TerrainFlags.WALL | TerrainFlags.IMPASSABLE
                )

        return MapGrid(width, height, cell_size, flags=flags, blocks_los_mask=blocks_los)


class LineOfSightManager:
    """Compatibility wrapper exposing the legacy LOS API."""

    def __init__(
        self,
        game_state: Any,
        terrain_manager: Any,
        event_bus: Any,
        los_granularity: int = 10,
        sampling_mode: str = "sparse",
    ) -> None:
        warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
        self.game_state = game_state
        self.terrain = terrain_manager
        self.event_bus = event_bus
        self.los_granularity = los_granularity
        self._resolver = _LegacyTerrainResolver(terrain_manager)

        ecs_manager = getattr(game_state, "ecs_manager", None)
        if ecs_manager is None and hasattr(game_state, "_ensure_ecs_manager"):
            ecs_manager = game_state._ensure_ecs_manager()
        if ecs_manager is None:
            raise ValueError("LineOfSightManager requires an ECS manager on the game state")

        self._system = _LineOfSightSystem(
            ecs_manager,
            event_bus=event_bus,
            map_resolver=self._resolver,
            los_granularity=los_granularity,
            sampling_mode=sampling_mode,
            use_fov=False,
        )

    # ------------------------------------------------------------------
    # Properties to mirror legacy attributes
    # ------------------------------------------------------------------
    @property
    def sampling_mode(self) -> str:
        return self._system.sampling_mode

    @sampling_mode.setter
    def sampling_mode(self, value: str) -> None:
        self._system.sampling_mode = value

    @property
    def _pair_cache(self) -> Dict[Tuple[Tuple[int, int], Tuple[int, int]], VisibilityEntry]:
        return self._system._pair_cache  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Legacy-facing helpers
    # ------------------------------------------------------------------
    def _sync_versions(self) -> None:
        terrain_v = getattr(self.game_state, "terrain_version", None)
        blocker_v = getattr(self.game_state, "blocker_version", None)
        self._system.set_version_counters(
            terrain_version=terrain_v,
            blocker_version=blocker_v,
        )

    def invalidate_cache(self, **_: Any) -> None:
        self._system.invalidate_cache()

    def reset_stats(self) -> None:
        self._system.reset_stats()

    def get_stats(self) -> Dict[str, int]:
        return self._system.get_stats()

    def set_sampling_mode(self, mode: str) -> str:
        result = self._system.set_sampling_mode(mode)
        self.sampling_mode = result
        return result

    def get_visibility_entry(self, start: Any, end: Any) -> VisibilityEntry:
        self._sync_versions()
        return self._system.get_visibility_entry(start, end)

    def benchmark_visibility(self, start: Tuple[int, int], end: Tuple[int, int], mode: str) -> VisibilityEntry:
        self._sync_versions()
        return self._system.benchmark_visibility(start, end, mode)

    def has_los(self, start: Any, end: Any) -> bool:
        return self.get_visibility_entry(start, end).has_los

    def has_line_of_sight(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        *,
        ignore_target_blocking: bool = False,
    ) -> bool:
        self._sync_versions()
        return self._system.has_line_of_sight(start, end, ignore_target_blocking=ignore_target_blocking)

    def trace_ray(self, start: Tuple[int, int], end: Tuple[int, int]) -> Tuple[Tuple[int, int], ...]:
        return tuple(self._system.trace_ray(start, end))

    def visibility_profile(self, start: Any, end: Any) -> Tuple[int, int]:
        return self._system.visibility_profile(start, end)

    def _get_los_points(self, pos: Tuple[int, int]) -> set[Tuple[float, float]]:
        return self._system._get_los_points(pos)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Legacy behaviour helpers relying on the legacy terrain/conditions
    # ------------------------------------------------------------------
    def can_see(self, attacker_id: str, defender_id: str) -> bool:
        attacker = self.game_state.get_entity(attacker_id)
        defender = self.game_state.get_entity(defender_id)
        if not attacker or not defender:
            return False
        apos = attacker.get("position")
        dpos = defender.get("position")
        if not apos or not dpos:
            return False

        att_states = self._extract_states(attacker)
        def_states = self._extract_states(defender)

        if hasattr(self.terrain, "has_effect"):
            attacker_dark_total = self.terrain.has_effect(apos.x, apos.y, EFFECT_DARK_TOTAL)
            defender_dark_total = self.terrain.has_effect(dpos.x, dpos.y, EFFECT_DARK_TOTAL)
            if attacker_dark_total and NIGHT_VISION_TOTAL not in att_states:
                return False
            if defender_dark_total and NIGHT_VISION_TOTAL not in att_states:
                return False

        if not self.has_los((apos.x, apos.y), (dpos.x, dpos.y)):
            return False

        if INVISIBLE in def_states and SEE_INVISIBLE not in att_states:
            return False
        return True

    def get_darkness_attack_modifier(self, attacker_id: str, defender_id: str) -> int:
        vision_system = getattr(self.game_state, "vision_system", None)
        if vision_system and hasattr(vision_system, "get_attack_modifier"):
            try:
                return int(vision_system.get_attack_modifier(attacker_id, defender_id)) or 0
            except Exception:
                pass

        terrain = getattr(self.game_state, "terrain", None)
        if not terrain or not hasattr(terrain, "has_effect"):
            return 0
        attacker = self.game_state.get_entity(attacker_id)
        defender = self.game_state.get_entity(defender_id)
        if not attacker or not defender:
            return 0
        dpos = defender.get("position")
        if not dpos:
            return 0
        att_states = self._extract_states(attacker)
        if terrain.has_effect(dpos.x, dpos.y, EFFECT_DARK_TOTAL):
            return 0
        if terrain.has_effect(dpos.x, dpos.y, EFFECT_DARK_LOW):
            if NIGHT_VISION_PARTIAL in att_states or NIGHT_VISION_TOTAL in att_states:
                return 0
            return -1
        return 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _extract_states(self, entity: Dict[str, Any]) -> set:
        states: Iterable[str] = set()
        char_ref = entity.get("character_ref")
        if char_ref is not None:
            character = getattr(char_ref, "character", None)
            states = getattr(character, "states", set()) or set()
        return set(states)


__all__ = [
    "LineOfSightManager",
    "VisibilityEntry",
    "EVT_WALL_ADDED",
    "EVT_WALL_REMOVED",
    "EVT_ENTITY_MOVED",
    "EVT_COVER_DESTROYED",
    "EVT_VISIBILITY_STATE_CHANGED",
]
