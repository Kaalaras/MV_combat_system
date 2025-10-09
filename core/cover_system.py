"""Deprecated adapter delegating to :mod:`modules.cover.system`."""
from __future__ import annotations

import warnings
from typing import Any, Optional, Sequence, Tuple

from modules.cover.system import CoverSystem as _CoverSystem, DEFAULT_NO_COVER_BONUS

_DEPRECATION_MESSAGE = (
    "`core.cover_system.CoverSystem` is deprecated. "
    "Use `modules.cover.system.CoverSystem` instead."
)


class CoverSystem:
    """Compatibility wrapper around :class:`modules.cover.system.CoverSystem`."""

    def __init__(
        self,
        game_state: Any,
        *,
        default_no_cover_bonus: int = DEFAULT_NO_COVER_BONUS,
    ) -> None:
        warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
        ecs_manager = getattr(game_state, "ecs_manager", None)
        if ecs_manager is None and hasattr(game_state, "_ensure_ecs_manager"):
            ecs_manager = game_state._ensure_ecs_manager()
        if ecs_manager is None:
            raise ValueError("CoverSystem requires an ECS manager on the game state")

        event_bus = getattr(game_state, "event_bus", None)
        los_manager = getattr(game_state, "los_manager", None)
        los_system = getattr(los_manager, "_system", None)
        map_resolver = getattr(los_manager, "_resolver", None)

        self._system = _CoverSystem(
            ecs_manager,
            event_bus=event_bus,
            map_resolver=map_resolver,
            los_system=los_system,
            default_no_cover_bonus=default_no_cover_bonus,
        )
        self.game_state = game_state

    def compute_ranged_cover_bonus(self, attacker_id: str, defender_id: str) -> int:
        return self._system.compute_ranged_cover_bonus(attacker_id, defender_id)

    def tile_cover_bonus(self, x: int, y: int, *, default: Optional[int] = None) -> int:
        return self._system.tile_cover_bonus(x, y, default=default)

    def cover_bonus(
        self,
        target: Tuple[int, int],
        *,
        edge_offsets: Optional[Sequence[Tuple[int, int]]] = None,
        default: Optional[int] = None,
    ) -> int:
        return self._system.cover_bonus(target, edge_offsets=edge_offsets, default=default)


__all__ = ["CoverSystem", "DEFAULT_NO_COVER_BONUS"]
