import os, sys, unittest
try:
    from MV_combat_system.core.game_state import GameState  # type: ignore
    from MV_combat_system.core.event_bus import EventBus  # type: ignore
    from MV_combat_system.ecs.components.position import PositionComponent  # type: ignore
    from MV_combat_system.ecs.components.facing import FacingComponent  # type: ignore
    from MV_combat_system.ecs.components.character_ref import CharacterRefComponent  # type: ignore
except ModuleNotFoundError:
    from core.game_state import GameState  # type: ignore
    from core.event_bus import EventBus  # type: ignore
    from ecs.components.position import PositionComponent  # type: ignore
    from ecs.components.facing import FacingComponent  # type: ignore
    from ecs.components.character_ref import CharacterRefComponent  # type: ignore

class DummyChar:
    def __init__(self, orientation='up'):
        self.orientation = orientation
        self.team = 'A'
        self.is_dead = False
    def set_orientation(self, o):
        self.orientation = o

class CharRef:
    def __init__(self, c):
        self.character = c

class OrientationMirrorTests(unittest.TestCase):
    def _facing_system(self, gs, eb):
        try:
            from MV_combat_system.ecs.systems.facing_system import FacingSystem  # type: ignore
        except ModuleNotFoundError:
            from ecs.systems.facing_system import FacingSystem  # type: ignore
        fs = FacingSystem(gs, eb)
        gs.facing_system = fs
        return fs

    def test_orientation_mirrors_after_attack(self):
        gs = GameState(); eb = EventBus(); gs.set_event_bus(eb)
        attacker_char = DummyChar(orientation='right')
        target_char = DummyChar(orientation='down')
        gs.add_entity('att', {
            'position': PositionComponent(x=0,y=0,width=1,height=1),
            'facing': FacingComponent(direction=(1.0,0.0)),
            'character_ref': CharRef(attacker_char)
        })
        gs.add_entity('tgt', {
            'position': PositionComponent(x=0,y=5,width=1,height=1),
            'facing': FacingComponent(direction=(0.0,-1.0)),
            'character_ref': CharRef(target_char)
        })
        self._facing_system(gs, eb)
        eb.publish('action_requested', entity_id='att', action_name='Registered Attack', target_id='tgt')
        self.assertEqual(attacker_char.orientation, 'up')

    def test_fixed_mode_does_not_change_orientation(self):
        gs = GameState(); eb = EventBus(); gs.set_event_bus(eb)
        char = DummyChar(orientation='up')
        
        # Use new ECS system 
        entity_id = gs.ecs_manager.create_entity(
            PositionComponent(x=1,y=1,width=1,height=1),
            FacingComponent(direction=(0.0,1.0), mode='Fixed'),
            CharacterRefComponent(char)
        )
        
        self._facing_system(gs, eb)
        eb.publish('action_requested', entity_id=str(entity_id), action_name='Standard Move', target_tile=(5,1))
        self.assertEqual(char.orientation, 'up')
        
        # Ensure still exactly facing up using new ECS system
        facing_comp = gs.ecs_manager.get_component(entity_id, FacingComponent)
        self.assertAlmostEqual(facing_comp.direction[0], 0.0)
        self.assertAlmostEqual(facing_comp.direction[1], 1.0)

if __name__ == '__main__':  # pragma: no cover
    unittest.main()

