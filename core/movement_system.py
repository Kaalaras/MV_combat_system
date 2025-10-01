from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple, Type, Set, cast
import heapq
from itertools import product

from ecs.components.character_ref import CharacterRefComponent
from ecs.components.cover import CoverComponent
from ecs.components.equipment import EquipmentComponent
from ecs.components.movement_usage import MovementUsageComponent
from ecs.components.position import PositionComponent
from ecs.ecs_manager import ECSManager
from ecs.helpers.occupancy import collect_blocked_tiles
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
    from core.event_bus import EventBus
    from ecs.ecs_manager import ECSManager

    event_bus = EventBus()
    ecs_manager = ECSManager(event_bus)
    game_state.ecs_manager = ecs_manager

    # Initialize movement system with ECS context
    movement_system = MovementSystem(game_state, ecs_manager, event_bus=event_bus)

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

    def __init__(
        self,
        game_state: Any,
        ecs_manager: Optional[ECSManager] = None,
        *,
        event_bus: Any | None = None,
    ) -> None:
        """
        Initializes the MovementSystem with a reference to the game state.

        Args:
            game_state: The central game state object providing access to entities and terrain

        Example:
            ```python
            event_bus = EventBus()
            ecs_manager = ECSManager(event_bus)
            movement_system = MovementSystem(game_state, ecs_manager, event_bus=event_bus)
            ```
        """
        if game_state is None:
            raise ValueError("MovementSystem requires a GameState instance.")

        manager_candidate = ecs_manager or getattr(game_state, "ecs_manager", None)
        if manager_candidate is None or not hasattr(manager_candidate, "iter_with_id"):
            raise ValueError(
                "MovementSystem requires an ECSManager. Provide ecs_manager explicitly as a parameter."
            )

        self.game_state = game_state
        self.ecs_manager: ECSManager = cast(ECSManager, manager_candidate)
        resolved_event_bus = event_bus or getattr(self.ecs_manager, "event_bus", None)
        if resolved_event_bus is None:
            resolved_event_bus = getattr(self.game_state, "event_bus", None)
        self.event_bus = resolved_event_bus

    # --- Internal component helpers ----------------------------------------------
    def _iter_entities_with(
        self, *component_types: Type[Any]
    ) -> Iterator[Tuple[str, ...]]:
        """Yield ``(entity_id, *components)`` using ECS when available."""

        yield from self.ecs_manager.iter_with_id(*component_types)

    def _get_component(self, entity_id: str, component_type: Type[Any]) -> Optional[Any]:
        component_tuple = self.ecs_manager.get_components_for_entity(entity_id, component_type)
        if component_tuple is None or not component_tuple:
            return None
        return component_tuple[0]

    @staticmethod
    def _bounding_box(position: Any) -> Optional[Tuple[int, int, int, int]]:
        if position is None:
            return None
        if hasattr(position, "x1") and hasattr(position, "y1") and hasattr(position, "x2") and hasattr(position, "y2"):
            return int(position.x1), int(position.y1), int(position.x2), int(position.y2)
        x = getattr(position, "x", None)
        y = getattr(position, "y", None)
        if x is not None and y is not None:
            width = int(getattr(position, "width", 1))
            height = int(getattr(position, "height", 1))
            return int(x), int(y), int(x) + width - 1, int(y) + height - 1
        if isinstance(position, tuple) and len(position) >= 2:
            return int(position[0]), int(position[1]), int(position[0]), int(position[1])
        return None

    @classmethod
    def _are_positions_adjacent(cls, pos_a: Any, pos_b: Any) -> bool:
        bbox_a = cls._bounding_box(pos_a)
        bbox_b = cls._bounding_box(pos_b)
        if not bbox_a or not bbox_b:
            return False
        ax1, ay1, ax2, ay2 = bbox_a
        bx1, by1, bx2, by2 = bbox_b
        dx = max(0, ax1 - bx2, bx1 - ax2)
        dy = max(0, ay1 - by2, by1 - ay2)
        return dx + dy == 1

    def _get_team_id(self, entity_id: str) -> Optional[Any]:
        char_ref = self._get_component(entity_id, CharacterRefComponent)
        if not char_ref:
            return None
        character = getattr(char_ref, "character", None)
        if not character:
            return None
        return getattr(character, "team", None)

    @staticmethod
    def _is_melee_capable(equipment: Any) -> bool:
        if not equipment or not hasattr(equipment, "weapons"):
            return False
        weapons = getattr(equipment, "weapons", {})
        for weapon in weapons.values():
            if weapon is None:
                continue
            weapon_type = getattr(weapon, "weapon_type", None)
            base_type = getattr(weapon_type, "value", weapon_type)
            if base_type in ("melee", "brawl"):
                return True
        return False

    def _record_movement_usage(self, entity_id: str, distance: int) -> None:
        if distance <= 0:
            return

        def add_to_component() -> None:
            internal_id = self.ecs_manager.resolve_entity(entity_id)
            if internal_id is None:
                return
            component = self.ecs_manager.try_get_component(internal_id, MovementUsageComponent)
            if component is None:
                component = MovementUsageComponent()
                self.ecs_manager.add_component(internal_id, component)
            component.add(distance)

        publish = getattr(self.event_bus, "publish", None) if self.event_bus else None
        if callable(publish):
            add_to_component()
            publish(
                "movement_distance_spent",
                entity_id=entity_id,
                distance=distance,
            )
            return

        if hasattr(self.game_state, "add_movement_steps"):
            self.game_state.add_movement_steps(entity_id, distance)
            return

        add_to_component()

    def register_movement_usage(self, entity_id: str, distance: int) -> None:
        """Public helper for non-movement-system callers to log travel distance."""

        self._record_movement_usage(entity_id, distance)

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
        """Return entity ids adjacent to ``mover_id`` eligible for opportunity attacks."""

        mover_position = self._get_component(mover_id, PositionComponent)
        if mover_position is None:
            return []

        mover_team = self._get_team_id(mover_id)
        sources: List[str] = []
        for eid, pos_comp, char_ref, equipment in self._iter_entities_with(
            PositionComponent,
            CharacterRefComponent,
            EquipmentComponent,
        ):
            if eid == mover_id:
                continue
            character = getattr(char_ref, "character", None)
            if not character or not getattr(character, "toggle_opportunity_attack", False):
                continue
            attacker_team = getattr(character, "team", None)
            if (
                mover_team is not None
                and attacker_team is not None
                and attacker_team == mover_team
            ):
                continue
            if not self._is_melee_capable(equipment):
                continue
            if self._are_positions_adjacent(mover_position, pos_comp):
                sources.append(eid)
        return sources

    def _trigger_opportunity_attacks(
        self,
        mover_id: str,
        previous_adjacent: List[str],
        future_position: PositionComponent | None = None,
    ) -> None:
        """Given list of entities that were adjacent before movement, trigger AoO for each
        that is no longer adjacent after movement. Publishes 'opportunity_attack_triggered'.
        Only basic event emission; actual attack resolution (if any) handled elsewhere.
        """
        if not previous_adjacent:
            return
        mover_position = self._get_component(mover_id, PositionComponent)
        if mover_position is None:
            return
        bus = self.event_bus
        for attacker_id in previous_adjacent:
            attacker_position = self._get_component(attacker_id, PositionComponent)
            if attacker_position is None:
                continue
            if future_position is not None:
                if self._are_positions_adjacent(future_position, attacker_position):
                    continue
            elif self._are_positions_adjacent(mover_position, attacker_position):
                continue
            char_ref = self._get_component(attacker_id, CharacterRefComponent)
            character = getattr(char_ref, "character", None) if char_ref else None
            if not character or not getattr(character, "toggle_opportunity_attack", False):
                continue
            if bus:
                bus.publish(
                    'opportunity_attack_triggered',
                    attacker_id=attacker_id,
                    target_id=mover_id,
                    origin_adjacent=True,
                )
    # ---------------------------------------------------------------------------------

    def get_reachable_tiles(self, entity_id: str, max_distance: int, reserved_tiles: Set[Tuple[int, int]] = None) -> List[Tuple[int, int, int]]:
        """Cost-aware reachable tiles using terrain movement cost (1/2/3)."""
        pos_comp = self._get_component(entity_id, PositionComponent)
        if pos_comp is None:
            return []
        start_pos = (pos_comp.x, pos_comp.y)
        entity_width = getattr(pos_comp, 'width', 1)
        entity_height = getattr(pos_comp, 'height', 1)
        terrain = getattr(self.game_state, "terrain", None)
        if terrain is None:
            return []
        reserved = reserved_tiles or set()
        static_occ = collect_blocked_tiles(
            self.ecs_manager,
            ignore_entities={entity_id},
            terrain=terrain,
        )
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
        pos_comp = self._get_component(entity_id, PositionComponent)
        if pos_comp is None:
            return []
        start = (pos_comp.x, pos_comp.y)
        if start == dest:
            return [start]
        terrain = getattr(self.game_state, "terrain", None)
        if terrain is None:
            return []
        entity_width = getattr(pos_comp,'width',1)
        entity_height = getattr(pos_comp,'height',1)
        static_occ = collect_blocked_tiles(
            self.ecs_manager,
            ignore_entities={entity_id},
            terrain=terrain,
        )
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
        pos_comp = self._get_component(entity_id, PositionComponent)
        if pos_comp is None:
            return False
        if self.game_state and not self.game_state.get_entity(entity_id):
            return False
        pre_adjacent = self._collect_adjacent_opportunity_sources(entity_id) if provoke_aoo else []
        has_char_ref = self._get_component(entity_id, CharacterRefComponent) is not None
        has_cover = self._get_component(entity_id, CoverComponent) is not None
        width = getattr(pos_comp,'width',1); height = getattr(pos_comp,'height',1)
        cur_x, cur_y = pos_comp.x, pos_comp.y
        dest_x, dest_y = dest
        distance = abs(dest_x - cur_x) + abs(dest_y - cur_y)
        if max_steps is not None and distance > max_steps:
            return False
        terrain = getattr(self.game_state, 'terrain', None)
        if terrain is None:
            return False
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
        future_position = PositionComponent(dest_x, dest_y, width=width, height=height)
        if provoke_aoo:
            self._trigger_opportunity_attacks(
                entity_id,
                pre_adjacent,
                future_position=future_position,
            )
        # Perform move and update terrain occupancy
        move_performed = False
        if hasattr(terrain, 'move_entity'):
            try:
                move_result = terrain.move_entity(entity_id, dest_x, dest_y)
            except Exception:
                move_result = False
            if move_result is False:
                return False
            move_performed = True
        pos_comp.x, pos_comp.y = dest_x, dest_y
        self._record_movement_usage(entity_id, distance)
        if (
            hasattr(self.game_state, 'bump_blocker_version')
            and (has_char_ref or has_cover)
        ):
            self.game_state.bump_blocker_version()
        if void_tile and hasattr(self.game_state, 'kill_entity'):
            self.game_state.kill_entity(entity_id, cause='void')
        return True

    def path_move(self, entity_id: str, dest: Tuple[int, int], max_steps: int | None = None, provoke_aoo: bool = True) -> bool:
        """Legacy path-based multi-step move (extracted from previous move implementation).
        Enhanced: triggers opportunity attacks stepwise upon leaving adjacency of any enemy
        that had adjacency at the beginning of a step.
        """
        pos_comp = self._get_component(entity_id, PositionComponent)
        if pos_comp is None:
            return False
        if self.game_state and not self.game_state.get_entity(entity_id):
            return False
        start = (pos_comp.x, pos_comp.y)
        if start == dest:
            return True
        path = self.find_path(entity_id, dest, max_distance=max_steps if max_steps is not None else None)
        if not path:
            return False
        terrain = getattr(self.game_state, 'terrain', None)
        if terrain is None:
            return False
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
        has_char_ref = self._get_component(entity_id, CharacterRefComponent) is not None
        has_cover = self._get_component(entity_id, CoverComponent) is not None
        entity_width = getattr(pos_comp, 'width', 1)
        entity_height = getattr(pos_comp, 'height', 1)
        for (x,y) in path[1:]:
            pre_adjacent = self._collect_adjacent_opportunity_sources(entity_id) if provoke_aoo else []
            future_position = PositionComponent(
                x,
                y,
                width=entity_width,
                height=entity_height,
            )
            if provoke_aoo:
                self._trigger_opportunity_attacks(
                    entity_id,
                    pre_adjacent,
                    future_position=future_position,
                )
            if hasattr(terrain, 'move_entity'):
                if not terrain.move_entity(entity_id, x, y):
                    return False
            pos_comp.x, pos_comp.y = x, y
            step_distance = terrain.get_movement_cost(x,y) if hasattr(terrain,'get_movement_cost') else 1
            self._record_movement_usage(entity_id, step_distance)
            if (
                hasattr(self.game_state, 'bump_blocker_version')
                and (has_char_ref or has_cover)
            ):
                self.game_state.bump_blocker_version()
        if void_tile and hasattr(self.game_state,'kill_entity'):
            self.game_state.kill_entity(entity_id, cause='void')
        return True
