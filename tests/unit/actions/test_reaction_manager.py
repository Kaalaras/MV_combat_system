from __future__ import annotations

from typing import Any, Callable

from core.actions.intent import ActionIntent, TargetSpec
from core.actions.performers import ActionPerformer
from core.events import topics
from core.reactions.manager import ReactionManager


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

