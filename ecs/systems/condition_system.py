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

from ecs.components.condition_tracker import ConditionTrackerComponent
from ecs.components.character_ref import CharacterRefComponent
from ecs.components.health import HealthComponent
from ecs.components.willpower import WillpowerComponent
from ecs.ecs_manager import ECSManager
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
    def __init__(
        self,
        ecs_manager: ECSManager,
        event_bus: Optional[Any] = None,
        game_state: Optional[Any] = None,
    ):
        self.ecs_manager = ecs_manager
        resolved_game_state = game_state
        if resolved_game_state is None and hasattr(ecs_manager, "game_state"):
            resolved_game_state = getattr(ecs_manager, "game_state")
        self.game_state = resolved_game_state

        resolved_bus = event_bus
        if resolved_bus is None and hasattr(ecs_manager, "event_bus"):
            resolved_bus = getattr(ecs_manager, "event_bus")
        if resolved_bus is None and resolved_game_state is not None:
            resolved_bus = getattr(resolved_game_state, "event_bus", None)
        self.event_bus = resolved_bus

        self._conditions: Dict[str, Dict[str, Condition]] = {}
        self._pool_modifier_registry: Dict[str, Any] = {}
        self._start_turn_handlers: Dict[str, Any] = {}
        self._movement_modifiers: Dict[str, Any] = {}
        self._action_slot_modifiers: Dict[str, Any] = {}
        self._remove_handlers: Dict[str, Any] = {}
        self._damage_out_mods: Dict[str, Dict[str, int]] = {}
        self._damage_in_mods: Dict[str, Dict[str, int]] = {}

        self._register_default_modifiers()
        self._register_default_start_turn_handlers()
        self._register_default_movement_modifiers()
        self._register_default_action_modifiers()
        self._subscribe_events()

    @classmethod
    def from_game_state(cls, game_state: Any) -> "ConditionSystem":
        ecs_manager = getattr(game_state, "ecs_manager", None)
        if ecs_manager is None:
            raise ValueError("game_state must expose an ecs_manager to build ConditionSystem")
        event_bus = getattr(game_state, "event_bus", None)
        if event_bus is None and hasattr(ecs_manager, "event_bus"):
            event_bus = getattr(ecs_manager, "event_bus")
        return cls(ecs_manager, event_bus=event_bus, game_state=game_state)

    @classmethod
    def from_ecs(
        cls,
        ecs_manager: ECSManager,
        event_bus: Optional[Any] = None,
        *,
        game_state: Optional[Any] = None,
    ) -> "ConditionSystem":
        return cls(ecs_manager, event_bus=event_bus, game_state=game_state)

    # ------------------------------------------------------------------
    # Event wiring
    # ------------------------------------------------------------------
    def _subscribe_events(self):
        bus = self.event_bus
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
            char = self._get_character(entity_id)
            if not char:
                return
            char.take_damage(amount, damage_type=damage_type, target=target_pool)
            self._sync_health_components(entity_id, target_pool, char)
            # Publish damage event so other systems react (e.g., weakened re-eval)
            if self.event_bus:
                self.event_bus.publish(
                    'damage_inflicted',
                    attacker_id=None,
                    target_id=entity_id,
                    damage_amount=amount,
                    damage_type=damage_type,
                    weapon_used='Poison',
                )
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

    # Helpers -----------------------------------------------------------------
    def _ensure_tracker(self, entity_id: str, create: bool = False) -> Optional[ConditionTrackerComponent]:
        if not self.ecs_manager:
            return None
        tracker = self.ecs_manager.get_component_for_entity(entity_id, ConditionTrackerComponent)
        if tracker is None and create:
            internal_id = self.ecs_manager.resolve_entity(entity_id)
            if internal_id is None:
                return None
            tracker = ConditionTrackerComponent()
            if entity_id in self._conditions:
                tracker.conditions.update(self._conditions[entity_id])
            self.ecs_manager.add_component(internal_id, tracker)
        if tracker is not None:
            self._conditions[entity_id] = tracker.conditions
        return tracker

    def _get_condition_store(self, entity_id: str, create: bool = False) -> Optional[Dict[str, Condition]]:
        tracker = self._ensure_tracker(entity_id, create=create)
        if tracker is None:
            if entity_id in self._conditions:
                return self._conditions[entity_id]
            if create:
                self._conditions.setdefault(entity_id, {})
                return self._conditions[entity_id]
            return None
        return tracker.conditions

    def _get_condition(self, entity_id: str, name: str) -> Optional[Condition]:
        store = self._get_condition_store(entity_id)
        if not store:
            return None
        return store.get(name)

    def _get_active_states(self, entity_id: str, character: Optional[Any] = None) -> Set[str]:
        states: Set[str] = set()
        tracker = self._ensure_tracker(entity_id)
        if tracker is not None:
            states |= tracker.active_states()
        if character is None:
            character = self._get_character(entity_id)
        if character is not None and hasattr(character, 'states'):
            states |= set(character.states)
        if not states and entity_id in self._conditions:
            states |= set(self._conditions[entity_id].keys())
        return states

    def _get_character(self, entity_id: str) -> Optional[Any]:
        character = None
        if self.ecs_manager:
            cref = self.ecs_manager.get_component_for_entity(entity_id, CharacterRefComponent)
            if cref:
                character = getattr(cref, 'character', None)
        if character is None and self.game_state is not None:
            ent = getattr(self.game_state, 'get_entity', lambda _eid: None)(entity_id)
            if ent:
                cref = ent.get('character_ref')
                if cref is not None:
                    character = getattr(cref, 'character', None)
        return character

    def _sync_health_components(self, entity_id: str, target_pool: str, character: Any) -> None:
        if not self.ecs_manager:
            return
        if target_pool == 'health':
            health_comp = self.ecs_manager.get_component_for_entity(entity_id, HealthComponent)
            if health_comp is not None and character is not None:
                health_comp.superficial_damage = character._health_damage['superficial']
                health_comp.aggravated_damage = character._health_damage['aggravated']
                total = health_comp.superficial_damage + health_comp.aggravated_damage
                health_comp.current_health = max(0, character.max_health - total)
        elif target_pool == 'willpower':
            will_comp = self.ecs_manager.get_component_for_entity(entity_id, WillpowerComponent)
            if will_comp is not None and character is not None:
                will_comp.superficial_damage = character._willpower_damage['superficial']
                will_comp.aggravated_damage = character._willpower_damage['aggravated']
                total = will_comp.superficial_damage + will_comp.aggravated_damage
                will_comp.current_willpower = max(0, character.max_willpower - total)

    def _register_default_modifiers(self):
        """Register built-in dice pool modifiers (Weakened variants + generic pool mods)."""
        def weakened_total(name, char, base_pool, used_traits, active, entity_id=None):
            if used_traits & (PHYSICAL_ATTRIBUTES | MENTAL_ATTRIBUTES | SOCIAL_ATTRIBUTES | WILLPOWER_TRAIT):
                return -2
            return 0
        def weakened_physical(name, char, base_pool, used_traits, active, entity_id=None):
            if WEAKENED_TOTAL in active:
                return 0
            if used_traits & PHYSICAL_ATTRIBUTES:
                return -2
            return 0
        def weakened_mental_social(name, char, base_pool, used_traits, active, entity_id=None):
            if WEAKENED_TOTAL in active:
                return 0
            if used_traits & (MENTAL_ATTRIBUTES | SOCIAL_ATTRIBUTES | WILLPOWER_TRAIT):
                return -2
            return 0
        self._pool_modifier_registry[WEAKENED_TOTAL] = weakened_total
        self._pool_modifier_registry[WEAKENED_PHYSICAL] = weakened_physical
        self._pool_modifier_registry[WEAKENED_MENTAL_SOCIAL] = weakened_mental_social
        # Generic pool modifier patterns: names: PoolMod.Attack / Defense / Physical / Mental / Social
        def generic_pool_mod(name, char, base_pool, used_traits, active, entity_id):
            if entity_id is None:
                raise ValueError(
                    f"generic_pool_mod: entity_id is required for PoolMod.* modifiers (name={name})"
                )
            cond = self._get_condition(entity_id, name)
            delta = cond.data.get('delta', 0) if cond is not None else 0
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
        char = self._get_character(entity_id)
        if not char:
            return
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
            self._sync_health_components(entity_id, 'health', char)
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
        char = self._get_character(entity_id)
        if not char:
            return
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
                self._sync_health_components(entity_id, 'health', char)
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
        char = self._get_character(entity_id)
        if not char:
            return
        store = self._get_condition_store(entity_id, create=True)
        if store is None:
            return
        key_name = name
        existing = store.get(name)
        if existing and name in STACKABLE_NAMES:
            # find next suffix
            idx = 1
            while f"{name}#{idx}" in store:
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
            store[key_name] = cond
            char.states.add(key_name)
            self._apply_side_effects(entity_id, cond)
            self._publish('condition_added', entity_id=entity_id, condition=key_name, rounds=rounds, source=source)
            base = key_name.split('#')[0]
            if base in (INVISIBLE, SEE_INVISIBLE) and hasattr(self.game_state, 'bump_blocker_version'):
                self.game_state.bump_blocker_version()

    def remove_condition(self, entity_id: str, name: str, reason: str = 'removed'):
        base = name.split('#')[0]
        if name in DYNAMIC_WEAKENED:
            char = self._get_character(entity_id)
            if not char:
                return
            if name in char.states:
                char.states.remove(name)
            tracker = self._ensure_tracker(entity_id)
            if tracker:
                tracker.dynamic_states.discard(name)
            self._publish('condition_removed', entity_id=entity_id, condition=name, reason=reason)
            return
        conds = self._get_condition_store(entity_id)
        if not conds or name not in conds:
            return
        handler = self._remove_handlers.get(base)
        if handler:
            try:
                handler(conds[name], entity_id)
            except Exception as e:
                print(f"[ConditionSystem] Remove handler for {name} failed: {e}")
        self._remove_side_effects(entity_id, conds[name])
        del conds[name]
        char = self._get_character(entity_id)
        if char and name in char.states:
            char.states.remove(name)
        self._publish('condition_removed', entity_id=entity_id, condition=name, reason=reason)
        base = name.split('#')[0]
        if base in (INVISIBLE, SEE_INVISIBLE) and hasattr(self.game_state, 'bump_blocker_version'):
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

    def apply_pool_modifiers(
        self,
        character: Any,
        base_pool: int,
        used_traits: Set[str],
        entity_id: Optional[str] = None,
    ) -> int:
        """
        Apply all relevant pool modifiers to a base dice pool.

        Args:
            character: The actor whose pool is being modified.
            base_pool: The starting pool value before modifiers.
            used_traits: Traits contributing to the pool calculation.
            entity_id: The ECS entity identifier for the character. Required for
                generic PoolMod.* conditions so their per-entity deltas can be
                resolved. When provided, active states are sourced from the
                condition tracker; otherwise they are taken from the
                character's ``states`` attribute.

        Returns:
            The modified pool value, floored at zero.
        """
        if base_pool <= 0:
            return 0
        active: Set[str] = set()
        if entity_id is not None:
            active = self._get_active_states(entity_id, character)
        if not active:
            active = set(getattr(character, 'states', set()))
        if not active:
            return base_pool
        total_delta = 0
        for state in active:
            base_state = state.split('#')[0]
            func = self._pool_modifier_registry.get(state) or self._pool_modifier_registry.get(
                base_state
            )
            if func:
                try:
                    delta = func(
                        state,
                        character,
                        base_pool + total_delta,
                        used_traits,
                        active,
                        entity_id=entity_id,
                    )
                except TypeError:
                    delta = func(
                        state,
                        character,
                        base_pool + total_delta,
                        used_traits,
                        active,
                    )
                except Exception as e:
                    print(f"[ConditionSystem] pool modifier {state} failed: {e}")
                    delta = 0
                total_delta += delta
        new_pool = base_pool + total_delta
        if new_pool < 0:
            new_pool = 0
        return new_pool

    def apply_movement_constraints(self, entity_id: str, allowance: int, movement_type: str) -> int:
        conds = self._get_condition_store(entity_id)
        if not conds:
            return allowance
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
        conds = self._get_condition_store(entity_id)
        if not conds:
            return counters
        for name, cond in list(conds.items()):
            handler = self._action_slot_modifiers.get(name.split('#')[0])
            if handler:
                try:
                    counters = handler(cond, counters)
                except Exception as e:
                    print(f"[ConditionSystem] action slot modifier {name} failed: {e}")
        return counters

    def list_conditions(self, entity_id: str) -> list:
        conds = self._get_condition_store(entity_id)
        if not conds:
            return []
        return list(conds.keys())

    def recheck_damage_based(self, entity_id: str):
        char = self._get_character(entity_id)
        if not char:
            return
        added, removed = evaluate_weakened_damage_based(char)
        tracker = self._ensure_tracker(entity_id, create=bool(added or removed))
        if tracker:
            for a in added:
                tracker.dynamic_states.add(a)
            for r in removed:
                tracker.dynamic_states.discard(r)
        if char:
            for a in added:
                char.states.add(a)
            for r in removed:
                char.states.discard(r)
        for a in added:
            self._publish('condition_added', entity_id=entity_id, condition=a, rounds=None, source='dynamic')
        for r in removed:
            self._publish('condition_removed', entity_id=entity_id, condition=r, reason='threshold')

    def _publish(self, evt: str, **payload):
        if self.event_bus:
            self.event_bus.publish(evt, **payload)

    def _on_round_started(self, **evt):
        expired = []
        processed: Set[str] = set()
        if self.ecs_manager:
            for entity_id, tracker in self.ecs_manager.iter_with_id(ConditionTrackerComponent):
                processed.add(entity_id)
                for name, cond in list(tracker.conditions.items()):
                    if cond.tick():
                        expired.append((entity_id, name))
        for entity_id, conds in list(self._conditions.items()):
            if entity_id in processed:
                continue
            for name, cond in list(conds.items()):
                if cond.tick():
                    expired.append((entity_id, name))
        for entity_id, name in expired:
            self.remove_condition(entity_id, name, reason='expired')
            self._publish('condition_expired', entity_id=entity_id, condition=name)
        if self.ecs_manager:
            for entity_id, _ in self.ecs_manager.iter_with_id(CharacterRefComponent):
                self.recheck_damage_based(entity_id)

    def _on_damage_inflicted(self, target_id: str, **evt):
        self.recheck_damage_based(target_id)

    def _on_turn_started(self, entity_id: str, **evt):
        conds = self._get_condition_store(entity_id)
        if not conds:
            self.recheck_damage_based(entity_id)
            return
        for name, cond in list(conds.items()):
            handler = self._start_turn_handlers.get(name.split('#')[0])
            if handler:
                handler(cond, entity_id)
        self.recheck_damage_based(entity_id)
