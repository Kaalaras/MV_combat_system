import unittest
from MV_combat_system.core.game_state import GameState
from MV_combat_system.core.movement_system import MovementSystem
from MV_combat_system.ecs.actions.movement_actions import StandardMoveAction
from MV_combat_system.ecs.systems.action_system import ActionSystem, ActionType
from MV_combat_system.entities.character import Character
from MV_combat_system.ecs.systems.opportunity_attack_system import OpportunityAttackSystem

class Position:
    def __init__(self,x,y,width=1,height=1):
        self.x=x; self.y=y; self.width=width; self.height=height

class Terrain:
    def __init__(self,w=20,h=20):
        self.width=w; self.height=h; self.grid={}
    def is_walkable(self,x,y,w=1,h=1):
        return 0<=x<self.width and 0<=y<self.height
    def is_occupied(self,x,y,w=1,h=1,entity_id_to_ignore=None,check_walls=True):
        occ=self.grid.get((x,y)); return occ is not None and occ!=entity_id_to_ignore
    def move_entity(self,eid,x,y):
        # simple move
        for k,v in list(self.grid.items()):
            if v==eid: del self.grid[k]
        if self.grid.get((x,y)): return False
        self.grid[(x,y)]=eid
        return True

class DummyBus:
    def __init__(self):
        self.subs={}
        self.events=[]
    def subscribe(self,name,cb):
        self.subs.setdefault(name,[]).append(cb)
    def publish(self,name,**kw):
        self.events.append((name,kw))
        for cb in self.subs.get(name,[]):
            cb(**kw)

class EquipmentStub:
    def __init__(self):
        self.weapons={}
        self.armor=None

class MeleeWeaponStub:
    def __init__(self,name='TestSword'):
        self.name=name
        self.weapon_type='melee'
        self.weapon_range=1
        self.maximum_range=1
        self.attack_traits=("Attributes.Physical.Dexterity","Abilities.Talents.Brawl")
        self.damage_type='superficial'
        self.effects=[]
    def get_damage_components(self):
        return [{'damage_bonus':0,'damage_type':self.damage_type}]

class RangedWeaponStub(MeleeWeaponStub):
    def __init__(self,name='Bow'):
        super().__init__(name)
        self.weapon_type='ranged'
        self.weapon_range=10
        self.maximum_range=30

class TestOpportunityAttack(unittest.TestCase):
    def setUp(self):
        self.gs=GameState()
        self.gs.terrain=Terrain()
        self.bus=DummyBus()
        self.gs.event_bus=self.bus
        self.gs.movement=MovementSystem(self.gs)
        self.action_system=ActionSystem(self.gs,self.bus)
        self.gs.action_system=self.action_system
        # Traits include Brawl so melee dice pool >0
        traits={"Attributes":{"Physical":{"Dexterity":3,"Stamina":2}},"Abilities":{"Talents":{"Brawl":2}}}
        a_char=Character(name='Attacker',traits=traits,base_traits=traits)
        b_char=Character(name='Mover',traits=traits,base_traits=traits)
        # Make mover AI controlled so defense auto-selects (no user input)
        b_char.is_ai_controlled=True
        self.att_id='A'; self.mov_id='B'
        # Equipment with melee weapon for attacker
        equip_att = EquipmentStub(); equip_att.weapons['main']=MeleeWeaponStub()
        equip_mov = EquipmentStub()  # mover weaponless (doesn't matter)
        self.gs.add_entity(self.att_id,{"position":Position(5,5),"character_ref":type('CR',(),{'character':a_char})(),"equipment":equip_att})
        self.gs.add_entity(self.mov_id,{"position":Position(5,6),"character_ref":type('CR',(),{'character':b_char})(),"equipment":equip_mov})
        self.gs.terrain.grid[(5,5)]=self.att_id
        self.gs.terrain.grid[(5,6)]=self.mov_id
        move_act=StandardMoveAction(self.gs.movement)
        self.action_system.register_action(self.mov_id, move_act)
        self.action_system.reset_counters(self.mov_id)
        self.action_system.reset_counters(self.att_id)
        self.gs.reset_movement_usage(self.mov_id)
        # Wire reaction system
        self.opportunity_system = OpportunityAttackSystem(self.gs,self.bus)

    def _get_events(self,name):
        return [e for e in self.bus.events if e[0]==name]

    def test_aoo_trigger(self):
        self.bus.publish('action_requested', entity_id=self.mov_id, action_name='Standard Move', target_tile=(5,8))
        aoos=self._get_events('opportunity_attack_triggered')
        self.assertEqual(len(aoos),1)
        self.assertEqual(aoos[0][1]['attacker_id'], self.att_id)

    def test_aoo_toggle_off(self):
        self.gs.get_entity(self.att_id)['character_ref'].character.toggle_opportunity_attack=False
        self.bus.publish('action_requested', entity_id=self.mov_id, action_name='Standard Move', target_tile=(5,8))
        aoos=self._get_events('opportunity_attack_triggered')
        self.assertEqual(len(aoos),0)

    def test_no_aoo_if_still_adjacent(self):
        self.bus.publish('action_requested', entity_id=self.mov_id, action_name='Standard Move', target_tile=(6,5))
        aoos=self._get_events('opportunity_attack_triggered')
        self.assertEqual(len(aoos),0)

    def test_pathfind_aoo_single_trigger(self):
        moved = self.gs.movement.move(self.mov_id, (5,10), max_steps=10, pathfind=True)
        self.assertTrue(moved)
        aoos=self._get_events('opportunity_attack_triggered')
        self.assertEqual(len(aoos),1)
        self.assertEqual(aoos[0][1]['attacker_id'], self.att_id)

    def test_reaction_attack_and_defense_flow(self):
        # Trigger AoO -> reaction
        self.bus.publish('action_requested', entity_id=self.mov_id, action_name='Standard Move', target_tile=(5,8))
        # Assert trigger
        self.assertEqual(len(self._get_events('opportunity_attack_triggered')),1)
        # Reaction event
        reactions=self._get_events('opportunity_attack_reaction')
        self.assertEqual(len(reactions),1)
        self.assertEqual(reactions[0][1]['attacker_id'], self.att_id)
        # Defense prompt & resolved events present
        self.assertGreaterEqual(len(self._get_events('defense_prompt')),1)
        self.assertGreaterEqual(len(self._get_events('defense_resolved')),1)
        # Action economy unchanged for attacker (PRIMARY/SECONDARY still 1)
        counters=self.action_system.action_counters[self.att_id]
        self.assertEqual(counters[ActionType.PRIMARY],1)
        self.assertEqual(counters[ActionType.SECONDARY],1)

    def test_no_reaction_same_team(self):
        # Put both on same team so no AoO
        self.gs.get_entity(self.att_id)['character_ref'].character.team='X'
        self.gs.get_entity(self.mov_id)['character_ref'].character.team='X'
        self.bus.publish('action_requested', entity_id=self.mov_id, action_name='Standard Move', target_tile=(5,8))
        self.assertEqual(len(self._get_events('opportunity_attack_triggered')),0)
        self.assertEqual(len(self._get_events('opportunity_attack_reaction')),0)

    def test_no_reaction_no_melee_weapon(self):
        # Replace melee weapon with ranged weapon -> no trigger
        equip = self.gs.get_entity(self.att_id)['equipment']
        equip.weapons={'ranged':RangedWeaponStub()}
        self.bus.publish('action_requested', entity_id=self.mov_id, action_name='Standard Move', target_tile=(5,8))
        self.assertEqual(len(self._get_events('opportunity_attack_triggered')),0)
        self.assertEqual(len(self._get_events('opportunity_attack_reaction')),0)

if __name__=='__main__':
    unittest.main()
