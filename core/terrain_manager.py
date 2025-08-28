from typing import Dict, Tuple, List, Optional, Set, Any, Callable # Ensure all are present
from utils.logger import log_calls
from tqdm import tqdm

# Event constants
EVT_TERRAIN_CHANGED = "terrain_changed"
EVT_ENTITY_MOVED = "entity_moved"
EVT_WALL_ADDED = "wall_added"
EVT_WALL_REMOVED = "wall_removed"

# --- Terrain Effect constants ---
EFFECT_DIFFICULT = "difficult"
EFFECT_VERY_DIFFICULT = "very_difficult"
EFFECT_IMPASSABLE_SOLID = "impassable_solid"  # cannot enter
EFFECT_IMPASSABLE_VOID = "impassable_void"    # cannot end movement (future: allow jump)
EFFECT_DANGEROUS = "dangerous"
EFFECT_VERY_DANGEROUS = "very_dangerous"      # center tile (aura handled separately)
EFFECT_CURRENT = "current"                    # flowing movement each round
EFFECT_DARK_LOW = "dark_low"
EFFECT_DARK_TOTAL = "dark_total"


class Terrain:
    """
    Represents a 2D grid terrain where characters and objects can be placed.

    Terrain manages a grid-based game world, handling entity positions, walls,
    walkable areas, and pathfinding. It provides functionality for adding/removing
    entities, checking position validity, and optimizing movement calculations.

    Attributes:
        width: Width of the terrain grid in cells
        height: Height of the terrain grid in cells
        cell_size: Size of each cell in pixels (for rendering)
        grid: Dictionary mapping coordinates (x, y) to entity IDs
        entity_positions: Dictionary mapping entity IDs to their positions
        walkable_cells: Set of all walkable cell coordinates
        walls: Set of all wall cell coordinates
        path_cache: Dictionary mapping start/end position pairs to precalculated paths
        reachable_tiles_cache: Dictionary mapping positions and movement distances to reachable tiles

    Example usage:
    ```python
    # Create a 20x20 terrain with 64px cells
    terrain = Terrain(20, 20, 64)

    # Add some walls and obstacles
    terrain.add_wall(5, 5)
    terrain.add_wall(5, 6)
    terrain.add_wall(6, 5)

    # Add entities to the terrain
    terrain.add_entity("player1", 1, 1)
    terrain.add_entity("enemy1", 10, 10)

    # Check if a position is valid and walkable
    if terrain.is_walkable(2, 2) and not terrain.is_occupied(2, 2):
        terrain.move_entity("player1", 2, 2)

    # Precompute paths for performance
    terrain.precompute_paths()
    terrain.precompute_reachable_tiles()

    # Use the path cache for movement
    path = terrain.path_cache.get(((1, 1), (15, 15)))
    if path:
        print(f"Path found with {len(path)} steps")
    ```
    """

    def __init__(self, width: int, height: int, cell_size: int = 64, game_state: Optional[Any] = None):
        """
        Initialize a new terrain with specified dimensions.

        Args:
            width: Width of the terrain grid in cells
            height: Height of the terrain grid in cells
            cell_size: Size of each cell in pixels, used for rendering (default: 64)
            game_state: Optional game state reference for entity management

        Example:
            ```python
            # Create a small 10x10 terrain with default cell size
            terrain = Terrain(10, 10)

            # Create a large 100x100 terrain with smaller cells
            large_terrain = Terrain(100, 100, cell_size=32)
            ```
        """
        self.width = width
        self.height = height
        self.cell_size = cell_size
        self.grid: Dict[Tuple[int, int], str] = {}  # Maps (x, y) to entity_id
        self.entity_positions: Dict[str, Tuple[int, int]] = {}  # Maps entity_id to (anchor_x, anchor_y)
        self.walkable_cells: Set[Tuple[int, int]] = set((x, y) for x in range(width) for y in range(height))
        self.walls: Set[Tuple[int, int]] = set() # Set is used here
        self.game_state = game_state  # Store game_state reference
        self.event_bus = game_state.event_bus if game_state and hasattr(game_state, 'event_bus') else None
        self.path_cache: Dict[Tuple[Tuple[int, int], Tuple[int, int]], List[Tuple[int, int]]] = {} # Dict is used here
        self.reachable_tiles_cache: Dict[Tuple[Tuple[int, int], int], Set[Tuple[int, int]]] = {} # Dict and Set are used here
        # Effects mapping: (x,y) -> list of dicts {'name':effect_name, 'data':{...}}
        self.effects_by_tile: Dict[Tuple[int,int], List[Dict[str,Any]]] = {}

    def _publish(self, event_type: str, payload: Optional[dict] = None) -> None:
        """
        Publish an event to the event bus if available.

        Args:
            event_type: The type of event to publish
            payload: Optional data to include with the event

        Example:
            ```python
            # Publish a wall added event
            self._publish(EVT_WALL_ADDED, {"position": (5, 3)})
            ```
        """
        if self.event_bus:
            self.event_bus.publish(event_type, **(payload or {}))

    def _get_entity_size(self, entity_id: str) -> Tuple[int, int]:
        """Helper to get entity's width and height."""
        if not self.game_state:
            # Fallback or error if game_state is not set
            return (1, 1)
        return self.game_state.get_entity_size(entity_id)

    @log_calls
    def is_valid_position(self, x: int, y: int, entity_width: int = 1, entity_height: int = 1) -> bool:
        """
        Check if the entire area for an entity is within terrain bounds.

        Args:
            x: X-coordinate to check
            y: Y-coordinate to check
            entity_width: Width of the entity (in cells)
            entity_height: Height of the entity (in cells)

        Returns:
            True if the position is valid for the entire entity, False otherwise

        Example:
            ```python
            # Check if position is valid before placing an entity
            if terrain.is_valid_position(x, y):
                terrain.add_entity("entity1", x, y)
            else:
                print(f"Position ({x}, {y}) is out of bounds")
            ```
        """
        for dy in range(entity_height):
            for dx in range(entity_width):
                if not (0 <= x + dx < self.width and 0 <= y + dy < self.height):
                    return False
        return True

    @log_calls
    def is_walkable(self, x: int, y: int, entity_width: int = 1, entity_height: int = 1) -> bool:
        """
        Check if all cells an entity would occupy are walkable (i.e., not a wall).

        Args:
            x: X-coordinate to check
            y: Y-coordinate to check
            entity_width: Width of the entity (in cells)
            entity_height: Height of the entity (in cells)

        Returns:
            True if the cells are walkable, False otherwise

        Example:
            ```python
            # Check if a cell is walkable before attempting movement
            if terrain.is_walkable(next_x, next_y):
                # Further checks for occupation are needed before moving
                if not terrain.is_occupied(next_x, next_y):
                    terrain.move_entity("player1", next_x, next_y)
            else:
                print(f"Cannot walk to ({next_x}, {next_y}), there's a wall")
            ```
        """
        if not self.is_valid_position(x, y, entity_width, entity_height):  # Must be valid first
            return False

        # Check if any cell in the entity's footprint is a wall
        for dy in range(entity_height):
            for dx in range(entity_width):
                cx, cy = x+dx, y+dy
                if (cx, cy) in self.walls:
                    return False
                if self._is_impassable(cx, cy):
                    return False
        return True

    @log_calls
    def is_occupied(self, x: int, y: int, entity_width: int = 1, entity_height: int = 1,
                    entity_id_to_ignore: Optional[str] = None, check_walls: bool = False) -> bool:
        """
        Check if any cell the entity would occupy is already taken by another entity or wall.

        For an area to be considered occupied, at least one cell must contain an entity or wall.

        Args:
            x: X-coordinate to check
            y: Y-coordinate to check
            entity_width: Width of the entity (in cells)
            entity_height: Height of the entity (in cells)
            entity_id_to_ignore: Entity ID to ignore (for moves, etc.)
            check_walls: If True, also checks if walls occupy the space

        Returns:
            True if the cells are occupied, False otherwise

        Example:
            ```python
            # Check if a cell is occupied by any entity
            if terrain.is_occupied(x, y):
                entity_id = terrain.get_entity_at(x, y)
                print(f"Cell ({x}, {y}) is occupied by {entity_id}")

            # Check if a cell is occupied by any entity or wall
            if terrain.is_occupied(x, y, check_walls=True):
                print(f"Cell ({x}, {y}) is occupied by entity or wall")
            ```
        """
        # First check if there are entities in the requested area
        for dy in range(entity_height):
            for dx in range(entity_width):
                cell_coord = (x + dx, y + dy)
                occupant_id = self.grid.get(cell_coord)
                if occupant_id is not None and occupant_id != entity_id_to_ignore:
                    return True

        # If requested, also check for walls
        if check_walls:
            for dy in range(entity_height):
                for dx in range(entity_width):
                    if (x + dx, y + dy) in self.walls:
                        return True

        return False

    def _clear_entity_occupancy(self, entity_id: str):
        """Clears all grid cells occupied by the entity."""
        if entity_id not in self.entity_positions:
            return

        old_x, old_y = self.entity_positions[entity_id]
        entity_width, entity_height = self._get_entity_size(entity_id)

        for dy in range(entity_height):
            for dx in range(entity_width):
                cell_coord = (old_x + dx, old_y + dy)
                if self.grid.get(cell_coord) == entity_id:
                    del self.grid[cell_coord]

    def _occupy_cells(self, entity_id: str, x: int, y: int, entity_width: int, entity_height: int):
        """Marks all grid cells for the entity's footprint and updates its anchor position."""
        for dy in range(entity_height):
            for dx in range(entity_width):
                self.grid[(x + dx, y + dy)] = entity_id
        self.entity_positions[entity_id] = (x, y)  # Store anchor point

    @log_calls
    def add_entity(self, entity_id: str, x: int, y: int) -> bool:
        """
        Add an entity to the terrain at specified coordinates.

        Args:
            entity_id: Unique identifier for the entity
            x: X-coordinate for placement
            y: Y-coordinate for placement

        Returns:
            True if entity was successfully added, False otherwise

        Example:
            ```python
            # Add player to starting position
            if terrain.add_entity("player1", 0, 0):
                print("Player added to starting position")
            else:
                print("Failed to add player - position invalid or occupied")

            # Add multiple entities
            entities = [("goblin1", 5, 5), ("goblin2", 7, 8), ("chest1", 3, 4)]
            for entity_id, x, y in entities:
                terrain.add_entity(entity_id, x, y)
            ```
        """
        # Fetch entity from game_state to get its PositionComponent for width and height
        if not self.game_state:
            # Handle error: game_state not available
            return False
        entity = self.game_state.get_entity(entity_id)
        if not entity or "position" not in entity:
            return False  # Entity or position not found

        pos_comp = entity["position"]
        entity_width, entity_height = pos_comp.width, pos_comp.height

        if not self.is_valid_position(x, y, entity_width, entity_height) or \
           self.is_occupied(x, y, entity_width, entity_height):
            # Log error or handle: Cannot place entity here
            return False

        self._occupy_cells(entity_id, x, y, entity_width, entity_height)
        return True

    @log_calls
    def remove_entity(self, entity_id: str) -> bool:
        """
        Remove an entity from the terrain.

        Args:
            entity_id: Unique identifier for the entity to remove

        Returns:
            True if entity was successfully removed, False if entity wasn't found

        Example:
            ```python
            # Remove a defeated enemy
            if terrain.remove_entity("goblin1"):
                print("Enemy removed from terrain")
                # Update game state to handle defeated enemy
            else:
                print("Entity not found in terrain")
            ```
        """
        if entity_id not in self.entity_positions:
            return False

        # Clear all cells occupied by this entity
        self._clear_entity_occupancy(entity_id)

        # Remove from entity positions dictionary
        del self.entity_positions[entity_id]
        return True

    @log_calls
    def move_entity(self, entity_id: str, new_x: int, new_y: int) -> bool:
        """
        Move an entity to a new position.

        Args:
            entity_id: Unique identifier for the entity to move
            new_x: Destination X-coordinate
            new_y: Destination Y-coordinate

        Returns:
            True if entity was successfully moved, False otherwise

        Example:
            ```python
            # Move player based on input
            player_id = "player1"
            current_x, current_y = terrain.get_entity_position(player_id)

            # Try to move right
            if terrain.move_entity(player_id, current_x + 1, current_y):
                print("Player moved right")
            else:
                print("Cannot move right - position invalid or occupied")
            ```
        """
        # Size is fetched internally using _get_entity_size
        entity_width, entity_height = self._get_entity_size(entity_id)

        # Store old position for event
        old_pos = self.entity_positions.get(entity_id)
        if not old_pos:
            return False

        # Check if new position is valid, not occupied by other entities, and not a wall
        if not self.is_valid_position(new_x, new_y, entity_width, entity_height) or \
           self.is_occupied(new_x, new_y, entity_width, entity_height,
                          entity_id_to_ignore=entity_id, check_walls=True):
            return False

        # Clear old position
        self._clear_entity_occupancy(entity_id)

        # Set new position
        self._occupy_cells(entity_id, new_x, new_y, entity_width, entity_height)

        # Publish event with old and new positions
        self._publish(EVT_ENTITY_MOVED, {
            "entity_id": entity_id,
            "old_position": old_pos,
            "new_position": (new_x, new_y),
            "size": (entity_width, entity_height)
        })

        # The entity's own PositionComponent (x,y) is updated by the MovementSystem
        return True

    @log_calls
    def get_entity_at(self, x: int, y: int) -> Optional[str]:
        """
        Get the entity ID at a specific position.

        Args:
            x: X-coordinate to check
            y: Y-coordinate to check

        Returns:
            Entity ID if an entity exists at the position, None otherwise

        Example:
            ```python
            # Get entity at clicked position
            clicked_x, clicked_y = 5, 7
            entity_id = terrain.get_entity_at(clicked_x, clicked_y)

            if entity_id:
                print(f"Clicked on entity: {entity_id}")
                # Show entity details or interaction options
            else:
                print("No entity at clicked position")
            ```
        """
        return self.grid.get((x, y))

    @log_calls
    def get_entity_position(self, entity_id: str) -> Optional[Tuple[int, int]]:
        """
        Get the position of an entity.

        Args:
            entity_id: Unique identifier for the entity

        Returns:
            Tuple (x, y) with entity's position, or None if entity doesn't exist

        Example:
            ```python
            # Get player position for camera centering
            player_pos = terrain.get_entity_position("player1")

            if player_pos:
                x, y = player_pos
                camera.center_on(x, y)
            else:
                print("Player not found in terrain")
            ```
        """
        return self.entity_positions.get(entity_id)

    @log_calls
    def add_wall(self, x: int, y: int) -> bool:
        """
        Add a wall at the specified position.

        Args:
            x: X-coordinate for the wall
            y: Y-coordinate for the wall

        Returns:
            True if wall was successfully added, False otherwise

        Example:
            ```python
            # Add walls to create a room
            for x in range(5, 10):
                terrain.add_wall(x, 5)  # Top wall
                terrain.add_wall(x, 10)  # Bottom wall

            for y in range(6, 10):
                terrain.add_wall(5, y)  # Left wall
                terrain.add_wall(9, y)  # Right wall

            # Add door
            terrain.remove_wall(7, 5)
            ```
        """
        # Check if position is valid and not already a wall
        if not self.is_valid_position(x, y) or (x, y) in self.walls:
            return False

        self.walls.add((x, y))
        if (x, y) in self.walkable_cells:
            self.walkable_cells.remove((x, y))

        # After any terrain change, caches must be rebuilt to stay in sync
        self.rebuild_optimizer_wall_matrix()
        if hasattr(self, 'precompute_paths'): # Check if optimizer is attached
            self.precompute_paths()
            self.precompute_reachable_tiles()

        self._publish(EVT_WALL_ADDED, {"position": (x, y)})  # Publish wall added event
        self.game_state.bump_terrain_version() if getattr(self, 'game_state', None) else None
        return True

    @log_calls
    def remove_wall(self, x: int, y: int) -> bool:
        """
        Remove a wall at the specified position.

        Args:
            x: X-coordinate of the wall to remove
            y: Y-coordinate of the wall to remove

        Returns:
            True if wall was successfully removed, False if no wall existed

        Example:
            ```python
            # Remove wall to create doorway or opening
            if terrain.remove_wall(5, 7):
                print("Wall removed, pathway opened")
            else:
                print("No wall at that position")
            ```
        """
        if (x, y) in self.walls:
            self.walls.remove((x, y))
            self.walkable_cells.add((x, y))  # A cell without a wall is walkable

            # After any terrain change, caches must be rebuilt
            self.rebuild_optimizer_wall_matrix()
            if hasattr(self, 'precompute_paths'): # Check if optimizer is attached
                self.precompute_paths()
                self.precompute_reachable_tiles()

            self._publish(EVT_WALL_REMOVED, {"position": (x, y)})  # Publish wall removed event
            self.game_state.bump_terrain_version() if getattr(self, 'game_state', None) else None
            return True
        return False

    @log_calls
    def get_neighbors(self, x: int, y: int) -> List[Tuple[int, int]]:
        """
        Get walkable neighboring cells in the four cardinal directions.

        Args:
            x: X-coordinate of the center position
            y: Y-coordinate of the center position

        Returns:
            List of (x, y) tuples representing walkable adjacent cells

        Example:
            ```python
            # Get all walkable neighbors for movement options
            player_x, player_y = terrain.get_entity_position("player1")

            # Find valid moves
            valid_moves = terrain.get_neighbors(player_x, player_y)
            print(f"Player can move to {len(valid_moves)} adjacent cells")

            # Highlight possible movement options
            for move_x, move_y in valid_moves:
                ui.highlight_cell(move_x, move_y, color="blue")
            ```
        """
        neighbors = []
        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:  # Up, Right, Down, Left
            nx, ny = x + dx, y + dy
            if self.is_valid_position(nx, ny) and self.is_walkable(nx, ny):
                neighbors.append((nx, ny))
        return neighbors

    @log_calls
    def precompute_paths(self):
        """
        Precompute shortest paths between all walkable cell pairs using BFS.

        This method calculates and stores paths between all walkable cells for quick access,
        significantly improving performance for pathfinding operations.

        Note: This can be memory-intensive for large terrains. The result is stored
        in self.path_cache as a dictionary mapping (start_pos, end_pos) to path lists.

        Example:
            ```python
            # Precompute paths at terrain initialization
            terrain = Terrain(50, 50)

            # Set up walls, obstacles etc.
            terrain.add_wall(10, 10)
            terrain.add_wall(11, 10)

            # Precompute paths after all obstacles are set
            terrain.precompute_paths()

            # Later, retrieve cached path
            start_pos = (1, 1)
            end_pos = (20, 20)
            path = terrain.path_cache.get((start_pos, end_pos))

            if path:
                print(f"Found cached path with {len(path)} steps")
            ```
        """
        from collections import deque
        # path_cache type hint was added in __init__
        print("[Terrain] Precomputing paths...")
        for start in tqdm(self.walkable_cells, desc="Paths", unit="start"):
            visited: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {start: None} # Corrected type for visited
            queue = deque([start])
            while queue:
                current = queue.popleft()
                x, y = current
                neighbors = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
                for neighbor in neighbors:
                    if neighbor in self.walkable_cells and neighbor not in visited and neighbor not in self.walls:
                        visited[neighbor] = current # current is Tuple[int, int], fits Optional[Tuple[int, int]]
                        queue.append(neighbor)
            # Reconstruct paths from start to every reachable cell
            for end in visited:
                if end == start:
                    continue
                path: List[Tuple[int, int]] = []
                curr_step = end
                while curr_step is not None: # Iterate back using the predecessor chain
                    path.append(curr_step)
                    curr_step = visited[curr_step] # Get the predecessor
                path.reverse() # Reverse to get path from start to end
                if path and path[0] == start: # Ensure path starts with 'start'
                    self.path_cache[(start, end)] = path

    @log_calls
    def precompute_reachable_tiles(self, move_distances=(7, 15)):
        """
        Precompute reachable tiles for each cell and each movement allowance.

        For each walkable cell and movement distance, this method computes all
        cells that can be reached within the specified movement range, accounting
        for walls and obstacles.

        Args:
            move_distances: Tuple of movement distances to calculate for, typically
                           standard move and sprint distances (default: (7, 15))

        Note: Results are stored in self.reachable_tiles_cache as a dictionary
        mapping (start_pos, move_distance) to sets of reachable positions.

        Example:
            ```python
            # Precompute standard and sprint movement ranges
            terrain.precompute_reachable_tiles()

            # Precompute custom movement distances
            terrain.precompute_reachable_tiles(move_distances=(5, 10, 20))

            # Later, get tiles reachable from a position with standard movement
            start_pos = (5, 5)
            standard_movement = 7

            reachable_tiles = terrain.reachable_tiles_cache.get((start_pos, standard_movement), set())

            # Use for highlighting movement range or validating moves
            for tile_pos in reachable_tiles:
                ui.highlight_move_range(tile_pos[0], tile_pos[1])
            ```
        """
        # Updated to consider difficult terrain costs using a Dijkstra-like expansion
        from heapq import heappush, heappop
        self.reachable_tiles_cache = {}
        print("[Terrain] Precomputing reachable tiles (cost aware)...")
        for move_distance in move_distances:
            for start in tqdm(self.walkable_cells, desc=f"Reachable (move={move_distance})", unit="start"):
                best: Dict[Tuple[int,int], int] = {start:0}
                heap: List[Tuple[int,Tuple[int,int]]] = [(0,start)]
                reachable: Set[Tuple[int,int]] = set()
                while heap:
                    dist,(x,y) = heappop(heap)
                    if dist>move_distance:
                        continue
                    reachable.add((x,y))
                    for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]: # Adjacent cells
                        nx,ny = x+dx,y+dy
                        if (nx,ny) not in self.walkable_cells:
                            continue
                        if self._is_impassable(nx,ny):
                            continue
                        step = self.get_movement_cost(nx,ny)
                        nd = dist + step
                        if nd>move_distance:
                            continue
                        if nd < best.get((nx,ny), 10**9):
                            best[(nx,ny)] = nd
                            heappush(heap,(nd,(nx,ny)))
                self.reachable_tiles_cache[(start, move_distance)] = reachable

    def world_to_cell(self, coord):
        return (int(coord[0]), int(coord[1]))

    def is_wall(self, x: int, y: int) -> bool:
        return (x, y) in self.walls

    def rebuild_optimizer_wall_matrix(self):
        # Placeholder: optimizer not initialized in tests; avoid AttributeError
        return

    def _is_impassable(self, x:int, y:int) -> bool:
        # Minimal implementation: look for EFFECT_IMPASSABLE_SOLID or VOID effects on tile
        effects = self.effects_by_tile.get((x,y), [])
        for eff in effects:
            if eff.get('name') in (EFFECT_IMPASSABLE_SOLID, EFFECT_IMPASSABLE_VOID):
                return True
        return False

    def get_movement_cost(self, x:int, y:int) -> int:
        # Minimal implementation: difficult terrain doubles cost (2), very difficult triples (3)
        effects = self.effects_by_tile.get((x,y), [])
        cost = 1
        for eff in effects:
            name = eff.get('name')
            if name == EFFECT_DIFFICULT:
                cost = max(cost,2)
            elif name == EFFECT_VERY_DIFFICULT:
                cost = max(cost,3)
        return cost
