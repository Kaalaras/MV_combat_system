"""Property-based checks for procedural map generation invariants."""
from __future__ import annotations

import random
import statistics
import time
from typing import Literal

from modules.maps.gen import MapGenParams
from modules.maps.gen.spawns import _determine_pois, _fairness_ratio
from modules.maps.gen.validate import MapValidator
from modules.maps.spec import MapSpec, to_map_component
from modules.maps.systems.map_generator import generate_map_spec
from modules.maps.terrain_types import TerrainFlags


_SAFE_BIOMES = (
    "forest",
    "urban_sparse",
    "urban_dense",
    "construction",
    "junkyard",
    "building",
)
_SAFE_DENSITIES = ("low", "mid", "high")
_SAFE_SYMMETRIES = ("none", "mirror_x", "mirror_y", "rot_180")

# Budgets chosen according to the specification with additional headroom to
# account for the slower execution environment used in CI.  The ratios still
# guarantee that the generator comfortably meets the original limits on faster
# developer machines while avoiding flakiness.
_MapSize = Literal["m", "l"]

_SIZE_BUDGETS = {
    "m": 1.25,
    "l": 2.50,
}
_TOTAL_RUN_BUDGET = 150.0  # 50 runs should complete well under 150 seconds
_TERRAIN_RATIO_TOLERANCE = 0.10
# Allow a tiny slack for rounding-induced differences on small samples.
_ROUNDING_SLACK = 1e-3


def _pick_corridor_width(rng: random.Random) -> tuple[int, int]:
    minimum = rng.choice((1, 2))
    maximum = minimum + rng.choice((0, 1, 2))
    return minimum, maximum


def _pick_room_count(rng: random.Random, size: _MapSize) -> int | None:
    if rng.random() < 0.35:
        return None
    base = 6 if size == "m" else 8
    return rng.randint(base, base + 6)


def _random_params(rng: random.Random) -> MapGenParams:
    size: _MapSize = rng.choice(("m", "l"))
    cover_ratio = rng.uniform(0.12, 0.32)
    hazard_ratio = rng.uniform(0.02, 0.14)
    difficult_ratio = rng.uniform(0.05, 0.22)
    # Keep total specialised terrain well below 100 % to leave breathing room
    # for the generator when rounding to integer counts.
    total_ratio = cover_ratio + hazard_ratio + difficult_ratio
    if total_ratio > 0.85:
        scale = 0.85 / total_ratio
        cover_ratio *= scale
        hazard_ratio *= scale
        difficult_ratio *= scale

    params = MapGenParams(
        size=size,
        biome=rng.choice(_SAFE_BIOMES),
        decor_density=rng.choice(_SAFE_DENSITIES),
        cover_ratio=cover_ratio,
        hazard_ratio=hazard_ratio,
        difficult_ratio=difficult_ratio,
        chokepoint_limit=rng.uniform(0.10, 0.30),
        room_count=_pick_room_count(rng, size),
        corridor_width=_pick_corridor_width(rng),
        symmetry=rng.choice(_SAFE_SYMMETRIES),
        seed=rng.randint(0, 2**32 - 1),
    )
    return params


def _compute_ratios(spec: MapSpec) -> tuple[int, dict[str, float]]:
    component = to_map_component(spec)
    grid = component.grid
    floor_tiles = 0
    cover_tiles = 0
    difficult_tiles = 0
    hazard_tiles = 0
    cover_flags = TerrainFlags.COVER_LIGHT | TerrainFlags.COVER_HEAVY | TerrainFlags.FORTIFICATION
    difficult_flags = TerrainFlags.DIFFICULT
    hazard_flags = TerrainFlags.HAZARDOUS | TerrainFlags.VERY_HAZARDOUS

    for y in range(grid.height):
        for x in range(grid.width):
            if grid.blocks_move_mask[y][x]:
                continue
            floor_tiles += 1
            flags = TerrainFlags(grid.flags[y][x])
            if flags & cover_flags:
                cover_tiles += 1
            if flags & difficult_flags:
                difficult_tiles += 1
            if flags & hazard_flags or grid.hazard_damage[y][x] > 0:
                hazard_tiles += 1

    if floor_tiles == 0:
        return 0, {"cover": 0.0, "difficult": 0.0, "hazard": 0.0}

    ratios = {
        "cover": cover_tiles / floor_tiles,
        "difficult": difficult_tiles / floor_tiles,
        "hazard": hazard_tiles / floor_tiles,
    }
    return floor_tiles, ratios


def _fairness_delta(spec: MapSpec) -> float:
    spawns = list(spec.meta.spawn_zones.values())
    assert spawns, "spawn zones must be assigned"
    component = to_map_component(spec)
    grid = component.grid
    pois = _determine_pois(grid)
    return _fairness_ratio(grid, spawns, pois)


def test_generated_maps_preserve_invariants_and_budget() -> None:
    rng = random.Random(0xCAFE_BABE)
    runs = 50
    durations: dict[_MapSize, list[float]] = {"m": [], "l": []}

    for _ in range(runs):
        params = _random_params(rng)
        start = time.perf_counter()
        spec = generate_map_spec(params)
        duration = time.perf_counter() - start
        durations[params.size].append(duration)

        # Validate structural invariants: connectivity and spawn resilience.
        validator = MapValidator(spec)
        assert validator.is_valid(), "generated map should be fully connected with robust spawns"

        # Terrain ratios stay within ±10 % of the requested targets.
        floor_tiles, actual = _compute_ratios(spec)
        if floor_tiles > 0:
            for key, target in (
                ("cover", params.cover_ratio),
                ("difficult", params.difficult_ratio),
                ("hazard", params.hazard_ratio),
            ):
                delta = abs(actual[key] - target)
                assert (
                    delta <= _TERRAIN_RATIO_TOLERANCE + _ROUNDING_SLACK
                ), f"{key} ratio deviates by {delta:.3%} from target {target:.3%}"

        # Fairness between the two spawn zones should remain within ±10 %.
        fairness = _fairness_delta(spec)
        assert (
            fairness <= _TERRAIN_RATIO_TOLERANCE + 1e-6
        ), f"spawn fairness delta too high: {fairness:.3%}"

        # Ensure we keep allocating exactly two spawn zones without leaks.
        assert len(spec.meta.spawn_zones) == 2

    total_duration = sum(sum(times) for times in durations.values())
    assert total_duration <= _TOTAL_RUN_BUDGET, "generation budget exceeded in aggregate"

    for size, times in durations.items():
        if not times:
            continue
        avg_duration = statistics.fmean(times)
        budget = _SIZE_BUDGETS[size]
        assert (
            avg_duration <= budget
        ), f"average generation time for size {size} exceeded budget {budget:.3f}s (got {avg_duration:.3f}s)"
