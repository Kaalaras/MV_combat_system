from __future__ import annotations

from collections.abc import Callable

import pytest

from core.actions.intent import ActionIntent, CostSpec, TargetSpec
from core.events import topics
from core.input.hotseat_cli import HotSeatCLIController


def test_cost_spec_round_trip() -> None:
    spec = CostSpec(action_points=2, movement_points=1, blood=3, willpower=4, ammunition=5)
    payload = spec.to_dict()
    restored = CostSpec.from_dict(payload)

    assert restored == spec
    assert payload["action_points"] == 2


def test_target_spec_serialisation_variants() -> None:
    self_target = TargetSpec.self()
    entity_target = TargetSpec.entity("enemy-1", advantage="flank")
    tile_target = TargetSpec.tile((3, 4))
    area_target = TargetSpec.area((5, 6), shape="circle", radius=2)

    for target in (self_target, entity_target, tile_target, area_target):
        payload = target.to_dict()
        restored = TargetSpec.from_dict(payload)
        assert restored == target


def test_target_spec_coordinate_validation() -> None:
    assert TargetSpec.tile((1, 2, 3)).position == (1, 2, 3)
    assert TargetSpec.tile((1.0, 2.0)).position == (1, 2)

    with pytest.raises(ValueError):
        TargetSpec.tile((1.5, 2))


def test_action_intent_round_trip_and_immutability() -> None:
    intent = ActionIntent(
        actor_id="hero",
        action_id="move",
        targets=(TargetSpec.tile((1, 2)),),
        params={"distance": 3},
        source_player_id="player-1",
        client_tx_id="abc123",
    )

    payload = intent.to_dict()
    restored = ActionIntent.from_dict(payload)

    assert restored == intent
    assert isinstance(restored.targets, tuple)

    with pytest.raises(TypeError):
        restored.params["distance"] = 5  # type: ignore[index]


class DummyEventBus:
    def __init__(self) -> None:
        self.subscriptions: dict[str, list[Callable[..., None]]] = {}
        self.published: list[tuple[str, dict[str, object]]] = []

    def subscribe(self, topic: str, callback: Callable[..., None]) -> None:
        self.subscriptions.setdefault(topic, []).append(callback)

    def publish(self, topic: str, **payload: object) -> None:
        self.published.append((topic, dict(payload)))
        for handler in self.subscriptions.get(topic, []):
            handler(**payload)


def test_hotseat_controller_empty_loop() -> None:
    inputs = iter(["0", "0"])

    def fake_input(prompt: str) -> str:
        return next(inputs, "")

    outputs: list[str] = []
    controller = HotSeatCLIController(input_fn=fake_input, output_fn=outputs.append)
    bus = DummyEventBus()

    controller.bind(bus)

    bus.publish(topics.REQUEST_ACTIONS, actor_id="hero")
    bus.publish(topics.ACTIONS_AVAILABLE, actor_id="hero", actions=[])
    bus.publish(topics.REACTION_WINDOW_OPENED, actor_id="hero", options=[])

    assert (
        topics.REACTION_DECLARED,
        {"actor_id": "hero", "reaction": None, "passed": True},
    ) in bus.published
