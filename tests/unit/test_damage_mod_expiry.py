import os, sys, unittest
CURRENT_DIR = os.path.dirname(__file__)
PACKAGE_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

from core.event_bus import EventBus
from core.game_state import GameState
from ecs.ecs_manager import ECSManager
from ecs.systems.condition_system import ConditionSystem
from ecs.components.character_ref import CharacterRefComponent
from entities.character import Character

class TestDamageModExpiry(unittest.TestCase):
    def setUp(self):
        self.event_bus = EventBus()
        self.ecs_manager = ECSManager(self.event_bus)
        self.gs = GameState(self.ecs_manager)
        self.gs.set_event_bus(self.event_bus)
        self.cond = ConditionSystem(self.ecs_manager, self.event_bus, game_state=self.gs)
        self.gs.set_condition_system(self.cond)
        traits_att = {'Attributes': {'Physical': {'Strength':3,'Dexterity':2,'Stamina':2}}, 'Virtues': {'Courage':1}}
        traits_def = {'Attributes': {'Physical': {'Strength':2,'Dexterity':2,'Stamina':2}}, 'Virtues': {'Courage':1}}
        self.att = Character(name='Att', traits=traits_att, base_traits=traits_att)
        self.defn = Character(name='Def', traits=traits_def, base_traits=traits_def)
        self.att_id='A_MOD'; self.def_id='D_MOD'
        self.gs.add_entity(self.att_id, {'character_ref': CharacterRefComponent(self.att)})
        self.gs.add_entity(self.def_id, {'character_ref': CharacterRefComponent(self.defn)})
        self.round = 0

    def _advance_round(self):
        self.round += 1
        self.gs.event_bus.publish('round_started', round_number=self.round, turn_order=[self.att_id, self.def_id])

    def test_simultaneous_and_staggered_expiry(self):
        base = 5
        # Outgoing: fire +3 (3 rounds), all +1 (2 rounds), fire -2 (1 round) => initial net fire = (+3 -2) + all(+1)= +2
        self.cond.add_condition(self.att_id, 'DamageOutMod', rounds=3, data={'category':'fire','delta':3})
        self.cond.add_condition(self.att_id, 'DamageOutMod', rounds=2, data={'delta':1})
        self.cond.add_condition(self.att_id, 'DamageOutMod', rounds=1, data={'category':'fire','delta':-2})
        # Incoming: fire +2 (2 rounds), all +1 (3 rounds) => +3 initial
        self.cond.add_condition(self.def_id, 'DamageInMod', rounds=2, data={'category':'fire','delta':2})
        self.cond.add_condition(self.def_id, 'DamageInMod', rounds=3, data={'delta':1})
        # Check initial
        adj0 = self.cond.adjust_damage(self.att_id, self.def_id, base, severity='unknown', category='fire')
        self.assertEqual(adj0, 10)  # 5 +2 +3
        # Round 1: fire -2 expires
        self._advance_round()
        adj1 = self.cond.adjust_damage(self.att_id, self.def_id, base, severity='unknown', category='fire')
        # Now out: fire +3, all +1 => +4 ; in: fire +2, all +1 => +3 => 5+4+3=12
        self.assertEqual(adj1, 12)
        # Round 2: outgoing all +1 and incoming fire +2 expire
        self._advance_round()
        adj2 = self.cond.adjust_damage(self.att_id, self.def_id, base, severity='unknown', category='fire')
        # Out: fire +3 => +3 ; In: all +1 => +1 => 5+3+1=9
        self.assertEqual(adj2, 9)
        # Round 3: outgoing fire +3 and incoming all +1 expire (end state)
        self._advance_round()
        adj3 = self.cond.adjust_damage(self.att_id, self.def_id, base, severity='unknown', category='fire')
        self.assertEqual(adj3, 5)

if __name__ == '__main__':
    unittest.main(verbosity=2)

