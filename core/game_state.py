"""Compatibility shim for the deprecated :mod:`core.game_state` module."""

from __future__ import annotations

import functools
import warnings
from typing import Any, Callable, Dict, Optional

from utils.logger import get_migration_logger

from ._legacy_game_state import GameState as _LegacyGameState
from ._legacy_game_state import LEGACY_CONDITION_VALUE_TYPES

__all__ = ["GameState", "LEGACY_CONDITION_VALUE_TYPES"]

_MIGRATION_LOGGER = get_migration_logger()
_DEPRECATION_PREFIX = "core.game_state"
_SEEN_MESSAGES: set[str] = set()


def _emit_deprecation(api_name: str, replacement: Optional[str] = None, *, stacklevel: int = 3) -> None:
    message = f"`{_DEPRECATION_PREFIX}.{api_name}` is deprecated."
    if replacement:
        message = f"{message} Use {replacement} instead."
    warnings.warn(message, DeprecationWarning, stacklevel=stacklevel)
    if message not in _SEEN_MESSAGES:
        _MIGRATION_LOGGER.warning(message)
        _SEEN_MESSAGES.add(message)


_emit_deprecation("import", "ecs.ecs_manager.ECSManager")


def _wrap_callable(name: str, func: Callable[..., Any], replacement: Optional[str]) -> Callable[..., Any]:
    @functools.wraps(func)
    def wrapper(self: "GameState", *args: Any, **kwargs: Any) -> Any:
        _emit_deprecation(f"GameState.{name}", replacement)
        return func(self, *args, **kwargs)

    return wrapper


def _wrap_property(name: str, prop: property, replacement: Optional[str]) -> property:
    def _getter(self: "GameState") -> Any:
        if prop.fget is None:
            raise AttributeError(name)
        _emit_deprecation(f"GameState.{name}", replacement)
        return prop.fget(self)

    def _setter(self: "GameState", value: Any) -> None:
        if prop.fset is None:
            raise AttributeError(name)
        _emit_deprecation(f"GameState.{name}", replacement)
        prop.fset(self, value)

    def _deleter(self: "GameState") -> None:
        if prop.fdel is None:
            raise AttributeError(name)
        _emit_deprecation(f"GameState.{name}", replacement)
        prop.fdel(self)

    return property(_getter if prop.fget else None, _setter if prop.fset else None, _deleter if prop.fdel else None, prop.__doc__)


class GameState(_LegacyGameState):
    """Shim layer emitting deprecation warnings while delegating to the legacy implementation."""

    _REPLACEMENTS: Dict[str, Optional[str]] = {
        "__init__": "ecs.ecs_manager.ECSManager",
        "add_entity": "PreparationManager / ecs.ECSManager",
        "remove_entity": "ecs.ECSManager.delete_entity",
        "get_component": "ecs.ECSManager.get_component_for_entity",
        "set_component": "ecs.ECSManager.add_component",
        "get_entity": "ecs.ECSManager.get_components_for_entity",
        "update_teams": "ecs.ECSManager.collect_team_rosters",
        "kill_entity": "ecs.ECSManager.delete_entity",
        "is_tile_occupied": "Terrain occupancy helpers",
        "reset_movement_usage": "MovementUsageComponent management",
        "add_movement_steps": "MovementUsageComponent management",
        "get_movement_used": "MovementUsageComponent management",
        "event_bus": "ecs.ECSManager.event_bus",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _emit_deprecation("GameState.__init__", self._REPLACEMENTS.get("__init__"), stacklevel=4)
        super().__init__(*args, **kwargs)


for _name, _value in list(vars(_LegacyGameState).items()):
    if _name.startswith("_") or _name == "__init__":
        continue
    replacement = GameState._REPLACEMENTS.get(_name)
    if isinstance(_value, property):
        setattr(GameState, _name, _wrap_property(_name, _value, replacement))
    elif callable(_value):
        setattr(GameState, _name, _wrap_callable(_name, _value, replacement))


del _name, _value
