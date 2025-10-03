from __future__ import annotations

from typing import Any, Callable

import pytest

from core.actions.intent import ActionIntent, TargetSpec
from core.actions.validation import IntentValidator, validate_intent
from core.events import topics


class StubECS:
    def __init__(self) -> None:
        self._entities = {"hero": 1, "ghoul": 2}

    def resolve_entity(self, entity_id: str) -> int | None:
        return self._entities.get(entity_id)


class StubRules:
    def get_movement_points(self, actor_id: str) -> int:
        return 4

    def get_action_points(self, actor_id: str) -> int:
        return 2

    def validate_targets(self, intent: ActionIntent, action_def: Any, **_: Any):
        return True


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


def test_validate_intent_success() -> None:
    ecs = StubECS()
    rules = StubRules()
    intent = ActionIntent(
        actor_id="hero",
        action_id="move",
        targets=(TargetSpec.tile((1, 2)),),
    )

    ok, reason, normalised = validate_intent(intent, ecs, rules)

    assert ok is True
    assert reason is None
    assert normalised == intent


def test_validate_intent_rejects_insufficient_resources() -> None:
    ecs = StubECS()

    class NoPoints(StubRules):
        def get_action_points(self, actor_id: str) -> int:
            return 0

    rules = NoPoints()
    intent = ActionIntent(
        actor_id="hero",
        action_id="attack_melee",
        targets=(TargetSpec.entity("ghoul"),),
    )

    ok, reason, _ = validate_intent(intent, ecs, rules)

    assert ok is False
    assert reason == "insufficient_action_points"


def test_validate_intent_rejects_bad_target_kind() -> None:
    ecs = StubECS()
    rules = StubRules()
    intent = ActionIntent(
        actor_id="hero",
        action_id="attack_melee",
        targets=(TargetSpec.tile((0, 0)),),
    )

    ok, reason, _ = validate_intent(intent, ecs, rules)

    assert ok is False
    assert reason == "invalid_target_kind"


def test_intent_validator_publishes_events() -> None:
    ecs = StubECS()
    rules = StubRules()
    validator = IntentValidator(ecs, rules)
    bus = DummyEventBus()
    validator.bind(bus)

    intent = ActionIntent(
        actor_id="hero",
        action_id="move",
        targets=(TargetSpec.tile((3, 4)),),
    )

    bus.publish(topics.INTENT_SUBMITTED, intent=intent.to_dict())

    events = [topic for topic, _ in bus.published]
    assert topics.INTENT_VALIDATED in events

