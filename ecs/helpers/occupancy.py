"""Helpers for expanding entity occupancy information from the ECS."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, Optional, Set, Tuple

from ecs.components.body_footprint import BodyFootprintComponent
from ecs.components.position import PositionComponent
from ecs.ecs_manager import ECSManager

GridCoord = Tuple[int, int]


def _expand_footprint(
    position: PositionComponent,
    footprint: Optional[BodyFootprintComponent],
) -> Set[GridCoord]:
    anchor_x = int(getattr(position, "x", 0))
    anchor_y = int(getattr(position, "y", 0))
    if footprint is not None:
        offsets = list(footprint.iter_offsets())
        if offsets:
            return {(
                anchor_x + int(dx),
                anchor_y + int(dy),
            ) for dx, dy in offsets}

    width = int(getattr(position, "width", 1))
    height = int(getattr(position, "height", 1))

    if width <= 0 or height <= 0:
        raise ValueError(
            "PositionComponent dimensions must be positive to compute occupancy: "
            f"width={width}, height={height}"
        )

    return {
        (anchor_x + dx, anchor_y + dy)
        for dx in range(width)
        for dy in range(height)
    }


def iter_entity_tiles(ecs_manager: ECSManager) -> Iterator[Tuple[str, Set[GridCoord]]]:
    """Yield ``(entity_id, occupied_tiles)`` tuples for ECS-tracked entities."""

    for entity_id, position in ecs_manager.iter_with_id(PositionComponent):
        internal_id = ecs_manager.resolve_entity(entity_id)
        footprint: Optional[BodyFootprintComponent] = None
        if internal_id is not None:
            footprint = ecs_manager.try_get_component(internal_id, BodyFootprintComponent)
        tiles = _expand_footprint(position, footprint)
        if tiles:
            yield entity_id, tiles


def build_entity_tile_index(ecs_manager: ECSManager) -> Dict[str, Set[GridCoord]]:
    """Return a mapping of entity id -> occupied tile set."""

    return {entity_id: tiles for entity_id, tiles in iter_entity_tiles(ecs_manager)}


def collect_blocked_tiles(
    ecs_manager: ECSManager,
    *,
    ignore_entities: Optional[Iterable[str]] = None,
    terrain: Optional[Any] = None,
    include_walls: bool = True,
) -> Set[GridCoord]:
    """Aggregate occupied tiles from entities (and optionally terrain walls)."""

    ignored = set(ignore_entities or ())
    blocked: Set[GridCoord] = set()
    for entity_id, tiles in iter_entity_tiles(ecs_manager):
        if entity_id in ignored:
            continue
        blocked.update(tiles)

    if include_walls:
        if terrain is None:
            terrain = getattr(ecs_manager, "terrain", None)
            if terrain is None:
                game_state = getattr(ecs_manager, "game_state", None)
                if game_state is not None:
                    terrain = getattr(game_state, "terrain", None)
        walls = getattr(terrain, "walls", None)
        if isinstance(walls, (set, list, tuple)):
            blocked.update({(int(x), int(y)) for x, y in walls})

    return blocked


def get_entity_tiles(ecs_manager: ECSManager, entity_id: str) -> Set[GridCoord]:
    """Return the set of occupied tiles for ``entity_id`` if available."""

    internal_id = ecs_manager.resolve_entity(entity_id)
    if internal_id is None:
        return set()

    position = ecs_manager.get_component_for_entity(entity_id, PositionComponent)
    if position is None:
        return set()

    footprint = ecs_manager.try_get_component(internal_id, BodyFootprintComponent)
    return _expand_footprint(position, footprint)


__all__ = [
    "GridCoord",
    "build_entity_tile_index",
    "collect_blocked_tiles",
    "get_entity_tiles",
    "iter_entity_tiles",
]

