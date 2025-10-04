from __future__ import annotations

from typing import Any

from core.actions.intent import ActionIntent, TargetSpec
from core.actions.performers import ActionPerformer
from core.events import topics
from core.reactions.manager import ReactionManager

from tests.unit.test_utils import DummyEventBus


class StubRules:
    def __init__(self) -> None:
        self._reaction_options = [
            {"id": "defend_dodge", "name": "Dodge", "reaction_speed": "fast"}
        ]

    def iter_reaction_options(self, action_def: Any, intent: ActionIntent):
        return list(self._reaction_options)

    def resolve_attack(self, actor_id: str, target_id: str, **_: Any) -> dict[str, Any]:
        return {"hit": True, "damage": 3, "target": target_id}

    @property
    def movement_system(self) -> None:  # pragma: no cover - not used here
        return None


def test_reaction_manager_opens_window_and_resumes_flow() -> None:
    bus = DummyEventBus()
    rules = StubRules()
    reactions = ReactionManager(rules)
    performer = ActionPerformer(rules)
    reactions.bind(bus)
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
        reservation_id="txn-1",
    )

    window_events = [payload for topic, payload in bus.published if topic == topics.REACTION_WINDOW_OPENED]
    assert window_events, "reaction window should be opened"
    window_payload = window_events[0]
    window_id = window_payload["window_id"]

    bus.publish(
        topics.REACTION_DECLARED,
        actor_id="ghoul",
        reaction={"id": "defend_dodge", "reaction_speed": "fast"},
        passed=False,
        window_id=window_id,
    )

    perform_events = [payload for topic, payload in bus.published if topic == topics.PERFORM_ACTION]
    assert any(payload.get("reactions_resolved") for payload in perform_events)

    resolved_events = [payload for topic, payload in bus.published if topic == topics.ACTION_RESOLVED]
    assert resolved_events, "action should eventually resolve"
    assert not reactions._pending_actions, "pending action should be cleared after resolution"


def test_reaction_manager_rejects_wrong_actor_response() -> None:
    bus = DummyEventBus()
    rules = StubRules()
    reactions = ReactionManager(rules)
    performer = ActionPerformer(rules)
    reactions.bind(bus)
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
        reservation_id="txn-2",
    )

    window_events = [payload for topic, payload in bus.published if topic == topics.REACTION_WINDOW_OPENED]
    window_id = window_events[0]["window_id"]

    bus.publish(
        topics.REACTION_DECLARED,
        actor_id="nosy_vampire",
        reaction={"id": "defend_dodge", "reaction_speed": "fast"},
        passed=False,
        window_id=window_id,
    )

    resolved_events = [payload for topic, payload in bus.published if topic == topics.ACTION_RESOLVED]
    assert not resolved_events, "unauthorised reaction should be ignored"

    bus.publish(
        topics.REACTION_DECLARED,
        actor_id="ghoul",
        reaction={"id": "defend_dodge", "reaction_speed": "fast"},
        passed=False,
        window_id=window_id,
    )

    resolved_events = [payload for topic, payload in bus.published if topic == topics.ACTION_RESOLVED]
    assert resolved_events, "authorized defender resolves the action"


def test_reaction_manager_clears_pending_for_auto_ids() -> None:
    bus = DummyEventBus()
    rules = StubRules()
    reactions = ReactionManager(rules)
    performer = ActionPerformer(rules)
    reactions.bind(bus)
    performer.bind(bus)

    intent = ActionIntent(
        actor_id="hunter",
        action_id="attack_melee",
        targets=(TargetSpec.entity("ghoul"),),
    )

    bus.publish(
        topics.PERFORM_ACTION,
        intent=intent.to_dict(),
        intent_obj=intent,
        await_reactions=True,
    )

    window_events = [payload for topic, payload in bus.published if topic == topics.REACTION_WINDOW_OPENED]
    window_id = window_events[0]["window_id"]

    bus.publish(
        topics.REACTION_DECLARED,
        actor_id="ghoul",
        reaction={"id": "defend_dodge", "reaction_speed": "fast"},
        passed=False,
        window_id=window_id,
    )

    assert not reactions._pending_actions, "auto-generated action id should be cleaned up"


def test_reaction_manager_derive_action_id_prefers_client_tx() -> None:
    rules = StubRules()
    reactions = ReactionManager(rules)
    intent = ActionIntent(
        actor_id="hunter",
        action_id="attack_melee",
        targets=(TargetSpec.entity("ghoul"),),
        client_tx_id="client-42",
    )

    action_id = reactions._derive_action_id({}, intent)

    assert action_id == "client-42"

