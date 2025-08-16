from typing import Optional, Tuple, List, Any
from . import utils

def simulate_move_and_find_melee(ctx) -> Optional[Tuple[Tuple[int, int], str]]:
    """
    Simulates moving to each reachable tile to find the best one for a melee attack.

    Args:
        ctx: The AITurnContext object.

    Returns:
        A tuple containing the best tile to move to and the target's entity ID,
        or None if no such move is possible.
    """
    best_option = None
    best_score = (float('-inf'), float('inf'), float('-inf'), float('inf'))  # (dps, -threat, mobility, -distance)

    # Get all reachable tiles within standard move distance, considering reserved tiles
    reachable_tiles = get_reachable_tiles(ctx.movement_system, ctx.char_id, 7, reserved_tiles=ctx.reserved_tiles)

    for tile_x, tile_y, _ in reachable_tiles:
        tile = (tile_x, tile_y)
        if tile == ctx.char_pos:
            continue

        # Find the best target from this tile
        best_target_from_tile = None
        best_target_score = (float('-inf'), float('inf'), float('-inf'), float('inf'))

        for enemy_id in ctx.enemies:
            # Check if we can attack this enemy from this tile (melee range = 1)
            if not utils.is_in_range(ctx.game_state, tile, enemy_id, 1):
                continue

            # Check cache first
            cache_key = (tile, enemy_id)
            if cache_key in ctx.metrics_cache:
                dps, threat, mobility, distance = ctx.metrics_cache[cache_key]
            else:
                # Calculate metrics
                dps = utils.get_potential_dps(ctx, ctx.melee_weapon, enemy_id)
                threat = utils.count_future_threats(ctx, tile)
                mobility = utils.count_free_adjacent_tiles(ctx, tile)
                distance = utils.calculate_distance(tile, ctx.game_state.get_entity(enemy_id)["position"])

                # Cache the result
                ctx.metrics_cache[cache_key] = (dps, threat, mobility, distance)

            target_score = (dps, -threat, mobility, -distance)

            if target_score > best_target_score:
                best_target_score = target_score
                best_target_from_tile = enemy_id

        # If we found a valid target from this tile, compare it to our best option
        if best_target_from_tile:
            if best_target_score > best_score:
                best_score = best_target_score
                best_option = (tile, best_target_from_tile)

    return best_option


def simulate_move_and_find_ranged(ctx) -> Optional[Tuple[Tuple[int, int], str]]:
    """
    Simulates moving to each reachable tile to find the best one for a ranged attack.

    Args:
        ctx: The AITurnContext object.

    Returns:
        A tuple containing the best tile to move to and the target's entity ID,
        or None if no such move is possible.
    """
    best_option = None
    best_score = (float('-inf'), float('inf'), float('-inf'), float('inf'))  # (dps, -threat, mobility, -distance)

    # Get weapon range
    try:
        weapon_range = getattr(ctx.ranged_weapon, "maximum_range",
                              getattr(ctx.ranged_weapon, "weapon_range", 6))
        weapon_range = int(weapon_range) if weapon_range is not None else 6
    except (TypeError, ValueError, AttributeError):
        weapon_range = 6

    # Get all reachable tiles within standard move distance, considering reserved tiles
    reachable_tiles = get_reachable_tiles(ctx.movement_system, ctx.char_id, 7, reserved_tiles=ctx.reserved_tiles)

    for tile_x, tile_y, _ in reachable_tiles:
        tile = (tile_x, tile_y)
        if tile == ctx.char_pos:
            continue

        # Find the best target from this tile
        best_target_from_tile = None
        best_target_score = (float('-inf'), float('inf'), float('-inf'), float('inf'))

        for enemy_id in ctx.enemies:
            enemy_entity = ctx.game_state.get_entity(enemy_id)
            enemy_pos = enemy_entity["position"]

            # Handle different position formats
            if hasattr(enemy_pos, 'x'):
                enemy_coords = (enemy_pos.x, enemy_pos.y)
            elif isinstance(enemy_pos, tuple):
                enemy_coords = enemy_pos
            else:
                enemy_coords = (enemy_pos[0], enemy_pos[1])

            # Check if target is in range from this tile
            range_check = utils.is_in_range_tiles(tile, enemy_coords, weapon_range)
            if not range_check:
                continue

            # Check if we have line of sight from this tile
            # Use LOS manager directly since ctx.has_los uses character's current position
            los_check = ctx.los_manager.has_los(tile, enemy_coords)
            if not los_check:
                continue

            # Check cache first
            cache_key = (tile, enemy_id)
            if cache_key in ctx.metrics_cache:
                dps, threat, mobility, distance = ctx.metrics_cache[cache_key]
            else:
                # Calculate metrics
                dps = utils.get_potential_dps(ctx, ctx.ranged_weapon, enemy_id)
                threat = utils.count_future_threats(ctx, tile)
                mobility = utils.count_free_adjacent_tiles(ctx, tile)

                # Calculate distance from tile to enemy
                distance = utils.calculate_distance(tile, enemy_coords)

                # Cache the result
                ctx.metrics_cache[cache_key] = (dps, threat, mobility, distance)

            target_score = (dps, -threat, mobility, -distance)

            if target_score > best_target_score:
                best_target_score = target_score
                best_target_from_tile = enemy_id

        # If we found a valid target from this tile, compare it to our best option
        if best_target_from_tile:
            if best_target_score > best_score:
                best_score = best_target_score
                best_option = (tile, best_target_from_tile)

    return best_option


def get_reachable_tiles(movement_system, char_id: str, max_distance: int, reserved_tiles=None) -> List[Tuple[int, int, int]]:
    """
    Get reachable tiles, filtering out reserved tiles.

    Args:
        movement_system: The movement system
        char_id: Character ID
        max_distance: Maximum movement distance
        reserved_tiles: Set of reserved tile coordinates to exclude

    Returns:
        List of (x, y, cost) tuples for reachable tiles
    """
    if reserved_tiles is None:
        reserved_tiles = set()

    all_tiles = movement_system.get_reachable_tiles(char_id, max_distance, reserved_tiles=reserved_tiles)

    # Filter out reserved tiles
    filtered_tiles = []
    for tile_x, tile_y, cost in all_tiles:
        if (tile_x, tile_y) not in reserved_tiles:
            filtered_tiles.append((tile_x, tile_y, cost))

    return filtered_tiles


def _find_best_tile_toward(ctx, target_pos, run=False) -> Optional[Tuple[int, int]]:
    """
    Find the best tile to move toward a target position.

    Args:
        ctx: AI turn context
        target_pos: Target position to move toward
        run: Whether to use sprint distance instead of normal move

    Returns:
        Best tile to move to, or None if no valid tiles
    """
    max_distance = 15 if run else 7
    reachable_tiles = get_reachable_tiles(ctx.movement_system, ctx.char_id, max_distance, reserved_tiles=ctx.reserved_tiles)

    if not reachable_tiles:
        return None

    # Find the tile that gets us closest to the target
    best_tile = None
    best_distance = float('inf')

    target_coords = (target_pos.x, target_pos.y) if hasattr(target_pos, 'x') else target_pos

    for tile_x, tile_y, _ in reachable_tiles:
        tile = (tile_x, tile_y)
        if tile == ctx.char_pos:
            continue

        distance = utils.calculate_distance(tile, target_coords)
        if distance < best_distance:
            best_distance = distance
            best_tile = tile

    return best_tile
