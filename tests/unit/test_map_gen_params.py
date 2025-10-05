from __future__ import annotations

from dataclasses import asdict

import pytest

from modules.maps.components import MapMeta
from modules.maps.gen.params import MapGenParams
from modules.maps.gen.random import get_rng, rand_choice
from modules.maps.spec import MapSpec


def _generate_mock_map(params: MapGenParams) -> MapSpec:
    width, height = params.dimensions
    rng = get_rng(params.seed)
    palette = ["floor", "difficult", "light_cover", "hazard"]
    cells = [
        [rand_choice(rng, palette) for _ in range(width)]
        for _ in range(height)
    ]
    meta = MapMeta(name="mock-map", biome=params.biome, seed=params.seed)
    return MapSpec(width=width, height=height, cell_size=1, meta=meta, cells=cells)


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ("xs", (16, 16)),
        ("s", (24, 24)),
        ("m", (32, 32)),
        ("l", (40, 40)),
        ("xl", (48, 48)),
    ],
)
def test_size_to_dimensions_mapping(size: str, expected: tuple[int, int]) -> None:
    params = MapGenParams(
        size=size,
        biome="forest",
        decor_density="mid",
        cover_ratio=0.2,
        hazard_ratio=0.1,
        difficult_ratio=0.3,
        chokepoint_limit=0.15,
        room_count=10,
        corridor_width=(2, 4),
        symmetry="none",
        seed=42,
    )
    assert params.dimensions == expected
    assert (params.width, params.height) == expected


def test_generation_is_deterministic_with_seed() -> None:
    params = MapGenParams(
        size="m",
        biome="urban_dense",
        decor_density="high",
        cover_ratio=0.3,
        hazard_ratio=0.2,
        difficult_ratio=0.4,
        chokepoint_limit=0.1,
        room_count=None,
        corridor_width=(1, 3),
        symmetry="mirror_x",
        seed=1234,
    )

    spec_a = _generate_mock_map(params)
    spec_b = _generate_mock_map(params)

    assert asdict(spec_a) == asdict(spec_b)
