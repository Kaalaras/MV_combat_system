from __future__ import annotations

from typing import Any

from core.actions.intent import ActionIntent, TargetSpec
from core.actions.performers import ActionPerformer
from core.events import topics

from tests.unit.test_utils import DummyEventBus


class StubMovementSystem:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[int, int]]] = []

    def move(self, actor_id: str, dest: tuple[int, int], max_steps: int | None = None) -> bool:
        self.calls.append((actor_id, dest))
        return True


class StubRules:
    def __init__(self) -> None:
        self.movement_system = StubMovementSystem()

    def resolve_attack(self, actor_id: str, target_id: str, **_: Any) -> dict[str, Any]:
        return {"hit": True, "damage": 2, "target": target_id}


def test_performer_executes_move_action() -> None:
    rules = StubRules()
    performer = ActionPerformer(rules)
    bus = DummyEventBus()
    performer.bind(bus)

    intent = ActionIntent(
        actor_id="hero",
        action_id="move",
        targets=(TargetSpec.tile((2, 3)),),
    )

    bus.publish(topics.PERFORM_ACTION, intent=intent.to_dict(), intent_obj=intent, await_reactions=False)

    events = [topic for topic, _ in bus.published]
    assert topics.ACTION_RESOLVED in events
    assert rules.movement_system.calls == [("hero", (2, 3))]


def test_performer_waits_for_reactions() -> None:
    rules = StubRules()
    performer = ActionPerformer(rules)
    bus = DummyEventBus()
    performer.bind(bus)

    intent = ActionIntent(
        actor_id="hero",
        action_id="attack_melee",
        targets=(TargetSpec.entity("ghoul"),),
    )

    bus.publish(
        topics.PERFORM_ACTION,
        intent=intent.to_dict(),
        intent_obj=intent,
        await_reactions=True,
        reactions_resolved=False,
    )

    assert all(topic != topics.ACTION_RESOLVED for topic, _ in bus.published)

