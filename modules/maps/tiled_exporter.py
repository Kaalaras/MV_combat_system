"""Helpers to export :class:`MapSpec` instances to Tiled TMX files."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

import xml.etree.ElementTree as ET

from modules.maps.spec import CellSpec, MapSpec


_COVER_PROPERTY: Mapping[str, str] = {
    "light_cover": "light",
    "heavy_cover": "heavy",
    "fortification": "fortification",
}

_HAZARD_PROPERTY: Mapping[str, tuple[str, str]] = {
    "hazard": ("dangerous", "on_enter"),
    "hazard_severe": ("very_dangerous", "per_tile"),
}

_BASE_TERRAIN_MOVE_COST: Mapping[str, int] = {
    "floor": 1,
    "difficult": 2,
    "very_difficult": 3,
}


def _normalise_cell(cell: CellSpec) -> list[str]:
    if isinstance(cell, str):
        return [cell]
    return list(cell)


def _select_base_descriptor(names: Iterable[str]) -> str | None:
    name_set = set(names)
    if "void" in name_set:
        return None
    if "wall" in name_set:
        return "wall"
    for candidate in ("very_difficult", "difficult", "floor"):
        if candidate in name_set:
            return candidate
    if name_set:
        return next(iter(name_set))
    return "floor"


def _terrain_properties(descriptor: str) -> Mapping[str, object]:
    if descriptor == "wall":
        return {"blocks_move": True, "blocks_los": True, "move_cost": 0}
    move_cost = _BASE_TERRAIN_MOVE_COST.get(descriptor)
    if move_cost is None:
        return {}
    if move_cost == 1:
        return {}
    return {"move_cost": move_cost}


def _cover_properties(names: Iterable[str]) -> Mapping[str, object] | None:
    for descriptor in ("fortification", "heavy_cover", "light_cover"):
        if descriptor in names:
            return {"cover": _COVER_PROPERTY[descriptor]}
    return None


def _hazard_properties(names: Iterable[str]) -> Mapping[str, object] | None:
    for descriptor in ("hazard_severe", "hazard"):
        if descriptor in names:
            hazard, timing = _HAZARD_PROPERTY[descriptor]
            return {"hazard": hazard, "hazard_timing": timing}
    return None


def _collision_properties(names: Iterable[str]) -> Mapping[str, object] | None:
    if "void" in names:
        return {"blocks_move": True, "blocks_los": True, "move_cost": 0}
    if "wall" in names:
        return {"blocks_move": True, "blocks_los": True, "move_cost": 1}
    return None


def _bool_value(value: bool) -> str:
    return "true" if value else "false"


def _prop_attributes(name: str, value: object) -> dict[str, str]:
    attrs = {"name": name}
    if isinstance(value, bool):
        attrs["type"] = "bool"
        attrs["value"] = _bool_value(value)
    elif isinstance(value, int):
        attrs["type"] = "int"
        attrs["value"] = str(value)
    else:
        attrs["value"] = str(value)
    return attrs


@dataclass(slots=True)
class _Tileset:
    name: str
    tilewidth: int
    tileheight: int
    tiles: list[dict[str, object]] = field(default_factory=list)
    _lookup: dict[tuple[tuple[str, object], ...], int] = field(default_factory=dict)
    firstgid: int | None = None

    def register(self, properties: Mapping[str, object]) -> int:
        key = tuple(sorted((k, properties[k]) for k in properties))
        tile_id = self._lookup.get(key)
        if tile_id is None:
            tile_id = len(self.tiles)
            self._lookup[key] = tile_id
            self.tiles.append(dict(properties))
        return tile_id

    def gid(self, tile_id: int | None) -> int:
        if tile_id is None or self.firstgid is None:
            return 0
        return self.firstgid + tile_id

    def assign_firstgid(self, next_gid: int) -> int:
        if not self.tiles:
            self.firstgid = None
            return next_gid
        self.firstgid = next_gid
        return next_gid + len(self.tiles)


def _encode_layer(data: list[list[int]]) -> str:
    flat: list[str] = []
    for row in data:
        flat.extend(str(value) for value in row)
    return ",".join(flat)


def export_to_tiled(spec: MapSpec, out_path: str | Path) -> None:
    """Write ``spec`` to ``out_path`` using the shared TMX schema."""

    terrain = _Tileset(name="terrain", tilewidth=spec.cell_size, tileheight=spec.cell_size)
    cover = _Tileset(name="cover", tilewidth=spec.cell_size, tileheight=spec.cell_size)
    hazard = _Tileset(name="hazard", tilewidth=spec.cell_size, tileheight=spec.cell_size)
    collision = _Tileset(name="collision", tilewidth=spec.cell_size, tileheight=spec.cell_size)

    width, height = spec.width, spec.height
    terrain_ids: list[list[int | None]] = [[None for _ in range(width)] for _ in range(height)]
    cover_ids: list[list[int | None]] = [[None for _ in range(width)] for _ in range(height)]
    hazard_ids: list[list[int | None]] = [[None for _ in range(width)] for _ in range(height)]
    collision_ids: list[list[int | None]] = [[None for _ in range(width)] for _ in range(height)]

    for y in range(height):
        for x in range(width):
            names = _normalise_cell(spec.cells[y][x])
            base_descriptor = _select_base_descriptor(names)
            if base_descriptor is not None:
                terrain_props = _terrain_properties(base_descriptor)
                tile_id = terrain.register(terrain_props)
                terrain_ids[y][x] = tile_id
            cover_props = _cover_properties(names)
            if cover_props:
                cover_ids[y][x] = cover.register(cover_props)
            hazard_props = _hazard_properties(names)
            if hazard_props:
                hazard_ids[y][x] = hazard.register(hazard_props)
            collision_props = _collision_properties(names)
            if collision_props:
                collision_ids[y][x] = collision.register(collision_props)

    tilesets = [terrain, cover, hazard, collision]
    next_gid = 1
    for tileset in tilesets:
        next_gid = tileset.assign_firstgid(next_gid)

    terrain_data = [
        [terrain.gid(tile_id) for tile_id in row]
        for row in terrain_ids
    ]
    cover_data = [
        [cover.gid(tile_id) for tile_id in row]
        for row in cover_ids
    ]
    hazard_data = [
        [hazard.gid(tile_id) for tile_id in row]
        for row in hazard_ids
    ]
    collision_data = [
        [collision.gid(tile_id) for tile_id in row]
        for row in collision_ids
    ]

    map_attrib = {
        "version": "1.9",
        "tiledversion": "1.9.2",
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "width": str(width),
        "height": str(height),
        "tilewidth": str(spec.cell_size),
        "tileheight": str(spec.cell_size),
        "infinite": "0",
        "nextlayerid": "1",  # placeholder updated below
        "nextobjectid": "1",
    }
    map_elem = ET.Element("map", map_attrib)

    properties_elem = ET.SubElement(map_elem, "properties")
    ET.SubElement(properties_elem, "property", {"name": "name", "value": spec.meta.name})
    ET.SubElement(properties_elem, "property", {"name": "biome", "value": spec.meta.biome})
    seed_value = spec.meta.seed if spec.meta.seed is not None else ""
    ET.SubElement(
        properties_elem,
        "property",
        {"name": "seed", "value": str(seed_value)},
    )
    if spec.meta.spawn_zones:
        spawn_payload = {
            label: {
                "x": zone.position[0],
                "y": zone.position[1],
                "width": zone.footprint[0],
                "height": zone.footprint[1],
                "safe_radius": zone.safe_radius,
                "allow_decor": zone.allow_decor,
                "allow_hazard": zone.allow_hazard,
            }
            for label, zone in spec.meta.spawn_zones.items()
        }
        ET.SubElement(
            properties_elem,
            "property",
            {
                "name": "spawn_zones",
                "type": "string",
                "value": json.dumps(spawn_payload, separators=(",", ":")),
            },
        )

    layer_specs = [
        ("layer.terrain", terrain_data),
        ("layer.cover", cover_data),
        ("layer.hazard", hazard_data),
        ("layer.collision", collision_data),
    ]

    map_elem.set("nextlayerid", str(len(layer_specs) + 1))

    for index, (name, data) in enumerate(layer_specs, start=1):
        layer_elem = ET.SubElement(
            map_elem,
            "layer",
            {
                "id": str(index),
                "name": name,
                "width": str(width),
                "height": str(height),
            },
        )
        data_elem = ET.SubElement(layer_elem, "data", {"encoding": "csv"})
        data_elem.text = _encode_layer(data)

    for tileset in tilesets:
        if not tileset.tiles or tileset.firstgid is None:
            continue
        tileset_elem = ET.SubElement(
            map_elem,
            "tileset",
            {
                "firstgid": str(tileset.firstgid),
                "name": tileset.name,
                "tilewidth": str(tileset.tilewidth),
                "tileheight": str(tileset.tileheight),
                "tilecount": str(len(tileset.tiles)),
                "columns": "0",
            },
        )
        ET.SubElement(tileset_elem, "grid", {"orientation": "orthogonal", "width": "1", "height": "1"})
        for tile_id, props in enumerate(tileset.tiles):
            tile_elem = ET.SubElement(tileset_elem, "tile", {"id": str(tile_id)})
            if not props:
                continue
            props_elem = ET.SubElement(tile_elem, "properties")
            for key, value in sorted(props.items()):
                ET.SubElement(props_elem, "property", _prop_attributes(key, value))

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(map_elem)
    try:
        ET.indent(tree, space="  ")  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - Python < 3.9 fallback
        pass
    tree.write(out_path, encoding="utf-8", xml_declaration=True)


__all__ = ["export_to_tiled"]

