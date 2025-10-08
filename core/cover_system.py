"""Deprecated adapter exposing the legacy cover API."""
from __future__ import annotations

import warnings
from typing import Any

from modules.cover.system import CoverSystem as _CoverSystem

__all__ = ["CoverSystem"]

_DEPRECATION_MESSAGE = (
    "`core.cover_system.CoverSystem` is deprecated; use `modules.cover.system.CoverSystem` instead."
)


class CoverSystem(_CoverSystem):
    """Compatibility shim delegating to :class:`modules.cover.system.CoverSystem`."""

    def __init__(self, game_state: Any) -> None:
        warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
        ecs_manager = getattr(game_state, "ecs_manager", None)
        event_bus = getattr(game_state, "event_bus", None)
        los_system = getattr(game_state, "los_manager", None)
        terrain = getattr(game_state, "terrain", None)
        super().__init__(
            ecs_manager,
            event_bus=event_bus,
            los_system=los_system,
            terrain=terrain,
            game_state=game_state,
        )
