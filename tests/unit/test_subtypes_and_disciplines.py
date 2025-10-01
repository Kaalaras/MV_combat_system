import os, sys
CURRENT_DIR = os.path.dirname(__file__)
PACKAGE_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

import unittest
import random
from core.event_bus import EventBus
from core.game_state import GameState
from ecs.ecs_manager import ECSManager
from ecs.systems.condition_system import ConditionSystem
from ecs.actions.discipline_actions import BloodPulsationAction, BloodHealingAction
from ecs.components.character_ref import CharacterRefComponent
from entities.subtypes import Undead, Ghost, Vampire

BASIC_VIRTUES = {'Virtues': {'Courage': 1}}

class TestUndeadAndDisciplines(unittest.TestCase):
    def setUp(self):
        self.original_randint = random.randint
        self.event_bus = EventBus()
        self.ecs_manager = ECSManager(self.event_bus)
        self.gs = GameState(self.ecs_manager)
        self.gs.set_event_bus(self.event_bus)
        self.cond_sys = ConditionSystem(self.ecs_manager, self.event_bus, game_state=self.gs)
        self.gs.set_condition_system(self.cond_sys)

    def tearDown(self):
        random.randint = self.original_randint

    def _add_entity(self, eid, char):
        self.gs.add_entity(eid, {'character_ref': CharacterRefComponent(char)})
        return eid

    def _mk_traits(self, strength=3, dex=2, sta=2):
        return {'Attributes': {'Physical': {'Strength': strength, 'Dexterity': dex, 'Stamina': sta}}, **BASIC_VIRTUES}

    def test_undead_superficial_halving(self):
        traits = self._mk_traits(sta=2)
        u = Undead(name='ZombieTest', traits=traits, base_traits=traits)
        before = u._health_damage['superficial']
        u.take_damage(5, damage_type='superficial')  # should halve 5 -> 3 (rounded up)
        self.assertEqual(u._health_damage['superficial'] - before, 3)

    def test_ghost_immunity_and_magic(self):
        traits = self._mk_traits(sta=2)
        g = Ghost(name='Ghosty', traits=traits, base_traits=traits)
        g.take_damage(4, damage_type='superficial')  # ignored
        self.assertEqual(g._health_damage['superficial'], 0)
        g.take_damage(5, damage_type='superficial_magic')  # halved 5 -> 3
        self.assertEqual(g._health_damage['superficial'], 3)

    def test_blood_pulsation_stacking_and_expiry(self):
        traits = self._mk_traits(strength=5)
        v = Vampire(name='Vlad', traits=traits, base_traits=traits)
        eid = self._add_entity('V1', v)
        pulsate = BloodPulsationAction()
        random.randint = lambda a,b: 3  # always increase hunger
        # Raise to 6 (permanent)
        pulsate.execute(eid, self.gs, attribute='Strength')
        self.assertEqual(v.traits['Attributes']['Physical']['Strength'], 6)
        self.gs.event_bus.publish('round_started', round_number=1, turn_order=[eid])
        # Create staggered temporary boosts
        pulsate.execute(eid, self.gs, attribute='Strength')  # 7 (A:3)
        self.gs.event_bus.publish('round_started', round_number=2, turn_order=[eid])  # A:2
        pulsate.execute(eid, self.gs, attribute='Strength')  # 8 (B:3)
        self.gs.event_bus.publish('round_started', round_number=3, turn_order=[eid])  # A:1 B:2
        pulsate.execute(eid, self.gs, attribute='Strength')  # 9 (C:3)
        self.assertEqual(v.traits['Attributes']['Physical']['Strength'], 9)
        # Expirations
        self.gs.event_bus.publish('round_started', round_number=4, turn_order=[eid])  # A expires -> 8
        self.assertEqual(v.traits['Attributes']['Physical']['Strength'], 8)
        self.gs.event_bus.publish('round_started', round_number=5, turn_order=[eid])  # B expires ->7
        self.assertEqual(v.traits['Attributes']['Physical']['Strength'], 7)
        self.gs.event_bus.publish('round_started', round_number=6, turn_order=[eid])  # C expires ->6
        self.assertEqual(v.traits['Attributes']['Physical']['Strength'], 6)

    def test_blood_healing_prioritizes_aggravated(self):
        traits = self._mk_traits()
        v = Vampire(name='HealTest', traits=traits, base_traits=traits)
        eid = self._add_entity('V2', v)
        v.take_damage(2, damage_type='superficial')
        v.take_damage(1, damage_type='aggravated')
        self.assertEqual(v._health_damage['aggravated'], 1)
        heal = BloodHealingAction()
        random.randint = lambda a,b: 4
        heal.execute(eid, self.gs)
        self.assertEqual(v._health_damage['aggravated'], 0)
        heal.execute(eid, self.gs)
        # After aggravated conversion mechanics, initial superficial reduced by aggravated damage application
        # so only 1 superficial remained before second heal -> now 0
        self.assertEqual(v._health_damage['superficial'], 0)

    def test_hunger_increases_and_caps(self):
        traits = self._mk_traits()
        v = Vampire(name='HungerTest', traits=traits, base_traits=traits)
        eid = self._add_entity('V3', v)
        pulsate = BloodPulsationAction()
        random.randint = lambda a,b: 2  # always increase hunger
        for _ in range(7):
            pulsate.execute(eid, self.gs, attribute='Strength')
        self.assertEqual(v.hunger, 5)

    def test_events_hunger_changed_and_discipline_used(self):
        traits = self._mk_traits()
        v = Vampire(name='EventTest', traits=traits, base_traits=traits)
        eid = self._add_entity('VE', v)
        pulsate = BloodPulsationAction()
        hunger_events = []
        discipline_events = []
        self.gs.event_bus.subscribe('hunger_changed', lambda **kw: hunger_events.append(kw))
        self.gs.event_bus.subscribe('discipline_used', lambda **kw: discipline_events.append(kw))
        # Force hunger increase
        import random as _r
        _r.randint = lambda a,b: 4
        pulsate.execute(eid, self.gs, attribute='Strength')
        self.assertEqual(len(hunger_events), 1)
        self.assertEqual(hunger_events[0]['old'], 0)
        self.assertEqual(hunger_events[0]['new'], 1)
        self.assertEqual(len(discipline_events), 1)
        self.assertEqual(discipline_events[0]['discipline'], 'Blood Pulsation')
        # Set hunger cap and ensure no hunger_changed when roll triggers increase
        v.hunger = 5
        pulsate.execute(eid, self.gs, attribute='Strength')
        self.assertEqual(len(hunger_events), 1)  # unchanged

if __name__ == '__main__':
    unittest.main(verbosity=2)
