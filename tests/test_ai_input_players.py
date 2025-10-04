"""Scenarios exercising AI agents that leverage player-style input controllers."""

from __future__ import annotations

from core.actions.intent import ActionIntent, TargetSpec
from core.events import topics
from tests.helpers.pipeline import AutoController, LoggedEventBus, SimpleRules, build_pipeline


class ClassicAI:
    """Simplified AI that bypasses the action selector and fires intents directly."""

    def __init__(self, bus: LoggedEventBus, actor_id: str, target_id: str) -> None:
        self.actor_id = actor_id
        self.target_id = target_id
        self.bus = bus
        bus.subscribe(topics.REQUEST_ACTIONS, self._handle_request)

    def _handle_request(self, *, actor_id: str, **_: object) -> None:
        if actor_id != self.actor_id:
            return
        intent = ActionIntent(
            actor_id=self.actor_id,
            action_id="attack_melee",
            targets=(TargetSpec.entity(self.target_id),),
        )
        self.bus.publish(
            topics.INTENT_SUBMITTED,
            intent=intent.to_dict(),
            intent_obj=intent,
        )


def _run_turn(bus: LoggedEventBus, actor_id: str) -> None:
    bus.publish(topics.BEGIN_TURN, actor_id=actor_id)
    bus.publish(topics.REQUEST_ACTIONS, actor_id=actor_id)


def _count_events(bus: LoggedEventBus, topic: str, *, actor_id: str | None = None) -> int:
    def _payload_actor(entry: dict[str, object]) -> str | None:
        direct = entry.get("actor_id")
        if direct:
            return str(direct)
        intent = entry.get("intent")
        if isinstance(intent, dict):
            return str(intent.get("actor_id")) if intent.get("actor_id") else None
        return None

    return sum(
        1
        for event_topic, payload in bus.log
        if event_topic == topic and (actor_id is None or _payload_actor(payload) == actor_id)
    )


def test_input_controller_vs_classic_ai() -> None:
    components = build_pipeline(default_action="attack_melee")
    bus: LoggedEventBus = components["bus"]
    rules: SimpleRules = components["rules"]

    classic = ClassicAI(bus, actor_id="ghoul", target_id="hero")

    _run_turn(bus, "hero")
    _run_turn(bus, "ghoul")

    assert _count_events(bus, topics.ACTIONS_AVAILABLE, actor_id="hero") >= 1
    assert _count_events(bus, topics.INTENT_SUBMITTED, actor_id="hero") >= 1
    assert _count_events(bus, topics.INTENT_SUBMITTED, actor_id="ghoul") >= 1
    assert any(event[0] == topics.ACTION_RESOLVED for event in bus.log)
    assert len(rules.attacks) >= 2


def test_input_controller_mirror_match() -> None:
    components = build_pipeline(default_action="attack_melee")
    bus: LoggedEventBus = components["bus"]
    rules: SimpleRules = components["rules"]
    hero_controller: AutoController = components["controller"]

    rival_controller = AutoController(default_action="attack_melee", controlled_actors={"ghoul"})
    rival_controller.bind(bus)

    _run_turn(bus, "hero")
    _run_turn(bus, "ghoul")

    assert _count_events(bus, topics.ACTIONS_AVAILABLE, actor_id="hero") >= 1
    assert _count_events(bus, topics.ACTIONS_AVAILABLE, actor_id="ghoul") >= 1
    assert "attack_melee" in hero_controller.performed
    assert "attack_melee" in rival_controller.performed
    assert len(rules.attacks) >= 2


def test_free_for_all_with_multiple_input_controllers() -> None:
    components = build_pipeline(default_action="move")
    bus: LoggedEventBus = components["bus"]
    ecs = components["ecs"]
    rules: SimpleRules = components["rules"]

    extra_ids = [f"agent_{idx}" for idx in range(10)]
    base_internal_id = max(ecs.entities.values()) + 1
    for offset, actor_id in enumerate(extra_ids):
        internal_id = base_internal_id + offset
        ecs.entities[actor_id] = internal_id
        ecs.positions[actor_id] = (offset + 1, offset + 1)
        ecs.action_points[actor_id] = 2
        ecs.ammunition[actor_id] = 1

    controllers: list[AutoController] = []
    for actor_id in extra_ids:
        controller = AutoController(controlled_actors={actor_id}, default_action="move")
        controller.bind(bus)
        controllers.append(controller)

    for actor_id in extra_ids:
        _run_turn(bus, actor_id)

    for actor_id, controller in zip(extra_ids, controllers):
        assert _count_events(bus, topics.ACTIONS_AVAILABLE, actor_id=actor_id) >= 1
        assert controller.performed and controller.performed[-1] == "move"

    recent_moves = rules.movement_system.moves[-len(extra_ids):]
    assert len(recent_moves) == len(extra_ids)
