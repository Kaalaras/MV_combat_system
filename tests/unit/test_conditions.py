import os, sys
CURRENT_DIR = os.path.dirname(__file__)
PACKAGE_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

import unittest
from core.event_bus import EventBus
from core.game_state import GameState
from ecs.ecs_manager import ECSManager
from ecs.systems.condition_system import ConditionSystem
from ecs.systems.action_system import ActionSystem, ActionType
from ecs.components.character_ref import CharacterRefComponent
from entities.character import Character
from utils.condition_utils import (
    WEAKENED_PHYSICAL, WEAKENED_MENTAL_SOCIAL, WEAKENED_TOTAL,
    POISONED, SLOWED, IMMOBILIZED, HANDICAP,
    INVISIBLE, SEE_INVISIBLE,
)

print('Executing test_conditions module')

class TestConditions(unittest.TestCase):
    def setUp(self):
        self.event_bus = EventBus()
        self.ecs_manager = ECSManager(self.event_bus)
        self.gs = GameState(self.ecs_manager)
        self.gs.set_event_bus(self.event_bus)
        self.cond_sys = ConditionSystem(self.ecs_manager, self.event_bus, game_state=self.gs)
        self.gs.set_condition_system(self.cond_sys)
        self.action_sys = ActionSystem(self.gs, self.gs.event_bus)
        self.gs.action_system = self.action_sys
        # Create character
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
        self.gs.add_entity(self.entity_id, {'character_ref': CharacterRefComponent(self.char)})

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_weakened_physical_activation(self):
        max_health = self.char.max_health
        # Apply superficial damage equal to health
        self.char.take_damage(max_health, damage_type='superficial', target='health')
        self.cond_sys.recheck_damage_based(self.entity_id)
        self.assertIn(WEAKENED_PHYSICAL, self.char.states)
        base_pool = 6
        modified = self.cond_sys.apply_pool_modifiers(
            self.char,
            base_pool,
            {'Strength'},
            entity_id=self.entity_id,
        )
        self.assertEqual(modified, base_pool - 2)

    def test_weakened_total_overrides(self):
        self.cond_sys.add_condition(self.entity_id, WEAKENED_TOTAL, rounds=3)
        self.char.states.add(WEAKENED_PHYSICAL)
        base_pool = 5
        modified = self.cond_sys.apply_pool_modifiers(
            self.char,
            base_pool,
            {'Strength'},
            entity_id=self.entity_id,
        )
        self.assertEqual(modified, base_pool - 2)  # not -4

    def test_poisoned_tick_and_expire(self):
        start_health_super = self.char._health_damage['superficial']
        self.cond_sys.add_condition(self.entity_id, POISONED, rounds=1, data={'damage_per_tick':2,'damage_type':'superficial','target_pool':'health'})
        # Simulate turn start -> apply poison
        self.gs.event_bus.publish('turn_started', entity_id=self.entity_id)
        self.assertEqual(self.char._health_damage['superficial'], start_health_super + 2)
        # Round start should tick and expire
        self.gs.event_bus.publish('round_started', round_number=1, turn_order=[self.entity_id])
        self.assertNotIn(POISONED, self.cond_sys.list_conditions(self.entity_id))

    def test_slowed_movement_reduction(self):
        self.cond_sys.add_condition(self.entity_id, SLOWED, rounds=3, data={'percent':50})
        reduced = self.cond_sys.apply_movement_constraints(self.entity_id, 10, 'standard')
        self.assertEqual(reduced, 5)

    def test_immobilized_overrides_slowed(self):
        self.cond_sys.add_condition(self.entity_id, SLOWED, rounds=3, data={'percent':50})
        self.cond_sys.add_condition(self.entity_id, IMMOBILIZED, rounds=2)
        reduced = self.cond_sys.apply_movement_constraints(self.entity_id, 10, 'standard')
        self.assertEqual(reduced, 0)

    def test_handicap_disables_primary(self):
        self.cond_sys.add_condition(self.entity_id, HANDICAP, rounds=2, data={'disable_primary':True})
        self.action_sys.reset_counters(self.entity_id)
        self.assertEqual(self.action_sys.action_counters[self.entity_id][ActionType.PRIMARY], 0)
        self.assertEqual(self.action_sys.action_counters[self.entity_id][ActionType.SECONDARY], 1)

    def test_handicap_disable_both(self):
        self.cond_sys.add_condition(self.entity_id, HANDICAP, rounds=2, data={'disable_primary':True,'disable_secondary':True})
        self.action_sys.reset_counters(self.entity_id)
        self.assertEqual(self.action_sys.action_counters[self.entity_id][ActionType.PRIMARY], 0)
        self.assertEqual(self.action_sys.action_counters[self.entity_id][ActionType.SECONDARY], 0)

    def test_visibility_event_emission(self):
        events = []

        def _capture(**payload):
            events.append(payload)

        self.event_bus.subscribe('visibility_state_changed', _capture)
        self.cond_sys.add_condition(self.entity_id, INVISIBLE)
        self.assertTrue(events)
        self.assertEqual(events[-1]['state'], INVISIBLE)
        self.assertTrue(events[-1]['active'])
        self.cond_sys.remove_condition(self.entity_id, INVISIBLE)
        self.assertGreaterEqual(len(events), 2)
        self.assertFalse(events[-1]['active'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
