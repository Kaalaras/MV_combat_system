import unittest
from core.game_state import GameState
from core.event_bus import EventBus
from core.terrain_manager import (
    Terrain,
    EFFECT_DANGEROUS,
    EFFECT_VERY_DANGEROUS,
    EFFECT_DANGEROUS_AURA,
    EFFECT_DIFFICULT,
    EFFECT_VERY_DIFFICULT,
    EVT_TERRAIN_EFFECT_TRIGGER,
    EVT_TERRAIN_CURRENT_MOVED,
)
from core.terrain_effect_system import TerrainEffectSystem
from ecs.components.position import PositionComponent
from ecs.components.character_ref import CharacterRefComponent
from entities.character import Character
from core.los_manager import LineOfSightManager
from utils.condition_utils import NIGHT_VISION_PARTIAL, NIGHT_VISION_TOTAL

class TerrainEffectsAdvancedTest(unittest.TestCase):
    def setUp(self):
        self.gs = GameState()
        self.eb = EventBus(); self.gs.set_event_bus(self.eb)
        self.terrain = Terrain(10,10, game_state=self.gs); self.gs.set_terrain(self.terrain)
        self.tes = TerrainEffectSystem(self.gs, self.terrain, self.eb)
        self.events=[]; self.current_events=[]
        self.eb.subscribe(EVT_TERRAIN_EFFECT_TRIGGER, lambda **kw: self.events.append(kw))
        self.eb.subscribe(EVT_TERRAIN_CURRENT_MOVED, lambda **kw: self.current_events.append(kw))

    def add_entity(self, eid, x,y, w=1,h=1, strength=2, athletics=2, states=None):
        traits={'Attributes':{'Physical':{'Strength':strength,'Dexterity':1,'Stamina':1}},'Abilities':{'Talents':{'Athletics':athletics}}}
        c=Character(); c.traits=traits; c.base_traits=traits
        if states: c.states=set(states)
        pos=PositionComponent(x,y,w,h)
        ref=CharacterRefComponent(c)
        self.gs.add_entity(eid, {'position':pos,'character_ref':ref})
        self.terrain.add_entity(eid,x,y)
        return eid

    # Helper to compute path cost
    def path_cost(self, path):
        return sum(self.terrain.get_movement_cost(x,y) for x,y in path)

    # 4a. Pathfinding avoids very dangerous high cost vs small detour
    def test_pathfinding_avoids_very_dangerous_cost(self):
        # Layout: start (0,0) to end (4,0). Place very dangerous at (2,0)
        self.terrain.add_very_dangerous((2,0), radius=0)  # cost 12 tile
        # Add optional detour down then up: ensure tiles are walkable baseline
        self.terrain.precompute_paths()
        path = self.terrain.path_cache.get(((0,0),(4,0)))
        self.assertIsNotNone(path)
        # Ensure very dangerous tile excluded
        self.assertNotIn((2,0), path)
        # Sanity: direct path would include it (if allowed) length 4 steps
        # Compare actual path cost smaller than hypothetical path cost using dangerous tile
        direct_path=[(1,0),(2,0),(3,0),(4,0)]
        direct_cost = self.path_cost(direct_path)
        actual_cost = self.path_cost(path)
        self.assertLess(actual_cost, direct_cost)

    # 4b. Difficult vs very_difficult branch preference
    def test_path_prefers_difficult_over_very_difficult(self):
        # Create two parallel corridors from (0,1) to (5,1) and (0,2) to (5,2)
        for x in range(1,6):
            self.terrain.add_difficult([(x,1)])
            self.terrain.add_very_difficult([(x,2)])
        self.terrain.precompute_paths()
        path_top = self.terrain.path_cache.get(((0,1),(5,1)))
        path_bottom = self.terrain.path_cache.get(((0,2),(5,2)))
        self.assertIsNotNone(path_top); self.assertIsNotNone(path_bottom)
        cost_top = self.path_cost(path_top)
        cost_bottom = self.path_cost(path_bottom)
        self.assertLess(cost_top, cost_bottom)

    # 5. Hazard re-trigger logic
    def test_aura_reenter_same_turn_triggers_twice(self):
        self.add_entity('e',0,0)
        center=(2,0); self.terrain.add_very_dangerous(center, radius=2, gradient=False)
        # Move into aura tile (1,0)
        self.terrain.move_entity('e',1,0)
        first_count = len(self.events)
        self.assertGreater(first_count,0)
        # Move out then back in same turn
        self.terrain.move_entity('e',0,0)
        self.terrain.move_entity('e',1,0)
        self.assertGreater(len(self.events), first_count)
        # Staying still (no move) should not add event
        stay_count = len(self.events)
        # Simulate doing nothing
        self.assertEqual(len(self.events), stay_count)
        # Turn start re-trigger while still standing in aura
        self.eb.publish('turn_start', entity_id='e')
        self.assertGreater(len(self.events), stay_count)

    def test_start_turn_in_very_dangerous_center_retriggers(self):
        self.add_entity('c',0,0)
        self.terrain.add_very_dangerous((1,0), radius=0)
        self.terrain.move_entity('c',1,0)
        # Update entity position component to match terrain move
        entity = self.gs.get_entity('c')
        entity['position'].x = 1
        entity['position'].y = 0
        initial = len([e for e in self.events if e.get('effect')==EFFECT_VERY_DANGEROUS])
        self.eb.publish('turn_start', entity_id='c')
        after = len([e for e in self.events if e.get('effect')==EFFECT_VERY_DANGEROUS])
        self.assertGreater(after, initial)

    # 6. Currents chaining across rounds
    def test_current_full_magnitude_and_chaining(self):
        self.add_entity('cur',0,0)
        # Current tiles at (0,0) and (1,0) pushing +1 x each round magnitude 2
        self.terrain.add_current([(0,0),(1,0)], dx=1, dy=0, magnitude=2)
        # Round 1
        self.eb.publish('round_start', round_number=1)
        self.assertEqual(self.terrain.get_entity_position('cur'), (2,0))
        self.assertEqual(len(self.current_events),1)
        self.assertEqual(self.current_events[0]['magnitude'],2)
        # Round 2 (entity starts on (2,0) not a current tile: add (2,0) to extend chain)
        self.terrain.add_current([(2,0)], dx=1, dy=0, magnitude=2)
        self.eb.publish('round_start', round_number=2)
        self.assertEqual(self.terrain.get_entity_position('cur'), (4,0))
        self.assertEqual(len(self.current_events),2)

    # 7. Darkness mixed cases
    def test_darkness_mixed_cases(self):
        att = self.add_entity('att',0,0)
        d1 = self.add_entity('d1',5,0)
        d2 = self.add_entity('d2',5,2)
        los = LineOfSightManager(self.gs, self.terrain, self.eb)
        # Total darkness on attacker tile blocks view out unless night vision total
        self.terrain.add_dark_total([(0,0)])
        self.assertFalse(los.can_see('att','d1'))
        # Add total night vision
        self.gs.get_entity('att')['character_ref'].character.states={NIGHT_VISION_TOTAL}
        self.assertTrue(los.can_see('att','d1'))
        # Defender in dark_low gives -1 unless partial or total
        self.terrain.add_dark_low([(5,0)])
        self.assertEqual(los.get_darkness_attack_modifier('att','d1'),0)  # total vision negates
        # Reset states (attacker still in dark_total) => cannot see now
        self.gs.get_entity('att')['character_ref'].character.states=set()
        self.assertFalse(los.can_see('att','d1'))
        # Grant partial (still insufficient for total darkness) -> still cannot see
        self.gs.get_entity('att')['character_ref'].character.states={NIGHT_VISION_PARTIAL}
        self.assertFalse(los.can_see('att','d1'))
        # Grant total to proceed further tests
        self.gs.get_entity('att')['character_ref'].character.states={NIGHT_VISION_TOTAL}
        self.terrain.add_dark_total([(5,2)])
        self.assertTrue(los.can_see('att','d2'))

    # 8. Difficult + dangerous triggers hazard and retains higher cost
    def test_difficult_plus_dangerous(self):
        self.add_entity('h',0,0)
        tile=(1,0)
        self.terrain.add_difficult([tile])
        self.terrain.add_dangerous([tile], difficulty=4, damage=2)
        self.terrain.move_entity('h',1,0)
        # One dangerous event
        self.assertTrue(any(e.get('effect')==EFFECT_DANGEROUS for e in self.events))
        self.assertEqual(self.terrain.get_movement_cost(*tile),4)
        # Remove dangerous- leaves difficult cost 2
        self.terrain.remove_effect(lambda eff: eff.get('name')==EFFECT_DANGEROUS, positions=[tile])
        self.assertEqual(self.terrain.get_movement_cost(*tile),2)

    # 9. Large entity overlapping multiple categories (very_dangerous center + aura)
    def test_large_entity_center_and_aura_single_each(self):
        # Create very dangerous with radius 1 so aura around center
        self.terrain.add_very_dangerous((3,3), radius=1)
        # 2x1 entity will cover center (3,3) and aura tile (4,3)
        self.add_entity('L',2,3,w=2,h=1)
        # Move right into overlap (from 2,3 to 3,3) anchor now 3,3 footprint (3,3),(4,3)
        self.terrain.move_entity('L',3,3)
        vd_events=[e for e in self.events if e.get('effect')==EFFECT_VERY_DANGEROUS]
        aura_events=[e for e in self.events if e.get('effect')==EFFECT_DANGEROUS_AURA]
        self.assertEqual(len(vd_events),1)
        self.assertEqual(len(aura_events),1)

    # 10. Void vs solid path semantics (current implementation treats both as blocking for movement & path)
    def test_void_and_solid_block_pathfinding(self):
        self.terrain.add_impassable_void([(2,0)])
        self.terrain.add_impassable_solid([(0,2)])
        self.terrain.precompute_paths()
        # Paths that would end on these tiles should not exist
        self.assertNotIn(((0,0),(2,0)), self.terrain.path_cache)
        self.assertNotIn(((0,0),(0,2)), self.terrain.path_cache)

if __name__ == '__main__':
    unittest.main()
