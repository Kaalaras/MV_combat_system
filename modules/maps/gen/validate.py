"""Validation and fix-ups for procedurally generated maps."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable, List, Sequence, Set, Tuple

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
        return self._has_min_cut(2)

    def validate(self) -> ValidationResult:
        components = self._connected_components()
        if len(components) > 1:
            if self._fix_connectivity(components):
                self._refresh()
                return ValidationResult(valid=False, fixed=True)
            return ValidationResult(valid=False, fixed=False)

        if not self._has_min_cut(2):
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
        component: Set[Tuple[int, int]] = set([start])
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

    def _spawn_positions(self) -> List[Tuple[int, int]]:
        zones = self.spec.meta.spawn_zones
        ordered = [zones[key] for key in sorted(zones.keys())]
        return [zone.position for zone in ordered]

    def _has_min_cut(self, required: int) -> bool:
        positions = self._spawn_positions()
        if len(positions) < 2:
            return True
        start, goal = positions[0], positions[1]
        critical = self._critical_points(start, goal)
        return len(critical) < required - 1

    def _critical_points(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
    ) -> List[Tuple[int, int]]:
        reachable = self._flood_fill(start, set())
        if goal not in reachable:
            return [start]
        adjacency = self._build_adjacency(reachable)
        articulation = self._articulation_points(adjacency, start)
        critical: List[Tuple[int, int]] = []
        for point in articulation:
            if point in (start, goal):
                continue
            if self._disconnects(start, goal, point):
                critical.append(point)
        return critical

    def _build_adjacency(self, nodes: Set[Tuple[int, int]]) -> dict[Tuple[int, int], List[Tuple[int, int]]]:
        adjacency: dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        for node in nodes:
            neighbours: List[Tuple[int, int]] = []
            x, y = node
            for dx, dy in _CARDINALS:
                nx, ny = x + dx, y + dy
                if (nx, ny) in nodes:
                    neighbours.append((nx, ny))
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
        blocked: Tuple[int, int],
    ) -> bool:
        if blocked == start or blocked == goal:
            return False
        queue: deque[Tuple[int, int]] = deque([start])
        visited: Set[Tuple[int, int]] = {start, blocked}
        while queue:
            x, y = queue.popleft()
            if (x, y) == goal:
                return False
            for dx, dy in _CARDINALS:
                nx, ny = x + dx, y + dy
                coord = (nx, ny)
                if coord in visited:
                    continue
                if not self._is_walkable(nx, ny):
                    continue
                visited.add(coord)
                queue.append(coord)
        return True

    def _fix_chokepoints(self) -> bool:
        positions = self._spawn_positions()
        if len(positions) < 2:
            return False
        start, goal = positions[0], positions[1]
        critical = self._critical_points(start, goal)
        for point in critical:
            if self._widen_corridor(point):
                return True
        return False

    def _widen_corridor(self, point: Tuple[int, int]) -> bool:
        x, y = point
        widened = False
        for dx, dy in _CARDINALS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < self.width and 0 <= ny < self.height):
                continue
            if not self.grid.blocks_move_mask[ny][nx]:
                continue
            self._set_floor(nx, ny)
            widened = True
        if widened:
            return True
        # Fallback: carve perpendicular tiles to create an alternate lane.
        for dx, dy in _CARDINALS:
            for px, py in ((x - dy, y + dx), (x + dy, y - dx)):
                if not (0 <= px < self.width and 0 <= py < self.height):
                    continue
                if self.grid.blocks_move_mask[py][px]:
                    self._set_floor(px, py)
                    return True
        return False


def ensure_valid_map(
    spec: MapSpec,
    *,
    reassign_spawns: Callable[[MapSpec], MapSpec],
    max_fixups: int = 3,
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
    validator = MapValidator(validator.spec)
    if validator.is_valid():
        return validator.spec
    raise RuntimeError("map validation failed after fix-ups")


__all__ = ["MapValidator", "ValidationResult", "ensure_valid_map"]
