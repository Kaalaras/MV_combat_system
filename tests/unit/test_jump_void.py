import unittest
from core.game_state import GameState
from core.event_bus import EventBus
from core.terrain_manager import Terrain
from core.movement_system import MovementSystem
from ecs.actions.movement_actions import JumpAction
from ecs.components.position import PositionComponent
from ecs.components.character_ref import CharacterRefComponent
from entities.character import Character

class TestJumpVoidLethal(unittest.TestCase):
    def setUp(self):
        self.gs = GameState()
        self.eb = EventBus(); self.gs.set_event_bus(self.eb)
        self.terrain = Terrain(5,5, game_state=self.gs); self.gs.set_terrain(self.terrain)
        self.move_sys = MovementSystem(self.gs); self.gs.movement = self.move_sys
        self.events = []
        self.eb.subscribe('entity_died', lambda **kw: self.events.append(kw))
    def _add_entity(self, eid:str, x:int, y:int, strength:int=2, athletics:int=2):
        traits={'Attributes':{'Physical':{'Strength':strength,'Dexterity':1,'Stamina':1}},'Abilities':{'Talents':{'Athletics':athletics}}}
        c=Character(); c.traits=traits; c.base_traits=traits
        pos=PositionComponent(x,y,1,1)
        ref=CharacterRefComponent(c)
        self.gs.add_entity(eid, {'position':pos,'character_ref':ref})
        self.terrain.add_entity(eid,x,y)
        return eid
    def test_jump_into_void_disallowed(self):
        # Suicide by void jump no longer permitted: availability + execution must both fail.
        eid = self._add_entity('jumper',0,0,strength=1,athletics=1)  # range 2 (1+1)
        self.terrain.add_impassable_void([(0,1)])
        jump = JumpAction(self.move_sys)
        # Cannot target void tile directly
        self.assertFalse(jump.is_available(eid,self.gs,target_tile=(0,1)), 'Jump onto void tile should be unavailable now')
        ok = jump.execute(eid,self.gs,target_tile=(0,1))
        self.assertFalse(ok, 'Execution should also fail for void destination')
        char = self.gs.get_entity(eid)['character_ref'].character
        self.assertFalse(getattr(char,'is_dead', False), 'Character should remain alive (no suicide)')
        self.assertFalse(any(e.get('entity_id')==eid and e.get('cause')=='void' for e in self.events), 'No void death event expected')

if __name__ == '__main__':
    unittest.main()
