from __future__ import annotations
from core.actions.intent import ActionIntent, TargetSpec
from core.actions.validation import IntentValidator, validate_intent
from core.events import topics

from tests.unit.test_utils import DummyEventBus, StubECS, StubRules

from core.actions.validation import _normalize_blocked_actions


ENTITIES = {"hero": 1, "ghoul": 2}


def test_validate_intent_success() -> None:
    ecs = StubECS(ENTITIES)
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
    ecs = StubECS(ENTITIES)

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
    ecs = StubECS(ENTITIES)
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
    ecs = StubECS(ENTITIES)
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


def test_normalize_blocked_actions_handles_various_inputs() -> None:
    assert _normalize_blocked_actions(None) == set()
    assert _normalize_blocked_actions("attack_melee") == {"attack_melee"}
    assert _normalize_blocked_actions(["move", "attack_melee"]) == {"move", "attack_melee"}
    assert _normalize_blocked_actions({"a": "move"}) == {"move"}

