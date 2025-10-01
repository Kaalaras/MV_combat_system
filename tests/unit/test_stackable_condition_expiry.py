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

class TestStackableExpiry(unittest.TestCase):
    def setUp(self):
        self.event_bus = EventBus()
        self.ecs_manager = ECSManager(self.event_bus)
        self.cond = ConditionSystem(self.ecs_manager, self.event_bus)
        traits = {
            'Attributes': {'Physical': {'Strength':3,'Dexterity':2,'Stamina':2}},
            'Virtues': {'Courage':1}
        }
        self.char = Character(name='Stacky', traits=traits, base_traits=traits)
        self.eid = 'E_STACK'
        self._create_entity(self.eid, self.char)

    def _create_entity(self, entity_id: str, character: Character):
        self.ecs_manager.create_entity(
            EntityIdComponent(entity_id),
            CharacterRefComponent(character),
            ConditionTrackerComponent(),
            InitiativeComponent(),
            HealthComponent(character.max_health),
            WillpowerComponent(character.max_willpower),
        )

    def _advance_round(self, r):
        self.event_bus.publish('round_started', round_number=r, turn_order=[self.eid])

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
        tracker = self.cond.get_tracker(self.eid)
        self.assertIsNotNone(tracker, "Condition tracker missing for stackable entity")
        neg_name = next(
            (
                n
                for n, cond in tracker.conditions.items()
                if n.startswith('MaxHealthMod') and cond.data.get('delta') == -2
            ),
            None,
        )
        self.assertIsNotNone(
            neg_name,
            "No MaxHealthMod condition with delta -2 found",
        )
        self.cond.remove_condition(self.eid, neg_name)
        self.assertEqual(self.char.max_health, base_max + 2)
        # Advance until +2 expires
        self._advance_round(2)
        self.assertEqual(self.char.max_health, base_max)

if __name__ == '__main__':
    unittest.main(verbosity=2)

