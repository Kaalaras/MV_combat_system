"""Tests for the MapSpec serialization helpers."""
from __future__ import annotations

from pathlib import Path

import json
import pytest

from modules.maps.components import MapMeta
from modules.maps.spec import (
    MapSpec,
    from_map_component,
    load_json,
    save_json,
    to_map_component,
)
from modules.maps.terrain_types import TERRAIN_CATALOG, combine


def _grid_snapshot(map_component):
    grid = map_component.grid
    return {
        "flags": [row[:] for row in grid.flags],
        "move_cost": [row[:] for row in grid.move_cost],
        "hazard_damage": [row[:] for row in grid.hazard_damage],
    }


def _normalise_cells(cells):
    normalised = []
    for row in cells:
        normalised_row = []
        for cell in row:
            if isinstance(cell, str):
                normalised_row.append([cell])
            else:
                normalised_row.append(sorted(cell))
        normalised.append(normalised_row)
    return normalised


def test_to_map_component_preserves_descriptor_data():
    meta = MapMeta(name="Test Map", biome="forest", seed=42)
    cells = [
        ["floor", ["difficult", "hazard"]],
        [["wall"], ["hazard_severe", "light_cover"]],
    ]
    spec = MapSpec(width=2, height=2, cell_size=1, meta=meta, cells=cells)

    component = to_map_component(spec)
    grid = component.grid

    floor = TERRAIN_CATALOG["floor"]
    combo = combine("difficult", "hazard")
    wall = TERRAIN_CATALOG["wall"]
    combo_two = combine("hazard_severe", "light_cover")

    assert grid.flags[0][0] == int(floor.flags)
    assert grid.move_cost[0][0] == floor.move_cost
    assert grid.hazard_damage[0][0] == floor.hazard_damage

    assert grid.flags[0][1] == int(combo.flags)
    assert grid.move_cost[0][1] == combo.move_cost
    assert grid.hazard_damage[0][1] == combo.hazard_damage

    assert grid.flags[1][0] == int(wall.flags)
    assert grid.move_cost[1][0] == 0
    assert grid.hazard_damage[1][0] == wall.hazard_damage

    assert grid.flags[1][1] == int(combo_two.flags)
    assert grid.move_cost[1][1] == combo_two.move_cost
    assert grid.hazard_damage[1][1] == combo_two.hazard_damage


def test_roundtrip_via_spec_and_json(tmp_path):
    meta = MapMeta(name="Roundtrip", biome="desert", seed=None)
    cells = [
        ["floor", ["hazard", "difficult"]],
        [["fortification", "light_cover"], "void"],
    ]
    spec = MapSpec(width=2, height=2, cell_size=2, meta=meta, cells=cells)

    component = to_map_component(spec)
    snapshot_original = _grid_snapshot(component)

    exported = from_map_component(component)
    component_roundtrip = to_map_component(exported)
    snapshot_roundtrip = _grid_snapshot(component_roundtrip)

    assert snapshot_roundtrip == snapshot_original

    original_cells = _normalise_cells(spec.cells)
    exported_cells = _normalise_cells(exported.cells)
    assert exported_cells == original_cells

    destination = Path(tmp_path) / "map.json"
    save_json(exported, destination)

    with destination.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["width"] == exported.width
    assert data["height"] == exported.height
    assert data["meta"]["name"] == exported.meta.name

    loaded = load_json(destination)
    assert _normalise_cells(loaded.cells) == exported_cells

    component_loaded = to_map_component(loaded)
    assert _grid_snapshot(component_loaded) == snapshot_original


def test_load_json_missing_required_field_includes_field_name(tmp_path):
    path = Path(tmp_path) / "missing_width.json"
    path.write_text(
        json.dumps({"height": 1, "cell_size": 1, "meta": {}, "cells": []}),
        encoding="utf-8",
    )

    with pytest.raises(KeyError) as excinfo:
        load_json(path)

    assert "Missing required field in map JSON data" in str(excinfo.value)
    assert "'width'" in str(excinfo.value)


def test_load_json_invalid_json_mentions_source_path(tmp_path):
    path = Path(tmp_path) / "bad.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError) as excinfo:
        load_json(path)

    assert str(path) in str(excinfo.value)

