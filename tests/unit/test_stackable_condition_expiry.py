import os, sys, unittest
CURRENT_DIR = os.path.dirname(__file__)
PACKAGE_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

from core.event_bus import EventBus
from core.game_state import GameState
from ecs.systems.condition_system import ConditionSystem
from entities.character import Character

class DummyCharRef:
    def __init__(self, character):
        self.character = character

class TestStackableExpiry(unittest.TestCase):
    def setUp(self):
        self.gs = GameState()
        self.gs.set_event_bus(EventBus())
        self.cond = ConditionSystem(self.gs)
        self.gs.set_condition_system(self.cond)
        traits = {
            'Attributes': {'Physical': {'Strength':3,'Dexterity':2,'Stamina':2}},
            'Virtues': {'Courage':1}
        }
        self.char = Character(name='Stacky', traits=traits, base_traits=traits)
        self.eid = 'E_STACK'
        self.gs.add_entity(self.eid, {'character_ref': DummyCharRef(self.char)})

    def _advance_round(self, r):
        self.gs.event_bus.publish('round_started', round_number=r, turn_order=[self.eid])

    def test_initiative_interleaved(self):
        # Add +3 (3 rounds), -1 (2 rounds), +5 (1 round)
        self.cond.add_condition(self.eid, 'InitiativeMod', rounds=3, data={'delta':3})
        self.assertEqual(self.char.initiative_mod, 3)
        self.cond.add_condition(self.eid, 'InitiativeMod', rounds=2, data={'delta':-1})
        self.assertEqual(self.char.initiative_mod, 2)  # 3 + (-1)
        self.cond.add_condition(self.eid, 'InitiativeMod', rounds=1, data={'delta':5})
        self.assertEqual(self.char.initiative_mod, 7)  # 3 -1 +5
        # Round 1: +5 expires
        self._advance_round(1)
        self.assertEqual(self.char.initiative_mod, 2)  # 3 -1
        # Round 2: -1 expires
        self._advance_round(2)
        self.assertEqual(self.char.initiative_mod, 3)
        # Manual remove base +3 (name without suffix)
        self.cond.remove_condition(self.eid, 'InitiativeMod')
        self.assertEqual(self.char.initiative_mod, 0)

    def test_max_health_interleaved_manual_removal(self):
        # deal some superficial damage
        self.char.take_damage(3, 'superficial')
        base_max = self.char.base_max_health
        # Add +2 (2 rounds)
        self.cond.add_condition(self.eid, 'MaxHealthMod', rounds=2, data={'delta':2})
        self.assertEqual(self.char.max_health, base_max + 2)
        # Add -2 (3 rounds) -> reduces max and removes damage first
        self.cond.add_condition(self.eid, 'MaxHealthMod', rounds=3, data={'delta':-2})
        self.assertEqual(self.char.max_health, base_max)  # +2 then -2
        # Add +4 (1 round)
        self.cond.add_condition(self.eid, 'MaxHealthMod', rounds=1, data={'delta':4})
        self.assertEqual(self.char.max_health, base_max + 4)  # net (+2 -2 +4)
        # Advance 1 round -> +4 expires
        self._advance_round(1)
        self.assertEqual(self.char.max_health, base_max)  # back to +2 -2 = 0
        # Manually remove the negative modifier (suffix unknown; find it)
        neg_name = [n for n in self.cond.list_conditions(self.eid) if n.startswith('MaxHealthMod') and self.cond._conditions[self.eid][n].data.get('delta') == -2][0]
        self.cond.remove_condition(self.eid, neg_name)
        self.assertEqual(self.char.max_health, base_max + 2)
        # Advance until +2 expires
        self._advance_round(2)
        self.assertEqual(self.char.max_health, base_max)

if __name__ == '__main__':
    unittest.main(verbosity=2)

