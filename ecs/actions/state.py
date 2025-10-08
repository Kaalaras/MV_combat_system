"""Helpers to query ECS-backed action state."""

from __future__ import annotations

from typing import Any, Optional, Type, TypeVar

from ecs.components.action_budget import ActionBudgetComponent
from ecs.components.movement_usage import MovementUsageComponent
from ecs.components.resource_pool import ResourcePoolComponent

T = TypeVar("T")

MOVEMENT_RESOURCE = "movement_points"


def _safe_int(value: Any) -> int:
    """Best-effort conversion to ``int`` that defaults to zero on failure."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _resolve_internal_id(ecs: Any, entity_id: str) -> Optional[int]:
    """Best-effort resolution of ``entity_id`` to an internal ECS id."""

    if ecs is None:
        return None

    resolver = getattr(ecs, "resolve_entity", None)
    if callable(resolver):
        internal_id = resolver(entity_id)
        if internal_id is not None:
            return internal_id

    # Fallback to a public mapping commonly exposed by tests/stubs.
    entities = getattr(ecs, "entities", None)
    if isinstance(entities, dict):
        internal_id = entities.get(entity_id)
        if isinstance(internal_id, int):
            return internal_id

    private = getattr(ecs, "_entities", None)
    if isinstance(private, dict):
        internal_id = private.get(entity_id)
        if isinstance(internal_id, int):
            return internal_id

    return None


def _try_get_component(ecs: Any, internal_id: int, component_type: Type[T]) -> Optional[T]:
    """Return ``component_type`` instance for ``internal_id`` if present."""

    if ecs is None:
        return None

    getter = getattr(ecs, "try_get_component", None)
    if callable(getter):
        return getter(internal_id, component_type)  # type: ignore[return-value]

    alt_getter = getattr(ecs, "get_component", None)
    if callable(alt_getter):
        try:
            component = alt_getter(internal_id, component_type)
        except KeyError:
            return None
        else:
            if isinstance(component, component_type):
                return component
    return None


def get_resource_pool(ecs: Any, entity_id: str) -> Optional[ResourcePoolComponent]:
    """Fetch the :class:`ResourcePoolComponent` for ``entity_id`` if available."""

    internal_id = _resolve_internal_id(ecs, entity_id)
    if internal_id is None:
        return None
    return _try_get_component(ecs, internal_id, ResourcePoolComponent)


def get_action_budget(ecs: Any, entity_id: str) -> Optional[ActionBudgetComponent]:
    """Fetch the :class:`ActionBudgetComponent` for ``entity_id`` if available."""

    internal_id = _resolve_internal_id(ecs, entity_id)
    if internal_id is None:
        return None
    return _try_get_component(ecs, internal_id, ActionBudgetComponent)


def get_movement_usage(ecs: Any, entity_id: str) -> Optional[MovementUsageComponent]:
    """Fetch the :class:`MovementUsageComponent` for ``entity_id`` if available."""

    internal_id = _resolve_internal_id(ecs, entity_id)
    if internal_id is None:
        return None
    return _try_get_component(ecs, internal_id, MovementUsageComponent)


def get_available_resource(
    entity_id: str,
    resource: str,
    ecs: Any,
    *,
    include_pending: bool = True,
) -> Optional[int]:
    """Return currently available ``resource`` for ``entity_id`` from ECS components."""

    resource = str(resource)
    pool = get_resource_pool(ecs, entity_id)
    available: Optional[int]
    if pool is not None:
        pooled_value = pool.get(resource, default=0)
        available = _safe_int(pooled_value)
    else:
        available = None

    if available is not None and resource == MOVEMENT_RESOURCE:
        usage = get_movement_usage(ecs, entity_id)
        if usage is not None:
            distance = getattr(usage, "distance", 0)
            used = _safe_int(distance)
            available = available - used

    if available is not None and include_pending:
        budget = get_action_budget(ecs, entity_id)
        if budget is not None:
            reserved = _safe_int(budget.reserved.get(resource, 0))
            pending = _safe_int(budget.pending.get(resource, 0))
            to_subtract = reserved + pending
            if to_subtract:
                available = available - to_subtract

    if available is None:
        return None

    return max(_safe_int(available), 0)


__all__ = [
    "get_available_resource",
    "get_action_budget",
    "get_movement_usage",
    "get_resource_pool",
]
