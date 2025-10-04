"""Tests for reaction window orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import dataclass
from typing import Any, Iterable

import pytest

from core.actions.intent import ActionIntent, TargetSpec
from core.reactions.manager import ReactionManager
from core.events import topics


@dataclass
class DummyEventBus:
    published: list[tuple[str, dict[str, Any]]]

    def __post_init__(self) -> None:
        self.subscribers: dict[str, list[Any]] = {}

    def subscribe(self, topic: str, handler: Any) -> None:
        self.subscribers.setdefault(topic, []).append(handler)

    def publish(self, topic: str, /, **payload: Any) -> None:
        record = (topic, dict(payload))
        self.published.append(record)
        for handler in list(self.subscribers.get(topic, [])):
            handler(**payload)


class StubRules:
    def iter_reaction_options(self, action_def, intent: ActionIntent) -> Iterable[dict[str, Any]]:
        yield {
            "id": "defend_dodge",
            "name": "Dodge",
            "reaction_speed": "fast",
        }
        yield {
            "id": "counter_attack",
            "name": "Counter",
            "reaction_speed": "slow",
        }


@pytest.fixture
def reaction_context():
    bus = DummyEventBus([])
    rules = StubRules()
    manager = ReactionManager(rules)
    manager.bind(bus)
    return bus, manager


def _publish_attack(bus: DummyEventBus, *, attackers: list[str], defenders: list[str]) -> ActionIntent:
    intent = ActionIntent(
        actor_id=attackers[0],
        action_id="attack_ranged",
        targets=tuple(TargetSpec.entity(target) for target in defenders),
    )
    bus.publish(
        topics.PERFORM_ACTION,
        await_reactions=True,
        intent=intent.to_dict(),
        intent_obj=intent,
    )
    return intent


def test_reaction_manager_opens_windows(reaction_context) -> None:
    bus, manager = reaction_context

    intent = _publish_attack(bus, attackers=["hero"], defenders=["ghoul"])

    windows = [payload for topic, payload in bus.published if topic == topics.REACTION_WINDOW_OPENED]
    assert windows
    window_payload = windows[0]
    assert window_payload["actor_id"] == "ghoul"
    assert len(window_payload["options"]) == 2

    # Defender chooses the slow reaction to make sure ordering works later.
    choice = window_payload["options"][1]
    bus.publish(
        topics.REACTION_DECLARED,
        actor_id="ghoul",
        reaction=choice,
        passed=False,
        window_id=window_payload["window_id"],
    )

    resolved = [payload for topic, payload in bus.published if topic == topics.REACTION_RESOLVED]
    assert resolved
    assert resolved[-1]["reactions"][0]["id"] == "counter_attack"


def test_reaction_manager_handles_multiple_defenders(reaction_context) -> None:
    bus, manager = reaction_context

    intent = _publish_attack(bus, attackers=["hero"], defenders=["ghoul", "vampire"])

    windows = [payload for topic, payload in bus.published if topic == topics.REACTION_WINDOW_OPENED]
    assert len(windows) == 2

    # First defender picks the slow option, second defender picks the fast one.
    first_window = windows[0]
    bus.publish(
        topics.REACTION_DECLARED,
        actor_id=first_window["actor_id"],
        reaction=first_window["options"][1],
        passed=False,
        window_id=first_window["window_id"],
    )

    second_window = windows[1]
    bus.publish(
        topics.REACTION_DECLARED,
        actor_id=second_window["actor_id"],
        reaction=second_window["options"][0],
        passed=False,
        window_id=second_window["window_id"],
    )

    resolved = [payload for topic, payload in bus.published if topic == topics.REACTION_RESOLVED]
    assert resolved
    reactions = resolved[-1]["reactions"]
    assert reactions[0]["id"] == "defend_dodge"
    assert reactions[1]["id"] == "counter_attack"

