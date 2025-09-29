# ecs/systems/condition_system.py
"""Generic condition (status effect) system.

Features:
- Generic Condition class (name, remaining rounds, source, data, dynamic flag)
- Timed or indefinite conditions (remaining_rounds None => indefinite)
- Dynamic conditions (e.g., damage-threshold Weakened variants) are recalculated, not decremented
- EventBus integration: publishes condition_added, condition_removed, condition_expired
- Subscribes to round_started for ticking durations
- Helper to re-evaluate damage-based weakened states on demand

Note:
Dynamic weakened variants (Weakened.Physical / Weakened.MentalSocial) are not tracked as timed
conditions internally; they live solely in Character.states and are re-evaluated via
recheck_damage_based(). The Total variant can be added as timed/permanent.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Set
from utils.condition_utils import (
    WEAKENED_PHYSICAL,
    WEAKENED_MENTAL_SOCIAL,
    WEAKENED_TOTAL,
    PHYSICAL_ATTRIBUTES,
    MENTAL_ATTRIBUTES,
    SOCIAL_ATTRIBUTES,
    WILLPOWER_TRAIT,
    evaluate_weakened_damage_based,
    POISONED,
    SLOWED,
    IMMOBILIZED,
    HANDICAP,
    INVISIBLE,
    SEE_INVISIBLE,
)

DYNAMIC_WEAKENED = {WEAKENED_PHYSICAL, WEAKENED_MENTAL_SOCIAL}
STACKABLE_NAMES = {'InitiativeMod','MaxHealthMod','DamageOutMod','DamageInMod'}

@dataclass
class Condition:
    name: str
    remaining_rounds: Optional[int] = None  # None => indefinite
    source: Optional[str] = None            # entity_id or system origin
    data: Dict[str, Any] = field(default_factory=dict)
    dynamic: bool = False                   # True = recalculated externally (no ticking)

    def tick(self) -> bool:
        """Advance one round.
        Returns True if condition expired and should be removed.
        """
        if self.dynamic:
            return False
        if self.remaining_rounds is None:
            return False
        if self.remaining_rounds > 0:
            self.remaining_rounds -= 1
        return self.remaining_rounds == 0

class ConditionSystem:
    def __init__(self, game_state: Any):
        self.game_state = game_state
        self._conditions: Dict[str, Dict[str, Condition]] = {}
        self._pool_modifier_registry: Dict[str, Any] = {}
        self._start_turn_handlers: Dict[str, Any] = {}
        self._movement_modifiers: Dict[str, Any] = {}
        self._action_slot_modifiers: Dict[str, Any] = {}
        self._remove_handlers: Dict[str, Any] = {}  # handlers invoked on removal/expiry
        # New modifier stores
        self._damage_out_mods: Dict[str, Dict[str, int]] = {}  # entity_id -> key -> delta
        self._damage_in_mods: Dict[str, Dict[str, int]] = {}
        self._register_default_modifiers()
        self._register_default_start_turn_handlers()
        self._register_default_movement_modifiers()
        self._register_default_action_modifiers()
        self._subscribe_events()

    # ------------------------------------------------------------------
    # Event wiring
    # ------------------------------------------------------------------
    def _subscribe_events(self):
        bus = getattr(self.game_state, 'event_bus', None)
        if not bus:
            return
        bus.subscribe('round_started', self._on_round_started)
        bus.subscribe('damage_inflicted', self._on_damage_inflicted)
        bus.subscribe('turn_started', self._on_turn_started)

    # Registration helpers --------------------------------------------------
    def register_start_turn_handler(self, condition_name: str, func: Any):
        self._start_turn_handlers[condition_name] = func
    def register_movement_modifier(self, condition_name: str, func: Any):
        self._movement_modifiers[condition_name] = func
    def register_action_slot_modifier(self, condition_name: str, func: Any):
        self._action_slot_modifiers[condition_name] = func
    def register_remove_handler(self, condition_name: str, func: Any):
        self._remove_handlers[condition_name] = func

    def _register_default_start_turn_handlers(self):
        def poison_tick(condition: Condition, entity_id: str):
            data = condition.data
            amount = data.get('damage_per_tick', 0)
            if amount <= 0:
                return
            damage_type = data.get('damage_type', 'superficial')
            target_pool = data.get('target_pool', 'health')  # 'health' or 'willpower'
            ent = self.game_state.get_entity(entity_id)
            if not ent or 'character_ref' not in ent:
                return
            char = ent['character_ref'].character
            char.take_damage(amount, damage_type=damage_type, target=target_pool)
            # Publish damage event so other systems react (e.g., weakened re-eval)
            bus = getattr(self.game_state, 'event_bus', None)
            if bus:
                bus.publish('damage_inflicted', attacker_id=None, target_id=entity_id,
                            damage_amount=amount, damage_type=damage_type, weapon_used='Poison')
        self._start_turn_handlers[POISONED] = poison_tick

    def _register_default_movement_modifiers(self):
        def slowed_modifier(condition: Condition, allowance: int, movement_type: str):
            percent = condition.data.get('percent', 0)
            if percent <= 0:
                return allowance
            new_allowance = int(allowance * max(0, 1 - percent / 100.0))
            return max(0, new_allowance)
        self._movement_modifiers[SLOWED] = slowed_modifier
        def immobilized_modifier(condition: Condition, allowance: int, movement_type: str):
            return 0
        self._movement_modifiers[IMMOBILIZED] = immobilized_modifier

    def _register_default_action_modifiers(self):
        def handicap_modifier(condition: Condition, counters: Dict[Any, float]):
            if condition.data.get('disable_primary'):
                counters_key = getattr(self.game_state, 'action_system_primary_key', None)
            # direct manipulation
            from ecs.systems.action_system import ActionType
            if condition.data.get('disable_primary'):
                counters[ActionType.PRIMARY] = 0
            if condition.data.get('disable_secondary'):
                counters[ActionType.SECONDARY] = 0
            return counters
        self._action_slot_modifiers[HANDICAP] = handicap_modifier
        def immobilized_actions(condition: Condition, counters: Dict[Any, float]):
            # Could disable certain move-tagged actions indirectly; leave counters intact
            return counters
        self._action_slot_modifiers[IMMOBILIZED] = immobilized_actions

    def _register_default_modifiers(self):
        """Register built-in dice pool modifiers (Weakened variants + generic pool mods)."""
        def weakened_total(name, char, base_pool, used_traits, active):
            if used_traits & (PHYSICAL_ATTRIBUTES | MENTAL_ATTRIBUTES | SOCIAL_ATTRIBUTES | WILLPOWER_TRAIT):
                return -2
            return 0
        def weakened_physical(name, char, base_pool, used_traits, active):
            if WEAKENED_TOTAL in active:
                return 0
            if used_traits & PHYSICAL_ATTRIBUTES:
                return -2
            return 0
        def weakened_mental_social(name, char, base_pool, used_traits, active):
            if WEAKENED_TOTAL in active:
                return 0
            if used_traits & (MENTAL_ATTRIBUTES | SOCIAL_ATTRIBUTES | WILLPOWER_TRAIT):
                return -2
            return 0
        self._pool_modifier_registry[WEAKENED_TOTAL] = weakened_total
        self._pool_modifier_registry[WEAKENED_PHYSICAL] = weakened_physical
        self._pool_modifier_registry[WEAKENED_MENTAL_SOCIAL] = weakened_mental_social
        # Generic pool modifier patterns: names: PoolMod.Attack / Defense / Physical / Mental / Social
        def generic_pool_mod(name, char, base_pool, used_traits, active):
            # Lookup stored condition to fetch its delta
            # Condition names are unique per entity
            for eid, conds in self._conditions.items():
                if name in conds:
                    delta = conds[name].data.get('delta', 0)
                    break
            else:
                delta = 0
            if name.endswith('Attack') and 'CONTEXT_ATTACK' in used_traits:
                return delta
            if name.endswith('Defense') and 'CONTEXT_DEFENSE' in used_traits:
                return delta
            if name.endswith('Physical') and (used_traits & PHYSICAL_ATTRIBUTES):
                return delta
            if name.endswith('Mental') and (used_traits & MENTAL_ATTRIBUTES):
                return delta
            if name.endswith('Social') and (used_traits & SOCIAL_ATTRIBUTES):
                return delta
            return 0
        for suffix in ('Attack','Defense','Physical','Mental','Social'):
            self._pool_modifier_registry[f'PoolMod.{suffix}'] = generic_pool_mod

    # Side-effect application -------------------------------------------------
    def _apply_side_effects(self, entity_id: str, condition: Condition):
        name = condition.name
        base = name.split('#')[0]
        ent = self.game_state.get_entity(entity_id)
        if not ent or 'character_ref' not in ent:
            return
        char = ent['character_ref'].character
        if base == 'InitiativeMod':
            delta = condition.data.get('delta', 0)
            current = getattr(char, 'initiative_mod', 0)
            setattr(char, 'initiative_mod', current + delta)
        elif base == 'MaxHealthMod':
            delta = int(condition.data.get('delta', 0))
            if delta == 0:
                return
            char._max_health_mod_total += delta
            if delta < 0:
                need_remove = -delta
                removed_super = min(need_remove, char._health_damage['superficial'])
                char._health_damage['superficial'] -= removed_super
                need_remove -= removed_super
                removed_aggr = 0
                if need_remove > 0:
                    removed_aggr = min(need_remove, char._health_damage['aggravated'])
                    char._health_damage['aggravated'] -= removed_aggr
                condition.data['removed_superficial'] = removed_super
                condition.data['removed_aggravated'] = removed_aggr
        elif base == 'DamageOutMod':
            key = condition.data.get('category') or condition.data.get('severity') or 'all'
            delta = int(condition.data.get('delta', 0))
            self._damage_out_mods.setdefault(entity_id, {})
            self._damage_out_mods[entity_id][key] = self._damage_out_mods[entity_id].get(key, 0) + delta
        elif base == 'DamageInMod':
            key = condition.data.get('category') or condition.data.get('severity') or 'all'
            delta = int(condition.data.get('delta', 0))
            self._damage_in_mods.setdefault(entity_id, {})
            self._damage_in_mods[entity_id][key] = self._damage_in_mods[entity_id].get(key, 0) + delta

    def _remove_side_effects(self, entity_id: str, condition: Condition):
        name = condition.name
        base = name.split('#')[0]
        ent = self.game_state.get_entity(entity_id)
        if not ent or 'character_ref' not in ent:
            return
        char = ent['character_ref'].character
        if base == 'InitiativeMod':
            delta = condition.data.get('delta', 0)
            current = getattr(char, 'initiative_mod', 0)
            setattr(char, 'initiative_mod', current - delta)
        elif base == 'MaxHealthMod':
            delta = int(condition.data.get('delta', 0))
            if delta != 0:
                char._max_health_mod_total -= delta
                if delta < 0:
                    rs = condition.data.get('removed_superficial', 0)
                    ra = condition.data.get('removed_aggravated', 0)
                    char._health_damage['superficial'] += rs
                    char._health_damage['aggravated'] += ra
        elif base == 'DamageOutMod':
            key = condition.data.get('category') or condition.data.get('severity') or 'all'
            delta = int(condition.data.get('delta', 0))
            if entity_id in self._damage_out_mods and key in self._damage_out_mods[entity_id]:
                self._damage_out_mods[entity_id][key] -= delta
        elif base == 'DamageInMod':
            key = condition.data.get('category') or condition.data.get('severity') or 'all'
            delta = int(condition.data.get('delta', 0))
            if entity_id in self._damage_in_mods and key in self._damage_in_mods[entity_id]:
                self._damage_in_mods[entity_id][key] -= delta

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def add_condition(self, entity_id: str, name: str, rounds: Optional[int] = None, source: Optional[str] = None, data: Optional[Dict[str, Any]] = None):
        """Add a condition to an entity. If already present and timed, refresh duration.
        Dynamic weakened variants are ignored here (handled via damage recheck).
        For stackable names, multiple independent instances are created with suffixed keys (Name#n).
        """
        if name in DYNAMIC_WEAKENED:
            return  # dynamic ones handled by recheck
        ent = self.game_state.get_entity(entity_id)
        if not ent or 'character_ref' not in ent:
            return
        char = ent['character_ref'].character
        self._conditions.setdefault(entity_id, {})
        key_name = name
        existing = self._conditions[entity_id].get(name)
        if existing and name in STACKABLE_NAMES:
            # find next suffix
            idx = 1
            while f"{name}#{idx}" in self._conditions[entity_id]:
                idx += 1
            key_name = f"{name}#{idx}"
            existing = None  # force new condition
        if existing:
            if rounds is not None:
                existing.remaining_rounds = rounds
        else:
            cond = Condition(
                name=key_name,
                remaining_rounds=rounds,
                source=source,
                data=data or {},
                dynamic=False
            )
            self._conditions[entity_id][key_name] = cond
            char.states.add(key_name)
            self._apply_side_effects(entity_id, cond)
            self._publish('condition_added', entity_id=entity_id, condition=key_name, rounds=rounds, source=source)
            base = key_name.split('#')[0]
            if base in (INVISIBLE, SEE_INVISIBLE) and hasattr(self.game_state,'bump_blocker_version'):
                self.game_state.bump_blocker_version()

    def remove_condition(self, entity_id: str, name: str, reason: str = 'removed'):
        base = name.split('#')[0]
        if name in DYNAMIC_WEAKENED:
            ent = self.game_state.get_entity(entity_id)
            if not ent or 'character_ref' not in ent:
                return
            char = ent['character_ref'].character
            if name in char.states:
                char.states.remove(name)
                self._publish('condition_removed', entity_id=entity_id, condition=name, reason=reason)
            return
        conds = self._conditions.get(entity_id)
        if not conds or name not in conds:
            return
        handler = self._remove_handlers.get(base)
        if handler:
            try:
                handler(conds[name], entity_id)
            except Exception as e:
                print(f"[ConditionSystem] Remove handler for {name} failed: {e}")
        self._remove_side_effects(entity_id, conds[name])
        cond_obj = conds[name]
        del conds[name]
        ent = self.game_state.get_entity(entity_id)
        if ent and 'character_ref' in ent:
            char = ent['character_ref'].character
            if name in char.states:
                char.states.remove(name)
        self._publish('condition_removed', entity_id=entity_id, condition=name, reason=reason)
        base = name.split('#')[0]
        if base in (INVISIBLE, SEE_INVISIBLE) and hasattr(self.game_state,'bump_blocker_version'):
            self.game_state.bump_blocker_version()

    # Reintroduce earlier methods lost during edit
    def adjust_damage(self, attacker_id: str, target_id: str, amount: int, severity: str, category: str) -> int:
        if amount <= 0:
            return amount
        if attacker_id in self._damage_out_mods:
            mods = self._damage_out_mods[attacker_id]
            amount += mods.get(category, 0) + mods.get(severity, 0) + mods.get('all', 0)
        if target_id in self._damage_in_mods:
            mods = self._damage_in_mods[target_id]
            amount += mods.get(category, 0) + mods.get(severity, 0) + mods.get('all', 0)
        if amount < 0:
            amount = 0
        return amount

    def apply_pool_modifiers(self, character: Any, base_pool: int, used_traits: Set[str]) -> int:
        if base_pool <= 0:
            return 0
        active = getattr(character, 'states', set())
        if not active:
            return base_pool
        total_delta = 0
        for state in active:
            func = self._pool_modifier_registry.get(state)
            if func:
                try:
                    delta = func(state, character, base_pool + total_delta, used_traits, active)
                except Exception as e:
                    print(f"[ConditionSystem] pool modifier {state} failed: {e}")
                    delta = 0
                total_delta += delta
        new_pool = base_pool + total_delta
        if new_pool < 0:
            new_pool = 0
        return new_pool

    def apply_movement_constraints(self, entity_id: str, allowance: int, movement_type: str) -> int:
        conds = self._conditions.get(entity_id, {})
        result = allowance
        for name, cond in conds.items():
            mod = self._movement_modifiers.get(name.split('#')[0])
            if mod:
                try:
                    result = mod(cond, result, movement_type)
                except Exception as e:
                    print(f"[ConditionSystem] movement modifier {name} failed: {e}")
        return max(0, result)

    def apply_action_slot_modifiers(self, entity_id: str, counters: Dict[Any, float]) -> Dict[Any, float]:
        conds = self._conditions.get(entity_id, {})
        for name, cond in list(conds.items()):
            handler = self._action_slot_modifiers.get(name.split('#')[0])
            if handler:
                try:
                    counters = handler(cond, counters)
                except Exception as e:
                    print(f"[ConditionSystem] action slot modifier {name} failed: {e}")
        return counters

    def list_conditions(self, entity_id: str) -> list:
        return list(self._conditions.get(entity_id, {}).keys())

    def recheck_damage_based(self, entity_id: str):
        ent = self.game_state.get_entity(entity_id)
        if not ent or 'character_ref' not in ent:
            return
        char = ent['character_ref'].character
        added, removed = evaluate_weakened_damage_based(char)
        for a in added:
            self._publish('condition_added', entity_id=entity_id, condition=a, rounds=None, source='dynamic')
        for r in removed:
            self._publish('condition_removed', entity_id=entity_id, condition=r, reason='threshold')

    def _publish(self, evt: str, **payload):
        bus = getattr(self.game_state, 'event_bus', None)
        if bus:
            bus.publish(evt, **payload)

    def _on_round_started(self, **evt):
        expired = []
        for entity_id, conds in list(self._conditions.items()):
            for name, cond in list(conds.items()):
                if cond.tick():
                    expired.append((entity_id, name))
        for entity_id, name in expired:
            self.remove_condition(entity_id, name, reason='expired')
            self._publish('condition_expired', entity_id=entity_id, condition=name)
        # Recheck damage-based conditions for all entities with character_ref
        from ecs.components.character_ref import CharacterRefComponent
        
        if self.game_state.ecs_manager:
            try:
                entities_with_char_ref = self.game_state.ecs_manager.get_components(CharacterRefComponent)
                for eid, (char_ref,) in entities_with_char_ref:
                    self.recheck_damage_based(eid)
            except AttributeError:
                # Fallback if get_components doesn't exist
                for entity_id in self.game_state.ecs_manager.get_all_entities():
                    try:
                        char_ref = self.game_state.ecs_manager.get_component(entity_id, CharacterRefComponent)
                        if char_ref:
                            self.recheck_damage_based(entity_id)
                    except:
                        continue

    def _on_damage_inflicted(self, target_id: str, **evt):
        self.recheck_damage_based(target_id)

    def _on_turn_started(self, entity_id: str, **evt):
        for name, cond in list(self._conditions.get(entity_id, {}).items()):
            handler = self._start_turn_handlers.get(name.split('#')[0])
            if handler:
                handler(cond, entity_id)
        self.recheck_damage_based(entity_id)
