"""Integration tests covering the round-trip action flow."""

from __future__ import annotations

from typing import Any

import pytest

from core.events import topics
from tests.helpers.pipeline import (
    AutoController,
    LoggedEventBus,
    SimpleRules,
    build_pipeline,
)


@pytest.fixture
def pipeline_components() -> dict[str, Any]:
    return build_pipeline()


def test_turn_flow_single_move_action(pipeline_components) -> None:
    bus: LoggedEventBus = pipeline_components["bus"]
    rules: SimpleRules = pipeline_components["rules"]

    bus.publish(topics.BEGIN_TURN, actor_id="hero")
    bus.publish(topics.REQUEST_ACTIONS, actor_id="hero")

    event_sequence = [topic for topic, _ in bus.log]
    expected = [
        topics.BEGIN_TURN,
        topics.REQUEST_ACTIONS,
        topics.ACTIONS_AVAILABLE,
        topics.INTENT_SUBMITTED,
        topics.INTENT_VALIDATED,
        topics.ACTION_ENQUEUED,
        topics.PERFORM_ACTION,
        topics.ACTION_RESOLVED,
        topics.END_TURN,
    ]
    assert event_sequence[: len(expected)] == expected
    assert rules.movement_system.moves == [("hero", (1, 0))]


def test_turn_flow_attack_triggers_resolution(pipeline_components) -> None:
    bus: LoggedEventBus = pipeline_components["bus"]
    rules: SimpleRules = pipeline_components["rules"]
    controller: AutoController = pipeline_components["controller"]

    controller._default_action = "attack_melee"

    bus.publish(topics.BEGIN_TURN, actor_id="hero")
    bus.publish(topics.REQUEST_ACTIONS, actor_id="hero")

    assert any(record[0] == topics.ACTION_RESOLVED for record in bus.log)
    assert rules.attacks
    last_attack = rules.attacks[-1]
    assert last_attack["attacker"] == "hero"
    assert last_attack["target"] == "ghoul"

