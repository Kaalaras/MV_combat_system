from __future__ import annotations

from typing import Any, Callable, Iterable


class DummyEventBus:
    """Minimal in-memory event bus used across unit tests."""

    def __init__(self) -> None:
        self.subscriptions: dict[str, list[Callable[..., None]]] = {}
        self.published: list[tuple[str, dict[str, Any]]] = []

    def subscribe(self, topic: str, handler: Callable[..., None]) -> None:
        self.subscriptions.setdefault(topic, []).append(handler)

    def publish(self, topic: str, /, **payload: Any) -> None:
        self.published.append((topic, dict(payload)))
        for handler in list(self.subscriptions.get(topic, [])):
            handler(**payload)


class StubECS:
    """Simple ECS stub that stores entities and components in dictionaries."""

    def __init__(self, entities: dict[str, int] | None = None) -> None:
        self._entities = dict(entities or {})
        self._components: dict[int, dict[type, Any]] = {}

    def add_entity(self, public_id: str, internal_id: int) -> None:
        self._entities[public_id] = internal_id

    def resolve_entity(self, entity_id: str) -> int | None:
        return self._entities.get(entity_id)

    def try_get_component(self, internal_id: int, component_type: type) -> Any | None:
        return self._components.get(internal_id, {}).get(component_type)

    def add_component(self, internal_id: int, component: Any) -> None:
        self._components.setdefault(internal_id, {})[type(component)] = component


class StubRules:
    """Default rule helpers shared by validation-related tests."""

    def __init__(self, action_points: int = 2, movement_points: int = 4) -> None:
        self._action_points = action_points
        self._movement_points = movement_points

    def get_movement_points(self, actor_id: str) -> int:
        return self._movement_points

    def get_action_points(self, actor_id: str) -> int:
        return self._action_points

    def validate_targets(self, intent: Any, action_def: Any, **_: Any) -> bool:
        return True

    def get_blocked_actions(self, actor_id: str) -> Iterable[str] | None:  # pragma: no cover - optional override
        return None


__all__ = ["DummyEventBus", "StubECS", "StubRules"]
