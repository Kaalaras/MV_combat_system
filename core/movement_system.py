from typing import List, Tuple, Dict, Any, Set, Deque
from collections import deque
from ecs.systems.ai.utils import get_occupied_static
from itertools import product
import heapq


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
        """Cost-aware reachable tiles using terrain movement cost (1/2/3)."""
        entity = self.game_state.get_entity(entity_id)
        if not entity or "position" not in entity:
            return []
        pos_comp = entity["position"]
        start_pos = (pos_comp.x, pos_comp.y)
        entity_width = getattr(pos_comp, 'width', 1)
        entity_height = getattr(pos_comp, 'height', 1)
        terrain = self.game_state.terrain
        reserved = reserved_tiles or set()
        static_occ = get_occupied_static(self.game_state)
        entity = self.game_state.get_entity(entity_id)
        pos = entity.get("position")
        width = getattr(pos, 'width', 1)
        height = getattr(pos, 'height', 1)
        start_x, start_y = (pos.x, pos.y) if hasattr(pos, 'x') else pos
        for dx, dy in product(range(width), range(height)):
            static_occ.discard((start_x + dx, start_y + dy))
        blocked = reserved.union(static_occ)
        # Dijkstra
        heap: List[Tuple[int, Tuple[int,int]]] = [(0, start_pos)]
        best: Dict[Tuple[int,int], int] = {start_pos:0}
        reachable: List[Tuple[int,int,int]] = []
        while heap:
            dist,(x,y) = heapq.heappop(heap)
            if dist>max_distance: continue
            reachable.append((x,y,dist))
            for dx,dy in [(0,1),(1,0),(0,-1),(-1,0)]:
                nx,ny = x+dx,y+dy
                if (nx,ny) in blocked: continue
                if not terrain.is_walkable(nx, ny, entity_width, entity_height) or \
                   terrain.is_occupied(nx, ny, entity_width, entity_height, entity_id_to_ignore=entity_id):
                    continue
                raw_cost_fn = getattr(terrain,'get_movement_cost', None)
                if callable(raw_cost_fn):
                    try:
                        step_cost_val = raw_cost_fn(nx, ny)
                        step_cost = int(step_cost_val)
                    except (TypeError, ValueError):
                        step_cost = 1
                else:
                    step_cost = 1
                nd = dist + step_cost
                if nd>max_distance: continue
                if nd < best.get((nx,ny), 10**9):
                    best[(nx,ny)] = nd
                    heapq.heappush(heap,(nd,(nx,ny)))
        return reachable

    def find_path(self, entity_id: str, dest: Tuple[int,int], max_distance: int | None = None) -> List[Tuple[int,int]]:
        """Cost-aware shortest path (movement cost)."""
        entity = self.game_state.get_entity(entity_id)
        if not entity or 'position' not in entity:
            return []
        pos_comp = entity['position']
        start = (pos_comp.x, pos_comp.y)
        if start == dest:
            return [start]
        terrain = self.game_state.terrain
        entity_width = getattr(pos_comp,'width',1)
        entity_height = getattr(pos_comp,'height',1)
        static_occ = get_occupied_static(self.game_state)
        for dx,dy in product(range(entity_width), range(entity_height)):
            static_occ.discard((start[0]+dx, start[1]+dy))
        heap: List[Tuple[int,Tuple[int,int]]] = [(0,start)]
        best: Dict[Tuple[int,int], int] = {start:0}
        parent: Dict[Tuple[int,int], Tuple[int,int]] = {}
        while heap:
            dist,(x,y) = heapq.heappop(heap)
            if (max_distance is not None) and dist>max_distance:
                continue
            if (x,y)==dest:
                # reconstruct
                path=[(x,y)]
                cur=(x,y)
                while cur!=start:
                    cur=parent[cur]
                    path.append(cur)
                path.reverse()
                return path
            for dx,dy in [(0,1),(1,0),(0,-1),(-1,0)]:
                nx,ny = x+dx,y+dy
                if (nx,ny) in static_occ: continue
                if not terrain.is_walkable(nx, ny, entity_width, entity_height) or \
                   terrain.is_occupied(nx, ny, entity_width, entity_height, entity_id_to_ignore=entity_id):
                    continue
                raw_cost_fn = getattr(terrain,'get_movement_cost', None)
                if callable(raw_cost_fn):
                    try:
                        step_cost_val = raw_cost_fn(nx, ny)
                        step_cost = int(step_cost_val)
                    except (TypeError, ValueError):
                        step_cost = 1
                else:
                    step_cost = 1
                nd = dist + step_cost
                if (max_distance is not None) and nd>max_distance: continue
                if nd < best.get((nx,ny), 10**9):
                    best[(nx,ny)] = nd
                    parent[(nx,ny)] = (x,y)
                    heapq.heappush(heap,(nd,(nx,ny)))
        return []

    def move(self, entity_id: str, dest: Tuple[int, int], max_steps: int | None = None, pathfind: bool = False) -> bool:
        """Move an entity.
        Default is a direct (single-tile destination) validation + move used by unit tests.
        Set pathfind=True to use path-based stepwise movement (previous implementation).
        Args:
            entity_id: entity identifier
            dest: (x,y) destination anchor
            max_steps: optional cap (only relevant when pathfind=True or for direct distance validation)
            pathfind: if True, perform BFS path movement (legacy behavior)
        Returns: True on success, False otherwise.
        """
        if pathfind:
            return self.path_move(entity_id, dest, max_steps=max_steps)
        entity = self.game_state.get_entity(entity_id)
        if not entity or 'position' not in entity:
            return False
        pos_comp = entity['position']
        cur_x, cur_y = pos_comp.x, pos_comp.y
        dest_x, dest_y = dest
        # Manhattan distance for direct move constraint
        distance = abs(dest_x - cur_x) + abs(dest_y - cur_y)
        if max_steps is not None and distance > max_steps:
            return False
        terrain = self.game_state.terrain
        if hasattr(terrain, '_get_entity_size'):
            try:
                width, height = terrain._get_entity_size(entity_id)
            except Exception:
                width = getattr(pos_comp, 'width', 1)
                height = getattr(pos_comp, 'height', 1)
        else:
            width = getattr(pos_comp, 'width', 1)
            height = getattr(pos_comp, 'height', 1)
        # If destination is current position, re-validate footprint rather than auto-success
        if (cur_x, cur_y) == (dest_x, dest_y):
            if hasattr(terrain, 'is_valid_position') and not terrain.is_valid_position(dest_x, dest_y, width, height):
                return False
            if not terrain.is_walkable(dest_x, dest_y, width, height):
                return False
            if terrain.is_occupied(dest_x, dest_y, width, height, entity_id_to_ignore=entity_id):
                return False
            return True
        # Validate destination
        if hasattr(terrain, 'is_valid_position') and not terrain.is_valid_position(dest_x, dest_y, width, height):
            return False
        if terrain.is_occupied(dest_x, dest_y, width, height, entity_id_to_ignore=entity_id):
            return False
        if not terrain.is_walkable(dest_x, dest_y, width, height):
            return False
        # Perform move
        pos_comp.x, pos_comp.y = dest_x, dest_y
        if hasattr(terrain, 'move_entity'):
            if not terrain.move_entity(entity_id, dest_x, dest_y):
                return False
        if hasattr(self.game_state, 'add_movement_steps'):
            self.game_state.add_movement_steps(entity_id, distance)
        # Bump blocker version if entity provides blocking (character or cover)
        if hasattr(self.game_state, 'bump_blocker_version') and (('character_ref' in entity) or ('cover' in entity)):
            self.game_state.bump_blocker_version()
        return True

    def path_move(self, entity_id: str, dest: Tuple[int, int], max_steps: int | None = None) -> bool:
        """Legacy path-based multi-step move (extracted from previous move implementation)."""
        entity = self.game_state.get_entity(entity_id)
        if not entity or 'position' not in entity:
            return False
        pos_comp = entity['position']
        start = (pos_comp.x, pos_comp.y)
        if start == dest:
            return True
        path = self.find_path(entity_id, dest, max_distance=max_steps if max_steps is not None else None)
        if not path:
            return False
        # Compute cumulative cost
        terrain = self.game_state.terrain
        total_cost = 0
        for (x,y) in path[1:]:
            step_cost = terrain.get_movement_cost(x,y) if hasattr(terrain,'get_movement_cost') else 1
            total_cost += step_cost
            if max_steps is not None and total_cost>max_steps:
                return False
        # Execute
        for (x,y) in path[1:]:
            if not terrain.move_entity(entity_id, x, y):
                return False
            pos_comp.x, pos_comp.y = x, y
            if hasattr(self.game_state, 'add_movement_steps'):
                self.game_state.add_movement_steps(entity_id, terrain.get_movement_cost(x,y) if hasattr(terrain,'get_movement_cost') else 1)
            if hasattr(self.game_state, 'bump_blocker_version') and (('character_ref' in entity) or ('cover' in entity)):
                self.game_state.bump_blocker_version()
        return True
