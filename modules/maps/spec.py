"""Serialization helpers for map specifications."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Sequence

import json

from modules.maps.components import MapComponent, MapGrid, MapMeta
from modules.maps.terrain_types import (
    TERRAIN_CATALOG,
    TerrainDescriptor,
    TerrainFlags,
    combine,
)


CellSpec = str | list[str]


def _descriptor_signature(descriptor: TerrainDescriptor) -> tuple[int, int | None, int]:
    """Return a stable signature tuple for a terrain descriptor.

    The tuple consists of the descriptor's flags, movement cost (``None`` for
    impassable tiles) and hazard damage values.  This information is sufficient
    to uniquely identify descriptors – including combined terrains – when
    round-tripping between :class:`MapSpec` instances and ECS grid data.
    """
    move_cost = descriptor.move_cost
    if move_cost is not None:
        move_cost = int(move_cost)
    return (int(descriptor.flags), move_cost, int(descriptor.hazard_damage))


def _normalise_cell_value(value: CellSpec) -> list[str] | str:
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item) for item in value]
    raise TypeError("cell values must be strings or sequences of strings")


@dataclass(slots=True)
class MapSpec:
    """Data transfer object describing a map."""

    width: int
    height: int
    cell_size: int
    meta: MapMeta
    cells: list[list[CellSpec]]

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if self.cell_size <= 0:
            raise ValueError("cell_size must be positive")
        if not isinstance(self.meta, MapMeta):
            raise TypeError("meta must be an instance of MapMeta")

        if len(self.cells) != self.height:
            raise ValueError("cells height does not match height")

        normalised_rows: list[list[CellSpec]] = []
        for row in self.cells:
            if len(row) != self.width:
                raise ValueError("cells width does not match width")
            normalised_row: list[CellSpec] = []
            for cell in row:
                normalised = _normalise_cell_value(cell)
                if isinstance(normalised, list):
                    if not normalised:
                        raise ValueError("cell combination cannot be empty")
                    if not all(isinstance(item, str) for item in normalised):
                        raise TypeError("cell combination values must be strings")
                normalised_row.append(normalised)
            normalised_rows.append(normalised_row)

        self.cells = normalised_rows

    def save_json(self, path: str | Path) -> None:
        save_json(self, path)

    @staticmethod
    def load_json(path: str | Path) -> "MapSpec":
        return load_json(path)


def _cell_to_descriptor(cell: CellSpec) -> TerrainDescriptor:
    if isinstance(cell, str):
        try:
            return TERRAIN_CATALOG[cell]
        except KeyError as exc:
            raise KeyError(f"unknown terrain descriptor '{cell}'") from exc
    if not cell:
        raise ValueError("combined terrain cell cannot be empty")
    names = list(cell)
    for name in names:
        if name not in TERRAIN_CATALOG:
            raise KeyError(f"unknown terrain descriptor '{name}'")
    if len(names) == 1:
        return TERRAIN_CATALOG[names[0]]
    return combine(*names)


def to_map_component(spec: MapSpec) -> MapComponent:
    """Instantiate a :class:`MapComponent` from a :class:`MapSpec`."""

    grid = MapGrid(spec.width, spec.height, spec.cell_size)
    for y in range(spec.height):
        for x in range(spec.width):
            descriptor = _cell_to_descriptor(spec.cells[y][x])
            grid.set_cell(x, y, descriptor)

    meta = MapMeta(name=spec.meta.name, biome=spec.meta.biome, seed=spec.meta.seed)
    return MapComponent(grid=grid, meta=meta)


def _build_signature_catalog() -> tuple[
    dict[tuple[int, int | None, int], list[str]], list[str]
]:
    """Construct a reverse lookup from descriptor signatures to names.

    The initial catalog only contains base descriptors; combinations are
    generated lazily to avoid eagerly materialising the entire ``2^n`` search
    space when the terrain catalog grows.  The returned tuple provides both the
    populated catalog and the ordered descriptor name list used for future
    combination expansion.
    """

    names = sorted(TERRAIN_CATALOG.keys())
    catalog: dict[tuple[int, int | None, int], list[str]] = {}
    for name in names:
        descriptor = TERRAIN_CATALOG[name]
        catalog.setdefault(_descriptor_signature(descriptor), [name])

    return catalog, names


class _SignatureCatalog:
    """Lazily populated descriptor signature lookup."""

    __slots__ = ("_catalog", "_names", "_max_size")

    def __init__(self) -> None:
        catalog, names = _build_signature_catalog()
        self._catalog = catalog
        self._names = names
        # Base descriptors are already present; combinations start from size two.
        self._max_size = 1

    def _populate_until(self, target_size: int) -> None:
        """Ensure the catalog contains combinations up to ``target_size``."""

        while self._max_size < target_size:
            next_size = self._max_size + 1
            for combo in combinations(self._names, next_size):
                descriptor = combine(*combo)
                self._catalog.setdefault(
                    _descriptor_signature(descriptor),
                    list(combo),
                )
            self._max_size = next_size

    def resolve(self, signature: tuple[int, int | None, int]) -> list[str]:
        """Return the descriptor names for ``signature`` or raise an error."""

        names = self._catalog.get(signature)
        if names is not None:
            return names

        max_size = len(self._names)
        while self._max_size < max_size:
            self._populate_until(self._max_size + 1)
            names = self._catalog.get(signature)
            if names is not None:
                return names

        raise ValueError(
            "no terrain descriptor combination matches cell signature "
            f"{signature}"
        )


def _grid_signature(grid: MapGrid, x: int, y: int) -> tuple[int, int | None, int]:
    """Compute a signature tuple for a cell in the ECS grid.

    Parameters
    ----------
    grid:
        The :class:`MapGrid` from which to extract the cell data.
    x, y:
        The cell coordinates within ``grid``.

    Returns
    -------
    tuple[int, int | None, int]
        A signature mirroring :func:`_descriptor_signature`, using the stored
        flag, movement cost and hazard damage values for the targeted cell.
    """
    flags_value = int(grid.flags[y][x])
    move_cost_value = int(grid.move_cost[y][x])
    hazard_damage = int(grid.hazard_damage[y][x])
    flags = TerrainFlags(flags_value)
    if flags & TerrainFlags.IMPASSABLE:
        move_cost: int | None = None
    else:
        move_cost = move_cost_value
    return (flags_value, move_cost, hazard_damage)


_SIGNATURE_CATALOG = _SignatureCatalog()


def from_map_component(map_component: MapComponent) -> MapSpec:
    """Convert a :class:`MapComponent` into a :class:`MapSpec`."""

    grid = map_component.grid
    cells: list[list[CellSpec]] = []
    for y in range(grid.height):
        row: list[CellSpec] = []
        for x in range(grid.width):
            signature = _grid_signature(grid, x, y)
            names = _SIGNATURE_CATALOG.resolve(signature)
            if len(names) == 1:
                row.append(names[0])
            else:
                row.append(list(names))
        cells.append(row)

    meta = MapMeta(
        name=map_component.meta.name,
        biome=map_component.meta.biome,
        seed=map_component.meta.seed,
    )

    return MapSpec(
        width=grid.width,
        height=grid.height,
        cell_size=grid.cell_size,
        meta=meta,
        cells=cells,
    )


def save_json(spec: MapSpec, path: str | Path) -> None:
    """Serialise a :class:`MapSpec` to JSON on disk."""

    data = {
        "width": spec.width,
        "height": spec.height,
        "cell_size": spec.cell_size,
        "meta": {
            "name": spec.meta.name,
            "biome": spec.meta.biome,
            "seed": spec.meta.seed,
        },
        "cells": spec.cells,
    }
    destination = Path(path)
    destination.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_json(path: str | Path) -> MapSpec:
    """Load a :class:`MapSpec` from JSON data on disk."""

    source = Path(path)
    text = source.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise json.JSONDecodeError(
            f"Error parsing JSON in file '{source}': {exc.msg}",
            exc.doc,
            exc.pos,
        ) from exc
    meta_data = data.get("meta", {})
    meta = MapMeta(
        name=meta_data.get("name", ""),
        biome=meta_data.get("biome", ""),
        seed=meta_data.get("seed"),
    )
    cells_data = data.get("cells", [])
    cells: list[list[CellSpec]] = []
    for row in cells_data:
        cells.append([_normalise_cell_value(cell) for cell in row])

    try:
        width = int(data["width"])
        height = int(data["height"])
        cell_size = int(data["cell_size"])
    except KeyError as exc:
        raise KeyError(
            f"Missing required field in map JSON data: {exc.args[0]!r}"
        ) from exc

    return MapSpec(
        width=width,
        height=height,
        cell_size=cell_size,
        meta=meta,
        cells=cells,
    )


__all__ = [
    "MapSpec",
    "to_map_component",
    "from_map_component",
    "save_json",
    "load_json",
]

