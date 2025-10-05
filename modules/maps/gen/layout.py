"""Procedural layout generator based on a simple BSP algorithm."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from modules.maps.components import MapMeta
from modules.maps.gen.params import MapGenParams, MapSymmetry
from modules.maps.gen.random import get_rng, rand_choice, rand_int
from modules.maps.spec import MapSpec


# Tunable constants defining the BSP behaviour.
_MIN_LEAF_SIZE = 8
_MIN_ROOM_SIZE = 4
_ROOM_MARGIN = 1


@dataclass(slots=True)
class Rect:
    """Axis-aligned rectangle helper."""

    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width - 1

    @property
    def y2(self) -> int:
        return self.y + self.height - 1

    @property
    def area(self) -> int:
        return self.width * self.height

    def center(self) -> tuple[int, int]:
        cx = self.x + self.width // 2
        cy = self.y + self.height // 2
        return cx, cy


@dataclass(slots=True)
class BSPNode:
    """Node representing a partition in the BSP tree."""

    rect: Rect
    left: Optional["BSPNode"] = None
    right: Optional["BSPNode"] = None
    room: Optional[Rect] = None

    def is_leaf(self) -> bool:
        return self.left is None and self.right is None

    def can_split(self) -> bool:
        return (
            self.rect.width >= 2 * _MIN_LEAF_SIZE
            or self.rect.height >= 2 * _MIN_LEAF_SIZE
        )

    def split(self, rng) -> bool:
        if not self.can_split():
            return False

        split_vertical = self.rect.width > self.rect.height
        if self.rect.width / max(1, self.rect.height) > 1.25:
            split_vertical = True
        elif self.rect.height / max(1, self.rect.width) > 1.25:
            split_vertical = False
        else:
            split_vertical = rng.random() < 0.5

        if split_vertical:
            min_split = _MIN_LEAF_SIZE
            max_split = self.rect.width - _MIN_LEAF_SIZE
            if max_split <= min_split:
                return False
            split = rand_int(rng, min_split, max_split)
            left_rect = Rect(self.rect.x, self.rect.y, split, self.rect.height)
            right_rect = Rect(
                self.rect.x + split, self.rect.y, self.rect.width - split, self.rect.height
            )
        else:
            min_split = _MIN_LEAF_SIZE
            max_split = self.rect.height - _MIN_LEAF_SIZE
            if max_split <= min_split:
                return False
            split = rand_int(rng, min_split, max_split)
            left_rect = Rect(self.rect.x, self.rect.y, self.rect.width, split)
            right_rect = Rect(
                self.rect.x, self.rect.y + split, self.rect.width, self.rect.height - split
            )

        self.left = BSPNode(left_rect)
        self.right = BSPNode(right_rect)
        return True

    def collect_rooms(self) -> list[Rect]:
        if self.is_leaf():
            return [self.room] if self.room is not None else []
        rooms: list[Rect] = []
        if self.left is not None:
            rooms.extend(self.left.collect_rooms())
        if self.right is not None:
            rooms.extend(self.right.collect_rooms())
        return rooms

    def random_room(self, rng) -> Rect:
        rooms = self.collect_rooms()
        if not rooms:
            raise RuntimeError("BSP node has no rooms to choose from")
        return rand_choice(rng, rooms)


def _estimate_room_target(params: MapGenParams) -> int:
    if params.room_count is not None:
        return max(1, params.room_count)
    width, height = params.dimensions
    area = width * height
    # Aim for roughly one room per 150 tiles as a fallback.
    estimate = max(4, area // 150)
    return estimate


# _rand_within removed; use rand_int directly and handle edge case at call sites.
def _generate_bsp(params: MapGenParams, rng) -> BSPNode:
    width, height = params.dimensions
    root_rect = Rect(1, 1, width - 2, height - 2)
    root = BSPNode(root_rect)

    target = _estimate_room_target(params)
    leaves: list[BSPNode] = [root]

    attempts = 0
    while len(leaves) < target and attempts < target * 8:
        attempts += 1
        leaf = max(leaves, key=lambda node: node.rect.area)
        if leaf.split(rng):
            leaves.remove(leaf)
            if leaf.left is not None:
                leaves.append(leaf.left)
            if leaf.right is not None:
                leaves.append(leaf.right)
        else:
            # If the largest leaf cannot be split, mark it as processed.
            processed = [node for node in leaves if node.can_split()]
            if not processed:
                break
            leaf = rand_choice(rng, processed)
            if leaf.split(rng):
                leaves.remove(leaf)
                if leaf.left is not None:
                    leaves.append(leaf.left)
                if leaf.right is not None:
                    leaves.append(leaf.right)

    return root


def _create_room(rect: Rect, rng) -> Rect:
    def _pick_span(span: int) -> int:
        interior_limit = span - 2 * _ROOM_MARGIN
        if interior_limit < 1:
            # Not enough space to honour the requested margins; fall back to the
            # full span while keeping the size positive when possible.
            if span <= 0:
                return 0
            return rand_int(rng, 1, span)

        min_span = min(_MIN_ROOM_SIZE, interior_limit)
        max_span = max(min_span, interior_limit)
        return rand_int(rng, min_span, max_span)

    def _pick_position(coord: int, span: int, size: int) -> int:
        margin = _ROOM_MARGIN
        min_pos = coord + margin
        max_pos = coord + span - margin - size
        if max_pos < min_pos:
            min_pos = coord
            max_pos = coord + span - size
        if max_pos < min_pos:
            max_pos = min_pos
        # Clamp to ensure the room stays within the partition boundary
        min_allowed = coord
        max_allowed = coord + span - size
        min_pos = max(min_pos, min_allowed)
        max_pos = min(max_pos, max_allowed)
        if max_pos < min_pos:
            max_pos = min_pos
        return rand_int(rng, min_pos, max_pos)

    room_width = _pick_span(rect.width)
    room_height = _pick_span(rect.height)

    room_x = _pick_position(rect.x, rect.width, room_width)
    room_y = _pick_position(rect.y, rect.height, room_height)

    return Rect(room_x, room_y, room_width, room_height)


def _populate_rooms(node: BSPNode, rng) -> None:
    if node.is_leaf():
        node.room = _create_room(node.rect, rng)
        return
    if node.left is not None:
        _populate_rooms(node.left, rng)
    if node.right is not None:
        _populate_rooms(node.right, rng)


def _corridor_band(center: int, width: int) -> tuple[int, int]:
    half = width // 2
    if width % 2 == 0:
        start = center - half + 1
        end = center + half
    else:
        start = center - half
        end = center + half
    return start, end


def _fill_rect(cells: list[list[str]], rect: Rect, value: str) -> None:
    height = len(cells)
    width = len(cells[0]) if cells else 0
    for y in range(rect.y, rect.y + rect.height):
        if not (0 <= y < height):
            continue
        row = cells[y]
        for x in range(rect.x, rect.x + rect.width):
            if 0 <= x < width:
                row[x] = value


def _carve_room(cells: list[list[str]], room: Rect) -> None:
    _fill_rect(cells, room, "floor")


def _carve_horizontal(
    cells: list[list[str]],
    y: int,
    x_start: int,
    x_end: int,
    width: int,
) -> None:
    start_y, end_y = _corridor_band(y, width)
    x0, x1 = sorted((x_start, x_end))
    rect = Rect(x0, start_y, x1 - x0 + 1, end_y - start_y + 1)
    _fill_rect(cells, rect, "floor")


def _carve_vertical(
    cells: list[list[str]],
    x: int,
    y_start: int,
    y_end: int,
    width: int,
) -> None:
    start_x, end_x = _corridor_band(x, width)
    y0, y1 = sorted((y_start, y_end))
    rect = Rect(start_x, y0, end_x - start_x + 1, y1 - y0 + 1)
    _fill_rect(cells, rect, "floor")


def _random_point_in_room(room: Rect, rng) -> tuple[int, int]:
    x = rand_int(rng, room.x, room.x2)
    y = rand_int(rng, room.y, room.y2)
    return x, y


def _carve_corridor(
    cells: list[list[str]],
    rng,
    start_room: Rect,
    end_room: Rect,
    corridor_width: tuple[int, int],
) -> None:
    min_width, max_width = corridor_width
    width = rand_int(rng, min_width, max_width)

    start_point = _random_point_in_room(start_room, rng)
    end_point = _random_point_in_room(end_room, rng)

    x1, y1 = start_point
    x2, y2 = end_point

    if rng.random() < 0.5:
        _carve_horizontal(cells, y1, x1, x2, width)
        _carve_vertical(cells, x2, y1, y2, width)
    else:
        _carve_vertical(cells, x1, y1, y2, width)
        _carve_horizontal(cells, y2, x1, x2, width)


def _connect_tree(
    node: BSPNode,
    cells: list[list[str]],
    rng,
    corridor_width: tuple[int, int],
) -> None:
    if node.left is not None and node.right is not None:
        left_room = node.left.random_room(rng)
        right_room = node.right.random_room(rng)
        _carve_corridor(cells, rng, left_room, right_room, corridor_width)

        _connect_tree(node.left, cells, rng, corridor_width)
        _connect_tree(node.right, cells, rng, corridor_width)
def _ensure_border_walls(cells: list[list[str]]) -> None:
    if not cells:
        return
    height = len(cells)
    width = len(cells[0])
    for x in range(width):
        cells[0][x] = "wall"
        cells[height - 1][x] = "wall"
    for y in range(height):
        cells[y][0] = "wall"
        cells[y][width - 1] = "wall"

def _apply_symmetry(cells: list[list[str]], symmetry: MapSymmetry) -> None:
    if symmetry == "none":
        return

    height = len(cells)
    width = len(cells[0]) if height else 0
    original = [row[:] for row in cells]

    if symmetry == "mirror_x":
        limit = (height + 1) // 2
        for y in range(limit):
            mirror_y = height - 1 - y
            cells[mirror_y][:] = original[y]
    elif symmetry == "mirror_y":
        limit = (width + 1) // 2
        for y in range(height):
            row = cells[y]
            source = original[y]
            for x in range(limit):
                mirror_x = width - 1 - x
                row[mirror_x] = source[x]
    elif symmetry == "rot_180":
        for y in range(height):
            for x in range(width):
                mirror_x = width - 1 - x
                mirror_y = height - 1 - y
                cells[mirror_y][mirror_x] = original[y][x]
    else:  # pragma: no cover - future symmetry modes
        raise ValueError(
            f"Unknown symmetry mode '{symmetry}'. Supported modes: none, mirror_x, mirror_y, rot_180"
        )
def generate_layout(params: MapGenParams) -> MapSpec:
    """Generate a :class:`MapSpec` using a BSP layout algorithm."""

    rng = get_rng(params.seed)
    width, height = params.dimensions
    cells: list[list[str]] = [["wall" for _ in range(width)] for _ in range(height)]

    bsp_root = _generate_bsp(params, rng)
    _populate_rooms(bsp_root, rng)

    for room in bsp_root.collect_rooms():
        _carve_room(cells, room)

    _connect_tree(bsp_root, cells, rng, params.corridor_width)
    _ensure_border_walls(cells)
    _apply_symmetry(cells, params.symmetry)

    meta = MapMeta(name="generated", biome=params.biome, seed=params.seed)
    return MapSpec(width=width, height=height, cell_size=1, meta=meta, cells=cells)


__all__ = ["generate_layout"]
