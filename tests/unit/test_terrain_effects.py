import unittest
from core.game_state import GameState
from core.event_bus import EventBus
from core.terrain_manager import Terrain, EVT_TERRAIN_EFFECT_TRIGGER, EVT_TERRAIN_CURRENT_MOVED, EFFECT_DANGEROUS, EFFECT_VERY_DANGEROUS, EFFECT_DANGEROUS_AURA
from core.terrain_effect_system import TerrainEffectSystem
from core.los_manager import LineOfSightManager
from ecs.components.position import PositionComponent
from ecs.components.character_ref import CharacterRefComponent
from entities.character import Character
from utils.condition_utils import NIGHT_VISION_PARTIAL, NIGHT_VISION_TOTAL

class TerrainEffectsTest(unittest.TestCase):
    def setUp(self):
        self.gs = GameState()
        self.eb = EventBus(); self.gs.set_event_bus(self.eb)
        self.terrain = Terrain(10,10, game_state=self.gs); self.gs.set_terrain(self.terrain)
        self.events = []
        self.current_events = []
        self.eb.subscribe(EVT_TERRAIN_EFFECT_TRIGGER, lambda **kw: self.events.append(kw))
        self.eb.subscribe(EVT_TERRAIN_CURRENT_MOVED, lambda **kw: self.current_events.append(kw))
        self.tes = TerrainEffectSystem(self.gs, self.terrain, self.eb)

    # Helper to add simple entity
    def add_entity(self, eid:str, x:int, y:int, w:int=1, h:int=1, states=None):
        c = Character(); c.traits={'Attributes':{'Physical':{'Strength':1,'Dexterity':1,'Stamina':1}},'Abilities':{'Talents':{'Athletics':1}}}
        if states:
            c.states = set(states)
        pos = PositionComponent(x,y,w,h)
        ref = CharacterRefComponent(c)
        self.gs.add_entity(eid, {'position':pos,'character_ref':ref})
        self.terrain.add_entity(eid,x,y)
        return pos

    def test_dangerous_tile_triggers_event(self):
        self.terrain.add_dangerous([(2,2)], difficulty=5, damage=2, aggravated=True)
        self.add_entity('e',1,2)
        # Move entity into dangerous tile
        moved = self.terrain.move_entity('e',2,2)
        self.assertTrue(moved)
        # Expect one event
        self.assertEqual(len(self.events),1)
        evt = self.events[0]
        self.assertEqual(evt.get('effect'), EFFECT_DANGEROUS)
        self.assertEqual(evt.get('difficulty'),5)
        self.assertEqual(evt.get('damage'),2)
        self.assertTrue(evt.get('aggravated'))

    def test_very_dangerous_tile_auto_fail(self):
        self.terrain.add_very_dangerous((3,3), radius=0, difficulty=7, damage=3, aggravated=False)
        self.add_entity('v',2,3)
        self.terrain.move_entity('v',3,3)
        # One very dangerous event (no aura due to radius 0)
        self.assertEqual(len(self.events),1)
        evt = self.events[0]
        self.assertEqual(evt.get('effect'), EFFECT_VERY_DANGEROUS)
        self.assertTrue(evt.get('auto_fail'))
        self.assertEqual(evt.get('difficulty'),7)
        self.assertEqual(evt.get('damage'),3)

    def test_large_entity_multiple_dangerous_tiles_single_event(self):
        # Two adjacent dangerous tiles
        self.terrain.add_dangerous([(0,0),(1,0)], difficulty=4, damage=1)
        self.add_entity('big',0,1,w=2,h=1)  # start below, width 2
        # Move up to cover both tiles simultaneously
        self.terrain.move_entity('big',0,0)
        # Only one dangerous event should trigger
        dangerous_events = [e for e in self.events if e.get('effect')==EFFECT_DANGEROUS]
        self.assertEqual(len(dangerous_events),1)

    def test_gradient_aura_movement_cost_scaling(self):
        center=(5,5); radius=3
        self.terrain.add_very_dangerous(center, radius=radius, gradient=True)  # adds aura with gradient flag
        # Distances 1,2,3 from center along x axis
        costs = {d: self.terrain.get_movement_cost(center[0]+d, center[1]) for d in (1,2,3)}
        # Expected costs: dist1->6, dist2->5, dist3->4
        self.assertEqual(costs[1],6)
        self.assertEqual(costs[2],5)
        self.assertEqual(costs[3],4)

    def test_current_moves_entity_and_publishes_event(self):
        self.terrain.add_current([(1,1)], dx=1, dy=0, magnitude=2)
        self.add_entity('c',1,1)
        # Fire round start
        self.eb.publish('round_start', round_number=1)
        # Expect movement event for current
        self.assertEqual(len(self.current_events),1)
        evt = self.current_events[0]
        self.assertEqual(evt.get('entity_id'),'c')
        self.assertEqual(evt.get('dx'),1)
        self.assertEqual(evt.get('magnitude'),2)
        self.assertEqual(evt.get('old_position'),(1,1))
        self.assertEqual(evt.get('new_position'),(3,1))
        # Position component updated
        self.assertEqual(self.gs.get_entity('c')['position'].x,3)

    def test_darkness_blocks_and_night_vision_allows(self):
        # Two entities in line
        self.add_entity('att',0,0)
        self.add_entity('def',5,0)
        los = LineOfSightManager(self.gs, self.terrain, self.eb)
        # Baseline: visible (no darkness)
        self.assertTrue(los.can_see('att','def'))
        # Add total darkness at defender
        self.terrain.add_dark_total([(5,0)])
        # Without night vision: blocked
        self.assertFalse(los.can_see('att','def'))
        # Grant total night vision to attacker
        self.gs.get_entity('att')['character_ref'].character.states = {NIGHT_VISION_TOTAL}
        # Should now see
        self.assertTrue(los.can_see('att','def'))

    def test_dark_low_attack_modifier(self):
        self.add_entity('att',0,0)
        self.add_entity('def',4,0)
        los = LineOfSightManager(self.gs, self.terrain, self.eb)
        self.terrain.add_dark_low([(4,0)])
        self.assertEqual(los.get_darkness_attack_modifier('att','def'), -1)
        # Partial night vision removes penalty
        self.gs.get_entity('att')['character_ref'].character.states = {NIGHT_VISION_PARTIAL}
        self.assertEqual(los.get_darkness_attack_modifier('att','def'), 0)

    def test_path_avoids_very_dangerous_high_cost(self):
        # Layout: start (0,1) end (4,1) very dangerous at (2,1)
        self.terrain.add_very_dangerous((2,1), radius=0)
        self.terrain.precompute_paths()
        start=(0,1); end=(4,1)
        path = self.terrain.path_cache.get((start,end))
        self.assertIsNotNone(path)
        # Path should not include (2,1)
        self.assertNotIn((2,1), path)

if __name__ == '__main__':
    unittest.main()

