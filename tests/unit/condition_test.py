import os, sys, unittest
CURRENT_DIR = os.path.dirname(__file__)
PACKAGE_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

from core.event_bus import EventBus
from core.game_state import GameState
from ecs.systems.condition_system import ConditionSystem
from ecs.systems.action_system import ActionSystem, ActionType
from entities.character import Character
from utils.condition_utils import (
    WEAKENED_PHYSICAL, WEAKENED_MENTAL_SOCIAL, WEAKENED_TOTAL,
    POISONED, SLOWED, IMMOBILIZED, HANDICAP,
)

class DummyCharRef:
    def __init__(self, character):
        self.character = character

class ConditionSystemTests(unittest.TestCase):
    def setUp(self):
        self.gs = GameState()
        self.gs.set_event_bus(EventBus())
        self.cond_sys = ConditionSystem(self.gs)
        self.gs.set_condition_system(self.cond_sys)
        self.action_sys = ActionSystem(self.gs, self.gs.event_bus)
        self.gs.action_system = self.action_sys
        traits = {
            'Attributes': {
                'Physical': {'Strength': 3, 'Dexterity': 2, 'Stamina': 2},
                'Mental': {'Intelligence': 2, 'Wits': 2, 'Perception': 2},
                'Social': {'Charisma': 2, 'Manipulation': 2, 'Appearance': 2},
            },
            'Virtues': {'Courage': 1},
        }
        self.char = Character(name="Test", traits=traits, base_traits=traits)
        self.entity_id = 'E1'
        self.gs.add_entity(self.entity_id, {'character_ref': DummyCharRef(self.char)})

    def test_weakened_physical_activation(self):
        max_health = self.char.max_health
        self.char.take_damage(max_health, damage_type='superficial', target='health')
        self.cond_sys.recheck_damage_based(self.entity_id)
        self.assertIn(WEAKENED_PHYSICAL, self.char.states)
        modified = self.cond_sys.apply_pool_modifiers(self.char, 6, {'Strength'})
        self.assertEqual(modified, 4)

    def test_weakened_total_overrides(self):
        self.cond_sys.add_condition(self.entity_id, WEAKENED_TOTAL, rounds=3)
        self.char.states.add(WEAKENED_PHYSICAL)
        modified = self.cond_sys.apply_pool_modifiers(self.char, 5, {'Strength'})
        self.assertEqual(modified, 3)

    def test_poisoned_and_expire(self):
        start = self.char._health_damage['superficial']
        self.cond_sys.add_condition(self.entity_id, POISONED, rounds=1, data={'damage_per_tick':2,'damage_type':'superficial','target_pool':'health'})
        self.gs.event_bus.publish('turn_started', entity_id=self.entity_id)
        self.assertEqual(self.char._health_damage['superficial'], start + 2)
        self.gs.event_bus.publish('round_started', round_number=1, turn_order=[self.entity_id])
        self.assertNotIn(POISONED, self.cond_sys.list_conditions(self.entity_id))

    def test_slowed_and_immobilized(self):
        self.cond_sys.add_condition(self.entity_id, SLOWED, rounds=3, data={'percent':50})
        self.assertEqual(self.cond_sys.apply_movement_constraints(self.entity_id, 10, 'standard'), 5)
        self.cond_sys.add_condition(self.entity_id, IMMOBILIZED, rounds=2)
        self.assertEqual(self.cond_sys.apply_movement_constraints(self.entity_id, 10, 'standard'), 0)

    def test_handicap_slots(self):
        self.cond_sys.add_condition(self.entity_id, HANDICAP, rounds=2, data={'disable_primary':True,'disable_secondary':True})
        self.action_sys.reset_counters(self.entity_id)
        self.assertEqual(self.action_sys.action_counters[self.entity_id][ActionType.PRIMARY], 0)
        self.assertEqual(self.action_sys.action_counters[self.entity_id][ActionType.SECONDARY], 0)

if __name__ == '__main__':
    unittest.main(verbosity=2)

