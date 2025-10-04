"""High-level tests for the declarative action selector layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pytest

from core.actions.selector import ActionOption, compute_available_actions


@dataclass
class DummyMovementSystem:
    reachable: list[tuple[int, int, int]]

    def get_reachable_tiles(self, actor_id: str, max_distance: int):
        assert actor_id == "hero"
        assert max_distance == 4
        return list(self.reachable)


@dataclass
class DummyLineOfSight:
    visible_pairs: set[tuple[str, str]]

    def has_line_of_sight(self, source_id: str, target_id: str) -> bool:
        return (source_id, target_id) in self.visible_pairs


class DummyRules:
    def __init__(self) -> None:
        self.movement_system = DummyMovementSystem(
            reachable=[(1, 0, 1), (0, 1, 1), (1, 1, 2)]
        )
        self.line_of_sight = DummyLineOfSight({("hero", "ghoul"), ("hero", "vampire")})

    def get_move_distance(self, actor_id: str) -> int:
        return 4

    def iter_enemy_ids(self, actor_id: str) -> Iterable[str]:
        return ("ghoul", "vampire")

    def get_position(self, entity_id: str):
        return {
            "hero": (0, 0),
            "ghoul": (0, 1),
            "vampire": (3, 0),
        }.get(entity_id)

    def get_action_points(self, actor_id: str) -> int:
        return 3

    def get_ammunition(self, actor_id: str) -> int:
        return 5

    def get_ranged_range(self, actor_id: str) -> int:
        return 6


class DummyECS:
    def __init__(self) -> None:
        self.positions = {"hero": (0, 0), "ghoul": (0, 1), "vampire": (3, 0)}
        self.action_points = {"hero": 3}
        self.ammunition = {"hero": 5}


@pytest.fixture
def selector_context():
    return DummyECS(), DummyRules()


def test_selector_filters_targets_by_los(selector_context) -> None:
    ecs, rules = selector_context
    rules.line_of_sight.visible_pairs.remove(("hero", "vampire"))

    options = compute_available_actions("hero", ecs, rules)
    option_map = {opt.action_id: opt for opt in options}

    ranged = option_map["attack_ranged"]
    assert isinstance(ranged, ActionOption)
    assert ranged.is_available
    assert all(target.reference != "vampire" for target in ranged.valid_targets)


def test_selector_reports_insufficient_movement(selector_context) -> None:
    ecs, rules = selector_context
    rules.movement_system.reachable = []

    options = compute_available_actions("hero", ecs, rules)
    move = next(opt for opt in options if opt.action_id == "move")
    assert not move.is_available
    assert "no_reachable_tiles" in move.predicates_failed


def test_selector_blocks_melee_without_adjacent_enemy(selector_context) -> None:
    ecs, rules = selector_context
    # Move ghoul farther away so nobody is adjacent.
    ecs.positions["ghoul"] = (2, 2)
    rules.get_position = lambda entity_id: ecs.positions.get(entity_id)

    options = compute_available_actions("hero", ecs, rules)
    melee = next(opt for opt in options if opt.action_id == "attack_melee")
    assert not melee.is_available
    assert "no_adjacent_enemies" in melee.predicates_failed

