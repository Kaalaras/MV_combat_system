import os, sys, unittest
CURRENT_DIR = os.path.dirname(__file__)
PACKAGE_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

from core.event_bus import EventBus
from core.game_state import GameState
from ecs.systems.condition_system import ConditionSystem
from entities.character import Character
from entities.weapon import Weapon, WeaponType
from entities.armor import Armor
from ecs.actions.attack_actions import AttackAction
from ecs.components.equipment import EquipmentComponent
from utils.damage_types import classify_damage

class DummyCharRef:
    def __init__(self, character):
        self.character = character

class Pos:
    def __init__(self, x, y):
        self.x = x; self.y = y; self.x1=x; self.y1=y; self.x2=x; self.y2=y

class MovementStub:
    def get_reachable_tiles(self, eid, dist):
        return [(0,0,0)]
    def move(self, eid, pos):
        return False

class LOSStub:
    def has_los(self, a, b):
        return True

class MinimalGameState(GameState):
    def __init__(self):
        super().__init__()
        self.set_event_bus(EventBus())
        self.condition_system = ConditionSystem(self)
        self.set_condition_system(self.condition_system)
        self.movement = MovementStub()
        self.los_manager = LOSStub()

class _TestAttackAction(AttackAction):
    """Test-only subclass to suppress defenses deterministically without monkeypatching core module."""
    def get_available_defenses(self, defender, is_close_combat: bool, is_superficial: bool):
        return []  # force no defenses

class TestAdditionalEdgeCases(unittest.TestCase):
    def setUp(self):
        self.gs = MinimalGameState()

    def _traits(self, str_=3, dex=2, sta=2, brawl=3):
        return {
            'Attributes': {'Physical': {'Strength': str_, 'Dexterity': dex, 'Stamina': sta}},
            'Abilities': {'Talents': {'Brawl': brawl}},
            'Virtues': {'Courage':1},
            'Disciplines': {}
        }

    # 1. DamageInMod + Armor resistance multiplier interactions
    def test_armor_resistance_and_damage_in_mod(self):
        traits = self._traits()
        defender = Character(name='Def', traits=traits, base_traits=traits)
        d_id = 'D'
        # Armor: superficial severity 0.5, fire category 0 (immunity), all 2 (overall)
        # We'll use two components: superficial (affected by severity+all) and aggravated_fire (category fire + all)
        armor = Armor(name='Mixed', armor_value=2, damage_type=['superficial'], weapon_type_protected=['brawl','melee'],
                      resistance_multipliers={'superficial':0.5, 'fire':0.0, 'all':2.0})
        equip = EquipmentComponent(); equip.armor = armor
        self.gs.add_entity(d_id, {'character_ref': DummyCharRef(defender), 'position': Pos(0,0), 'equipment': equip})
        # Attacker with no modifiers
        attacker = Character(name='Att', traits=traits, base_traits=traits)
        a_id='A'; self.gs.add_entity(a_id, {'character_ref': DummyCharRef(attacker), 'position': Pos(0,0)})
        # Apply DamageInMod conditions for defender: category fire +2, severity superficial +3, all +1
        self.gs.condition_system.add_condition(d_id, 'DamageInMod', data={'category':'fire','delta':2})
        self.gs.condition_system.add_condition(d_id, 'DamageInMod', data={'severity':'superficial','delta':3})
        self.gs.condition_system.add_condition(d_id, 'DamageInMod', data={'delta':1})
        # Weapon with two components
        weapon = Weapon(name='TestClaw', damage_bonus=0, weapon_range=1, damage_type='superficial', weapon_type=WeaponType.BRAWL,
                        damage_components=[{'damage_bonus':4,'damage_type':'superficial'},
                                           {'damage_bonus':5,'damage_type':'aggravated_fire'}])
        atk = _TestAttackAction(a_id, d_id, weapon, self.gs)
        class StubDice:
            def roll_pool(self, pool, hunger_dice=0):
                return {'successes':3,'bestial_failures':0,'critical_successes':0,'hunger_bestial_successes':0,'hunger_bestial_failures':0}
        atk.dice_roller = StubDice()
        total = atk.execute()
        # After applying 9 superficial damage, overflow converts to aggravated until track full: expect aggravated=max, superficial=0
        self.assertEqual(defender._health_damage['superficial'], 0)
        self.assertEqual(defender._health_damage['aggravated'], defender.max_health)
        self.assertEqual(total, 9)

    # 2. DamageOutMod + DamageInMod stacking (category + severity + all)
    def test_damage_out_in_stacking(self):
        traits = self._traits()
        attacker = Character(name='Att', traits=traits, base_traits=traits)
        defender = Character(name='Def', traits=traits, base_traits=traits)
        a_id='A2'; d_id='D2'
        self.gs.add_entity(a_id, {'character_ref': DummyCharRef(attacker), 'position': Pos(0,0)})
        self.gs.add_entity(d_id, {'character_ref': DummyCharRef(defender), 'position': Pos(0,0)})
        # Add outgoing mods
        self.gs.condition_system.add_condition(a_id, 'DamageOutMod', data={'category':'fire','delta':2})
        self.gs.condition_system.add_condition(a_id, 'DamageOutMod', data={'severity':'superficial','delta':1})
        self.gs.condition_system.add_condition(a_id, 'DamageOutMod', data={'delta':1})
        # Add incoming mods
        self.gs.condition_system.add_condition(d_id, 'DamageInMod', data={'category':'fire','delta':3})
        self.gs.condition_system.add_condition(d_id, 'DamageInMod', data={'severity':'superficial','delta':2})
        # Base incoming damage amount
        base_amount = 5
        sev, cat = 'superficial', 'fire'
        adjusted = self.gs.condition_system.adjust_damage(a_id, d_id, base_amount, sev, cat)
        # Expected: 5 + (attacker:2+1+1)=9 + (defender:3+2)=14
        self.assertEqual(adjusted, 14)

    # 3. MaxHealthMod stacking + expiry restoration
    def test_max_health_mod_stacking_and_restoration(self):
        traits = self._traits(sta=2)  # base max health = 5
        c = Character(name='HP', traits=traits, base_traits=traits)
        eid='HP1'
        self.gs.add_entity(eid, {'character_ref': DummyCharRef(c)})
        # Deal superficial damage 4
        c.take_damage(4, 'superficial')
        self.assertEqual(c._health_damage['superficial'], 4)
        # Apply negative max health mod (-3) rounds=1 (removes up to 3 superficial)
        self.gs.condition_system.add_condition(eid, 'MaxHealthMod', rounds=1, data={'delta':-3})
        # After application, superficial reduced to 1
        self.assertEqual(c._health_damage['superficial'], 1)
        # Apply positive mod +2 rounds=2
        self.gs.condition_system.add_condition(eid, 'MaxHealthMod', rounds=2, data={'delta':2})
        # Advance one round -> negative expires restores 3 superficial (back to 4)
        self.gs.event_bus.publish('round_started', round_number=1, turn_order=[eid])
        self.assertEqual(c._health_damage['superficial'], 4)
        # Advance second round -> positive expires, max health returns to base
        self.gs.event_bus.publish('round_started', round_number=2, turn_order=[eid])
        self.assertEqual(c.max_health, c.base_max_health)

    # 4. InitiativeMod stacking and removal order
    def test_initiative_mod_stacking(self):
        traits = self._traits()
        c = Character(name='Init', traits=traits, base_traits=traits)
        eid='INIT'
        self.gs.add_entity(eid, {'character_ref': DummyCharRef(c)})
        self.gs.condition_system.add_condition(eid, 'InitiativeMod', rounds=2, data={'delta':3})
        self.gs.condition_system.add_condition(eid, 'InitiativeMod', rounds=1, data={'delta':-1})
        self.assertEqual(c.initiative_mod, 2)  # 3 + (-1)
        # After one round second expires -> +3 remains
        self.gs.event_bus.publish('round_started', round_number=1, turn_order=[eid])
        self.assertEqual(c.initiative_mod, 3)
        # After second round first expires -> back to 0
        self.gs.event_bus.publish('round_started', round_number=2, turn_order=[eid])
        self.assertEqual(c.initiative_mod, 0)

    # 5. Multi-component weapon with partial nullification
    def test_multi_component_partial_nullification(self):
        traits_att = self._traits(str_=3, dex=3, brawl=5)
        traits_def = self._traits()
        attacker = Character(name='Att', traits=traits_att, base_traits=traits_att)
        defender = Character(name='Def', traits=traits_def, base_traits=traits_def)
        a_id='MA'; d_id='MD'
        # Armor immune to superficial via multiplier 0
        armor = Armor(name='SupImmune', armor_value=2, damage_type=['superficial'], weapon_type_protected=['brawl','melee'],
                      resistance_multipliers={'superficial':0.0})
        equip = EquipmentComponent(); equip.armor = armor
        self.gs.add_entity(a_id, {'character_ref': DummyCharRef(attacker), 'position': Pos(0,0)})
        self.gs.add_entity(d_id, {'character_ref': DummyCharRef(defender), 'position': Pos(0,0), 'equipment': equip})
        weapon = Weapon(name='ClawsMulti', damage_bonus=0, weapon_range=1, damage_type='superficial', weapon_type=WeaponType.BRAWL,
                        damage_components=[{'damage_bonus':2,'damage_type':'superficial'},
                                           {'damage_bonus':1,'damage_type':'aggravated'},
                                           {'damage_bonus':3,'damage_type':'superficial'}])
        atk = _TestAttackAction(a_id, d_id, weapon, self.gs)
        class StubDice:
            def roll_pool(self, pool, hunger_dice=0):
                return {'successes':2,'bestial_failures':0,'critical_successes':0,'hunger_bestial_successes':0,'hunger_bestial_failures':0}
        atk.dice_roller = StubDice()
        total = atk.execute()
        # Net successes=2 => component base damages: 2+2=4 (superficial) -> immunity ->0; 1+2=3 aggravated -> applied; 3+2=5 superficial -> 0
        self.assertEqual(defender._health_damage['aggravated'], 3)
        self.assertEqual(defender._health_damage['superficial'], 0)
        self.assertEqual(total, 3)

if __name__ == '__main__':
    unittest.main(verbosity=2)
