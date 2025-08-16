from typing import List, Tuple, Dict, Any, Set, Deque
from collections import deque
from ecs.systems.ai.utils import get_occupied_static
from itertools import product


class MovementSystem:
    """
    System responsible for handling entity movement within the game world.

    The MovementSystem manages movement-related operations such as:
    - Finding reachable tiles for an entity
    - Moving entities to valid positions
    - Calculating movement costs based on entity attributes
    - Pathfinding and traversal

    Attributes:
        game_state: Reference to the central game state containing entities and terrain

    Example usage:
    ```python
    # Initialize movement system with game state
    movement_system = MovementSystem(game_state)

    # Find tiles reachable by player
    reachable_tiles = movement_system.get_reachable_tiles("player1", max_distance=7)

    # Move player to a new location
    success = movement_system.move("player1", (10, 15))
    if success:
        print("Player moved successfully")
    else:
        print("Movement failed - destination unreachable")
    ```
    """

    def __init__(self, game_state: Any) -> None:
        """
        Initializes the MovementSystem with a reference to the game state.

        Args:
            game_state: The central game state object providing access to entities and terrain

        Example:
            ```python
            # Create movement system
            movement_system = MovementSystem(game_state)
            ```
        """
        self.game_state = game_state

    # --- Convenience wrappers for AI / other systems ---------------------------------
    def is_walkable(self, x: int, y: int, entity_width: int = 1, entity_height: int = 1) -> bool:
        """Lightweight proxy so AI helper functions can query walkability directly.
        Delegates to terrain.is_walkable; returns False if terrain missing."""
        terrain = getattr(self.game_state, 'terrain', None)
        if not terrain:
            return False
        return terrain.is_walkable(x, y, entity_width, entity_height)
    # ---------------------------------------------------------------------------------

    def get_dexterity(self, entity: Dict[str, Any]) -> int:
        """
        Retrieves the Dexterity trait value for a given entity.

        Dexterity typically affects movement capabilities and initiative.

        Args:
            entity: The entity dictionary containing character reference and components

        Returns:
            The entity's Dexterity attribute value, or 0 if not found

        Example:
            ```python
            # Get player entity
            player = game_state.get_entity("player1")

            # Get dexterity value
            dex = movement_system.get_dexterity(player)
            print(f"Player dexterity: {dex}")
            ```
        """
        # Assumes traits are stored as in Character
        char_ref = entity.get("character_ref")
        if not char_ref:
            return 0
        return char_ref.character.traits.get("Attributes", {}).get("Physical", {}).get("Dexterity", 0)

    def get_reachable_tiles(self, entity_id: str, max_distance: int, reserved_tiles: Set[Tuple[int, int]] = None) -> List[Tuple[int, int, int]]:
        """
        Find all tiles reachable by an entity within a specified movement range.

        Uses breadth-first search to find all valid positions an entity can move to,
        accounting for terrain obstacles, other entities, and movement limits.

        Args:
            entity_id: The unique identifier of the entity performing movement
            max_distance: Maximum movement distance (e.g., 7 for standard move, 15 for sprint)
            reserved_tiles: A set of (x, y) tuples for tiles that are reserved and thus unreachable.

        Returns:
            List of tuples (x, y, movement_cost) representing reachable positions and their cost

        Example:
            ```python
            # Find tiles reachable in a standard move
            standard_move_tiles = movement_system.get_reachable_tiles("character1", 7)

            # Find tiles reachable in a sprint
            sprint_tiles = movement_system.get_reachable_tiles("character1", 15)

            # Visualize movement range (example)
            for x, y, cost in standard_move_tiles:
                game_ui.highlight_tile(x, y, color="blue", alpha=1.0 - (cost/7))
            ```
        """
        entity = self.game_state.get_entity(entity_id)
        if not entity or "position" not in entity:
            return []

        pos_comp = entity["position"]
        start_pos = (pos_comp.x, pos_comp.y)
        entity_width = getattr(pos_comp, 'width', 1)
        entity_height = getattr(pos_comp, 'height', 1)

        visited: Set[Tuple[int, int]] = {start_pos}
        queue: Deque[Tuple[Tuple[int, int], int]] = deque([(start_pos, 0)])
        reachable: List[Tuple[int, int, int]] = [(start_pos[0], start_pos[1], 0)]

        terrain = self.game_state.terrain

        # Ensure reserved_tiles is a set
        reserved = reserved_tiles or set()
        # Compute static occupied tiles (entities footprints and walls)
        static_occ = get_occupied_static(self.game_state)
        # Exclude this entity's current footprint
        entity = self.game_state.get_entity(entity_id)
        pos = entity.get("position")
        width = getattr(pos, 'width', 1)
        height = getattr(pos, 'height', 1)
        start_x, start_y = (pos.x, pos.y) if hasattr(pos, 'x') else pos
        for dx, dy in product(range(width), range(height)):
            static_occ.discard((start_x + dx, start_y + dy))
        # Combine reserved and static occupied for filtering
        blocked = reserved.union(static_occ)

        while queue:
            (x, y), dist = queue.popleft()

            if dist >= max_distance:
                continue

            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy

                if (nx, ny) in visited or (nx, ny) in blocked:
                    continue

                # Check if the new anchor position (nx,ny) is valid for the entity's footprint
                if not terrain.is_walkable(nx, ny, entity_width, entity_height) or \
                   terrain.is_occupied(nx, ny, entity_width, entity_height, entity_id_to_ignore=entity_id):
                    continue

                visited.add((nx, ny))
                new_dist = dist + 1
                queue.append(((nx, ny), new_dist))
                reachable.append((nx, ny, new_dist))

        return reachable

    def move(self, entity_id: str, dest: Tuple[int, int]) -> bool:
        """
        Moves an entity to the specified destination if the movement is valid.

        Validates that the destination is within bounds, not occupied by other entities,
        and not blocked by terrain features.

        Args:
            entity_id: The unique identifier of the entity to move
            dest: Tuple (x, y) destination coordinates

        Returns:
            True if the move was successful, False otherwise

        Example:
            ```python
            # Try to move player to destination
            player_id = "player1"
            destination = (5, 8)

            if movement_system.move(player_id, destination):
                print("Player moved to", destination)
                # Update UI or trigger movement animation
            else:
                print("Cannot move to destination")
                # Display error message to player
            ```
        """
        entity = self.game_state.get_entity(entity_id)
        if not entity or "position" not in entity:
            return False

        pos_comp = entity["position"]

        terrain = self.game_state.terrain
        dest_x, dest_y = dest

        # Terrain's is_occupied and is_valid_position methods (called by move_entity or directly)
        # should now correctly use the entity's size by fetching it via game_state.
        # The MovementSystem's primary check here is if the *destination anchor point*
        # is valid and not occupied by *another* entity's footprint.

        # Get entity's actual size for checks
        current_entity_width, current_entity_height = terrain._get_entity_size(entity_id)


        # Check if destination is valid for the entity's footprint
        if not terrain.is_valid_position(dest_x, dest_y, current_entity_width, current_entity_height):
            # print(f"Move fail: Dest {dest} out of bounds for size {current_entity_width}x{current_entity_height}")
            return False

        # Check if destination is occupied by *another* entity
        if terrain.is_occupied(dest_x, dest_y, current_entity_width, current_entity_height, entity_id_to_ignore=entity_id):
            # print(f"Move fail: Dest {dest} (size {current_entity_width}x{current_entity_height}) occupied by another.")
            return False

        # Check if the destination is walkable (e.g. not a wall)
        if not terrain.is_walkable(dest_x, dest_y, current_entity_width, current_entity_height):
            # print(f"Move fail: Dest {dest} (size {current_entity_width}x{current_entity_height}) not walkable.")
            return False

        # Attempt to move the entity in the terrain subsystem
        moved_in_terrain = terrain.move_entity(entity_id, dest_x, dest_y)

        if moved_in_terrain:
            pos_comp.x, pos_comp.y = dest_x, dest_y # Update entity's own position component
            # print(f"Move success: {entity_id} to {dest}")
            return True

        # print(f"Move fail: terrain.move_entity for {entity_id} to {dest} returned False")
        return False