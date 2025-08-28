from ecs.systems.action_system import Action, ActionType
from typing import Any
import random

MAX_HUNGER = 5
BLOOD_PULSATION_CONDITION_PREFIX = "BloodPulsationTemp"


def perform_hunger_test(character, game_state=None, entity_id: str = None) -> int:
    """Roll 1d10; on 1-5 increase hunger by 1 (capped). Return roll result.
    Publishes hunger_changed if value actually changes and event bus present.
    """
    old = character.hunger
    roll = random.randint(1, 10)
    if roll <= 5 and character.hunger < MAX_HUNGER:
        character.hunger = min(MAX_HUNGER, character.hunger + 1)
    if game_state and entity_id and character.hunger != old:
        bus = getattr(game_state, 'event_bus', None)
        if bus:
            bus.publish('hunger_changed', entity_id=entity_id, old=old, new=character.hunger, roll=roll)
    return roll


def _get_physical_attribute_ref(character, attr_name: str):
    return character.traits.setdefault('Attributes', {}).setdefault('Physical', {}).setdefault(attr_name, 0)


class BloodPulsationAction(Action):
    """Free Discipline: Increase a physical attribute by 1.
    Up to 6 it's permanent for battle; above 6 each extra point lasts 3 rounds.

    Implementation detail: Each increment above 6 creates a unique condition so
    that expirations stagger correctly and revert only one point each.
    """
    def __init__(self, name: str = "Blood Pulsation"):
        super().__init__(
            name=name,
            action_type=ActionType.FREE,
            execute_func=self._execute,
            description="Increase a physical attribute by 1 (Discipline).",
            keywords=["discipline", "buff"],
        )

    def _execute(self, entity_id: str, game_state: Any, attribute: str = 'Strength') -> bool:
        ent = game_state.get_entity(entity_id)
        if not ent or 'character_ref' not in ent:
            return False
        char = ent['character_ref'].character
        roll = perform_hunger_test(char, game_state, entity_id)
        phys = char.traits.setdefault('Attributes', {}).setdefault('Physical', {})
        if attribute not in phys:
            return False
        phys[attribute] = phys[attribute] + 1
        added_temp_condition = None
        if phys[attribute] > 6:
            cond_sys = getattr(game_state, 'condition_system', None)
            if cond_sys:
                unique_name = f"{BLOOD_PULSATION_CONDITION_PREFIX}_{attribute}_{phys[attribute]}"
                def make_revert():
                    def revert(condition, eid):
                        e = game_state.get_entity(eid)
                        if not e or 'character_ref' not in e:
                            return
                        c = e['character_ref'].character
                        phys_local = c.traits.get('Attributes', {}).get('Physical', {})
                        attr = condition.data.get('attribute')
                        if attr in phys_local and phys_local[attr] > 6:
                            phys_local[attr] -= 1
                    return revert
                cond_sys.register_remove_handler(unique_name, make_revert())
                cond_sys.add_condition(entity_id, unique_name, rounds=3, data={'attribute': attribute})
                added_temp_condition = unique_name
        bus = getattr(game_state, 'event_bus', None)
        if bus:
            bus.publish('discipline_used', entity_id=entity_id, discipline=self.name, success=True,
                        detail={'attribute': attribute, 'new_value': phys[attribute], 'roll': roll, 'temp_condition': added_temp_condition})
        return True


class BloodHealingAction(Action):
    """Discipline: Heal 1 point of damage (aggravated first if present)."""
    def __init__(self, name: str = "Blood Healing"):
        super().__init__(
            name=name,
            action_type=ActionType.FREE,
            execute_func=self._execute,
            description="Heal 1 damage (aggravated prioritized).",
            keywords=["discipline", "healing"],
            per_turn_limit=None
        )

    def _execute(self, entity_id: str, game_state: Any, target_pool: str = 'health') -> bool:
        ent = game_state.get_entity(entity_id)
        if not ent or 'character_ref' not in ent:
            return False
        char = ent['character_ref'].character
        roll = perform_hunger_test(char, game_state, entity_id)
        damage = char._health_damage if target_pool == 'health' else char._willpower_damage
        healed_type = None
        if damage['aggravated'] > 0:
            char.heal_damage(1, damage_type='aggravated', target=target_pool)
            healed_type = 'aggravated'
        elif damage['superficial'] > 0:
            char.heal_damage(1, damage_type='superficial', target=target_pool)
            healed_type = 'superficial'
        bus = getattr(game_state, 'event_bus', None)
        if bus:
            bus.publish('discipline_used', entity_id=entity_id, discipline=self.name, success=True,
                        detail={'target_pool': target_pool, 'healed_type': healed_type, 'roll': roll})
        return True

__all__ = [
    'BloodPulsationAction', 'BloodHealingAction', 'perform_hunger_test'
]
