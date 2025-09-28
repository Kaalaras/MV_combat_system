import unittest
from core.game_state import GameState
from core.event_bus import EventBus
from core.terrain_manager import (
    Terrain,
    EFFECT_DANGEROUS,
    EFFECT_DIFFICULT,
    EFFECT_VERY_DANGEROUS,
    EFFECT_DANGEROUS_AURA,
    EFFECT_IMPASSABLE_VOID,
    EFFECT_IMPASSABLE_SOLID,
    EVT_TERRAIN_EFFECT_TRIGGER,
    EVT_TERRAIN_CURRENT_MOVED,
)
from core.terrain_effect_system import TerrainEffectSystem
from ecs.components.position import PositionComponent
from ecs.components.character_ref import CharacterRefComponent
from entities.character import Character
from ecs.actions.movement_actions import JumpAction
from core.movement_system import MovementSystem

class TerrainEffectsMoreTest(unittest.TestCase):
    def setUp(self):
        self.gs = GameState()
        self.eb = EventBus(); self.gs.set_event_bus(self.eb)
        self.terrain = Terrain(12,12, game_state=self.gs); self.gs.set_terrain(self.terrain)
        self.tes = TerrainEffectSystem(self.gs, self.terrain, self.eb)
        self.events = []
        self.current_events = []
        self.eb.subscribe(EVT_TERRAIN_EFFECT_TRIGGER, lambda **kw: self.events.append(kw))
        self.eb.subscribe(EVT_TERRAIN_CURRENT_MOVED, lambda **kw: self.current_events.append(kw))
        self.move_sys = MovementSystem(self.gs); self.gs.movement = self.move_sys

    def add_entity(self, eid, x,y, w=1,h=1, strength=2, athletics=2):
        traits={'Attributes':{'Physical':{'Strength':strength,'Dexterity':1,'Stamina':1}},'Abilities':{'Talents':{'Athletics':athletics}}}
        c=Character(); c.traits=traits; c.base_traits=traits
        pos=PositionComponent(x,y,w,h)
        ref=CharacterRefComponent(c)
        self.gs.add_entity(eid, {'position':pos,'character_ref':ref})
        self.terrain.add_entity(eid,x,y)
        return eid

    # 1. Overlapping effects cost precedence
    def test_cost_precedence_dangerous_over_difficult(self):
        tile=(3,3)
        self.terrain.add_difficult([tile])  # cost at least 2
        self.assertEqual(self.terrain.get_movement_cost(*tile),2)
        self.terrain.add_dangerous([tile])  # dangerous should raise to 4
        self.assertEqual(self.terrain.get_movement_cost(*tile),4)

    def test_cost_precedence_after_removal(self):
        tile=(4,4)
        self.terrain.add_difficult([tile])
        self.terrain.add_dangerous([tile])
        self.assertEqual(self.terrain.get_movement_cost(*tile),4)
        prev_version = self.gs.terrain_version
        # Remove only dangerous
        self.terrain.remove_effect(lambda eff: eff.get('name')==EFFECT_DANGEROUS, positions=[tile])
        self.assertEqual(self.terrain.get_movement_cost(*tile),2)
        self.assertGreater(self.gs.terrain_version, prev_version)
        # Remove difficult
        prev_version = self.gs.terrain_version
        self.terrain.remove_effect(lambda eff: eff.get('name')==EFFECT_DIFFICULT, positions=[tile])
        self.assertEqual(self.terrain.get_movement_cost(*tile),1)
        self.assertGreater(self.gs.terrain_version, prev_version)

    # 2. Current blocked by wall / entity
    def test_current_partial_blocked_by_wall(self):
        self.terrain.add_current([(1,1)], dx=1, dy=0, magnitude=3)
        # Wall two steps ahead (after one move possible)
        self.terrain.add_wall(3,1)
        self.add_entity('c1',1,1)
        self.eb.publish('round_start', round_number=1)
        self.assertEqual(len(self.current_events),1)
        evt=self.current_events[0]
        # Only moved 1 step to (2,1)
        self.assertEqual(evt.get('magnitude'),1)
        self.assertEqual(evt.get('new_position'),(2,1))

    def test_current_partial_blocked_by_entity(self):
        self.terrain.add_current([(1,2)], dx=1, dy=0, magnitude=3)
        self.add_entity('c2',1,2)
        # Blocking entity ahead at (3,2)
        self.add_entity('block',3,2)
        self.eb.publish('round_start', round_number=2)
        self.assertEqual(len(self.current_events),1)
        evt=self.current_events[0]
        self.assertEqual(evt.get('magnitude'),1)
        self.assertEqual(evt.get('new_position'),(2,2))

    # 3. Gradient aura large radius cap (cost never above 6)
    def test_gradient_aura_large_radius_cap(self):
        # Center moved near left edge so radius fully fits in 12x12 grid
        center=(1,6); radius=10
        self.terrain.add_very_dangerous(center, radius=radius, gradient=True)
        self.assertEqual(self.terrain.get_movement_cost(*center),12)
        for dist in (1,2,3,4,5):
            tile=(center[0]+dist, center[1])
            self.assertEqual(self.terrain.get_movement_cost(*tile),6, f"Cost at dist {dist} not capped to 6")
        # Near edge dist 9 => cost 5
        self.assertEqual(self.terrain.get_movement_cost(center[0]+9, center[1]),5)
        # Edge dist 10 => cost 4
        self.assertEqual(self.terrain.get_movement_cost(center[0]+10, center[1]),4)

    # 4. Hazard removal stops re-trigger
    def test_hazard_removal_stops_trigger(self):
        self.add_entity('h',1,2)
        self.terrain.add_dangerous([(2,2)], difficulty=5, damage=1)
        # Enter once -> trigger
        self.terrain.move_entity('h',2,2)
        self.assertEqual(len(self.events),1)
        self.events.clear()
        # Remove hazard
        self.terrain.remove_effect(lambda eff: eff.get('name')==EFFECT_DANGEROUS, positions=[(2,2)])
        # Move off and back
        self.terrain.move_entity('h',1,2)
        self.terrain.move_entity('h',2,2)
        self.assertEqual(len(self.events),0, 'Hazard should not trigger after removal')

    # 5. Jump over void allowed; solid blocks mid-path
    def test_jump_over_single_void_succeeds(self):
        jumper=self.add_entity('jumper',0,0,strength=1,athletics=1)  # range 2
        self.terrain.add_impassable_void([(1,0)])  # mid tile void
        jump=JumpAction(self.move_sys)
        self.assertTrue(jump.is_available(jumper,self.gs,target_tile=(2,0)))
        self.assertTrue(jump.execute(jumper,self.gs,target_tile=(2,0)))
        self.assertEqual(self.terrain.get_entity_position(jumper),(2,0))

    def test_jump_over_multiple_void_succeeds(self):
        jumper=self.add_entity('jumper2',0,0,strength=2,athletics=2)  # range 4
        voids=[(1,0),(2,0),(3,0)]
        self.terrain.add_impassable_void(voids)
        jump=JumpAction(self.move_sys)
        # Destination beyond void chain
        self.assertTrue(jump.is_available(jumper,self.gs,target_tile=(4,0)))
        self.assertTrue(jump.execute(jumper,self.gs,target_tile=(4,0)))
        self.assertEqual(self.terrain.get_entity_position(jumper),(4,0))

    def test_jump_blocked_by_solid_midpoint(self):
        jumper=self.add_entity('jumper3',0,0,strength=1,athletics=1)  # range 2
        self.terrain.add_impassable_solid([(1,0)])
        jump=JumpAction(self.move_sys)
        # Attempt to jump over solid should fail (cannot clear first midpoint)
        self.assertFalse(jump.is_available(jumper,self.gs,target_tile=(2,0)))
        self.assertFalse(jump.execute(jumper,self.gs,target_tile=(2,0)))
        self.assertEqual(self.terrain.get_entity_position(jumper),(0,0))

if __name__ == '__main__':
    unittest.main()
