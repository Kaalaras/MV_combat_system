"""Validation and fix-ups for procedurally generated maps."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import combinations
from typing import Callable, Iterable, List, Sequence, Set, Tuple

from modules.maps.components import SpawnZone
from modules.maps.spec import MapSpec, to_map_component


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    fixed: bool


_CARDINALS: Tuple[Tuple[int, int], ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))


class MapValidator:
    """Validate maps for connectivity and chokepoint resilience."""

    def __init__(self, spec: MapSpec) -> None:
        self.spec = spec
        self._refresh()

    def _refresh(self) -> None:
        component = to_map_component(self.spec)
        self.grid = component.grid
        self.width = self.grid.width
        self.height = self.grid.height

    def is_valid(self) -> bool:
        if len(self._connected_components()) > 1:
            return False
        return self._has_min_cut_for_spawns(2)

    def validate(self) -> ValidationResult:
        components = self._connected_components()
        if len(components) > 1:
            if self._fix_connectivity(components):
                self._refresh()
                return ValidationResult(valid=False, fixed=True)
            return ValidationResult(valid=False, fixed=False)

        if not self._has_min_cut_for_spawns(2):
            if self._fix_chokepoints():
                self._refresh()
                return ValidationResult(valid=False, fixed=True)
            return ValidationResult(valid=False, fixed=False)

        return ValidationResult(valid=True, fixed=False)

    def _connected_components(self) -> List[Set[Tuple[int, int]]]:
        visited: Set[Tuple[int, int]] = set()
        components: List[Set[Tuple[int, int]]] = []
        for y in range(self.height):
            for x in range(self.width):
                if self.grid.blocks_move_mask[y][x]:
                    continue
                coord = (x, y)
                if coord in visited:
                    continue
                component = self._flood_fill(coord, visited)
                components.append(component)
        return components

    def _flood_fill(
        self,
        start: Tuple[int, int],
        visited: Set[Tuple[int, int]],
    ) -> Set[Tuple[int, int]]:
        queue: deque[Tuple[int, int]] = deque([start])
        component: Set[Tuple[int, int]] = {start}
        visited.add(start)
        while queue:
            x, y = queue.popleft()
            for dx, dy in _CARDINALS:
                nx, ny = x + dx, y + dy
                neighbour = (nx, ny)
                if not self._is_walkable(nx, ny):
                    continue
                if neighbour in visited:
                    continue
                visited.add(neighbour)
                component.add(neighbour)
                queue.append(neighbour)
        return component

    def _is_walkable_footprint(
        self,
        x: int,
        y: int,
        footprint: Tuple[int, int],
    ) -> bool:
        width, height = footprint
        if width <= 0 or height <= 0:
            return False
        if x < 0 or y < 0:
            return False
        if x + width > self.width or y + height > self.height:
            return False
        for oy in range(height):
            for ox in range(width):
                if self.grid.blocks_move_mask[y + oy][x + ox]:
                    return False
        return True

    def _footprint_neighbours(
        self,
        x: int,
        y: int,
        footprint: Tuple[int, int],
    ) -> Iterable[Tuple[int, int]]:
        for dx, dy in _CARDINALS:
            nx, ny = x + dx, y + dy
            if self._is_walkable_footprint(nx, ny, footprint):
                yield (nx, ny)

    def _flood_fill_footprint(
        self,
        start: Tuple[int, int],
        visited: Set[Tuple[int, int]],
        footprint: Tuple[int, int],
    ) -> Set[Tuple[int, int]]:
        queue: deque[Tuple[int, int]] = deque([start])
        component: Set[Tuple[int, int]] = {start}
        visited.add(start)
        while queue:
            x, y = queue.popleft()
            for neighbour in self._footprint_neighbours(x, y, footprint):
                if neighbour in visited:
                    continue
                visited.add(neighbour)
                component.add(neighbour)
                queue.append(neighbour)
        return component

    def _is_walkable(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and not self.grid.blocks_move_mask[y][x]

    def _set_floor(self, x: int, y: int) -> None:
        if 0 <= x < self.spec.width and 0 <= y < self.spec.height:
            self.spec.cells[y][x] = "floor"

    def _fix_connectivity(self, components: Sequence[Set[Tuple[int, int]]]) -> bool:
        if len(components) <= 1:
            return False
        base = max(components, key=len)
        others = [comp for comp in components if comp is not base]
        for comp in others:
            if self._bridge_components(base, comp):
                return True
        return False

    def _bridge_components(
        self,
        base: Set[Tuple[int, int]],
        other: Set[Tuple[int, int]],
    ) -> bool:
        # Attempt direct bridge by widening wall between adjacent components.
        for x, y in other:
            for dx, dy in _CARDINALS:
                wx, wy = x + dx, y + dy
                tx, ty = x + 2 * dx, y + 2 * dy
                if not (0 <= wx < self.width and 0 <= wy < self.height):
                    continue
                if not (0 <= tx < self.width and 0 <= ty < self.height):
                    continue
                if (tx, ty) not in base:
                    continue
                if not self.grid.blocks_move_mask[wy][wx]:
                    continue
                self._set_floor(wx, wy)
                return True
        # Fallback: carve a Manhattan corridor between closest cells.
        closest_pair = None
        best_distance = None
        for bx, by in base:
            for ox, oy in other:
                distance = abs(bx - ox) + abs(by - oy)
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    closest_pair = ((bx, by), (ox, oy))
        if closest_pair is None:
            return False
        (bx, by), (ox, oy) = closest_pair
        x, y = ox, oy
        while x != bx:
            x += 1 if bx > x else -1
            self._set_floor(x, y)
        while y != by:
            y += 1 if by > y else -1
            self._set_floor(x, y)
        return True

    def _ordered_spawn_zones(self) -> List[SpawnZone]:
        zones = self.spec.meta.spawn_zones
        return [zones[key] for key in sorted(zones.keys())]

    def _spawn_positions(self) -> List[Tuple[int, int]]:
        return [zone.position for zone in self._ordered_spawn_zones()]

    def _primary_spawn_pair(self) -> tuple[SpawnZone, SpawnZone] | None:
        ordered = self._ordered_spawn_zones()
        if len(ordered) < 2:
            return None
        return ordered[0], ordered[1]

    def _spawn_footprints(self) -> List[Tuple[int, int]]:
        pair = self._primary_spawn_pair()
        if pair is None:
            return []
        footprints: List[Tuple[int, int]] = []
        for zone in pair:
            width, height = zone.footprint
            width = max(1, int(width))
            height = max(1, int(height))
            footprint = (width, height)
            if footprint not in footprints:
                footprints.append(footprint)
        if not footprints:
            footprints.append((1, 1))
        return footprints

    def _has_min_cut_for_spawns(self, required: int) -> bool:
        pair = self._primary_spawn_pair()
        if pair is None:
            return True
        if required <= 1:
            return True
        start_zone, goal_zone = pair
        start, goal = start_zone.position, goal_zone.position
        for footprint in self._spawn_footprints():
            if not self._has_min_cut(start, goal, footprint, required):
                return False
        return True

    def _has_min_cut(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        footprint: Tuple[int, int],
        required: int,
    ) -> bool:
        if required <= 1:
            return True
        if not self._is_walkable_footprint(start[0], start[1], footprint):
            return False
        if not self._is_walkable_footprint(goal[0], goal[1], footprint):
            return False
        if required == 2:
            return not self._critical_points(start, goal, footprint)
        reachable = self._flood_fill_footprint(start, set(), footprint)
        if goal not in reachable:
            return False
        candidates = [node for node in reachable if node not in (start, goal)]
        max_blockers = min(required - 1, len(candidates))
        for size in range(1, required):
            if size > max_blockers:
                break
            for blocked in combinations(candidates, size):
                if self._disconnects(start, goal, blocked, footprint):
                    return False
        return True

    def _critical_points(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        footprint: Tuple[int, int],
    ) -> List[Tuple[int, int]]:
        reachable = self._flood_fill_footprint(start, set(), footprint)
        if goal not in reachable:
            return [start]
        adjacency = self._build_adjacency(reachable, footprint)
        articulation = self._articulation_points(adjacency, start)
        critical: List[Tuple[int, int]] = []
        for point in articulation:
            if point in (start, goal):
                continue
            if self._disconnects(start, goal, [point], footprint):
                critical.append(point)
        return critical

    def _build_adjacency(
        self,
        nodes: Set[Tuple[int, int]],
        footprint: Tuple[int, int],
    ) -> dict[Tuple[int, int], List[Tuple[int, int]]]:
        adjacency: dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        for node in nodes:
            x, y = node
            neighbours = [
                neighbour
                for neighbour in self._footprint_neighbours(x, y, footprint)
                if neighbour in nodes
            ]
            adjacency[node] = neighbours
        return adjacency

    def _articulation_points(
        self,
        adjacency: dict[Tuple[int, int], List[Tuple[int, int]]],
        root: Tuple[int, int],
    ) -> Set[Tuple[int, int]]:
        index: dict[Tuple[int, int], int] = {}
        low: dict[Tuple[int, int], int] = {}
        parent: dict[Tuple[int, int], Tuple[int, int] | None] = {}
        articulation: Set[Tuple[int, int]] = set()
        counter = 0

        def dfs(node: Tuple[int, int]) -> None:
            nonlocal counter
            counter += 1
            index[node] = counter
            low[node] = counter
            children = 0
            for neighbour in adjacency.get(node, []):
                if neighbour not in index:
                    parent[neighbour] = node
                    children += 1
                    dfs(neighbour)
                    low[node] = min(low[node], low[neighbour])
                    if parent.get(node) is None:
                        if children > 1:
                            articulation.add(node)
                    elif low[neighbour] >= index[node]:
                        articulation.add(node)
                elif parent.get(node) != neighbour:
                    low[node] = min(low[node], index[neighbour])

        parent[root] = None
        dfs(root)
        return articulation

    def _disconnects(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        blocked: Iterable[Tuple[int, int]],
        footprint: Tuple[int, int],
    ) -> bool:
        blocked_set = set(blocked)
        if start in blocked_set or goal in blocked_set:
            return False
        queue: deque[Tuple[int, int]] = deque([start])
        visited: Set[Tuple[int, int]] = set(blocked_set)
        visited.add(start)
        while queue:
            x, y = queue.popleft()
            if (x, y) == goal:
                return False
            for neighbour in self._footprint_neighbours(x, y, footprint):
                if neighbour in visited:
                    continue
                visited.add(neighbour)
                queue.append(neighbour)
        return True

    def _fix_chokepoints(self) -> bool:
        pair = self._primary_spawn_pair()
        if pair is None:
            return False
        start_zone, goal_zone = pair
        start, goal = start_zone.position, goal_zone.position
        fixed_any = False
        for footprint in self._spawn_footprints():
            critical = self._critical_points(start, goal, footprint)
            for point in critical:
                if self._widen_corridor(point, footprint):
                    fixed_any = True
        return fixed_any

    def _widen_corridor(self, point: Tuple[int, int], footprint: Tuple[int, int]) -> bool:
        x, y = point
        width, height = footprint
        width = max(1, width)
        height = max(1, height)
        widened = False
        # Clear immediate border around the footprint rectangle.
        for dx in range(width):
            if self._carve_if_wall(x + dx, y - 1):
                widened = True
            if self._carve_if_wall(x + dx, y + height):
                widened = True
        for dy in range(height):
            if self._carve_if_wall(x - 1, y + dy):
                widened = True
            if self._carve_if_wall(x + width, y + dy):
                widened = True
        if widened:
            return True
        # Fallback: carve perpendicular tiles near the corridor to create alternate lanes.
        for dx, dy in _CARDINALS:
            for oy in range(height):
                for ox in range(width):
                    if self._carve_if_wall(x + ox - dy, y + oy + dx):
                        return True
        # Final fallback: clear a buffer around the corridor to guarantee additional space.
        carved = False
        for dy in range(-1, height + 1):
            for dx in range(-1, width + 1):
                if self._carve_if_wall(x + dx, y + dy):
                    carved = True
        return carved

    def _carve_if_wall(self, x: int, y: int) -> bool:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        if not self.grid.blocks_move_mask[y][x]:
            return False
        self._set_floor(x, y)
        return True


def ensure_valid_map(
    spec: MapSpec,
    *,
    reassign_spawns: Callable[[MapSpec], MapSpec],
    max_fixups: int = 6,
) -> MapSpec:
    """Validate ``spec`` and attempt fix-ups when necessary."""

    validator = MapValidator(spec)
    attempts = 0
    while attempts < max_fixups:
        result = validator.validate()
        if result.valid:
            return validator.spec
        if not result.fixed:
            break
        spec = reassign_spawns(validator.spec)
        validator = MapValidator(spec)
        attempts += 1
    final_valid = validator.is_valid()
    if final_valid:
        return validator.spec
    zone_labels = sorted(validator.spec.meta.spawn_zones.keys())
    raise RuntimeError(
        f"map validation failed after {attempts} fix-up attempt(s); "
        f"last validation: valid={final_valid}, width={validator.spec.width}, "
        f"height={validator.spec.height}, spawn_zones={zone_labels}"
    )


__all__ = ["MapValidator", "ValidationResult", "ensure_valid_map"]
