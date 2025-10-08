"""Opportunity attack handling driven by movement events."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Set, Tuple

from ecs.actions.attack_actions import AttackAction
from ecs.components.body_footprint import BodyFootprintComponent
from ecs.components.character_ref import CharacterRefComponent
from ecs.components.equipment import EquipmentComponent
from ecs.components.position import PositionComponent
from ecs.ecs_manager import ECSManager
from interface.event_constants import CombatEvents, MovementEvents

GridCoord = Tuple[int, int]


class OpportunityAttackSystem:
    """Listen to movement events and trigger melee reactions when adjacency breaks."""

    def __init__(self, game_state: Any, event_bus: Any):
        self.game_state = game_state
        self.event_bus = event_bus
        manager = getattr(game_state, "ecs_manager", None)
        if manager is None:
            raise ValueError(
                "OpportunityAttackSystem requires a GameState with an attached ECS manager."
            )
        self.ecs_manager: ECSManager = manager
        if event_bus:
            event_bus.subscribe(MovementEvents.MOVEMENT_STARTED, self._on_movement_started)
            event_bus.subscribe(MovementEvents.MOVEMENT_ENDED, self._on_movement_ended)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_movement_started(
        self,
        entity_id: str,
        from_position: Tuple[int, int],
        to_position: Tuple[int, int],
        *,
        provoke_opportunity_attacks: bool = True,
        **metadata: Any,
    ) -> None:
        if not provoke_opportunity_attacks:
            return
        attackers = self._collect_adjacent_sources(entity_id)
        if not attackers:
            return
        future_tiles = self._get_tiles(entity_id, anchor=to_position)
        if not future_tiles:
            return
        meta: Dict[str, Any] = {
            "from_position": tuple(from_position),
            "to_position": tuple(to_position),
            "path_step": metadata.get("path_step"),
            "path_length": metadata.get("path_length"),
        }
        for attacker_id, (equipment, position) in attackers.items():
            attacker_tiles = self._get_tiles(attacker_id, position_component=position)
            if not attacker_tiles or self._tiles_adjacent(attacker_tiles, future_tiles):
                continue
            self._trigger_reaction(attacker_id, entity_id, equipment, meta)

    def _on_movement_ended(self, **_: Any) -> None:
        """Hook maintained for future use; currently no post-move processing needed."""

    # ------------------------------------------------------------------
    # Core logic helpers
    # ------------------------------------------------------------------
    def _collect_adjacent_sources(
        self,
        mover_id: str,
    ) -> Dict[str, Tuple[EquipmentComponent, PositionComponent]]:
        manager = self.ecs_manager
        if manager is None:
            return {}
        mover_tiles = self._get_tiles(mover_id)
        if not mover_tiles:
            return {}
        mover_team = self._get_team_id(mover_id)
        adjacent: Dict[str, Tuple[EquipmentComponent, PositionComponent]] = {}
        for attacker_id, position, char_ref, equipment in manager.iter_with_id(
            PositionComponent,
            CharacterRefComponent,
            EquipmentComponent,
        ):
            if attacker_id == mover_id:
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
            attacker_tiles = self._get_tiles(attacker_id, position_component=position)
            if not attacker_tiles:
                continue
            if self._tiles_adjacent(attacker_tiles, mover_tiles):
                adjacent[attacker_id] = (equipment, position)
        return adjacent

    def _trigger_reaction(
        self,
        attacker_id: str,
        target_id: str,
        equipment: EquipmentComponent,
        meta: Dict[str, Any],
    ) -> None:
        attacker_entity = self.game_state.get_entity(attacker_id)
        target_entity = self.game_state.get_entity(target_id)
        if not attacker_entity or not target_entity:
            return
        attacker_char_ref = attacker_entity.get("character_ref")
        target_char_ref = target_entity.get("character_ref")
        if not attacker_char_ref or not target_char_ref:
            return
        attacker_character = getattr(attacker_char_ref, "character", None)
        target_character = getattr(target_char_ref, "character", None)
        if attacker_character is None or target_character is None:
            return
        if getattr(attacker_character, "is_dead", False) or getattr(target_character, "is_dead", False):
            return
        weapon = self._select_melee_weapon(equipment)
        payload: Dict[str, Any] = {
            "attacker_id": attacker_id,
            "target_id": target_id,
            "origin_adjacent": True,
        }
        for key, value in meta.items():
            if value is not None:
                payload[key] = value
        self._publish_trigger_event(payload)
        attack_executor = AttackAction(
            attacker_id=attacker_id,
            target_id=target_id,
            weapon=weapon,
            game_state=self.game_state,
            is_opportunity=True,
        )
        damage = attack_executor.execute()
        if self.event_bus:
            reaction_payload = dict(payload)
            reaction_payload.update({"damage": damage, "is_opportunity": True})
            self.event_bus.publish(
                CombatEvents.OPPORTUNITY_ATTACK_REACTION,
                **reaction_payload,
            )

    # ------------------------------------------------------------------
    # Component helpers
    # ------------------------------------------------------------------
    def _get_tiles(
        self,
        entity_id: str,
        *,
        position_component: Optional[PositionComponent] = None,
        anchor: Optional[Tuple[int, int]] = None,
    ) -> Set[GridCoord]:
        manager = self.ecs_manager
        if manager is None:
            return set()
        internal_id = manager.resolve_entity(entity_id)
        if internal_id is None:
            return set()
        position = position_component or manager.get_component_for_entity(entity_id, PositionComponent)
        if position is None:
            return set()
        footprint: Optional[BodyFootprintComponent] = manager.try_get_component(
            internal_id, BodyFootprintComponent
        )
        anchor_x: int
        anchor_y: int
        if anchor is not None:
            anchor_x, anchor_y = int(anchor[0]), int(anchor[1])
        else:
            anchor_x, anchor_y = int(position.x), int(position.y)
        if footprint and footprint.cells:
            return {
                (anchor_x + int(dx), anchor_y + int(dy))
                for dx, dy in footprint.iter_offsets()
            }
        width = int(getattr(position, "width", 1))
        height = int(getattr(position, "height", 1))
        return {
            (anchor_x + dx, anchor_y + dy)
            for dx in range(width)
            for dy in range(height)
        }

    def _get_team_id(self, entity_id: str) -> Optional[Any]:
        manager = self.ecs_manager
        if manager is None:
            return None
        internal_id = manager.resolve_entity(entity_id)
        if internal_id is None:
            return None
        char_ref = manager.try_get_component(internal_id, CharacterRefComponent)
        if not char_ref:
            return None
        character = getattr(char_ref, "character", None)
        if not character:
            return None
        return getattr(character, "team", None)

    @staticmethod
    def _tiles_adjacent(a: Iterable[GridCoord], b: Iterable[GridCoord]) -> bool:
        for ax, ay in a:
            for bx, by in b:
                if abs(ax - bx) + abs(ay - by) == 1:
                    return True
        return False

    @staticmethod
    def _is_melee_capable(equipment: EquipmentComponent) -> bool:
        weapons = getattr(equipment, "weapons", {})
        for weapon in weapons.values():
            weapon_type = getattr(weapon, "weapon_type", None)
            base_type = getattr(weapon_type, "value", weapon_type)
            if base_type in ("melee", "brawl"):
                return True
        return False

    @staticmethod
    def _select_melee_weapon(equipment: EquipmentComponent):
        weapons = getattr(equipment, "weapons", {})
        for weapon in weapons.values():
            weapon_type = getattr(weapon, "weapon_type", None)
            base_type = getattr(weapon_type, "value", weapon_type)
            if base_type in ("melee", "brawl"):
                return weapon
        return None

    def _publish_trigger_event(self, payload: Dict[str, Any]) -> None:
        if not self.event_bus:
            return
        self.event_bus.publish(CombatEvents.AOO_TRIGGERED, **payload)


__all__ = ["OpportunityAttackSystem"]
