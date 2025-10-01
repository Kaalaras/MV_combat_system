import os, sys, unittest, random
CURRENT_DIR = os.path.dirname(__file__)
PACKAGE_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

from core.event_bus import EventBus
from core.game_state import GameState
from ecs.ecs_manager import ECSManager
from ecs.systems.condition_system import ConditionSystem
from ecs.actions.discipline_actions import BloodPulsationAction, BloodHealingAction
from ecs.components.character_ref import CharacterRefComponent
from entities.subtypes import Undead, Ghost, Vampire
from entities.character import Character
from entities.weapon import Weapon, WeaponType
from utils.damage_types import DamageType, is_magic, base_type
from ecs.actions.attack_actions import AttackAction

class DummyPosition:
    def __init__(self, x, y):
        self.x = x; self.y = y; self.x1 = x; self.y1 = y; self.x2 = x; self.y2 = y

class MinimalGameState(GameState):
    def __init__(self):
        bus = EventBus()
        ecs_manager = ECSManager(bus)
        super().__init__(ecs_manager)
        self.set_event_bus(bus)
        self.condition_system = ConditionSystem(ecs_manager, bus, game_state=self)
        self.set_condition_system(self.condition_system)
        # Provide movement stub with required methods for dodge but not used in tests with 0 pool
        class MovementStub:
            def get_reachable_tiles(self, entity_id, dist):
                return [(0,0,0)]
            def move(self, entity_id, pos):
                return False
        self.movement = MovementStub()
        # Provide LOS manager stub
        class LOSStub:
            def has_los(self, a, b):
                return True
        self.los_manager = LOSStub()

class TestComprehensiveEdgeCases(unittest.TestCase):
    def setUp(self):
        self.gs = MinimalGameState()

    # ---------------- Damage Type Helpers -----------------
    def test_damage_type_helpers(self):
        self.assertTrue(is_magic(DamageType.SUPERFICIAL_MAGIC.value))
        self.assertFalse(is_magic(DamageType.SUPERFICIAL.value))
        self.assertEqual(base_type(DamageType.SUPERFICIAL_MAGIC.value), 'superficial')
        self.assertEqual(base_type(DamageType.AGGRAVATED.value), 'aggravated')

    def test_invalid_weapon_type_raises(self):
        with self.assertRaises(ValueError):
            Weapon(name='Bad', damage_bonus=1, weapon_range=1, damage_type='invalid_type', weapon_type=WeaponType.BRAWL)

    # ---------------- Undead / Ghost Damage -----------------
    def _mk_traits(self, sta=2, dex=2):
        return {'Attributes': {'Physical': {'Strength': 2, 'Dexterity': dex, 'Stamina': sta}}, 'Virtues': {'Courage':1}, 'Abilities': {'Talents': {'Brawl': 2}}}

    def test_undead_halving_even_and_odd(self):
        u = Undead(name='U', traits=self._mk_traits(), base_traits=self._mk_traits())
        u.take_damage(4, 'superficial')  # even -> 2
        self.assertEqual(u._health_damage['superficial'], 2)
        u.take_damage(5, 'superficial')  # odd -> ceil(5/2)=3 => cumulative 5
        self.assertEqual(u._health_damage['superficial'], 5)

    def test_undead_aggravated_not_halved(self):
        u = Undead(name='U2', traits=self._mk_traits(), base_traits=self._mk_traits())
        u.take_damage(3, 'aggravated')
        self.assertEqual(u._health_damage['aggravated'], 3)

    def test_ghost_magic_and_non_magic_aggravated(self):
        g = Ghost(name='G', traits=self._mk_traits(), base_traits=self._mk_traits())
        g.take_damage(3, 'aggravated')  # ignored
        self.assertEqual(g._health_damage['aggravated'], 0)
        g.take_damage(3, 'aggravated_magic')  # not halved aggravated (undead halving only superficial)
        self.assertEqual(g._health_damage['aggravated'], 3)

    # ---------------- Overflow Conversion -----------------
    def test_superficial_overflow_conversion(self):
        traits = self._mk_traits(sta=2)  # max health = 3+2=5
        c = Character(name='Overflow', traits=traits, base_traits=traits)
        c.take_damage(6, 'superficial')  # expect aggravated=5, superficial=0 (per current logic)
        self.assertEqual(c._health_damage['aggravated'], c.max_health)
        self.assertEqual(c._health_damage['superficial'], 0)
        self.assertTrue(c.is_dead)

    # ---------------- Disciplines Edge Cases -----------------
    def test_blood_pulsation_attribute_missing(self):
        v_traits = {'Attributes': {'Physical': {'Dexterity':2, 'Stamina':2}}, 'Virtues': {'Courage':1}}
        v = Vampire(name='NoStrength', traits=v_traits, base_traits=v_traits)
        eid='VS'; self.gs.add_entity(eid, {'character_ref': CharacterRefComponent(v)})
        bp = BloodPulsationAction()
        # Should return False since Strength missing
        self.assertFalse(bp.execute(eid, self.gs, attribute='Strength'))

    def test_blood_healing_no_damage(self):
        v = Vampire(name='HealNone', traits=self._mk_traits(), base_traits=self._mk_traits())
        eid='VH'; self.gs.add_entity(eid, {'character_ref': CharacterRefComponent(v)})
        heal = BloodHealingAction()
        random.randint = lambda a,b: 6  # no hunger change
        self.assertTrue(heal.execute(eid, self.gs))
        self.assertEqual(v._health_damage['superficial'], 0)
        self.assertEqual(v._health_damage['aggravated'], 0)

    def test_blood_pulsation_multiple_expire_same_round(self):
        traits = self._mk_traits()
        v = Vampire(name='StackExpire', traits=traits, base_traits=traits)
        eid='VSE'; self.gs.add_entity(eid, {'character_ref': CharacterRefComponent(v)})
        bp = BloodPulsationAction()
        random.randint = lambda a,b: 2
        # Raise Strength path first
        v.traits['Attributes']['Physical']['Strength'] = 6
        for _ in range(3):
            bp.execute(eid, self.gs, attribute='Strength')  # Strength 7,8,9 each with independent timers
        # Fast-forward 3 rounds at once by calling round_started thrice; each condition should expire staggered normally
        for r in range(1,7):
            self.gs.event_bus.publish('round_started', round_number=r, turn_order=[eid])
        # Final should revert to 6
        self.assertEqual(v.traits['Attributes']['Physical']['Strength'], 6)

    def test_blood_healing_willpower_pool(self):
        traits = self._mk_traits()
        v = Vampire(name='WPHeal', traits=traits, base_traits=traits)
        eid='VWP'; self.gs.add_entity(eid, {'character_ref': CharacterRefComponent(v)})
        # Deal willpower damage
        v.take_damage(2, 'superficial', target='willpower')
        heal = BloodHealingAction()
        random.randint = lambda a,b: 3
        heal.execute(eid, self.gs, target_pool='willpower')
        self.assertEqual(v._willpower_damage['superficial'], 0)

    # ---------------- Hunger Events Edge Cases -----------------
    def test_hunger_no_event_when_roll_high(self):
        traits = self._mk_traits()
        v = Vampire(name='HungerHigh', traits=traits, base_traits=traits)
        eid='HH'; self.gs.add_entity(eid, {'character_ref': CharacterRefComponent(v)})
        events=[]
        self.gs.event_bus.subscribe('hunger_changed', lambda **kw: events.append(kw))
        bp = BloodPulsationAction()
        random.randint = lambda a,b: 9  # no increase
        bp.execute(eid, self.gs, attribute='Strength')
        self.assertEqual(len(events), 0)

    def test_hunger_event_not_emitted_when_capped(self):
        traits = self._mk_traits()
        v = Vampire(name='HungerCap', traits=traits, base_traits=traits)
        v.hunger = 5
        eid='HC'; self.gs.add_entity(eid, {'character_ref': CharacterRefComponent(v)})
        events=[]
        self.gs.event_bus.subscribe('hunger_changed', lambda **kw: events.append(kw))
        bp = BloodPulsationAction()
        random.randint = lambda a,b: 2  # would increase if not capped
        bp.execute(eid, self.gs, attribute='Strength')
        self.assertEqual(len(events), 0)

    # ---------------- Attack Action Hunger Dice Cap -----------------
    def test_attack_action_hunger_cap(self):
        # Attacker with hunger > pool size should not raise error
        traits_att = self._mk_traits(dex=2)
        attacker = Vampire(name='Att', traits=traits_att, base_traits=traits_att)
        attacker.hunger = 10  # deliberately higher than expected pool
        att_id='ATT'; self.gs.add_entity(att_id, {'character_ref': CharacterRefComponent(attacker), 'position': DummyPosition(0,0)})
        # Add minimal skill path for weapon trait resolution
        traits_def = self._mk_traits()
        defender = Character(name='Def', traits=traits_def, base_traits=traits_def)
        def_id='DEF'; self.gs.add_entity(def_id, {'character_ref': CharacterRefComponent(defender), 'position': DummyPosition(0,0)})
        weapon = Weapon(name='Claw', damage_bonus=1, weapon_range=1, damage_type='superficial', weapon_type=WeaponType.BRAWL)
        attack = AttackAction(att_id, def_id, weapon, self.gs)
        # Force small pool by clearing skills
        attacker.traits['Abilities']['Talents']['Brawl'] = 1
        # Should execute without raising (may do 0 damage due to pool)
        try:
            attack.execute()
        except Exception as e:
            self.fail(f"AttackAction raised exception with high hunger: {e}")

if __name__ == '__main__':
    unittest.main(verbosity=2)
