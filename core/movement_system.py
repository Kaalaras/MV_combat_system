from typing import List, Tuple, Dict, Any, Set
from ecs.systems.ai.utils import get_occupied_static
from itertools import product
import heapq
from core.terrain_manager import EFFECT_IMPASSABLE_VOID


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

    # --- Opportunity Attack Helpers -------------------------------------------------
    def _collect_adjacent_opportunity_sources(self, mover_id: str) -> List[str]:
        """Return list of entity_ids that are adjacent (Manhattan distance 1) to mover and
        eligible to perform an opportunity attack (toggle flag True).
        """
        mover = self.game_state.get_entity(mover_id)
        if not mover or 'position' not in mover:
            return []
        mover_team = None
        if 'character_ref' in mover:
            mover_team = getattr(mover['character_ref'].character, 'team', None)
        mx, my = mover['position'].x, mover['position'].y
        sources: List[str] = []
        
        # Get all entities with character_ref using ECS
        from ecs.components.character_ref import CharacterRefComponent
        from ecs.components.position import PositionComponent
        from ecs.components.equipment import EquipmentComponent
        
        if self.game_state.ecs_manager:
            try:
                entities_with_char_ref = self.game_state.ecs_manager.get_components(CharacterRefComponent)
                for eid, (char_ref_comp,) in entities_with_char_ref:
                    if str(eid) == mover_id:
                        continue
                    
                    # Get position component
                    try:
                        pos_comp = self.game_state.ecs_manager.get_component(eid, PositionComponent)
                        if not pos_comp:
                            continue
                    except:
                        continue
                    
                    char = getattr(char_ref_comp, 'character', None)
                    if not char or not getattr(char, 'toggle_opportunity_attack', False):
                        continue
                    
                    # Team / hostility filter: must be different team if both teams defined
                    attacker_team = getattr(char, 'team', None)
                    if mover_team is not None and attacker_team is not None and attacker_team == mover_team:
                        continue
                    
                    # Require melee-capable weapon (melee or brawl) in equipment
                    melee_capable = False
                    try:
                        equip = self.game_state.ecs_manager.get_component(eid, EquipmentComponent)
                        if equip and hasattr(equip, 'weapons'):
                            for w in getattr(equip, 'weapons', {}).values():
                                wtype = getattr(w, 'weapon_type', None)
                                base_type = getattr(wtype, 'value', wtype)
                                if base_type in ('melee', 'brawl'):
                                    melee_capable = True
                                    break
                    except:
                        pass
                    
                    if not melee_capable:
                        continue
                    
                    # Range check: adjacent
                    if abs(pos_comp.x - mx) + abs(pos_comp.y - my) == 1:  # adjacent
                        sources.append(str(eid))
            except AttributeError:
                # Fallback if get_components doesn't exist
                pass
        
        return sources

    def _trigger_opportunity_attacks(self, mover_id: str, previous_adjacent: List[str]):
        """Given list of entities that were adjacent before movement, trigger AoO for each
        that is no longer adjacent after movement. Publishes 'opportunity_attack_triggered'.
        Only basic event emission; actual attack resolution (if any) handled elsewhere.
        """
        if not previous_adjacent:
            return
        mover = self.game_state.get_entity(mover_id)
        if not mover or 'position' not in mover:
            return
        mx, my = mover['position'].x, mover['position'].y
        bus = getattr(self.game_state, 'event_bus', None)
        for attacker_id in previous_adjacent:
            ent = self.game_state.get_entity(attacker_id)
            if not ent or 'position' not in ent:
                continue
            pos = ent['position']
            # Still adjacent? then no trigger.
            if abs(pos.x - mx) + abs(pos.y - my) == 1:
                continue
            # Re-check toggle (it may have changed during move effects)
            char_ref = ent.get('character_ref')
            char = getattr(char_ref, 'character', None) if char_ref else None
            if not char or not getattr(char, 'toggle_opportunity_attack', False):
                continue
            if bus:
                bus.publish('opportunity_attack_triggered', attacker_id=attacker_id, target_id=mover_id, origin_adjacent=True)
    # ---------------------------------------------------------------------------------

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

    def move(self, entity_id: str, dest: Tuple[int, int], max_steps: int | None = None, pathfind: bool = False, provoke_aoo: bool = True) -> bool:
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
            return self.path_move(entity_id, dest, max_steps=max_steps, provoke_aoo=provoke_aoo)
        entity = self.game_state.get_entity(entity_id)
        if not entity or 'position' not in entity:
            return False
        pre_adjacent = self._collect_adjacent_opportunity_sources(entity_id) if provoke_aoo else []
        pos_comp = entity['position']
        width = getattr(pos_comp,'width',1); height = getattr(pos_comp,'height',1)
        cur_x, cur_y = pos_comp.x, pos_comp.y
        dest_x, dest_y = dest
        distance = abs(dest_x - cur_x) + abs(dest_y - cur_y)
        if max_steps is not None and distance > max_steps:
            return False
        terrain = self.game_state.terrain
        void_tile = False
        if hasattr(terrain, 'has_effect'):
            hf = getattr(terrain, 'has_effect')
            if callable(hf):
                try:
                    vt_res = hf(dest_x, dest_y, EFFECT_IMPASSABLE_VOID)
                    void_tile = (vt_res is True)  # only treat explicit True as void
                except Exception:
                    void_tile = False
        # Occupancy / forbid / bounds checks
        if terrain.is_occupied(dest_x, dest_y, width, height, entity_id_to_ignore=entity_id):
            return False
        fl = getattr(terrain, 'forbid_landing', None)
        if callable(fl):
            try:
                fl_res = fl(dest_x, dest_y)
                if fl_res is True:  # only explicit True forbids landing
                    return False
            except Exception:
                pass
        ivp = getattr(terrain,'is_valid_position', None)
        if callable(ivp) and not ivp(dest_x, dest_y, width, height):
            return False
        if (cur_x, cur_y) == (dest_x, dest_y):
            if not terrain.is_walkable(dest_x, dest_y, width, height) and not void_tile:
                return False
            return True
        if not terrain.is_walkable(dest_x, dest_y, width, height) and not void_tile:
            return False
        # Fire AoO events BEFORE moving: any pre-adjacent attacker for which destination is NOT adjacent
        if pre_adjacent and provoke_aoo:
            bus = getattr(self.game_state, 'event_bus', None)
            if bus:
                for attacker_id in pre_adjacent:
                    att = self.game_state.get_entity(attacker_id)
                    if not att or 'position' not in att:
                        continue
                    ap = att['position']
                    # If attacker will still be adjacent to destination, no opportunity attack
                    if abs(ap.x - dest_x) + abs(ap.y - dest_y) == 1:
                        continue
                    char_ref = att.get('character_ref')
                    char = getattr(char_ref, 'character', None) if char_ref else None
                    if not char or not getattr(char, 'toggle_opportunity_attack', False):
                        continue
                    bus.publish('opportunity_attack_triggered', attacker_id=attacker_id, target_id=entity_id, origin_adjacent=True)
        # Perform move AFTER AoO resolution
        pos_comp.x, pos_comp.y = dest_x, dest_y
        if hasattr(terrain, 'move_entity'):
            if not terrain.move_entity(entity_id, dest_x, dest_y):
                return False
        if hasattr(self.game_state, 'add_movement_steps'):
            self.game_state.add_movement_steps(entity_id, distance)
        if hasattr(self.game_state, 'bump_blocker_version') and (('character_ref' in entity) or ('cover' in entity)):
            self.game_state.bump_blocker_version()
        if void_tile and hasattr(self.game_state, 'kill_entity'):
            self.game_state.kill_entity(entity_id, cause='void')
        return True

    def path_move(self, entity_id: str, dest: Tuple[int, int], max_steps: int | None = None, provoke_aoo: bool = True) -> bool:
        """Legacy path-based multi-step move (extracted from previous move implementation).
        Enhanced: triggers opportunity attacks stepwise upon leaving adjacency of any enemy
        that had adjacency at the beginning of a step.
        """
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
        terrain = self.game_state.terrain
        if hasattr(terrain,'forbid_landing'):
            fl = getattr(terrain,'forbid_landing')
            if callable(fl):
                try:
                    if fl(dest[0], dest[1]) is True:
                        return False
                except Exception:
                    pass
        void_tile = False
        if hasattr(terrain,'has_effect'):
            hf = getattr(terrain,'has_effect')
            if callable(hf):
                try:
                    vt_res = hf(dest[0], dest[1], EFFECT_IMPASSABLE_VOID)
                    void_tile = (vt_res is True)
                except Exception:
                    void_tile = False
        total_cost = 0
        for (x,y) in path[1:]:
            step_cost = terrain.get_movement_cost(x,y) if hasattr(terrain,'get_movement_cost') else 1
            total_cost += step_cost
            if max_steps is not None and total_cost>max_steps:
                return False
        for (x,y) in path[1:]:
            pre_adjacent = self._collect_adjacent_opportunity_sources(entity_id) if provoke_aoo else []
            # publish AoO triggers for those losing adjacency relative to next step
            if pre_adjacent and provoke_aoo:
                bus = getattr(self.game_state, 'event_bus', None)
                if bus:
                    for attacker_id in pre_adjacent:
                        att = self.game_state.get_entity(attacker_id)
                        if not att or 'position' not in att:
                            continue
                        ap = att['position']
                        if abs(ap.x - x) + abs(ap.y - y) == 1:
                            continue
                        char_ref = att.get('character_ref'); char = getattr(char_ref,'character', None) if char_ref else None
                        if not char or not getattr(char,'toggle_opportunity_attack', False):
                            continue
                        bus.publish('opportunity_attack_triggered', attacker_id=attacker_id, target_id=entity_id, origin_adjacent=True)
            if not terrain.move_entity(entity_id, x, y):
                return False
            pos_comp.x, pos_comp.y = x, y
            if hasattr(self.game_state, 'add_movement_steps'):
                self.game_state.add_movement_steps(entity_id, terrain.get_movement_cost(x,y) if hasattr(terrain,'get_movement_cost') else 1)
            if hasattr(self.game_state, 'bump_blocker_version') and (('character_ref' in entity) or ('cover' in entity)):
                self.game_state.bump_blocker_version()
        if void_tile and hasattr(self.game_state,'kill_entity'):
            self.game_state.kill_entity(entity_id, cause='void')
        return True
