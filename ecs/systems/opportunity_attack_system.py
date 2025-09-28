from typing import Any, Optional
from MV_combat_system.ecs.actions.attack_actions import AttackAction

class OpportunityAttackSystem:
    """System that listens for 'opportunity_attack_triggered' events and resolves
    the corresponding melee reaction attack automatically without consuming the
    standard action economy (bypasses ActionSystem counters).

    Flow:
      1. event_bus publishes 'opportunity_attack_triggered' (attacker_id, target_id)
      2. This system validates melee weapon + adjacency + alive states
      3. Executes AttackAction directly (reaction)
      4. Publishes 'opportunity_attack_reaction' summarizing outcome
    """
    def __init__(self, game_state: Any, event_bus: Any):
        self.game_state = game_state
        self.event_bus = event_bus
        if event_bus:
            event_bus.subscribe('opportunity_attack_triggered', self.handle_opportunity_attack)

    # --- Internal helpers ---------------------------------------------------------
    def _select_melee_weapon(self, attacker_entity: dict):
        equip = attacker_entity.get('equipment') if attacker_entity else None
        if not equip or not hasattr(equip, 'weapons'):
            return None
        for w in getattr(equip, 'weapons', {}).values():
            wtype = getattr(w, 'weapon_type', None)
            base_type = getattr(wtype, 'value', wtype)
            if base_type in ('melee','brawl'):
                return w
        return None

    def _is_adjacent(self, attacker_pos, target_pos) -> bool:
        return abs(attacker_pos.x - target_pos.x) + abs(attacker_pos.y - target_pos.y) == 1
    # -----------------------------------------------------------------------------

    def handle_opportunity_attack(self, attacker_id: str, target_id: str, **event_meta):
        # Accept arbitrary metadata like origin_adjacent without breaking.
        attacker_ent = self.game_state.get_entity(attacker_id)
        target_ent = self.game_state.get_entity(target_id)
        if not attacker_ent or not target_ent:
            return
        if 'character_ref' not in attacker_ent or 'character_ref' not in target_ent:
            return
        attacker_char = attacker_ent['character_ref'].character
        target_char = target_ent['character_ref'].character
        if attacker_char.is_dead or target_char.is_dead:
            return
        att_pos = attacker_ent.get('position'); tgt_pos = target_ent.get('position')
        if not att_pos or not tgt_pos:
            return
        # Require current adjacency (reaction before movement resolution)
        if abs(att_pos.x - tgt_pos.x) + abs(att_pos.y - tgt_pos.y) != 1:
            return
        weapon = self._select_melee_weapon(attacker_ent)
        if not weapon:
            return
        attack_executor = AttackAction(attacker_id=attacker_id, target_id=target_id, weapon=weapon, game_state=self.game_state, is_opportunity=True)
        damage = attack_executor.execute()
        if self.event_bus:
            event_meta['is_opportunity'] = True
            self.event_bus.publish('opportunity_attack_reaction', attacker_id=attacker_id, target_id=target_id, damage=damage, **event_meta)
