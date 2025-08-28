import math, os, sys, unittest
# Flexible imports whether run from repo root or inside package folder
try:
    from MV_combat_system.core.game_state import GameState  # type: ignore
    from MV_combat_system.core.event_bus import EventBus  # type: ignore
    from MV_combat_system.ecs.components.position import PositionComponent  # type: ignore
    from MV_combat_system.ecs.components.facing import FacingComponent  # type: ignore
except ModuleNotFoundError:
    try:
        from core.game_state import GameState  # type: ignore
        from core.event_bus import EventBus  # type: ignore
        from ecs.components.position import PositionComponent  # type: ignore
        from ecs.components.facing import FacingComponent  # type: ignore
    except ModuleNotFoundError:
        ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'MV_combat_system'))
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from core.game_state import GameState  # type: ignore
        from core.event_bus import EventBus  # type: ignore
        from ecs.components.position import PositionComponent  # type: ignore
        from ecs.components.facing import FacingComponent  # type: ignore

class MockCharacter:
    def __init__(self):
        self.orientation = 'up'
    def set_orientation(self, o: str):
        self.orientation = o
class MockCharRef:
    def __init__(self, character):
        self.character = character

def approx(a,b,eps=1e-6):
    return all(abs(x-y)<=eps for x,y in zip(a,b))

def make_entity(gs, eid, x,y, dir_vec=(0.0,1.0), mode='Auto'):
    gs.add_entity(eid, {
        'position': PositionComponent(x=x,y=y,width=1,height=1),
        'facing': FacingComponent(direction=dir_vec, mode=mode),
        'character_ref': MockCharRef(MockCharacter())
    })

class FacingSystemTests(unittest.TestCase):
    def _fs(self, gs, eb):
        try:
            from MV_combat_system.ecs.systems.facing_system import FacingSystem  # type: ignore
        except ModuleNotFoundError:
            from ecs.systems.facing_system import FacingSystem  # type: ignore
        return FacingSystem(gs, eb)

    def test_face_entity_target(self):
        gs=GameState(); eb=EventBus(); gs.set_event_bus(eb)
        make_entity(gs,'A',0,0,(1,0))
        make_entity(gs,'B',0,4,(0,-1))
        self._fs(gs, eb)
        eb.publish('action_requested', entity_id='A', action_name='Attack', target_id='B')
        self.assertTrue(approx(gs.get_entity('A')['facing'].direction, (0.0,1.0)))

    def test_face_move_tile(self):
        gs=GameState(); eb=EventBus(); gs.set_event_bus(eb)
        make_entity(gs,'A',2,2,(0,1))
        self._fs(gs, eb)
        eb.publish('action_requested', entity_id='A', action_name='Standard Move', target_tile=(6,2))
        self.assertTrue(approx(gs.get_entity('A')['facing'].direction,(1.0,0.0)))

    def test_fixed_mode_skips(self):
        gs=GameState(); eb=EventBus(); gs.set_event_bus(eb)
        make_entity(gs,'A',1,1,(0,1), mode='Fixed')
        fs=self._fs(gs, eb)
        eb.publish('action_requested', entity_id='A', action_name='Standard Move', target_tile=(5,1))
        self.assertTrue(approx(gs.get_entity('A')['facing'].direction,(0.0,1.0)))
        fs.set_entity_facing_direction('A',(1,0))
        self.assertTrue(approx(gs.get_entity('A')['facing'].direction,(1.0,0.0)))

    def test_diagonal_normalized(self):
        gs=GameState(); eb=EventBus(); gs.set_event_bus(eb)
        make_entity(gs,'A',0,0,(1,0))
        self._fs(gs, eb)
        eb.publish('action_requested', entity_id='A', action_name='Move', target_tile=(3,3))
        dx,dy = gs.get_entity('A')['facing'].direction
        self.assertTrue(math.isclose(dx,dy,rel_tol=1e-5))
        self.assertTrue(math.isclose(dx*dx+dy*dy,1.0,rel_tol=1e-6))

    def test_same_tile_no_change(self):
        gs=GameState(); eb=EventBus(); gs.set_event_bus(eb)
        make_entity(gs,'A',2,2,(0,1))
        self._fs(gs, eb)
        eb.publish('action_requested', entity_id='A', action_name='Move', target_tile=(2,2))
        self.assertTrue(approx(gs.get_entity('A')['facing'].direction,(0.0,1.0)))

if __name__ == '__main__':  # pragma: no cover
    unittest.main()
