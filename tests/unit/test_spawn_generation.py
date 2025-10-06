from collections import deque

from modules.maps.components import MapMeta
from core.pathfinding_optimization import OptimizedPathfinding
from modules.maps.gen.spawns import (
    assign_spawn_zones,
    _determine_pois,
    _fairness_ratio,
    _SpawnTerrain,
)
from modules.maps.spec import MapSpec, to_map_component


def _create_open_map(width: int, height: int) -> MapSpec:
    cells = [["floor" for _ in range(width)] for _ in range(height)]
    meta = MapMeta(name="arena", biome="forest", seed=0)
    return MapSpec(width=width, height=height, cell_size=1, meta=meta, cells=cells)


def _compute_fairness(spec: MapSpec) -> float:
    component = to_map_component(spec)
    grid = component.grid
    terrain = _SpawnTerrain(grid)
    optimizer = OptimizedPathfinding(terrain)
    optimizer.min_region_size = max(8, min(grid.width, grid.height) // 2)
    optimizer.precompute_paths()
    spawns = list(spec.meta.spawn_zones.values())
    pois = _determine_pois(grid)
    return _fairness_ratio(optimizer, spawns, pois)


def _zone_cells(zone, grid):
    x, y = zone.position
    width, height = zone.footprint
    return [
        (x + dx, y + dy)
        for dy in range(height)
        for dx in range(width)
        if 0 <= x + dx < grid.width and 0 <= y + dy < grid.height
    ]


def test_assign_spawn_zones_produces_fair_safe_spawns():
    spec = _create_open_map(16, 16)
    assign_spawn_zones(spec)
    zones = spec.meta.spawn_zones
    assert len(zones) >= 2
    for zone in zones.values():
        assert zone.safe_radius >= 0
        assert not zone.allow_hazard
    fairness = _compute_fairness(spec)
    assert fairness <= 0.051


def test_assign_spawn_zones_supports_larger_footprints():
    spec = _create_open_map(18, 18)
    assign_spawn_zones(spec, footprint=(2, 3))
    zones = spec.meta.spawn_zones
    assert len(zones) >= 2

    component = to_map_component(spec)
    grid = component.grid
    for zone in zones.values():
        assert zone.footprint == (2, 3)
        assert zone.safe_radius >= 0
        for cell in _zone_cells(zone, grid):
            x, y = cell
            assert grid.blocks_move_mask[y][x] is False
            assert grid.hazard_damage[y][x] == 0
    fairness = _compute_fairness(spec)
    assert fairness <= 0.051
