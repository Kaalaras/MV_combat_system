from modules.maps.gen.layout import generate_layout
from modules.maps.gen.params import MapGenParams
from modules.maps.gen.validate import MapValidator
from modules.maps.gen.spawns import (
    _determine_pois,
    _fairness_ratio,
    _fairness_tolerance,
    assign_spawn_zones,
)
from modules.maps.spec import MapSpec, to_map_component


def _compute_fairness(spec: MapSpec) -> float:
    component = to_map_component(spec)
    grid = component.grid
    spawns = list(spec.meta.spawn_zones.values())
    pois = _determine_pois(grid)
    return _fairness_ratio(grid, spawns, pois)


def test_generate_layout_produces_balanced_maps():
    params_template = dict(
        size="s",
        biome="forest",
        decor_density="mid",
        cover_ratio=0.2,
        hazard_ratio=0.1,
        difficult_ratio=0.1,
        chokepoint_limit=0.2,
        room_count=None,
        corridor_width=(1, 3),
        symmetry="none",
    )
    for seed in range(100):
        params = MapGenParams(seed=seed, **params_template)
        spec = generate_layout(params)
        validator = MapValidator(spec)
        assert validator.is_valid()
        fairness = _compute_fairness(spec)
        footprint = next(iter(spec.meta.spawn_zones.values())).footprint
        assert fairness <= _fairness_tolerance(footprint) + 1e-6
        # Ensure spawn zones are recorded in metadata and not empty.
        assert spec.meta.spawn_zones
        for zone in spec.meta.spawn_zones.values():
            assert isinstance(zone.position, tuple)
            assert len(zone.position) == 2
            assert zone.safe_radius >= 0


def test_generate_layout_handles_larger_spawn_footprints():
    params_template = dict(
        size="s",
        biome="forest",
        decor_density="mid",
        cover_ratio=0.2,
        hazard_ratio=0.1,
        difficult_ratio=0.1,
        chokepoint_limit=0.2,
        room_count=None,
        corridor_width=(2, 3),
        symmetry="none",
    )
    for seed in range(10):
        params = MapGenParams(seed=seed, **params_template)
        spec = generate_layout(params)
        spec = assign_spawn_zones(spec, max_spawns=2, footprint=(2, 2))
        validator = MapValidator(spec)
        assert validator.is_valid()
        fairness = _compute_fairness(spec)
        footprint = next(iter(spec.meta.spawn_zones.values())).footprint
        assert fairness <= _fairness_tolerance(footprint) + 1e-6
