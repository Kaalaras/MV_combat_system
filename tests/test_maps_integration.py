"""Smoke tests exercising Tiled map integration across core systems."""
from __future__ import annotations

import pytest

from core.event_bus import EventBus
from ecs.ecs_manager import ECSManager
from modules.cover.system import CoverSystem as GridCoverSystem
from modules.los.system import LineOfSightSystem
from modules.maps.events import LoadMapFromTiled
from modules.maps.resolver import ActiveMapResolver
from modules.maps.systems.map_loader import MapLoaderSystem
from modules.movement.system import MovementSystem, TileBlockedError


@pytest.fixture
def load_map_systems():
    """Return helpers wired to the active map loaded from ``path``."""

    def _loader(path: str):
        bus = EventBus()
        ecs_manager = ECSManager(event_bus=bus)
        MapLoaderSystem(ecs_manager, event_bus=bus)
        LoadMapFromTiled(path).publish(bus)

        resolver = ActiveMapResolver(ecs_manager)
        movement = MovementSystem(ecs_manager, map_resolver=resolver)
        los = LineOfSightSystem(ecs_manager, map_resolver=resolver)
        cover = GridCoverSystem(ecs_manager, map_resolver=resolver)
        grid = resolver.get_active_map().grid
        return movement, los, cover, grid

    return _loader


def test_light_cover_bonus_from_tiled_map(load_map_systems):
    movement, los, cover, grid = load_map_systems("assets/maps/test_cover.tmx")

    attacker = (1, 5)
    defender = (3, 5)

    # Light cover tiles should still allow the shot but penalise the defender.
    assert los.has_line_of_sight(attacker, defender, ignore_target_blocking=True)
    assert cover.cover_bonus(defender) == -1

    # Heavier fortifications on the same row escalate the modifier.
    assert cover.tile_cover_bonus(5, 5) == 0  # Heavy cover
    assert cover.tile_cover_bonus(7, 5) == 1  # Fortification provides +1


def test_pathfinding_respects_impassable_and_cost(load_map_systems):
    movement, los, cover, grid = load_map_systems("assets/maps/test_hazard.tmx")

    corridor_path = [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]
    assert movement.can_enter(*corridor_path[0])
    assert movement.path_cost(corridor_path) == 8  # 1 + 2 + 3 + 1 + 1

    with pytest.raises(TileBlockedError):
        movement.get_move_cost(0, 5)


def test_hazard_tiles_apply_damage_on_entry(load_map_systems):
    movement, los, cover, grid = load_map_systems("assets/maps/test_hazard.tmx")

    safe_tile = (4, 5)
    hazard_tile = (5, 5)

    assert grid.get_hazard_damage(*safe_tile) == 0
    assert grid.get_hazard_damage(*hazard_tile) == 5

    path = [(1, 5), (2, 5), (3, 5), (4, 5), hazard_tile]
    hazard_total = sum(grid.get_hazard_damage(x, y) for x, y in path)
    assert hazard_total == 5
