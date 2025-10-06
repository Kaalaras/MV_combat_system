from __future__ import annotations

from pathlib import Path

from modules.maps.gen import MapGenParams
from modules.maps.systems.map_generator import generate_map_spec
from modules.maps.tiled_importer import TiledImporter


def _normalise(cell):
    if isinstance(cell, str):
        return {cell}
    return set(cell)


def test_exported_tmx_roundtrips_to_mapspec(tmp_path):
    params = MapGenParams(
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
        seed=42,
    )

    spec = generate_map_spec(params)
    spec.meta.name = "roundtrip"
    spec.meta.biome = params.biome

    tmx_path = Path(tmp_path) / "export.tmx"
    spec.save_tmx(tmx_path)

    importer = TiledImporter()
    loaded = importer.load(str(tmx_path))

    assert loaded.width == spec.width
    assert loaded.height == spec.height
    assert loaded.cell_size == spec.cell_size
    assert loaded.meta.name == spec.meta.name
    assert loaded.meta.biome == spec.meta.biome
    assert loaded.meta.seed == spec.meta.seed
    assert set(loaded.meta.spawn_zones) == set(spec.meta.spawn_zones)

    for label, zone in spec.meta.spawn_zones.items():
        other = loaded.meta.spawn_zones[label]
        assert other.position == zone.position
        assert other.footprint == zone.footprint
        assert other.safe_radius == zone.safe_radius
        assert other.allow_decor == zone.allow_decor
        assert other.allow_hazard == zone.allow_hazard

    for y in range(spec.height):
        for x in range(spec.width):
            assert _normalise(loaded.cells[y][x]) == _normalise(spec.cells[y][x])

