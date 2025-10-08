"""Deprecated adapter exposing the legacy ``core.los_manager`` API."""
from __future__ import annotations

import warnings
from typing import Any

from modules.los.system import (
    LineOfSightSystem as _LineOfSightSystem,
    VisibilityEntry,
    EVT_COVER_DESTROYED,
    EVT_ENTITY_MOVED,
    EVT_VISIBILITY_CHANGED,
    EVT_WALL_ADDED,
    EVT_WALL_REMOVED,
)

__all__ = [
    "LineOfSightManager",
    "VisibilityEntry",
    "EVT_WALL_ADDED",
    "EVT_WALL_REMOVED",
    "EVT_ENTITY_MOVED",
    "EVT_COVER_DESTROYED",
]

_DEPRECATION_MESSAGE = (
    "`core.los_manager.LineOfSightManager` is deprecated; use "
    "`modules.los.system.LineOfSightSystem` instead."
)


class LineOfSightManager(_LineOfSightSystem):
    """Compatibility shim delegating to :class:`modules.los.system.LineOfSightSystem`."""

    def __init__(
        self,
        game_state: Any,
        terrain_manager: Any,
        event_bus: Any,
        los_granularity: int = 10,
        sampling_mode: str = "sparse",
    ) -> None:
        warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
        ecs_manager = getattr(game_state, "ecs_manager", None)
        super().__init__(
            ecs_manager,
            event_bus=event_bus,
            map_resolver=None,
            los_granularity=los_granularity,
            sampling_mode=sampling_mode,
            terrain=terrain_manager,
            game_state=game_state,
        )

    # Retain explicit re-export of deprecated event constant for backwards compatibility.
    EVT_WALL_ADDED = EVT_WALL_ADDED
    EVT_WALL_REMOVED = EVT_WALL_REMOVED
    EVT_ENTITY_MOVED = EVT_ENTITY_MOVED
    EVT_COVER_DESTROYED = EVT_COVER_DESTROYED
    EVT_VISIBILITY_CHANGED = EVT_VISIBILITY_CHANGED
