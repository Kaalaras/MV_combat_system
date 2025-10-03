from __future__ import annotations

from typing import Any, Callable

from core.actions.intent import ActionIntent, TargetSpec
from core.actions.scheduler import ActionScheduler
from core.events import topics
from ecs.components.action_budget import ActionBudgetComponent


class DummyEventBus:
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
    def __init__(self) -> None:
        self._entities = {"hero": 1}
        self._components: dict[int, dict[type, Any]] = {}

    def resolve_entity(self, entity_id: str) -> int | None:
        return self._entities.get(entity_id)

    def try_get_component(self, internal_id: int, component_type: type) -> Any | None:
        return self._components.get(internal_id, {}).get(component_type)

    def add_component(self, internal_id: int, component: Any) -> None:
        self._components.setdefault(internal_id, {})[type(component)] = component


def test_scheduler_reserves_and_dispatches() -> None:
    ecs = StubECS()
    bus = DummyEventBus()
    scheduler = ActionScheduler(ecs)
    scheduler.bind(bus)

    intent = ActionIntent(
        actor_id="hero",
        action_id="attack_melee",
        targets=(TargetSpec.entity("ghoul"),),
    )

    bus.publish(topics.INTENT_VALIDATED, intent=intent.to_dict(), intent_obj=intent)

    events = [topic for topic, _ in bus.published]
    assert topics.ACTION_ENQUEUED in events
    assert events.count(topics.PERFORM_ACTION) == 1

    internal_id = ecs.resolve_entity("hero")
    assert internal_id is not None
    component = ecs.try_get_component(internal_id, ActionBudgetComponent)
    assert isinstance(component, ActionBudgetComponent)
    assert component.pending.get("action_points") == 1

