from __future__ import annotations

import heapq
from typing import Any, Dict, List, Optional, Set, Tuple, Type, cast

from ecs.components.character_ref import CharacterRefComponent
from ecs.components.cover import CoverComponent
from ecs.components.facing import FacingComponent
from ecs.components.movement_usage import MovementUsageComponent
from ecs.components.position import PositionComponent
from ecs.ecs_manager import ECSManager
from ecs.helpers.occupancy import collect_blocked_tiles
from interface.event_constants import MovementEvents
from core.terrain_manager import EFFECT_IMPASSABLE_VOID


class MovementSystem:
    """System responsible for handling entity movement within the game world."""

    def __init__(
        self,
        game_state: Any,
        ecs_manager: Optional[ECSManager] = None,
        *,
        event_bus: Any | None = None,
    ) -> None:
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
    def _get_component(self, entity_id: str, component_type: Type[Any]) -> Optional[Any]:
        component_tuple = self.ecs_manager.get_components_for_entity(entity_id, component_type)
        if component_tuple is None or not component_tuple:
            return None
        return component_tuple[0]

    def _can_enter_tile(
        self,
        terrain: Any,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        entity_id: str,
    ) -> bool:
        if not terrain.is_walkable(x, y, width, height):
            return False
        return not terrain.is_occupied(
            x,
            y,
            width,
            height,
            entity_id_to_ignore=entity_id,
        )

    @staticmethod
    def _compute_step_cost(terrain: Any, x: int, y: int) -> int:
        raw_cost_fn = getattr(terrain, "get_movement_cost", None)
        if not callable(raw_cost_fn):
            return 1
        try:
            step_cost_val = raw_cost_fn(x, y)
            step_cost = int(step_cost_val)
        except (TypeError, ValueError):
            # Some legacy terrains still expose non-numeric costs; treat them as neutral tiles
            # rather than crashing the movement system while we migrate providers.
            # NOTE: Remove this fallback once all terrain providers return numeric movement costs.
            return 1
        return step_cost if step_cost > 0 else 1

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
            if not getattr(self.game_state, "_movement_event_registered", False):
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

    # --- Event helpers ----------------------------------------------------------
    def _publish_movement_started(
        self,
        entity_id: str,
        from_position: Tuple[int, int],
        to_position: Tuple[int, int],
        *,
        provoke_opportunity_attacks: bool,
        path_step: Optional[int] = None,
        path_length: Optional[int] = None,
    ) -> None:
        if not self.event_bus:
            return
        self.event_bus.publish(
            MovementEvents.MOVEMENT_STARTED,
            entity_id=entity_id,
            from_position=from_position,
            to_position=to_position,
            provoke_opportunity_attacks=provoke_opportunity_attacks,
            path_step=path_step,
            path_length=path_length,
        )

    def _publish_movement_ended(
        self,
        entity_id: str,
        from_position: Tuple[int, int],
        to_position: Tuple[int, int],
        *,
        provoke_opportunity_attacks: bool,
        succeeded: bool,
        path_step: Optional[int] = None,
        path_length: Optional[int] = None,
    ) -> None:
        if not self.event_bus:
            return
        self.event_bus.publish(
            MovementEvents.MOVEMENT_ENDED,
            entity_id=entity_id,
            from_position=from_position,
            to_position=to_position,
            provoke_opportunity_attacks=provoke_opportunity_attacks,
            succeeded=succeeded,
            path_step=path_step,
            path_length=path_length,
        )

    def _update_facing(
        self,
        entity_id: str,
        origin: Tuple[int, int],
        destination: Tuple[int, int],
    ) -> None:
        if origin == destination:
            return
        internal_id = self.ecs_manager.resolve_entity(entity_id)
        if internal_id is None:
            return
        facing: Optional[FacingComponent] = self.ecs_manager.try_get_component(
            internal_id, FacingComponent
        )
        if facing is None or facing.is_fixed():
            return
        facing.face_towards_position(origin, destination)

        entity = self.game_state.get_entity(entity_id)
        if not entity:
            return
        char_ref = entity.get("character_ref")
        if not char_ref or not hasattr(char_ref, "character"):
            return
        character = char_ref.character
        orientation = facing.get_character_orientation()
        if hasattr(character, "set_orientation"):
            character.set_orientation(orientation)

    # --- Convenience wrappers for AI / other systems ---------------------------------
    def is_walkable(self, x: int, y: int, entity_width: int = 1, entity_height: int = 1) -> bool:
        terrain = getattr(self.game_state, 'terrain', None)
        if not terrain:
            return False
        return terrain.is_walkable(x, y, entity_width, entity_height)

    # ---------------------------------------------------------------------------------

    def get_reachable_tiles(
        self,
        entity_id: str,
        max_distance: int,
        reserved_tiles: Optional[Set[Tuple[int, int]]] = None,
    ) -> List[Tuple[int, int, int]]:
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
        heap: List[Tuple[int, Tuple[int, int]]] = [(0, start_pos)]
        best: Dict[Tuple[int, int], int] = {start_pos: 0}
        reachable: List[Tuple[int, int, int]] = []
        while heap:
            dist, (x, y) = heapq.heappop(heap)
            if dist > max_distance:
                continue
            reachable.append((x, y, dist))
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if (nx, ny) in blocked:
                    continue
                if not self._can_enter_tile(
                    terrain,
                    nx,
                    ny,
                    entity_width,
                    entity_height,
                    entity_id=entity_id,
                ):
                    continue
                step_cost = self._compute_step_cost(terrain, nx, ny)
                nd = dist + step_cost
                if nd > max_distance:
                    continue
                if nd < best.get((nx, ny), 10**9):
                    best[(nx, ny)] = nd
                    heapq.heappush(heap, (nd, (nx, ny)))
        return reachable

    def find_path(
        self,
        entity_id: str,
        dest: Tuple[int, int],
        max_distance: int | None = None,
    ) -> List[Tuple[int, int]]:
        pos_comp = self._get_component(entity_id, PositionComponent)
        if pos_comp is None:
            return []
        start = (pos_comp.x, pos_comp.y)
        if start == dest:
            return [start]
        terrain = getattr(self.game_state, "terrain", None)
        if terrain is None:
            return []
        entity_width = getattr(pos_comp, 'width', 1)
        entity_height = getattr(pos_comp, 'height', 1)
        static_occ = collect_blocked_tiles(
            self.ecs_manager,
            ignore_entities={entity_id},
            terrain=terrain,
        )
        heap: List[Tuple[int, Tuple[int, int]]] = [(0, start)]
        best: Dict[Tuple[int, int], int] = {start: 0}
        parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
        while heap:
            dist, (x, y) = heapq.heappop(heap)
            if (max_distance is not None) and dist > max_distance:
                continue
            if (x, y) == dest:
                path = [(x, y)]
                cur = (x, y)
                while cur != start:
                    cur = parent[cur]
                    path.append(cur)
                path.reverse()
                return path
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if (nx, ny) in static_occ:
                    continue
                if not self._can_enter_tile(
                    terrain,
                    nx,
                    ny,
                    entity_width,
                    entity_height,
                    entity_id=entity_id,
                ):
                    continue
                step_cost = self._compute_step_cost(terrain, nx, ny)
                nd = dist + step_cost
                if (max_distance is not None) and nd > max_distance:
                    continue
                if nd < best.get((nx, ny), 10**9):
                    best[(nx, ny)] = nd
                    parent[(nx, ny)] = (x, y)
                    heapq.heappush(heap, (nd, (nx, ny)))
        return []

    def move(
        self,
        entity_id: str,
        dest: Tuple[int, int],
        max_steps: int | None = None,
        pathfind: bool = False,
        provoke_aoo: bool = True,
    ) -> bool:
        if pathfind:
            return self.path_move(entity_id, dest, max_steps=max_steps, provoke_aoo=provoke_aoo)
        pos_comp = self._get_component(entity_id, PositionComponent)
        if pos_comp is None:
            return False
        if self.game_state and not self.game_state.get_entity(entity_id):
            return False
        width = getattr(pos_comp, 'width', 1)
        height = getattr(pos_comp, 'height', 1)
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
                    void_tile = (vt_res is True)
                except Exception:
                    void_tile = False
        if terrain.is_occupied(dest_x, dest_y, width, height, entity_id_to_ignore=entity_id):
            return False
        fl = getattr(terrain, 'forbid_landing', None)
        if callable(fl):
            try:
                fl_res = fl(dest_x, dest_y)
                if fl_res is True:
                    return False
            except Exception:
                pass
        ivp = getattr(terrain, 'is_valid_position', None)
        if callable(ivp) and not ivp(dest_x, dest_y, width, height):
            return False
        if (cur_x, cur_y) == (dest_x, dest_y):
            if not terrain.is_walkable(dest_x, dest_y, width, height) and not void_tile:
                return False
            return True
        if not terrain.is_walkable(dest_x, dest_y, width, height) and not void_tile:
            return False

        from_position = (cur_x, cur_y)
        to_position = (dest_x, dest_y)
        self._publish_movement_started(
            entity_id,
            from_position,
            to_position,
            provoke_opportunity_attacks=provoke_aoo,
        )

        if hasattr(terrain, 'move_entity'):
            move_result = terrain.move_entity(entity_id, dest_x, dest_y)
            if move_result is not True:
                self._publish_movement_ended(
                    entity_id,
                    from_position,
                    to_position,
                    provoke_opportunity_attacks=provoke_aoo,
                    succeeded=False,
                )
                return False
        pos_comp.x, pos_comp.y = dest_x, dest_y
        self._publish_movement_ended(
            entity_id,
            from_position,
            to_position,
            provoke_opportunity_attacks=provoke_aoo,
            succeeded=True,
        )

        self._update_facing(entity_id, from_position, to_position)
        self._record_movement_usage(entity_id, distance)
        bump_blocker = getattr(self.game_state, 'bump_blocker_version', None)
        if callable(bump_blocker):
            has_char_ref = self._get_component(entity_id, CharacterRefComponent) is not None
            has_cover = self._get_component(entity_id, CoverComponent) is not None
            if has_char_ref or has_cover:
                bump_blocker()
        if void_tile and hasattr(self.game_state, 'kill_entity'):
            self.game_state.kill_entity(entity_id, cause='void')
        return True

    def path_move(
        self,
        entity_id: str,
        dest: Tuple[int, int],
        max_steps: int | None = None,
        provoke_aoo: bool = True,
    ) -> bool:
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
        if hasattr(terrain, 'forbid_landing'):
            fl = getattr(terrain, 'forbid_landing')
            if callable(fl):
                try:
                    if fl(dest[0], dest[1]) is True:
                        return False
                except Exception:
                    pass
        void_tile = False
        if hasattr(terrain, 'has_effect'):
            hf = getattr(terrain, 'has_effect')
            if callable(hf):
                try:
                    vt_res = hf(dest[0], dest[1], EFFECT_IMPASSABLE_VOID)
                    void_tile = (vt_res is True)
                except Exception:
                    void_tile = False
        total_cost = 0
        current = start
        for step_index, (x, y) in enumerate(path[1:], start=1):
            step_cost = self._compute_step_cost(terrain, x, y)
            total_cost += step_cost
            if max_steps is not None and total_cost > max_steps:
                return False
            from_position = current
            to_position = (x, y)
            self._publish_movement_started(
                entity_id,
                from_position,
                to_position,
                provoke_opportunity_attacks=provoke_aoo,
                path_step=step_index,
                path_length=len(path) - 1,
            )
            if hasattr(terrain, 'move_entity'):
                if not terrain.move_entity(entity_id, x, y):
                    self._publish_movement_ended(
                        entity_id,
                        from_position,
                        to_position,
                        provoke_opportunity_attacks=provoke_aoo,
                        succeeded=False,
                        path_step=step_index,
                        path_length=len(path) - 1,
                    )
                    return False
            pos_comp.x, pos_comp.y = x, y
            self._publish_movement_ended(
                entity_id,
                from_position,
                to_position,
                provoke_opportunity_attacks=provoke_aoo,
                succeeded=True,
                path_step=step_index,
                path_length=len(path) - 1,
            )
            self._record_movement_usage(entity_id, step_cost)
            bump_blocker = getattr(self.game_state, 'bump_blocker_version', None)
            if callable(bump_blocker):
                has_char_ref = self._get_component(entity_id, CharacterRefComponent) is not None
                has_cover = self._get_component(entity_id, CoverComponent) is not None
                if has_char_ref or has_cover:
                    bump_blocker()
            current = to_position
            self._update_facing(entity_id, from_position, to_position)
        if void_tile and hasattr(self.game_state, 'kill_entity'):
            self.game_state.kill_entity(entity_id, cause='void')
        return True


__all__ = ["MovementSystem"]
