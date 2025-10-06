"""Biome-driven decoration helpers for generated maps."""
from __future__ import annotations

from collections import deque
from typing import Mapping, MutableSequence, Sequence

from modules.maps.gen.biomes import get_biome_rules
from modules.maps.gen.params import DecorDensity, MapGenParams
from modules.maps.gen.random import shuffle
from modules.maps.spec import CellSpec, MapSpec


Coord = tuple[int, int]
_CARDINALS: Sequence[Coord] = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _cell_names(cell: CellSpec) -> list[str]:
    if isinstance(cell, str):
        return [cell]
    return list(cell)


def _set_cell_names(spec: MapSpec, x: int, y: int, names: MutableSequence[str]) -> None:
    unique: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen:
            unique.append(name)
            seen.add(name)
    if len(unique) == 1:
        spec.cells[y][x] = unique[0]
    else:
        spec.cells[y][x] = list(unique)


def _apply_descriptor(spec: MapSpec, x: int, y: int, descriptor: str) -> None:
    names = _cell_names(spec.cells[y][x])
    if "wall" in names:
        return
    if "floor" not in names:
        names.insert(0, "floor")
    if descriptor not in names:
        names.append(descriptor)
    _set_cell_names(spec, x, y, names)


def _is_floor(cell: CellSpec) -> bool:
    names = _cell_names(cell)
    return "floor" in names


def _is_wall(cell: CellSpec) -> bool:
    names = _cell_names(cell)
    return "wall" in names or "void" in names


def _weighted_choice(rng, weights: Mapping[str, float]) -> str | None:
    items = [(key, float(value)) for key, value in weights.items() if value > 0]
    if not items:
        return None
    total = sum(weight for _, weight in items)
    pick = rng.random() * total
    acc = 0.0
    for key, weight in items:
        acc += weight
        if pick < acc:
            return key
    return items[-1][0]


def _resolve_zone_weights(
    mapping: Mapping[str, Mapping[str, float]], zone: str
) -> Mapping[str, float]:
    if zone in mapping:
        return mapping[zone]
    default = mapping.get("default")
    if default is not None:
        return default
    for weights in mapping.values():
        return weights
    return {}


def _classify_cells(spec: MapSpec) -> dict[str, list[Coord]]:
    width, height = spec.width, spec.height
    floor_cells: list[Coord] = []
    corridor_cells: list[Coord] = []
    secondary_corridors: list[Coord] = []
    room_edges: list[Coord] = []
    room_interior: list[Coord] = []
    open_cells: list[Coord] = []

    for y in range(height):
        for x in range(width):
            cell = spec.cells[y][x]
            if not _is_floor(cell):
                continue
            coord = (x, y)
            floor_cells.append(coord)

            floor_neighbours = 0
            wall_neighbours = 0
            for dx, dy in _CARDINALS:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    wall_neighbours += 1
                    continue
                neighbour = spec.cells[ny][nx]
                if _is_floor(neighbour):
                    floor_neighbours += 1
                elif _is_wall(neighbour):
                    wall_neighbours += 1

            is_corridor = floor_neighbours <= 2
            is_secondary = floor_neighbours <= 1
            is_edge = wall_neighbours > 0

            if is_corridor:
                corridor_cells.append(coord)
                if is_secondary:
                    secondary_corridors.append(coord)
            else:
                if is_edge:
                    room_edges.append(coord)
                else:
                    room_interior.append(coord)

            if not is_edge:
                open_cells.append(coord)

    secondary_set = set(secondary_corridors)
    corridor_primary = [coord for coord in corridor_cells if coord not in secondary_set]
    room_cells = room_interior + room_edges

    return {
        "floor": floor_cells,
        "corridor": corridor_primary,
        "secondary": secondary_corridors,
        "room_edge": room_edges,
        "room_interior": room_interior,
        "room": room_cells,
        "open": open_cells,
    }


def _collect_cluster(
    center: Coord,
    desired: int,
    candidates: set[Coord],
    used: set[Coord],
    width: int,
    height: int,
) -> list[Coord]:
    cluster: list[Coord] = []
    queue: deque[Coord] = deque([center])
    seen: set[Coord] = {center}

    while queue and len(cluster) < desired:
        x, y = queue.popleft()
        coord = (x, y)
        if coord in used or coord not in candidates:
            continue
        cluster.append(coord)
        for dx, dy in _CARDINALS:
            nx, ny = x + dx, y + dy
            neighbour = (nx, ny)
            if 0 <= nx < width and 0 <= ny < height and neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)

    return cluster


def _density_weights(
    mapping: Mapping[DecorDensity, Mapping[str, float]], density: DecorDensity
) -> Mapping[str, float]:
    try:
        return mapping[density]
    except KeyError as exc:  # pragma: no cover - guarded by :class:`MapGenParams`
        raise ValueError(f"unknown decor density '{density}'") from exc


def decorate(spec: MapSpec, params: MapGenParams, rng) -> MapSpec:
    """Apply biome-specific decoration to ``spec`` using ``params`` and ``rng``."""

    rules = get_biome_rules(params.biome)
    classified = _classify_cells(spec)
    floor_cells = classified["floor"]
    if not floor_cells:
        return spec

    total_floor = len(floor_cells)
    cover_target = min(int(round(total_floor * params.cover_ratio)), total_floor)
    difficult_target = min(int(round(total_floor * params.difficult_ratio)), total_floor)
    hazard_target = min(int(round(total_floor * params.hazard_ratio)), total_floor)

    used: set[Coord] = set()

    # --- Cover placement -------------------------------------------------
    cover_zone_cells = {
        "edge": list(classified["room_edge"]),
        "corridor": list(classified["corridor"]),
        "open": list(classified["room_interior"]),
    }
    for cells in cover_zone_cells.values():
        shuffle(rng, cells)

    cover_zone_weights = _density_weights(rules.cover_zone_weights, params.decor_density)
    cover_type_weights = rules.cover_type_weights

    cover_count = 0
    while cover_count < cover_target:
        available_zones = {
            zone: weight
            for zone, weight in cover_zone_weights.items()
            if cover_zone_cells.get(zone)
        }
        if not available_zones:
            break
        zone = _weighted_choice(rng, available_zones)
        if zone is None:
            break
        zone_cells = cover_zone_cells.get(zone)
        if not zone_cells:
            continue
        coord = zone_cells.pop()
        if coord in used:
            continue
        weights = _resolve_zone_weights(cover_type_weights, zone)
        cover_type = _weighted_choice(rng, weights)
        if cover_type is None:
            continue
        x, y = coord
        _apply_descriptor(spec, x, y, cover_type)
        used.add(coord)
        cover_count += 1

    # --- Difficult terrain placement ------------------------------------
    difficult_zone_cells = {
        "secondary": [coord for coord in classified["secondary"] if coord not in used],
        "corridor": [coord for coord in classified["corridor"] if coord not in used],
        "room": [coord for coord in classified["room"] if coord not in used],
    }
    for cells in difficult_zone_cells.values():
        shuffle(rng, cells)

    difficult_zone_weights = _density_weights(
        rules.difficult_zone_weights, params.decor_density
    )
    difficult_type_weights = rules.difficult_type_weights

    difficult_count = 0
    while difficult_count < difficult_target:
        available_zones = {
            zone: weight
            for zone, weight in difficult_zone_weights.items()
            if difficult_zone_cells.get(zone)
        }
        if not available_zones:
            break
        zone = _weighted_choice(rng, available_zones)
        if zone is None:
            break
        zone_cells = difficult_zone_cells.get(zone)
        if not zone_cells:
            continue
        coord = zone_cells.pop()
        if coord in used:
            continue
        terrain_type = _weighted_choice(rng, difficult_type_weights)
        if terrain_type is None:
            continue
        x, y = coord
        _apply_descriptor(spec, x, y, terrain_type)
        used.add(coord)
        difficult_count += 1

    # --- Hazard placement ------------------------------------------------
    hazard_candidates_set: set[Coord] = {
        coord for coord in classified["room_interior"] if coord not in used
    }
    if len(hazard_candidates_set) < hazard_target:
        hazard_candidates_set.update(
            coord for coord in classified["room_edge"] if coord not in used
        )
    if len(hazard_candidates_set) < hazard_target:
        hazard_candidates_set.update(
            coord for coord in classified["corridor"] if coord not in used
        )

    hazard_candidates: list[Coord] = list(hazard_candidates_set)
    shuffle(rng, hazard_candidates)
    hazard_set: set[Coord] = set(hazard_candidates)

    cluster_min, cluster_max = rules.hazard_cluster_size[params.decor_density]
    cluster_min = max(1, cluster_min)
    cluster_max = max(cluster_min, cluster_max)
    hazard_type_weights = rules.hazard_type_weights

    hazard_count = 0
    width, height = spec.width, spec.height
    while hazard_count < hazard_target and hazard_candidates:
        coord = hazard_candidates.pop()
        if coord in used or coord not in hazard_set:
            continue
        remaining = hazard_target - hazard_count
        desired = max(cluster_min, min(cluster_max, remaining))
        cluster = _collect_cluster(coord, desired, hazard_set, used, width, height)
        if not cluster:
            continue
        hazard_type = _weighted_choice(rng, hazard_type_weights)
        if hazard_type is None:
            break
        for cell in cluster:
            x, y = cell
            _apply_descriptor(spec, x, y, hazard_type)
            used.add(cell)
            hazard_set.discard(cell)
            hazard_count += 1
            if hazard_count >= hazard_target:
                break

    return spec


__all__ = ["decorate"]

