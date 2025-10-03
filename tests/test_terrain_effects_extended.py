import unittest
from core.game_state import GameState
from core.event_bus import EventBus
from core.terrain_manager import Terrain, EFFECT_DANGEROUS, EFFECT_VERY_DANGEROUS, EFFECT_DANGEROUS_AURA, EFFECT_DARK_LOW, EFFECT_DARK_TOTAL
from core.movement_system import MovementSystem
from ecs.actions.movement_actions import JumpAction
from ecs.systems.action_system import ActionSystem
from ecs.components.position import PositionComponent
from ecs.components.character_ref import CharacterRefComponent
from ecs.components.cover import CoverComponent
from ecs.ecs_manager import ECSManager
from entities.character import Character
from utils.condition_utils import NIGHT_VISION_PARTIAL, NIGHT_VISION_TOTAL
from core.los_manager import LineOfSightManager
from core.terrain_effect_system import TerrainEffectSystem

class TestTerrainEffectsExtended(unittest.TestCase):
    def setUp(self):
        self.eb = EventBus()
        self.ecs = ECSManager(self.eb)
        self.gs = GameState(self.ecs)
        self.gs.set_event_bus(self.eb)
        self.terrain = Terrain(10,10, game_state=self.gs); self.gs.set_terrain(self.terrain)
        self.move_sys = MovementSystem(self.gs, self.ecs, event_bus=self.eb); self.gs.movement = self.move_sys
        self.action_sys = ActionSystem(self.gs, self.eb); self.gs.action_system = self.action_sys
        self.terrain_effect_sys = TerrainEffectSystem(self.gs, self.terrain, self.eb); self.gs.set_terrain_effect_system(self.terrain_effect_sys)
        self.events = []
        self.eb.subscribe('terrain_effect_trigger', lambda **kw: self.events.append(kw))

    def _add_entity(self, eid:str, x:int, y:int, w:int=1, h:int=1, strength:int=2, athletics:int=2):
        traits = {
            'Attributes': {'Physical': {'Strength': strength, 'Dexterity':1, 'Stamina':1}},
            'Abilities': {'Talents': {'Athletics': athletics}}
        }
        char = Character(); char.traits = traits; char.base_traits = traits
        pos = PositionComponent(x=x,y=y,width=w,height=h)
        ref = CharacterRefComponent(char)
        self.gs.add_entity(eid, {'position':pos,'character_ref':ref})
        self.terrain.add_entity(eid,x,y)
        return eid

    def test_jump_basic_over_void(self):
        eid = self._add_entity('jumper',0,0,strength=2,athletics=2)
        self.terrain.add_impassable_void([(0,1)])
        jump = JumpAction(self.move_sys)
        self.assertTrue(jump.is_available(eid, self.gs, target_tile=(0,2)))
        self.assertTrue(jump.execute(eid, self.gs, target_tile=(0,2)))
        self.assertEqual((self.gs.get_entity(eid)['position'].x, self.gs.get_entity(eid)['position'].y),(0,2))
        self.assertFalse(jump.execute(eid, self.gs, target_tile=(0,1)))

    def test_jump_range_and_heavy_cover_block(self):
        eid = self._add_entity('jumper',0,0,strength=1,athletics=1)
        jump = JumpAction(self.move_sys)
        self.assertTrue(jump.is_available(eid,self.gs,target_tile=(2,0)))
        self.assertFalse(jump.is_available(eid,self.gs,target_tile=(3,0)))
        cover_id = self._add_entity('cover',1,0)
        self.gs.set_component(
            cover_id,
            'cover',
            CoverComponent(cover_type='custom', bonus=3),
        )
        self.assertFalse(jump.execute(eid,self.gs,target_tile=(2,0)))

    def test_movement_cost_stacking_and_removal(self):
        self.terrain.add_difficult([(1,0)])
        self.assertEqual(self.terrain.get_movement_cost(1,0),2)
        self.terrain.add_dangerous([(1,0)])
        self.assertEqual(self.terrain.get_movement_cost(1,0),4)
        self.terrain.remove_effect(lambda e: e.get('name')==EFFECT_DANGEROUS, positions=[(1,0)])
        self.assertEqual(self.terrain.get_movement_cost(1,0),2)

    def test_path_avoids_very_dangerous(self):
        eid = self._add_entity('mover',0,0)
        dest = (4,0)
        self.terrain.add_very_dangerous((2,0), radius=0)
        path = self.move_sys.find_path(eid,dest,max_distance=50)
        self.assertIn((0,1), path, f"Path did not detour: {path}")
        self.assertNotIn((2,0), path)

    def test_hazard_trigger_enter_and_turn_start(self):
        eid = self._add_entity('hero',0,0)
        self.terrain.add_dangerous([(1,0)])
        self.move_sys.move(eid,(1,0),max_steps=7)
        self.assertEqual(len(self.events),1)
        self.eb.publish('turn_start', entity_id=eid)
        self.assertEqual(len(self.events),2)

    def test_aura_reenter_same_turn(self):
        eid = self._add_entity('hero',0,0)
        self.terrain.add_very_dangerous((2,0), radius=1)
        self.move_sys.move(eid,(1,0),max_steps=7)
        aura_events = [e for e in self.events if e['effect']==EFFECT_DANGEROUS_AURA]
        self.assertEqual(len(aura_events),1)
        self.move_sys.move(eid,(0,0),max_steps=7)
        self.move_sys.move(eid,(1,0),max_steps=7)
        aura_events = [e for e in self.events if e['effect']==EFFECT_DANGEROUS_AURA]
        self.assertEqual(len(aura_events),2)

    def test_current_displacement_and_block(self):
        eid = self._add_entity('swimmer',0,0)
        self.terrain.add_current([(0,0)], dx=1, dy=0, magnitude=2)
        self.eb.publish('round_start', round_number=1)
        self.assertEqual((self.gs.get_entity(eid)['position'].x,self.gs.get_entity(eid)['position'].y),(2,0))
        eid2 = self._add_entity('swimmer2',0,1)
        self.terrain.add_current([(0,1)], dx=1, dy=0, magnitude=3)
        self.terrain.add_wall(1,1)
        self.eb.publish('round_start', round_number=2)
        self.assertEqual((self.gs.get_entity('swimmer2')['position'].x,self.gs.get_entity('swimmer2')['position'].y),(0,1))

    def test_darkness_and_night_vision(self):
        eid_att = self._add_entity('att',0,0)
        eid_def = self._add_entity('def',3,0)
        los = LineOfSightManager(self.gs, self.terrain, self.eb)
        self.terrain.add_dark_total([(3,0)])
        self.assertFalse(los.can_see(eid_att, eid_def))
        att_char = self.gs.get_entity(eid_att)['character_ref'].character
        att_char.states.add(NIGHT_VISION_TOTAL)
        self.assertTrue(los.can_see(eid_att, eid_def))
        self.terrain.remove_effect(lambda e: e.get('name')==EFFECT_DARK_TOTAL, positions=[(3,0)])
        self.terrain.add_dark_low([(3,0)])
        att_char.states.discard(NIGHT_VISION_TOTAL)
        self.assertTrue(los.can_see(eid_att, eid_def))
        self.assertEqual(los.get_darkness_attack_modifier(eid_att,eid_def), -1)
        att_char.states.add(NIGHT_VISION_PARTIAL)
        self.assertEqual(los.get_darkness_attack_modifier(eid_att,eid_def), 0)

    def test_large_entity_partial_hazard(self):
        eid = self._add_entity('giant',0,0,w=2,h=1)
        self.terrain.add_dangerous([(1,0)])
        self.terrain.handle_entity_enter(eid,0,0)
        danger_events = [e for e in self.events if e['effect']==EFFECT_DANGEROUS]
        self.assertEqual(len(danger_events),1)

    def test_very_dangerous_auto_fail(self):
        eid = self._add_entity('hero_vd',0,0)
        self.terrain.add_very_dangerous((1,0), radius=0)
        self.move_sys.move(eid,(1,0),max_steps=7)
        vd_events = [e for e in self.events if e['effect']==EFFECT_VERY_DANGEROUS]
        self.assertEqual(len(vd_events),1)
        self.assertTrue(vd_events[0].get('auto_fail'))

    def test_gradient_aura_cost_scaling(self):
        # radius 2 gradient aura
        self.terrain.add_very_dangerous((5,5), radius=2, gradient=True)
        c_adj = self.terrain.get_movement_cost(5,4)  # dist 1 -> expect >=5
        c_far = self.terrain.get_movement_cost(5,3)  # dist 2 -> expect 4
        self.assertGreaterEqual(c_adj,5)
        self.assertEqual(c_far,4)

if __name__ == '__main__':
    unittest.main()

