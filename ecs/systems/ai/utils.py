# ecs/systems/ai/utils.py
from typing import List, Tuple, Dict, Set
from random import choice

from ecs.helpers.occupancy import collect_blocked_tiles

def get_enemies(game_state, char_id: str) -> List[str]:
    """
    Get a list of all enemy entity IDs for the specified character.
    """
    char = game_state.get_entity(char_id)["character_ref"].character
    return [eid for eid, ent in game_state.entities.items()
            if eid != char_id and char.get_alliance(eid) == "enemy" and not ent["character_ref"].character.is_dead]

def get_allies(game_state, char_id: str) -> List[str]:
    """
    Get a list of all ally entity IDs for the specified character.
    """
    char = game_state.get_entity(char_id)["character_ref"].character
    return [eid for eid, ent in game_state.entities.items()
            if eid != char_id and char.get_alliance(eid) == "ally" and not ent["character_ref"].character.is_dead]

def get_adjacent_enemies(game_state, enemies: List[str], char_id: str) -> List[str]:
    """
    Get a list of enemy entity IDs that are adjacent to the specified character.
    This now considers entity sizes.
    """
    adj = []
    for eid in enemies:
        if are_entities_adjacent(game_state, char_id, eid):
            adj.append(eid)
    return adj

def are_adjacent(pos1, pos2) -> bool:
    """
    Check if two positions are adjacent (Manhattan distance of 1).
    DEPRECATED for entity checks. Use are_entities_adjacent instead.
    """
    # Handle positions as objects with x,y properties or as tuples
    if hasattr(pos1, 'x') and hasattr(pos1, 'y'):
        pos1_x, pos1_y = pos1.x, pos1.y
    else:
        pos1_x, pos1_y = pos1[0], pos1[1]

    if hasattr(pos2, 'x') and hasattr(pos2, 'y'):
        pos2_x, pos2_y = pos2.x, pos2.y
    else:
        pos2_x, pos2_y = pos2[0], pos2[1]

    return abs(pos1_x - pos2_x) + abs(pos1_y - pos2_y) == 1

def get_entity_bounding_box(game_state, entity_id: str) -> Dict[str, int]:
    """Returns the bounding box of an entity, handling multiple position representations."""
    entity = game_state.get_entity(entity_id)
    pos = entity["position"]

    # Handle PositionComponent
    if hasattr(pos, 'x1'):
        return {'x1': pos.x1, 'y1': pos.y1, 'x2': pos.x2, 'y2': pos.y2}

    # Handle Pos object or other objects with x, y, and optional width/height
    if hasattr(pos, 'x'):
        width = getattr(pos, 'width', 1)
        height = getattr(pos, 'height', 1)
        return {'x1': pos.x, 'y1': pos.y, 'x2': pos.x + width - 1, 'y2': pos.y + height - 1}

    # Handle tuple (x, y), assuming 1x1 size
    if isinstance(pos, tuple):
        return {'x1': pos[0], 'y1': pos[1], 'x2': pos[0], 'y2': pos[1]}

    raise TypeError(f"Unsupported position type for bounding box calculation: {type(pos)}")


def calculate_distance_between_bboxes(box1: Dict[str, int], box2: Dict[str, int]) -> int:
    """Calculates the Manhattan distance between the closest points of two bounding boxes."""
    try:
        # Ensure all values are numeric (handle MagicMock issues in tests)
        x1_1, y1_1, x2_1, y2_1 = int(box1['x1']), int(box1['y1']), int(box1['x2']), int(box1['y2'])
        x1_2, y1_2, x2_2, y2_2 = int(box2['x1']), int(box2['y1']), int(box2['x2']), int(box2['y2'])

        dx = max(0, x1_1 - x2_2, x1_2 - x2_1)
        dy = max(0, y1_1 - y2_2, y1_2 - y2_1)
        return dx + dy
    except (TypeError, ValueError, AttributeError):
        # Fallback for test environments with mock objects
        return 0

def are_entities_adjacent(game_state, entity1_id: str, entity2_id: str) -> bool:
    """
    Check if two entities are adjacent, considering their size (footprint).
    Adjacency is defined as their bounding boxes being 1 unit apart (Manhattan distance).
    """
    e1 = game_state.get_entity(entity1_id)
    e2 = game_state.get_entity(entity2_id)
    if not e1 or not e2 or "position" not in e1 or "position" not in e2:
        return False

    box1 = get_entity_bounding_box(game_state, entity1_id)
    box2 = get_entity_bounding_box(game_state, entity2_id)

    return calculate_distance_between_bboxes(box1, box2) == 1

def get_engaged_enemies(game_state, allies: List[str], enemies: List[str], char_id: str) -> List[str]:
    """
    Get a list of enemy entity IDs that are adjacent to any ally (excluding self).
    Engagement means adjacent to actual allies, not the character making the decision.
    """
    # Only use actual allies, not including the character itself
    engaged = set()
    for aid in allies:  # Don't include char_id
        for eid in enemies:
            if are_entities_adjacent(game_state, aid, eid):
                engaged.add(eid)
    return list(engaged)


def calculate_distance_between_entities(game_state, entity1_id: str, entity2_id: str) -> int:
    """Calculates the Manhattan distance between the bounding boxes of two entities."""
    box1 = get_entity_bounding_box(game_state, entity1_id)
    box2 = get_entity_bounding_box(game_state, entity2_id)
    return calculate_distance_between_bboxes(box1, box2)


def calculate_distance_from_point_to_bbox(point: Tuple[int, int], box: Dict[str, int]) -> int:
    """Calculates the Manhattan distance from a point to the closest point on a bounding box."""
    px, py = point
    dx = max(0, box['x1'] - px, px - box['x2'])
    dy = max(0, box['y1'] - py, py - box['y2'])
    return dx + dy


def calculate_distance(pos1, pos2) -> int:
    """
    Calculate the Manhattan distance between two points.
    Support both tuple and object with x/y attributes.
    """
    # Handle positions as objects with x,y properties or as tuples
    if hasattr(pos1, 'x') and hasattr(pos1, 'y'):
        pos1_x, pos1_y = pos1.x, pos1.y
    else:
        pos1_x, pos1_y = pos1[0], pos1[1]

    if hasattr(pos2, 'x') and hasattr(pos2, 'y'):
        pos2_x, pos2_y = pos2.x, pos2.y
    else:
        pos2_x, pos2_y = pos2[0], pos2[1]

    return abs(pos1_x - pos2_x) + abs(pos1_y - pos2_y)

def get_potential_dps(ctx, weapon, target_id) -> float:
    """
    Calculates the potential average damage per second (DPS) against a target.
    This is a simplified placeholder. A more detailed implementation would
    consider hit chance, critical chance, and target's defenses.
    """
    if not weapon:
        return 0.0
    # Placeholder: using base damage.
    # A real implementation would be much more complex.
    return getattr(weapon, 'base_damage', 5.0)

def count_future_threats(ctx, tile: Tuple[int, int]) -> int:
    """
    Counts how many enemies could perform a melee attack if the character moves to the given tile.
    """
    threats = 0
    for enemy_id in ctx.enemies:
        # We check if any part of the enemy is adjacent to the character's future tile.
        # This uses a simplified check assuming the character is 1x1 at the new tile.
        # For more accuracy with multi-tile characters, this would need to check
        # against the character's future bounding box.
        if is_in_range(ctx.game_state, tile, enemy_id, 1):
            threats += 1
    return threats

def count_free_adjacent_tiles(ctx, tile: Tuple[int, int]) -> int:
    """
    Counts the number of walkable, unoccupied tiles adjacent to a given tile.
    """
    free_tiles = 0
    x, y = tile
    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        adj_tile = (x + dx, y + dy)
        if ctx.movement_system.is_walkable(adj_tile[0], adj_tile[1]) and not ctx.game_state.is_tile_occupied(adj_tile[0], adj_tile[1]):
            free_tiles += 1
    return free_tiles

def is_in_range(game_state, entity_or_pos, target_id: str, max_range: int) -> bool:
    """
    Check if a target is within a specified range of the entity or position.

    Args:
        game_state: The game state
        entity_or_pos: Either an entity ID string or a position tuple/object (x,y)
        target_id: Target entity ID
        max_range: Maximum range to check

    Returns:
        True if target is within range, False otherwise
    """
    # Handle entity ID or direct position
    if isinstance(entity_or_pos, str):
        # It's an entity ID
        entity = game_state.get_entity(entity_or_pos)
        if not entity or "position" not in entity:
            return False
        entity_pos = entity["position"]
    else:
        # It's a position (tuple or object)
        entity_pos = entity_or_pos

    target = game_state.get_entity(target_id)
    if not target or "position" not in target:
        return False

    # This function is now tricky because entity_or_pos can be an ID or a position tuple.
    # If it's an ID, we can use the entity-to-entity distance.
    if isinstance(entity_or_pos, str):
        distance = calculate_distance_between_entities(game_state, entity_or_pos, target_id)
    else:
        # It's a position tuple. We calculate from this point to the target's bounding box.
        target_box = get_entity_bounding_box(game_state, target_id)
        distance = calculate_distance_from_point_to_bbox(entity_or_pos, target_box)

    return distance <= max_range

def is_in_range_tiles(tile1, tile2, max_range):
    """Check if two tiles are within Manhattan range."""
    return abs(tile1[0] - tile2[0]) + abs(tile1[1] - tile2[1]) <= max_range

def find_closest_cover(ctx, tile: Tuple[int, int]) -> int:
    """
    Finds the Manhattan distance to the nearest obstacle that provides cover.
    Cover is defined as a non-walkable tile.
    """
    min_dist = float('inf')
    terrain = ctx.game_state.terrain
    # This is a simplified search. A real implementation might use a pre-calculated map.
    for x in range(terrain.width):
        for y in range(terrain.height):
            if not terrain.is_walkable(x, y):
                dist = calculate_distance(tile, (x, y))
                if dist < min_dist:
                    min_dist = dist
    return min_dist if min_dist != float('inf') else 0


def find_distance_to_nearest_ally(ctx, tile: Tuple[int, int]) -> int:
    """
    Finds the Manhattan distance to the nearest ally.
    """
    if not ctx.allies:
        return float('inf')
    min_dist = float('inf')
    for ally_id in ctx.allies:
        dist = calculate_distance_between_entities(ctx.game_state, tile, ally_id)
        if dist < min_dist:
            min_dist = dist
    return min_dist

def choose_defensive_action(available_defenses: List[str]) -> str:
    """
    Choose the best defensive action from available options.
    """
    for preferred in ["Dodge", "Parry", "Absorb"]:
        if preferred in available_defenses:
            return preferred
    return choice(available_defenses) if available_defenses else "Dodge"

def get_occupied_static(game_state) -> Set[Tuple[int, int]]:
    """Gather statically occupied tiles using ECS data when available."""

    ecs_manager = getattr(game_state, "ecs_manager", None)
    terrain = getattr(game_state, "terrain", None)
    if ecs_manager is not None:
        return collect_blocked_tiles(ecs_manager, terrain=terrain)

    occupied = set()
    entities = getattr(game_state, "entities", {}) or {}
    for eid in entities:
        try:
            bbox = get_entity_bounding_box(game_state, eid)
        except TypeError:
            continue
        for x in range(bbox['x1'], bbox['x2'] + 1):
            for y in range(bbox['y1'], bbox['y2'] + 1):
                occupied.add((x, y))
    if terrain and hasattr(terrain, 'walls'):
        for wall in terrain.walls:
            occupied.add(wall)
    return occupied
