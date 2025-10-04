import pytest

from modules.maps.terrain_types import (
    TERRAIN_CATALOG,
    TerrainFlags,
    combine,
)


def test_catalog_contains_basic_entries():
    assert "floor" in TERRAIN_CATALOG
    assert TERRAIN_CATALOG["floor"].flags == TerrainFlags(0)
    assert TERRAIN_CATALOG["wall"].flags & TerrainFlags.IMPASSABLE


def test_combine_difficult_light_cover():
    descriptor = combine("difficult", "light_cover")
    assert descriptor.flags & TerrainFlags.DIFFICULT
    assert descriptor.flags & TerrainFlags.COVER_LIGHT
    assert descriptor.move_cost is not None and descriptor.move_cost >= 2


def test_combine_hazard_severity():
    descriptor = combine("hazard", "hazard_severe")
    assert descriptor.flags & TerrainFlags.VERY_HAZARDOUS
    assert descriptor.hazard_damage == TERRAIN_CATALOG["hazard_severe"].hazard_damage
    assert descriptor.hazard_timing == "per_tile"


def test_combine_impassable_forces_none_move_cost():
    descriptor = combine("wall", "light_cover")
    assert descriptor.flags & TerrainFlags.IMPASSABLE
    assert descriptor.move_cost is None


def test_combine_requires_name():
    with pytest.raises(ValueError):
        combine()
