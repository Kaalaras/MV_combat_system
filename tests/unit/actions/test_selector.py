from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ecs.actions.selector import (
    ActionOption,
    ActionSelector,
    _manhattan_distance,
    compute_available_actions,
)
from core.events import topics
from ecs.components.resource_pool import ResourcePoolComponent
from tests.unit.test_utils import StubECS


@dataclass
class StubMovementSystem:
    reachable: list[tuple[int, int, int]]

    def get_reachable_tiles(self, actor_id: str, max_distance: int):
        assert max_distance > 0
        return self.reachable


class StubLineOfSight:
    def __init__(self, visible_pairs: set[tuple[str, str]]) -> None:
        self.visible_pairs = visible_pairs

    def has_line_of_sight(self, source_id: str, target_id: str) -> bool:
        return (source_id, target_id) in self.visible_pairs


class DummyRulesContext:
    def __init__(self) -> None:
        self.movement_system = StubMovementSystem(
            reachable=[(1, 0, 1), (0, 1, 1)]
        )
        self.line_of_sight = StubLineOfSight({("hero", "ghoul"), ("hero", "vampire")})

    def get_ranged_range(self, actor_id: str) -> int:
        return 6

    def iter_enemy_ids(self, actor_id: str):
        return ["ghoul", "vampire"]

    def get_position(self, entity_id: str):
        positions = {
            "hero": (0, 0),
            "ghoul": (0, 1),
            "vampire": (3, 0),
        }
        return positions.get(entity_id)

class DummyECS(StubECS):
    def __init__(self) -> None:
        super().__init__({"hero": 1, "ghoul": 2, "vampire": 3})
        self.positions = {"hero": (0, 0), "ghoul": (0, 1), "vampire": (3, 0)}

        internal_id = self.resolve_entity("hero")
        if internal_id is not None:
            self.add_component(
                internal_id,
                ResourcePoolComponent(
                    action_points=2,
                    movement_points=4,
                    ammunition=5,
                ),
            )


def test_compute_available_actions_core_paths() -> None:
    ecs = DummyECS()
    ctx = DummyRulesContext()

    options = compute_available_actions("hero", ecs, ctx)
    option_map = {opt.action_id: opt for opt in options}

    move_option = option_map["move"]
    assert isinstance(move_option, ActionOption)
    assert move_option.is_available
    assert len(move_option.valid_targets) == 2

    melee_option = option_map["attack_melee"]
    assert melee_option.is_available
    target_refs = [target.to_dict()["reference"] for target in melee_option.valid_targets]
    assert "ghoul" in target_refs

    ranged_option = option_map["attack_ranged"]
    assert ranged_option.is_available
    assert len(ranged_option.valid_targets) == 2

    assert "defend_dodge" not in option_map


def test_compute_available_actions_handles_blockers() -> None:
    ecs = DummyECS()
    ctx = DummyRulesContext()
    ctx.movement_system.reachable = []

    options = compute_available_actions("hero", ecs, ctx)
    move_option = next(opt for opt in options if opt.action_id == "move")

    assert not move_option.is_available
    assert "no_reachable_tiles" in move_option.predicates_failed


class DummyEventBus:
    def __init__(self) -> None:
        self.subscriptions: dict[str, list[Callable[..., None]]] = {}
        self.published: list[tuple[str, dict[str, object]]] = []

    def subscribe(self, topic: str, handler: Callable[..., None]) -> None:
        self.subscriptions.setdefault(topic, []).append(handler)

    def publish(self, topic: str, /, **payload: object) -> None:
        self.published.append((topic, dict(payload)))
        for handler in self.subscriptions.get(topic, []):
            handler(**payload)


def test_action_selector_publishes_on_bus() -> None:
    ecs = DummyECS()
    ctx = DummyRulesContext()
    selector = ActionSelector(ecs, ctx)
    bus = DummyEventBus()

    selector.bind(bus)
    bus.publish(topics.REQUEST_ACTIONS, actor_id="hero")

    assert any(topic == topics.ACTIONS_AVAILABLE for topic, _ in bus.published)
    published_payloads = [payload for topic, payload in bus.published if topic == topics.ACTIONS_AVAILABLE]
    assert published_payloads
    payload = published_payloads[-1]
    assert payload["actor_id"] == "hero"
    actions = payload["actions"]
    assert isinstance(actions, list)
    action_ids = [action["id"] for action in actions if isinstance(action, dict)]
    assert "move" in action_ids


def test_manhattan_distance_raises_on_mismatched_lengths() -> None:
    try:
        _manhattan_distance((0, 0), (1, 2, 3))
    except ValueError as exc:
        assert "2 != 3" in str(exc)
    else:
        raise AssertionError("Expected ValueError for mismatched coordinate lengths")
