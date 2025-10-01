import os, sys, unittest
CURRENT_DIR = os.path.dirname(__file__)
PACKAGE_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

from core.event_bus import EventBus
from ecs.ecs_manager import ECSManager
from ecs.systems.condition_system import ConditionSystem
from ecs.components.entity_id import EntityIdComponent
from ecs.components.character_ref import CharacterRefComponent
from ecs.components.condition_tracker import ConditionTrackerComponent
from ecs.components.health import HealthComponent
from ecs.components.willpower import WillpowerComponent
from ecs.components.initiative import InitiativeComponent
from entities.character import Character
from tests.unit.helpers import assert_tracker_has_condition

class TestDamageClamp(unittest.TestCase):
    def setUp(self):
        self.event_bus = EventBus()
        self.ecs_manager = ECSManager(self.event_bus)
        self.cond = ConditionSystem(self.ecs_manager, self.event_bus)
        traits = {'Attributes': {'Physical': {'Strength':2,'Dexterity':2,'Stamina':2}}, 'Virtues': {'Courage':1}}
        self.att = Character(name='Att', traits=traits, base_traits=traits)
        self.defn = Character(name='Def', traits=traits, base_traits=traits)
        self.att_id='ATT_CLAMP'; self.def_id='DEF_CLAMP'
        self._create_entity(self.att_id, self.att)
        self._create_entity(self.def_id, self.defn)

    def _create_entity(self, entity_id: str, character: Character):
        self.ecs_manager.create_entity(
            EntityIdComponent(entity_id),
            CharacterRefComponent(character),
            ConditionTrackerComponent(),
            InitiativeComponent(),
            HealthComponent(character.max_health),
            WillpowerComponent(character.max_willpower),
        )

    def test_full_negative_clamp(self):
        base = 5
        # Outgoing: severity superficial -3; Incoming: all -5 => total delta -8 -> clamp to 0
        self.cond.add_condition(self.att_id, 'DamageOutMod', rounds=2, data={'severity':'superficial','delta':-3})
        self.cond.add_condition(self.def_id, 'DamageInMod', rounds=2, data={'delta':-5})
        adjusted = self.cond.adjust_damage(self.att_id, self.def_id, base, severity='superficial', category='physical')
        self.assertEqual(adjusted, 0)

    def test_remove_strong_negative_restores(self):
        base = 4
        # Outgoing +2 category fire; Outgoing -7 all -> net -5 so clamp 0 initially
        self.cond.add_condition(self.att_id, 'DamageOutMod', rounds=3, data={'category':'fire','delta':2})
        self.cond.add_condition(self.att_id, 'DamageOutMod', rounds=3, data={'delta':-7})
        adj0 = self.cond.adjust_damage(self.att_id, self.def_id, base, severity='unknown', category='fire')
        self.assertEqual(adj0, 0)
        # Remove the strong negative (find suffix)
        neg_name = assert_tracker_has_condition(
            self,
            self.cond,
            self.att_id,
            'DamageOutMod',
            -7,
            tracker_message="Condition tracker missing for attacker entity",
            missing_message="Could not find the negative DamageOutMod condition with delta -7",
        )
        self.cond.remove_condition(self.att_id, neg_name)
        adj1 = self.cond.adjust_damage(self.att_id, self.def_id, base, severity='unknown', category='fire')
        self.assertEqual(adj1, base + 2)

    def test_base_zero_ignores_modifiers(self):
        base = 0
        self.cond.add_condition(self.att_id, 'DamageOutMod', rounds=1, data={'delta':5})
        self.cond.add_condition(self.def_id, 'DamageInMod', rounds=1, data={'delta':5})
        # adjust_damage short-circuits when amount <= 0
        adjusted = self.cond.adjust_damage(self.att_id, self.def_id, base, severity='superficial', category='physical')
        self.assertEqual(adjusted, 0)

if __name__ == '__main__':
    unittest.main(verbosity=2)

