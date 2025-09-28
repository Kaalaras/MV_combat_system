from typing import Dict, Tuple, List, Optional, Set, Any, Callable # Ensure all are present
from utils.logger import log_calls
from tqdm import tqdm
import time

# Event constants
EVT_TERRAIN_CHANGED = "terrain_changed"
EVT_ENTITY_MOVED = "entity_moved"
EVT_WALL_ADDED = "wall_added"
EVT_WALL_REMOVED = "wall_removed"
# New terrain effect events
EVT_TERRAIN_EFFECT_ADDED = "terrain_effect_added"
EVT_TERRAIN_EFFECT_REMOVED = "terrain_effect_removed"
EVT_TERRAIN_EFFECT_TRIGGER = "terrain_effect_trigger"  # e.g. dangerous tile entered
EVT_TERRAIN_CURRENT_MOVED = "terrain_current_moved"     # entity displaced by current

# --- Terrain Effect constants ---
EFFECT_DIFFICULT = "difficult"
EFFECT_VERY_DIFFICULT = "very_difficult"
EFFECT_IMPASSABLE_SOLID = "impassable_solid"  # cannot enter
EFFECT_IMPASSABLE_VOID = "impassable_void"    # cannot end movement (future: allow jump)
EFFECT_DANGEROUS = "dangerous"
EFFECT_VERY_DANGEROUS = "very_dangerous"      # center tile (aura handled separately)
EFFECT_DANGEROUS_AURA = "dangerous_aura"      # aura tiles around very dangerous center
EFFECT_CURRENT = "current"                    # flowing movement each round
EFFECT_DARK_LOW = "dark_low"
EFFECT_DARK_TOTAL = "dark_total"
EFFECT_GRADIENT_KEY = 'gradient'


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
        # Modified: void tiles now non-walkable (cannot step onto), solid impassable also blocked.
        if not self.is_valid_position(x, y, entity_width, entity_height):
            return False
        for dy in range(entity_height):
            for dx in range(entity_width):
                cx, cy = x+dx, y+dy
                if (cx,cy) in self.walls:
                    return False
                if self._is_impassable_solid(cx,cy) or self._is_impassable_void(cx,cy):
                    return False
        return True

    @log_calls

    def is_walkable_traverse(self, x:int, y:int, entity_width:int=1, entity_height:int=1) -> bool:
        """Traversal variant kept equal to is_walkable for safety (no void pass-through)."""
        return self.is_walkable(x, y, entity_width, entity_height)
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
        # Trigger enter effects on anchor tile (only once per move)
        self.handle_entity_enter(entity_id, new_x, new_y)
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
        start_t = time.perf_counter()
        import heapq
        self.path_cache.clear()
        print('[Terrain] Precomputing paths (Dijkstra)...')
        for start in tqdm(self.walkable_cells, desc='Paths', unit='start'):
            if start in self.walls or self._is_impassable_solid(*start) or self._is_impassable_void(*start):
                continue
            dist: Dict[Tuple[int,int], int] = {start:0}
            prev: Dict[Tuple[int,int], Tuple[int,int]] = {}
            heap: List[Tuple[int,Tuple[int,int]]] = [(0,start)]
            while heap:
                d,(x,y) = heapq.heappop(heap)
                if d != dist[(x,y)]:
                    continue
                for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                    nx,ny = x+dx,y+dy
                    if (nx,ny) not in self.walkable_cells: continue
                    if (nx,ny) in self.walls: continue
                    if self._is_impassable_solid(nx,ny) or self._is_impassable_void(nx,ny): continue
                    step_cost = self.get_movement_cost(nx,ny)
                    nd = d + step_cost
                    if nd < dist.get((nx,ny), 10**9):
                        dist[(nx,ny)] = nd
                        prev[(nx,ny)] = (x,y)
                        heapq.heappush(heap,(nd,(nx,ny)))
            for end in dist:
                if end == start: continue
                if self._is_impassable_void(*end) or self._is_impassable_solid(*end):
                    continue
                path=[end]; cur=end
                while cur!=start:
                    cur=prev[cur]; path.append(cur)
                path.reverse(); self.path_cache[(start,end)] = path
        self.last_path_compute_seconds = time.perf_counter() - start_t

    @log_calls
    def precompute_reachable_tiles(self, move_distances=(7, 15)):
        start_t = time.perf_counter()
        from heapq import heappush, heappop
        self.reachable_tiles_cache = {}
        print('[Terrain] Precomputing reachable tiles (cost aware)...')
        for move_distance in move_distances:
            for start in tqdm(self.walkable_cells, desc=f'Reachable (move={move_distance})', unit='start'):
                if self._is_impassable_solid(*start) or self._is_impassable_void(*start):
                    continue
                best: Dict[Tuple[int,int], int] = {start:0}
                heap: List[Tuple[int,Tuple[int,int]]] = [(0,start)]
                reachable: Set[Tuple[int,int]] = set()
                while heap:
                    dist,(x,y)=heappop(heap)
                    if dist>move_distance: continue
                    reachable.add((x,y))
                    for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nx,ny = x+dx,y+dy
                        if (nx,ny) not in self.walkable_cells: continue
                        if (nx,ny) in self.walls: continue
                        if self._is_impassable_solid(nx,ny) or self._is_impassable_void(nx,ny): continue
                        step=self.get_movement_cost(nx,ny)
                        nd=dist+step
                        if nd>move_distance: continue
                        if nd < best.get((nx,ny),10**9):
                            best[(nx,ny)] = nd
                            heappush(heap,(nd,(nx,ny)))
                self.reachable_tiles_cache[(start,move_distance)] = reachable
        self.last_reachable_compute_seconds = time.perf_counter() - start_t

    def world_to_cell(self, coord):
        return (int(coord[0]), int(coord[1]))

    def is_wall(self, x: int, y: int) -> bool:
        return (x, y) in self.walls

    def rebuild_optimizer_wall_matrix(self):
        # Placeholder: optimizer not initialized in tests; avoid AttributeError
        return

    def add_effect(self, name: str, positions: List[Tuple[int,int]], **data) -> None:
        """Generic effect adder. Positions are tiles to mark.
        data merged into effect dict {name, data}.
        Publishes EVT_TERRAIN_EFFECT_ADDED once (batched) with summary."""
        added: List[Tuple[int,int]] = []
        for pos in positions:
            if not self.is_valid_position(pos[0], pos[1]):
                continue
            eff_list = self.effects_by_tile.setdefault(pos, [])
            eff_list.append({'name': name, 'data': data.copy()})
            added.append(pos)
        if added:
            self._publish(EVT_TERRAIN_EFFECT_ADDED, {"name": name, "positions": tuple(added), "data": data})
            # terrain changes affecting movement/path or LOS caches -> rebuild minimal
            if name in (EFFECT_DIFFICULT, EFFECT_VERY_DIFFICULT, EFFECT_IMPASSABLE_SOLID, EFFECT_IMPASSABLE_VOID, EFFECT_DARK_LOW, EFFECT_DARK_TOTAL,
                        EFFECT_DANGEROUS, EFFECT_VERY_DANGEROUS, EFFECT_DANGEROUS_AURA):
                self.rebuild_optimizer_wall_matrix()
                if hasattr(self, 'precompute_paths'):
                    self.precompute_paths()
                    self.precompute_reachable_tiles()
            self.game_state.bump_terrain_version() if getattr(self, 'game_state', None) else None

    def remove_effect(self, predicate: Callable[[dict], bool], positions: Optional[List[Tuple[int,int]]] = None) -> None:
        """Remove effects matching predicate at given positions (or all tiles if positions None)."""
        targets = positions if positions is not None else list(self.effects_by_tile.keys())
        removed_total: List[Tuple[int,int]] = []
        for pos in targets:
            effs = self.effects_by_tile.get(pos)
            if not effs:
                continue
            before = len(effs)
            effs = [e for e in effs if not predicate(e)]
            if effs:
                self.effects_by_tile[pos] = effs
            else:
                del self.effects_by_tile[pos]
            if len(effs) != before:
                removed_total.append(pos)
        if removed_total:
            self._publish(EVT_TERRAIN_EFFECT_REMOVED, {"positions": tuple(removed_total)})
            self.game_state.bump_terrain_version() if getattr(self, 'game_state', None) else None

    # Convenience wrappers -------------------------------------------------
    def add_difficult(self, positions: List[Tuple[int,int]]):
        self.add_effect(EFFECT_DIFFICULT, positions)
    def add_very_difficult(self, positions: List[Tuple[int,int]]):
        self.add_effect(EFFECT_VERY_DIFFICULT, positions)
    def add_impassable_solid(self, positions: List[Tuple[int,int]]):
        self.add_effect(EFFECT_IMPASSABLE_SOLID, positions)
    def add_impassable_void(self, positions: List[Tuple[int,int]]):
        self.add_effect(EFFECT_IMPASSABLE_VOID, positions)
    def add_dangerous(self, positions: List[Tuple[int,int]], difficulty: int = 2, damage: int = 1, aggravated: bool = False):
        self.add_effect(EFFECT_DANGEROUS, positions, difficulty=difficulty, damage=damage, aggravated=aggravated)
    def add_very_dangerous(self, center: Tuple[int,int], radius: int = 3, difficulty: int = 3, damage: int = 1, aggravated: bool = False, gradient: bool = False):
        self.add_effect(EFFECT_VERY_DANGEROUS, [center], difficulty=difficulty, damage=damage, aggravated=aggravated, radius=radius)
        cx, cy = center; aura_tiles: List[Tuple[int,int]] = []
        for dx in range(-radius, radius+1):
            for dy in range(-radius, radius+1):
                if dx==0 and dy==0: continue
                ax,ay = cx+dx, cy+dy
                if not self.is_valid_position(ax,ay): continue
                if abs(dx)+abs(dy) <= radius:
                    aura_tiles.append((ax,ay))
        if aura_tiles:
            self.add_effect(EFFECT_DANGEROUS_AURA, aura_tiles, source=center, difficulty=difficulty, damage=damage, aggravated=aggravated, radius=radius, gradient=gradient)
    def add_current(self, positions: List[Tuple[int,int]], dx: int, dy: int, magnitude: int = 1):
        # dx,dy define direction unit (or any vector). magnitude cells moved each round (can be overridden per-tile in data later)
        self.add_effect(EFFECT_CURRENT, positions, dx=dx, dy=dy, magnitude=magnitude)
    def add_dark_low(self, positions: List[Tuple[int,int]]):
        self.add_effect(EFFECT_DARK_LOW, positions)
    def add_dark_total(self, positions: List[Tuple[int,int]]):
        self.add_effect(EFFECT_DARK_TOTAL, positions)

    # Query helpers --------------------------------------------------------
    def get_effects(self, x:int, y:int) -> List[dict]:
        return self.effects_by_tile.get((x,y), [])
    def has_effect(self, x:int, y:int, name: str) -> bool:
        return any(eff.get('name') == name for eff in self.effects_by_tile.get((x,y), []))

    def handle_entity_enter(self, entity_id: str, x: int, y: int):
        # Aggregate strongest effects across the entity footprint, then publish one event per category.
        if self.game_state:
            w,h = self.game_state.get_entity_size(entity_id)
        else:
            w=h=1
        tiles = [(x+dx, y+dy) for dx in range(w) for dy in range(h)]
        best_vdanger = None
        best_danger = None
        best_aura = None
        for tx,ty in tiles:
            for eff in self.get_effects(tx,ty):
                nm = eff.get('name'); data = eff.get('data', {}) or {}
                if nm == EFFECT_VERY_DANGEROUS:
                    best_vdanger = data
                elif nm == EFFECT_DANGEROUS:
                    cur = best_danger or {}
                    if data.get('difficulty',0) > cur.get('difficulty',0) or data.get('damage',0) > cur.get('damage',0):
                        best_danger = data
                elif nm == EFFECT_DANGEROUS_AURA:
                    if data.get('gradient'):
                        # Prefer gradient aura with largest radius; if previous best was nongradient, prefer gradient.
                        if (not best_aura) or (best_aura.get('gradient') and data.get('radius',0) > best_aura.get('radius',0)) or (not best_aura.get('gradient')):
                            best_aura = data
                    else:
                        if not best_aura or (not best_aura.get('gradient') and data.get('intensity',0) > best_aura.get('intensity',0)):
                            best_aura = data
        if best_vdanger is not None:
            self._publish(EVT_TERRAIN_EFFECT_TRIGGER, {
                'entity_id': entity_id, 'position': (x,y), 'effect': EFFECT_VERY_DANGEROUS, 'auto_fail': True, **best_vdanger
            })
        if best_danger is not None:
            self._publish(EVT_TERRAIN_EFFECT_TRIGGER, {
                'entity_id': entity_id, 'position': (x,y), 'effect': EFFECT_DANGEROUS, **best_danger
            })
        if best_aura is not None:
            self._publish(EVT_TERRAIN_EFFECT_TRIGGER, {
                'entity_id': entity_id, 'position': (x,y), 'effect': EFFECT_DANGEROUS_AURA, **best_aura
            })
    def _is_impassable(self, x:int, y:int) -> bool:
        effects = self.effects_by_tile.get((x,y), [])
        for eff in effects:
            if eff.get('name') in (EFFECT_IMPASSABLE_SOLID, EFFECT_IMPASSABLE_VOID):  # VERY_DANGEROUS now enterable
                return True
        return False

    def _is_impassable_solid(self, x:int, y:int) -> bool:
        effects = self.effects_by_tile.get((x,y), [])
        for eff in effects:
            if eff.get('name') == EFFECT_IMPASSABLE_SOLID:
                return True
        return False

    def _is_impassable_void(self, x:int, y:int) -> bool:
        effects = self.effects_by_tile.get((x,y), [])
        for eff in effects:
            if eff.get('name') == EFFECT_IMPASSABLE_VOID:
                return True
        return False

    def get_movement_cost(self, x:int, y:int) -> int:
        effects = self.effects_by_tile.get((x,y), [])
        cost = 1
        max_aura_intensity = 0
        max_aura_radius = 0
        aura_has_gradient = False
        aura_source = None
        for eff in effects:
            nm = eff.get('name'); data = eff.get('data', {}) or {}
            if nm == EFFECT_DIFFICULT:
                cost = max(cost,2)
            elif nm == EFFECT_VERY_DIFFICULT:
                cost = max(cost,3)
            elif nm == EFFECT_DANGEROUS:
                cost = max(cost,4)
            elif nm == EFFECT_VERY_DANGEROUS:
                cost = max(cost,12)
            elif nm == EFFECT_DANGEROUS_AURA:
                if data.get('gradient'):
                    aura_has_gradient = True
                    radius = int(data.get('radius',3))
                    src = data.get('source')
                    if isinstance(src,(list,tuple)) and len(src)==2:
                        aura_source = src
                        max_aura_radius = max(max_aura_radius, radius)
                else:
                    intensity = int(data.get('intensity',1))
                    max_aura_intensity = max(max_aura_intensity, intensity)
        # Apply aura effect
        if aura_has_gradient and aura_source is not None:
            dist = abs(x - aura_source[0]) + abs(y - aura_source[1])
            cost = max(cost, min(6, 4 + max(0, max_aura_radius - dist)))
        elif max_aura_intensity > 0:
            cost = max(cost, min(6, 3 + max_aura_intensity))
        return cost