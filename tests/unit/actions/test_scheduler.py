from __future__ import annotations

from core.actions.intent import ActionIntent, TargetSpec
from core.actions.scheduler import ActionScheduler
from core.events import topics
from ecs.components.action_budget import ActionBudgetComponent

from tests.unit.test_utils import DummyEventBus, StubECS


def test_scheduler_reserves_and_dispatches() -> None:
    ecs = StubECS({"hero": 1})
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

