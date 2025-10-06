"""Spawn zone selection for generated maps."""
from __future__ import annotations

from collections import deque
from typing import Iterable, List, Sequence, Tuple

from core.pathfinding_optimization import OptimizedPathfinding
from modules.maps.components import SpawnZone
from modules.maps.spec import MapSpec, to_map_component
from modules.maps.terrain_types import TerrainFlags


_CARDINALS: Sequence[Tuple[int, int]] = ((1, 0), (-1, 0), (0, 1), (0, -1))
_CHEB_NEIGHBOURHOOD: Sequence[Tuple[int, int]] = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 0),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)
_FAIRNESS_THRESHOLD = 0.05
_FORBIDDEN_FLAGS = (
    TerrainFlags.COVER_LIGHT
    | TerrainFlags.COVER_HEAVY
    | TerrainFlags.FORTIFICATION
    | TerrainFlags.DIFFICULT
    | TerrainFlags.VERY_DIFFICULT
    | TerrainFlags.HAZARDOUS
    | TerrainFlags.VERY_HAZARDOUS
)


class _SpawnTerrain:
    """Minimal terrain adapter used for pathfinding distance checks."""

    def __init__(self, grid) -> None:
        self.width = grid.width
        self.height = grid.height
        wall_list: List[Tuple[int, int]] = []
        for y in range(self.height):
            for x in range(self.width):
                if grid.blocks_move_mask[y][x]:
                    wall_list.append((x, y))
        self.walls = set(wall_list)
        self.path_cache = None
        self.reachable_tiles_cache = None

    def is_walkable(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and (x, y) not in self.walls


def _is_walkable(grid, x: int, y: int) -> bool:
    return 0 <= x < grid.width and 0 <= y < grid.height and not grid.blocks_move_mask[y][x]


def _is_safe_area(
    grid,
    x: int,
    y: int,
    footprint: Tuple[int, int],
    clearance: int,
) -> bool:
    width, height = footprint
    if width <= 0 or height <= 0:
        return False
    if x < clearance or y < clearance:
        return False
    if x + width + clearance > grid.width:
        return False
    if y + height + clearance > grid.height:
        return False

    for ny in range(y - clearance, y + height + clearance):
        for nx in range(x - clearance, x + width + clearance):
            if not _is_walkable(grid, nx, ny):
                return False
            flags = TerrainFlags(grid.flags[ny][nx])
            if flags & _FORBIDDEN_FLAGS:
                return False
            if grid.hazard_damage[ny][nx] > 0:
                return False
    return True


def _collect_candidates(
    grid,
    footprint: Tuple[int, int],
    clearance: int,
) -> List[Tuple[int, int]]:
    width, height = footprint
    candidates: List[Tuple[int, int]] = []
    max_x = grid.width - width - clearance + 1
    max_y = grid.height - height - clearance + 1
    if max_x <= clearance or max_y <= clearance:
        return candidates
    for y in range(clearance, max_y):
        for x in range(clearance, max_x):
            if _is_safe_area(grid, x, y, footprint, clearance):
                candidates.append((x, y))
    return candidates


def _bfs_distances(grid, start: Tuple[int, int]) -> dict[Tuple[int, int], int]:
    queue: deque[Tuple[int, int]] = deque([start])
    distances: dict[Tuple[int, int], int] = {start: 0}
    while queue:
        x, y = queue.popleft()
        base_dist = distances[(x, y)]
        for dx, dy in _CARDINALS:
            nx, ny = x + dx, y + dy
            if not _is_walkable(grid, nx, ny):
                continue
            if (nx, ny) in distances:
                continue
            distances[(nx, ny)] = base_dist + 1
            queue.append((nx, ny))
    return distances


def _pick_spawn_pair(
    candidates: List[Tuple[int, int]],
    grid,
    pois: Sequence[Tuple[int, int]],
    optimizer: OptimizedPathfinding,
    footprint: Tuple[int, int],
) -> tuple[List[Tuple[int, int]], float]:
    if len(candidates) < 2:
        return (candidates[:], float("inf"))
    best_pair: tuple[Tuple[int, int], Tuple[int, int]] | None = None
    best_distance = -1
    best_ratio = float("inf")
    distance_cache: dict[Tuple[int, int], dict[Tuple[int, int], int]] = {}
    for idx, start in enumerate(candidates[:-1]):
        dist_map = distance_cache.setdefault(start, _bfs_distances(grid, start))
        for other in candidates[idx + 1 :]:
            pair_distance = dist_map.get(other)
            if pair_distance is None:
                continue
            ratio = _fairness_ratio(
                optimizer,
                [start, other],
                pois,
                footprint,
            )
            if ratio <= _FAIRNESS_THRESHOLD:
                if pair_distance > best_distance or best_pair is None:
                    best_distance = pair_distance
                    best_ratio = ratio
                    best_pair = (start, other)
            elif best_pair is None or ratio < best_ratio:
                best_pair = (start, other)
                best_distance = pair_distance
                best_ratio = ratio
    if best_pair is None:
        best_pair = (candidates[0], candidates[1])
    return [best_pair[0], best_pair[1]], best_ratio


def _nearest_walkable(grid, target: Tuple[int, int]) -> Tuple[int, int] | None:
    tx, ty = target
    if _is_walkable(grid, tx, ty):
        return target
    queue: deque[Tuple[int, int]] = deque([target])
    seen = {target}
    while queue:
        x, y = queue.popleft()
        for dx, dy in _CHEB_NEIGHBOURHOOD:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < grid.width and 0 <= ny < grid.height):
                continue
            if (nx, ny) in seen:
                continue
            seen.add((nx, ny))
            if _is_walkable(grid, nx, ny):
                return (nx, ny)
            queue.append((nx, ny))
    return None


def _determine_pois(grid) -> List[Tuple[int, int]]:
    width, height = grid.width, grid.height
    raw_points = {
        (width // 2, height // 2),
        (width // 4, height // 2),
        (3 * width // 4, height // 2),
        (width // 2, height // 4),
        (width // 2, 3 * height // 4),
    }
    pois: List[Tuple[int, int]] = []
    for point in raw_points:
        candidate = _nearest_walkable(grid, point)
        if candidate is not None and candidate not in pois:
            pois.append(candidate)
    return pois


def _path_length(optimizer: OptimizedPathfinding, start: Tuple[int, int], end: Tuple[int, int]) -> float:
    if start == end:
        return 0.0
    path = optimizer._compute_path_astar(start, end)
    if not path:
        return float("inf")
    return float(len(path) - 1)


def _spawn_cells(position: Tuple[int, int], footprint: Tuple[int, int]) -> List[Tuple[int, int]]:
    x, y = position
    width, height = footprint
    return [
        (x + dx, y + dy)
        for dy in range(height)
        for dx in range(width)
    ]


def _spawn_distance(
    optimizer: OptimizedPathfinding,
    position: Tuple[int, int],
    footprint: Tuple[int, int],
    poi: Tuple[int, int],
) -> float:
    best = float("inf")
    for cell in _spawn_cells(position, footprint):
        length = _path_length(optimizer, cell, poi)
        if length < best:
            best = length
    return best


def _fairness_ratio(
    optimizer: OptimizedPathfinding,
    spawns: Sequence[SpawnZone | Tuple[int, int]],
    pois: Sequence[Tuple[int, int]],
    footprint: Tuple[int, int] = (1, 1),
) -> float:
    spawn_infos: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
    for spawn in spawns:
        if hasattr(spawn, "position") and hasattr(spawn, "footprint"):
            spawn_infos.append((spawn.position, spawn.footprint))
        else:
            spawn_infos.append((spawn, footprint))

    worst = 0.0
    for poi in pois:
        distances: List[float] = []
        unreachable = False
        for position, spawn_footprint in spawn_infos:
            length = _spawn_distance(optimizer, position, spawn_footprint, poi)
            if length == float("inf"):
                unreachable = True
                break
            distances.append(length)
        if unreachable or not distances:
            continue
        avg = sum(distances) / len(distances)
        if avg == 0:
            continue
        delta = max(distances) - min(distances)
        worst = max(worst, delta / avg)
    return worst


def _neighbourhood_candidates(
    center: Tuple[int, int],
    candidates: set[Tuple[int, int]],
    radius: int,
) -> Iterable[Tuple[int, int]]:
    cx, cy = center
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            nx, ny = cx + dx, cy + dy
            if abs(dx) + abs(dy) > radius:
                continue
            coord = (nx, ny)
            if coord in candidates:
                yield coord


def _improve_fairness(
    optimizer: OptimizedPathfinding,
    spawns: List[Tuple[int, int]],
    pois: Sequence[Tuple[int, int]],
    candidates: set[Tuple[int, int]],
    footprint: Tuple[int, int],
) -> List[Tuple[int, int]]:
    if not candidates:
        return list(spawns)

    best = list(spawns)
    best_ratio = _fairness_ratio(optimizer, best, pois, footprint)
    if best_ratio <= _FAIRNESS_THRESHOLD:
        return best
    max_iterations = 12
    for _ in range(max_iterations):
        improved = False
        for idx, position in enumerate(list(best)):
            for candidate in _neighbourhood_candidates(position, candidates, radius=4):
                if candidate == position:
                    continue
                if candidate in best:
                    continue
                trial = list(best)
                trial[idx] = candidate
                ratio = _fairness_ratio(optimizer, trial, pois, footprint)
                if ratio < best_ratio:
                    best = trial
                    best_ratio = ratio
                    improved = True
                    break
            if improved and best_ratio <= _FAIRNESS_THRESHOLD:
                return best
        if not improved:
            break
    return best


def assign_spawn_zones(
    spec: MapSpec,
    max_spawns: int = 2,
    *,
    footprint: Tuple[int, int] = (1, 1),
    clearance: int = 1,
    enforce_fairness: bool = True,
) -> MapSpec:
    """Assign spawn zones to ``spec`` ensuring fairness and safety constraints."""

    if max_spawns < 2:
        raise ValueError("at least two spawn zones are required")
    width, height = footprint
    if width <= 0 or height <= 0:
        raise ValueError("footprint dimensions must be positive")
    clearance = max(0, clearance)

    component = to_map_component(spec)
    grid = component.grid

    safe_clearance = clearance
    candidates = _collect_candidates(grid, footprint, safe_clearance)
    allow_decor = False
    if len(candidates) < max_spawns:
        safe_clearance = 0
        candidates = _collect_candidates(grid, footprint, safe_clearance)
        allow_decor = True
    if len(candidates) < max_spawns:
        raise RuntimeError("unable to place spawn zones: insufficient safe tiles")

    terrain = _SpawnTerrain(grid)
    optimizer = OptimizedPathfinding(terrain)
    optimizer.min_region_size = max(8, min(grid.width, grid.height) // 2)
    optimizer.precompute_paths()

    pois = _determine_pois(grid)
    spawn_positions, _ = _pick_spawn_pair(candidates, grid, pois, optimizer, footprint)
    spawn_positions = spawn_positions[:max_spawns]
    if len(spawn_positions) < max_spawns:
        remaining = [coord for coord in candidates if coord not in spawn_positions]
        spawn_positions.extend(remaining[: max_spawns - len(spawn_positions)])
    spawn_positions = _improve_fairness(
        optimizer,
        spawn_positions,
        pois,
        set(candidates),
        footprint,
    )
    ratio = _fairness_ratio(optimizer, spawn_positions, pois, footprint)
    if enforce_fairness and ratio > _FAIRNESS_THRESHOLD:
        raise RuntimeError("failed to produce fair spawn distribution")

    labels = ["spawn_A", "spawn_B", "spawn_C", "spawn_D"]
    zones = {
        label: SpawnZone(
            label=label,
            position=position,
            footprint=footprint,
            safe_radius=safe_clearance,
            allow_decor=allow_decor,
            allow_hazard=False,
        )
        for label, position in zip(labels, spawn_positions)
    }
    spec.meta.spawn_zones = zones
    return spec


__all__ = ["assign_spawn_zones"]
