"""Helper functions to create and query ECS-backed entities in tests."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ecs.components.movement_usage import MovementUsageComponent
from ecs.components.position import PositionComponent


def add_entity_with_position(
    game_state: Any,
    entity_id: str,
    *,
    position: Optional[PositionComponent] = None,
    terrain: Optional[Any] = None,
    extra_components: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Add an entity with a :class:`PositionComponent` to the game state and ECS."""

    pos_component = position or PositionComponent(0, 0)
    components: Dict[str, Any] = {"position": pos_component}
    if extra_components:
        components.update(extra_components)
    game_state.add_entity(entity_id, components)
    terrain_ref = terrain if terrain is not None else getattr(game_state, "terrain", None)
    if terrain_ref is not None and hasattr(terrain_ref, "add_entity"):
        result = terrain_ref.add_entity(entity_id, pos_component.x, pos_component.y)
        if result is False:
            raise AssertionError(
                "Failed to add entity to terrain during test setup"
            )
    return components


def get_movement_usage_distance(ecs_manager: Any, entity_id: str) -> int:
    """Return the tracked movement distance for ``entity_id`` via ECS components."""

    if ecs_manager is None:
        return 0
    internal_id = ecs_manager.resolve_entity(entity_id)
    if internal_id is None:
        return 0
    component = ecs_manager.try_get_component(internal_id, MovementUsageComponent)
    if component is None:
        return 0
    return int(getattr(component, "distance", 0))


__all__ = ["add_entity_with_position", "get_movement_usage_distance"]

