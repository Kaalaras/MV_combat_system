"""Spawn zone selection for generated maps."""
from __future__ import annotations

from collections import deque
from typing import Iterable, List, Sequence, Tuple

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


def _fairness_tolerance(footprint: Tuple[int, int]) -> float:
    width, height = footprint
    area = max(1, width) * max(1, height)
    tolerance = _FAIRNESS_THRESHOLD + 0.04 * max(0, area - 1)
    return min(0.25, tolerance)


def _is_walkable(grid, x: int, y: int) -> bool:
    return 0 <= x < grid.width and 0 <= y < grid.height and not grid.blocks_move_mask[y][x]


def _rectangles_overlap(
    a_pos: Tuple[int, int],
    a_size: Tuple[int, int],
    b_pos: Tuple[int, int],
    b_size: Tuple[int, int],
) -> bool:
    ax, ay = a_pos
    aw, ah = a_size
    bx, by = b_pos
    bw, bh = b_size
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return False
    if ax + aw <= bx or bx + bw <= ax:
        return False
    if ay + ah <= by or by + bh <= ay:
        return False
    return True


def _is_disjoint(
    position: Tuple[int, int],
    others: Sequence[Tuple[int, int]],
    footprint: Tuple[int, int],
) -> bool:
    return all(
        not _rectangles_overlap(position, footprint, other, footprint)
        for other in others
    )


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
    footprint: Tuple[int, int],
    require_reachability: bool = True,
) -> tuple[List[Tuple[int, int]], float]:
    tolerance = _fairness_tolerance(footprint)
    if len(candidates) < 2:
        return (candidates[:], float("inf"))
    distance_cache: dict[Tuple[int, int], dict[Tuple[int, int], int]] = {}
    fairness_cache: dict[
        tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]],
        float,
    ] = {}
    evaluated: List[tuple[tuple[int, float, float], Tuple[int, int], Tuple[int, int], float]] = []
    for idx, start in enumerate(candidates[:-1]):
        dist_map = distance_cache.setdefault(start, _bfs_distances(grid, start))
        for other in candidates[idx + 1 :]:
            if _rectangles_overlap(start, footprint, other, footprint):
                continue
            pair_distance = dist_map.get(other)
            if pair_distance is None:
                pair_distance = -1
            ratio = _fairness_ratio(
                grid,
                [start, other],
                pois,
                footprint,
                fairness_cache,
            )
            category = 0 if ratio <= tolerance else 1
            score = (category, ratio, -pair_distance)
            evaluated.append((score, start, other, ratio))
    evaluated.sort(key=lambda item: item[0])
    if not evaluated:
        grid_width = getattr(grid, "width", "unknown")
        grid_height = getattr(grid, "height", "unknown")
        raise RuntimeError(
            "Unable to find two disjoint spawn positions: "
            f"{len(candidates)} candidate(s) found for footprint {footprint} "
            f"on grid size ({grid_width}x{grid_height}). "
            "This may be due to insufficient safe areas, the footprint being too large for the map, "
            "or the map being too small."
        )
    reachable_entry: tuple[tuple[int, float, float], Tuple[int, int], Tuple[int, int], float] | None = None
    for entry in evaluated:
        _, first, second, ratio = entry
        if _spawns_are_mutually_reachable(
            grid,
            [first, second],
            footprint,
            fairness_cache,
        ):
            reachable_entry = entry
            break
    if reachable_entry is not None:
        _, first, second, ratio = reachable_entry
        return [first, second], ratio
    if not require_reachability:
        _, first, second, ratio = evaluated[0]
        return [first, second], ratio
    raise RuntimeError("unable to find mutually reachable spawn positions")


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


def _is_footprint_valid(grid, top_left: Tuple[int, int], footprint: Tuple[int, int]) -> bool:
    x, y = top_left
    width, height = footprint
    if width <= 0 or height <= 0:
        return False
    if x < 0 or y < 0:
        return False
    if x + width > grid.width:
        return False
    if y + height > grid.height:
        return False
    for dy in range(height):
        for dx in range(width):
            if not _is_walkable(grid, x + dx, y + dy):
                return False
    return True


def _footprint_cells(position: Tuple[int, int], footprint: Tuple[int, int]) -> List[Tuple[int, int]]:
    x, y = position
    width, height = footprint
    return [
        (x + dx, y + dy)
        for dy in range(height)
        for dx in range(width)
    ]


def _footprint_path_length(
    grid,
    start: Tuple[int, int],
    footprint: Tuple[int, int],
    poi: Tuple[int, int],
) -> float:
    if not _is_footprint_valid(grid, start, footprint):
        return float("inf")
    width, height = footprint
    queue: deque[Tuple[int, int, int]] = deque([(start[0], start[1], 0)])
    seen = {start}
    goal_offsets = [(dx, dy) for dy in range(height) for dx in range(width)]
    while queue:
        x, y, dist = queue.popleft()
        if any(x + dx == poi[0] and y + dy == poi[1] for dx, dy in goal_offsets):
            return float(dist)
        for dx, dy in _CARDINALS:
            nx, ny = x + dx, y + dy
            candidate = (nx, ny)
            if candidate in seen:
                continue
            if not _is_footprint_valid(grid, candidate, footprint):
                continue
            seen.add(candidate)
            queue.append((nx, ny, dist + 1))
    return float("inf")


def _fairness_ratio(
    grid,
    spawns: Sequence[SpawnZone | Tuple[int, int]],
    pois: Sequence[Tuple[int, int]],
    footprint: Tuple[int, int] = (1, 1),
    distance_cache: dict[
        tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]],
        float,
    ] | None = None,
) -> float:
    spawn_infos: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
    for spawn in spawns:
        if isinstance(spawn, SpawnZone):
            spawn_infos.append((spawn.position, spawn.footprint))
        else:
            spawn_infos.append((spawn, footprint))

    if distance_cache is None:
        distance_cache = {}

    worst = 0.0
    for poi in pois:
        distances: List[float] = []
        unreachable = False
        for position, spawn_footprint in spawn_infos:
            key = (position, spawn_footprint, poi)
            length = distance_cache.get(key)
            if length is None:
                length = _footprint_path_length(grid, position, spawn_footprint, poi)
                distance_cache[key] = length
            if length == float("inf"):
                unreachable = True
                break
            distances.append(length)
        if unreachable:
            continue
        if not distances:
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
    spawns: List[Tuple[int, int]],
    pois: Sequence[Tuple[int, int]],
    candidates: set[Tuple[int, int]],
    grid,
    footprint: Tuple[int, int],
) -> List[Tuple[int, int]]:
    if not candidates:
        return list(spawns)

    best = list(spawns)
    distance_cache: dict[
        tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]],
        float,
    ] = {}
    best_ratio = _fairness_ratio(grid, best, pois, footprint, distance_cache)
    tolerance = _fairness_tolerance(footprint)
    if best_ratio <= tolerance:
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
                if not _is_disjoint(candidate, [pos for j, pos in enumerate(best) if j != idx], footprint):
                    continue
                trial = list(best)
                trial[idx] = candidate
                ratio = _fairness_ratio(grid, trial, pois, footprint, distance_cache)
                if ratio < best_ratio:
                    best = trial
                    best_ratio = ratio
                    improved = True
                    break
            if improved and best_ratio <= tolerance:
                return best
        if not improved:
            break
    return best


def _spawns_are_mutually_reachable(
    grid,
    spawns: Sequence[Tuple[int, int]],
    footprint: Tuple[int, int],
    distance_cache: dict[
        tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]],
        float,
    ],
) -> bool:
    if len(spawns) < 2:
        return True
    target_offsets = _footprint_cells((0, 0), footprint)
    for idx, start in enumerate(spawns[:-1]):
        for other in spawns[idx + 1 :]:
            if not _can_reach_target(grid, start, other, footprint, target_offsets, distance_cache):
                return False
            if not _can_reach_target(grid, other, start, footprint, target_offsets, distance_cache):
                return False
    return True


def _can_reach_target(
    grid,
    start: Tuple[int, int],
    target: Tuple[int, int],
    footprint: Tuple[int, int],
    target_offsets: Sequence[Tuple[int, int]],
    distance_cache: dict[
        tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]],
        float,
    ],
) -> bool:
    tx, ty = target
    for dx, dy in target_offsets:
        poi = (tx + dx, ty + dy)
        key = (start, footprint, poi)
        length = distance_cache.get(key)
        if length is None:
            length = _footprint_path_length(grid, start, footprint, poi)
            distance_cache[key] = length
        if length != float("inf"):
            return True
    return False


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

    pois = _determine_pois(grid)
    spawn_positions, _ = _pick_spawn_pair(
        candidates,
        grid,
        pois,
        footprint,
        require_reachability=enforce_fairness,
    )
    spawn_positions = spawn_positions[:max_spawns]
    for candidate in candidates:
        if len(spawn_positions) >= max_spawns:
            break
        if candidate in spawn_positions:
            continue
        if not _is_disjoint(candidate, spawn_positions, footprint):
            continue
        spawn_positions.append(candidate)
    if len(spawn_positions) < max_spawns:
        raise RuntimeError("unable to place non-overlapping spawn zones")
    spawn_positions = _improve_fairness(
        spawn_positions,
        pois,
        set(candidates),
        grid,
        footprint,
    )
    distance_cache: dict[
        tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]],
        float,
    ] = {}
    if enforce_fairness and not _spawns_are_mutually_reachable(
        grid, spawn_positions, footprint, distance_cache
    ):
        raise RuntimeError("spawn zones are mutually unreachable")
    ratio = _fairness_ratio(grid, spawn_positions, pois, footprint, distance_cache)
    tolerance = _fairness_tolerance(footprint)
    if enforce_fairness and ratio > tolerance:
        raise RuntimeError("failed to produce fair spawn distribution")

    for idx, current in enumerate(spawn_positions):
        for other in spawn_positions[idx + 1 :]:
            if _rectangles_overlap(current, footprint, other, footprint):
                raise RuntimeError("spawn zones overlap after optimization")

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
