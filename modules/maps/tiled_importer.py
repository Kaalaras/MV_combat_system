"""Utilities to import Tiled maps (TMX) into :class:`MapSpec` objects."""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, Mapping

from pytiled_parser import parse_map
from pytiled_parser.layer import Layer, LayerGroup, ObjectLayer, TileLayer

from modules.maps.components import MapMeta, SpawnZone
from modules.maps.spec import MapSpec
from modules.maps.terrain_types import TERRAIN_CATALOG, TerrainFlags
from modules.maps.tiled_schema import (
    TILED_DEFAULTS,
    TILED_KEYS,
    apply_tile_defaults,
    parse_bool_flag,
    parse_cover_str,
    parse_hazard_str,
    parse_hazard_timing,
    parse_move_cost,
)


logger = logging.getLogger(__name__)


_FLIP_FLAGS_MASK = 0xE0000000


OBJECT_LAYER_DESCRIPTORS: Mapping[str, str] = {
    "walls": "wall",
    "doors": "door",
}


@dataclass(slots=True)
class _ResolvedProperties:
    move_cost: int
    blocks_move: bool
    blocks_los: bool
    cover_flags: TerrainFlags
    hazard_flags: TerrainFlags
    hazard_damage: int
    hazard_timing: str


def _iter_layers(layers: Iterable[Layer]) -> Iterator[Layer]:
    for layer in layers:
        if isinstance(layer, LayerGroup):
            if layer.visible is False:
                continue
            nested = layer.layers or []
            yield from _iter_layers(nested)
        else:
            yield layer


def _normalise_gid(gid: int) -> int:
    return gid & ~_FLIP_FLAGS_MASK


def _gather_tile_properties(tiled_map) -> dict[int, Mapping[str, object]]:
    gid_properties: dict[int, Mapping[str, object]] = {}

    def _combine_props(
        base_props: Mapping[str, object], tile
    ) -> dict[str, object]:
        combined: dict[str, object] = dict(base_props)
        if tile is not None and getattr(tile, "properties", None):
            combined.update(tile.properties)
        return combined

    for firstgid, tileset in tiled_map.tilesets.items():
        tileset_props = tileset.properties or {}
        tile_entries = tileset.tiles or {}
        tile_count = tileset.tile_count or 0

        indices: set[int] = set(tile_entries.keys())
        if tile_count:
            indices.update(range(tile_count))

        for offset in sorted(indices):
            tile = tile_entries.get(offset)
            gid_properties[firstgid + offset] = _combine_props(tileset_props, tile)

    return gid_properties


def _resolve_properties(mapping: Mapping[str, object]) -> _ResolvedProperties:
    resolved = apply_tile_defaults(mapping)
    move_cost = parse_move_cost(resolved.get(TILED_KEYS["properties"]["move_cost"]))
    blocks_move = parse_bool_flag(
        resolved.get(TILED_KEYS["properties"]["blocks_move"]),
        default=TILED_DEFAULTS["blocks_move"],
    )
    blocks_los = parse_bool_flag(
        resolved.get(TILED_KEYS["properties"]["blocks_los"]),
        default=TILED_DEFAULTS["blocks_los"],
    )
    cover_flags = parse_cover_str(resolved.get(TILED_KEYS["properties"]["cover"]))
    hazard_flags, hazard_damage = parse_hazard_str(
        resolved.get(TILED_KEYS["properties"]["hazard"])
    )
    hazard_timing = parse_hazard_timing(
        resolved.get(TILED_KEYS["properties"]["hazard_timing"])
    )
    return _ResolvedProperties(
        move_cost=move_cost,
        blocks_move=blocks_move,
        blocks_los=blocks_los,
        cover_flags=cover_flags,
        hazard_flags=hazard_flags,
        hazard_damage=hazard_damage,
        hazard_timing=hazard_timing,
    )


def _append_name(names: list[str], names_set: set[str], name: str) -> None:
    if name in names_set:
        return
    names.append(name)
    names_set.add(name)


def _append_name_if_available(
    names: list[str], names_set: set[str], name: str
) -> bool:
    if name not in TERRAIN_CATALOG:
        return False
    _append_name(names, names_set, name)
    return True


def _append_floor_overlay(names: list[str], names_set: set[str]) -> None:
    if not _append_name_if_available(names, names_set, "floor"):
        _append_name(names, names_set, "floor")


def _terrain_descriptors(_gid: int, resolved: _ResolvedProperties) -> list[str]:
    names: list[str] = []
    names_set: set[str] = set()
    if resolved.blocks_move:
        _append_name(names, names_set, "wall")
        return names

    move_cost = resolved.move_cost
    if move_cost <= 1:
        _append_floor_overlay(names, names_set)
    elif move_cost == 2:
        _append_name_if_available(names, names_set, "difficult")
        _append_floor_overlay(names, names_set)
    elif move_cost >= 3:
        _append_name_if_available(names, names_set, "very_difficult")
        _append_floor_overlay(names, names_set)
    else:
        _append_floor_overlay(names, names_set)

    cover_flags = resolved.cover_flags
    if cover_flags & TerrainFlags.FORTIFICATION and "fortification" in TERRAIN_CATALOG:
        _append_name_if_available(names, names_set, "fortification")
    elif cover_flags & TerrainFlags.COVER_HEAVY and "heavy_cover" in TERRAIN_CATALOG:
        _append_name_if_available(names, names_set, "heavy_cover")
    elif cover_flags & TerrainFlags.COVER_LIGHT and "light_cover" in TERRAIN_CATALOG:
        _append_name_if_available(names, names_set, "light_cover")

    hazard_names = _hazard_descriptors(_gid, resolved)
    for name in hazard_names:
        _append_name(names, names_set, name)

    if resolved.blocks_los and len(names) == 1 and names[0] == "floor":
        _append_name_if_available(names, names_set, "light_cover")

    return names


def _hazard_descriptors(_gid: int, resolved: _ResolvedProperties) -> list[str]:
    if resolved.hazard_damage <= 0:
        return []
    if (
        resolved.hazard_flags & TerrainFlags.VERY_HAZARDOUS
        or resolved.hazard_timing == "per_tile"
    ) and "hazard_severe" in TERRAIN_CATALOG:
        return ["hazard_severe"]
    if "hazard" in TERRAIN_CATALOG:
        return ["hazard"]
    return []


def _cover_descriptors(_gid: int, resolved: _ResolvedProperties) -> list[str]:
    cover_flags = resolved.cover_flags
    if cover_flags & TerrainFlags.FORTIFICATION and "fortification" in TERRAIN_CATALOG:
        return ["fortification"]
    if cover_flags & TerrainFlags.COVER_HEAVY and "heavy_cover" in TERRAIN_CATALOG:
        return ["heavy_cover"]
    if cover_flags & TerrainFlags.COVER_LIGHT and "light_cover" in TERRAIN_CATALOG:
        return ["light_cover"]
    return []


def _collision_descriptors(_gid: int, resolved: _ResolvedProperties) -> list[str]:
    if (
        "void" in TERRAIN_CATALOG
        and resolved.blocks_move
        and resolved.blocks_los
        and resolved.move_cost == 0
    ):
        return ["void"]
    if "wall" in TERRAIN_CATALOG and resolved.blocks_move:
        return ["wall"]
    return []


def _iter_tile_data(layer: TileLayer) -> Iterator[tuple[int, int, int]]:
    if layer.chunks:
        for chunk in layer.chunks:
            origin_x = int(chunk.coordinates.x)
            origin_y = int(chunk.coordinates.y)
            for row_index, row in enumerate(chunk.data):
                y = origin_y + row_index
                for column_index, gid in enumerate(row):
                    x = origin_x + column_index
                    yield x, y, gid
    elif layer.data:
        for y, row in enumerate(layer.data):
            for x, gid in enumerate(row):
                yield x, y, gid


def _add_descriptors(cells: list[list[list[str]]], x: int, y: int, names: list[str]) -> None:
    if not names:
        return
    if y < 0 or y >= len(cells) or x < 0 or x >= len(cells[y]):
        return
    cell = cells[y][x]
    for name in names:
        if name not in TERRAIN_CATALOG:
            logger.warning("Unknown terrain descriptor '%s' ignored during import", name)
            continue
        if name == "void" and "wall" in cell:
            # Walls take precedence over the auxiliary void descriptor emitted by
            # the collision layer. Retain the existing wall entry to preserve the
            # original MapSpec semantics.
            continue
        if name not in cell:
            cell.append(name)


def _apply_object_layer(
    cells: list[list[list[str]]],
    layer: ObjectLayer,
    descriptor: str,
    cell_size_x: int,
    cell_size_y: int,
) -> None:
    if cell_size_x <= 0 or cell_size_y <= 0:
        raise ValueError("Cell size must be positive when applying object layers")

    if descriptor not in TERRAIN_CATALOG:
        logger.warning("Unknown terrain descriptor '%s' for object layer", descriptor)
        return

    grid_height = len(cells)
    grid_width = len(cells[0]) if grid_height > 0 else 0

    for tiled_object in layer.tiled_objects:
        if not tiled_object.visible:
            continue

        x0 = float(tiled_object.coordinates.x) / cell_size_x
        y0 = float(tiled_object.coordinates.y) / cell_size_y
        width = float(tiled_object.size.width) / cell_size_x
        height = float(tiled_object.size.height) / cell_size_y

        min_x = max(0, int(math.floor(x0)))
        min_y = max(0, int(math.floor(y0)))
        max_x = min(grid_width, int(math.ceil(x0 + width))) if grid_width > 0 else 0
        max_y = min(grid_height, int(math.ceil(y0 + height))) if grid_height > 0 else 0

        if min_x >= grid_width or min_y >= grid_height or max_x <= 0 or max_y <= 0:
            continue

        if max_x <= min_x:
            max_x = min(min_x + 1, grid_width)
        if max_y <= min_y:
            max_y = min(min_y + 1, grid_height)

        for y in range(min_y, max_y):
            for x in range(min_x, max_x):
                cell = cells[y][x]
                if descriptor not in cell:
                    cell.append(descriptor)


class TiledImporter:
    """Load Tiled TMX maps and convert them to :class:`MapSpec` instances."""

    def load(self, path: str) -> MapSpec:
        source = Path(path)
        tiled_map = parse_map(source)
        width = int(tiled_map.map_size.width)
        height = int(tiled_map.map_size.height)
        tile_width = int(tiled_map.tile_size.width)
        tile_height = int(tiled_map.tile_size.height)

        if width <= 0 or height <= 0:
            raise ValueError("Map dimensions must be positive")
        if tile_width <= 0 or tile_height <= 0:
            raise ValueError("Map tiles must have a positive size")

        cells: list[list[list[str]]] = [
            [[] for _ in range(width)] for _ in range(height)
        ]

        gid_properties = _gather_tile_properties(tiled_map)

        layers_by_name: dict[str, Layer] = {
            layer.name: layer for layer in _iter_layers(tiled_map.layers)
        }

        def process_tile_layer(
            name: str, mapper: Callable[[int, _ResolvedProperties], list[str]]
        ) -> None:
            layer = layers_by_name.get(name)
            if not isinstance(layer, TileLayer) or layer.visible is False:
                return
            for x, y, raw_gid in _iter_tile_data(layer):
                gid = _normalise_gid(raw_gid)
                if gid == 0:
                    continue
                properties = gid_properties.get(gid, {})
                resolved = _resolve_properties(properties)
                names = mapper(gid, resolved)
                _add_descriptors(cells, x, y, names)

        tile_layer_keys = TILED_KEYS["tile_layers"]
        process_tile_layer(tile_layer_keys["terrain"], _terrain_descriptors)
        process_tile_layer(tile_layer_keys["hazard"], _hazard_descriptors)
        process_tile_layer(tile_layer_keys["cover"], _cover_descriptors)
        process_tile_layer(tile_layer_keys["collision"], _collision_descriptors)

        object_layer_keys = TILED_KEYS["object_layers"]
        for key, descriptor in OBJECT_LAYER_DESCRIPTORS.items():
            name = object_layer_keys.get(key)
            layer = layers_by_name.get(name)
            if isinstance(layer, ObjectLayer) and layer.visible:
                _apply_object_layer(cells, layer, descriptor, tile_width, tile_height)

        properties = tiled_map.properties or {}
        name = str(properties.get("name", source.stem))
        biome = str(properties.get("biome", ""))
        seed_value = properties.get("seed")
        seed: int | None = None
        if isinstance(seed_value, int):
            seed = seed_value
        elif isinstance(seed_value, str):
            try:
                seed = int(seed_value)
            except ValueError:
                pass

        spawn_property = properties.get("spawn_zones")
        spawn_zones: dict[str, SpawnZone] = {}
        if isinstance(spawn_property, str) and spawn_property:
            try:
                raw_spawn = json.loads(spawn_property)
            except json.JSONDecodeError:
                logger.warning("Invalid spawn_zones JSON in TMX properties; ignoring value")
            else:
                for label, entry in raw_spawn.items():
                    try:
                        x = int(entry["x"])
                        y = int(entry["y"])
                        zone_width = int(entry.get("width", 1))
                        zone_height = int(entry.get("height", 1))
                    except (KeyError, TypeError, ValueError):
                        logger.debug("Ignoring malformed spawn zone '%s' in TMX metadata", label)
                        continue
                    safe_radius = int(entry.get("safe_radius", 1))
                    allow_decor = bool(entry.get("allow_decor", False))
                    allow_hazard = bool(entry.get("allow_hazard", False))
                    spawn_zones[label] = SpawnZone(
                        label=label,
                        position=(x, y),
                        footprint=(zone_width, zone_height),
                        safe_radius=max(0, safe_radius),
                        allow_decor=allow_decor,
                        allow_hazard=allow_hazard,
                    )

        meta = MapMeta(name=name, biome=biome, seed=seed, spawn_zones=spawn_zones)

        if "floor" in TERRAIN_CATALOG:
            default_descriptor = "floor"
        elif TERRAIN_CATALOG:
            default_descriptor = next(iter(TERRAIN_CATALOG))
        else:
            logger.warning(
                "Terrain catalog is empty; using fallback default descriptor 'floor'"
            )
            default_descriptor = "floor"

        normalised_cells: list[list[str | list[str]]] = []
        for row in cells:
            normalised_row: list[str | list[str]] = []
            for cell in row:
                if not cell:
                    normalised_row.append(default_descriptor)
                elif len(cell) == 1:
                    normalised_row.append(cell[0])
                else:
                    normalised_row.append(cell[:])
            normalised_cells.append(normalised_row)

        if tile_width != tile_height:
            logger.warning(
                "Non-square tiles detected (%s x %s), using tile width as cell size",
                tile_width,
                tile_height,
            )
        cell_size = tile_width

        return MapSpec(
            width=width,
            height=height,
            cell_size=cell_size,
            meta=meta,
            cells=normalised_cells,
        )


__all__ = ["TiledImporter"]

