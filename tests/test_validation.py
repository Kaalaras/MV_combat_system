"""Unit tests for the action validation pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.actions.intent import ActionIntent, TargetSpec
from core.actions.validation import validate_intent


@dataclass
class DummyECS:
    entities: dict[str, object]

    def resolve_entity(self, entity_id: str):
        return self.entities.get(entity_id)

    def has_entity(self, entity_id: str) -> bool:
        return entity_id in self.entities


class DummyRules:
    def __init__(self) -> None:
        self._locked: set[str] = set()
        self._blocked: dict[str, set[str]] = {}
        self._ownership: dict[tuple[str, str], bool] = {}
        self._resources: dict[str, dict[str, int]] = {}

    def set_locked(self, actor_id: str, locked: bool = True) -> None:
        if locked:
            self._locked.add(actor_id)
        else:
            self._locked.discard(actor_id)

    def set_blocked(self, actor_id: str, actions: set[str]) -> None:
        self._blocked[actor_id] = set(actions)

    def set_owner(self, actor_id: str, player_id: str, allowed: bool) -> None:
        self._ownership[(actor_id, player_id)] = allowed

    def set_resource(self, actor_id: str, resource: str, amount: int) -> None:
        self._resources.setdefault(actor_id, {})[resource] = amount

    def is_action_locked(self, actor_id: str) -> bool:
        return actor_id in self._locked

    def get_blocked_actions(self, actor_id: str):
        return self._blocked.get(actor_id, set())

    def is_actor_controlled_by(self, actor_id: str, player_id: str) -> bool:
        return self._ownership.get((actor_id, player_id), False)

    def get_action_points(self, actor_id: str) -> int:
        return self._resources.get(actor_id, {}).get("action_points", 0)


@pytest.fixture
def validation_context():
    ecs = DummyECS({"hero": object(), "ghoul": object()})
    rules = DummyRules()
    rules.set_resource("hero", "action_points", 1)
    return ecs, rules


def test_validation_rejects_locked_actor(validation_context) -> None:
    ecs, rules = validation_context
    rules.set_locked("hero")

    intent = ActionIntent(
        actor_id="hero",
        action_id="move",
        targets=(TargetSpec.tile((1, 2)),),
    )

    ok, reason, _ = validate_intent(intent, ecs, rules)
    assert not ok
    assert reason == "actor_locked"


def test_validation_rejects_blocked_action(validation_context) -> None:
    ecs, rules = validation_context
    rules.set_blocked("hero", {"attack_melee"})

    intent = ActionIntent(
        actor_id="hero",
        action_id="attack_melee",
        targets=(TargetSpec.entity("ghoul"),),
    )

    ok, reason, _ = validate_intent(intent, ecs, rules)
    assert not ok
    assert reason == "action_blocked"


def test_validation_checks_resource_cost(validation_context) -> None:
    ecs, rules = validation_context
    rules.set_resource("hero", "action_points", 0)

    intent = ActionIntent(
        actor_id="hero",
        action_id="attack_melee",
        targets=(TargetSpec.entity("ghoul"),),
    )

    ok, reason, _ = validate_intent(intent, ecs, rules)
    assert not ok
    assert reason == "insufficient_action_points"


def test_validation_checks_ownership(validation_context) -> None:
    ecs, rules = validation_context
    rules.set_owner("hero", "player-a", False)

    intent = ActionIntent(
        actor_id="hero",
        action_id="move",
        targets=(TargetSpec.tile((0, 1)),),
        source_player_id="player-a",
    )

    ok, reason, _ = validate_intent(intent, ecs, rules)
    assert not ok
    assert reason == "unauthorised_actor"

