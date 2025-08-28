import math, os, sys
# Flexible import handling whether run from project root or package dir
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
        ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
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


def _approx_tuple(a, b, eps=1e-6):
    return all(abs(x-y) <= eps for x, y in zip(a, b))


def test_facing_updates_on_action_target_entity():
    gs = GameState()
    eb = EventBus()
    gs.set_event_bus(eb)

    # Add two entities: attacker at (0,0), target at (0,5)
    attacker_id = 'E1'
    target_id = 'E2'
    attacker_facing = FacingComponent(direction=(1.0, 0.0))
    target_facing = FacingComponent(direction=(0.0, -1.0))
    gs.add_entity(attacker_id, {
        'position': PositionComponent(x=0, y=0, width=1, height=1),
        'facing': attacker_facing,
        'character_ref': MockCharRef(MockCharacter())
    })
    gs.add_entity(target_id, {
        'position': PositionComponent(x=0, y=5, width=1, height=1),
        'facing': target_facing,
        'character_ref': MockCharRef(MockCharacter())
    })

    # Initialize facing system (subscribe to events)
    from MV_combat_system.ecs.systems.facing_system import FacingSystem
    fs = FacingSystem(gs, eb)
    gs.facing_system = fs

    # Publish an attack action referencing the target entity
    eb.publish('action_requested', entity_id=attacker_id, action_name='Registered Attack', target_id=target_id)

    # Attacker should now face upward (0,1)
    new_dir = attacker_facing.direction
    assert _approx_tuple(new_dir, (0.0, 1.0)), f"Expected (0,1) got {new_dir}"
    # Character orientation mirrored
    assert gs.get_entity(attacker_id)['character_ref'].character.orientation in ('up', 'right', 'left', 'down')


def test_facing_updates_on_movement_target_tile():
    gs = GameState()
    eb = EventBus()
    gs.set_event_bus(eb)

    ent_id = 'E1'
    facing = FacingComponent(direction=(0.0, 1.0))
    gs.add_entity(ent_id, {
        'position': PositionComponent(x=2, y=2, width=1, height=1),
        'facing': facing,
        'character_ref': MockCharRef(MockCharacter())
    })

    from MV_combat_system.ecs.systems.facing_system import FacingSystem
    fs = FacingSystem(gs, eb)

    # Move action to tile (5,2) should face right
    eb.publish('action_requested', entity_id=ent_id, action_name='Standard Move', target_tile=(5,2))

    assert _approx_tuple(facing.direction, (1.0, 0.0)), f"Expected (1,0) got {facing.direction}"


def test_facing_fixed_mode_skips_auto_update():
    gs = GameState()
    eb = EventBus()
    gs.set_event_bus(eb)

    ent_id = 'E1'
    # Fixed mode - should not update
    facing = FacingComponent(direction=(0.0, 1.0), mode='Fixed')
    gs.add_entity(ent_id, {
        'position': PositionComponent(x=1, y=1, width=1, height=1),
        'facing': facing,
        'character_ref': MockCharRef(MockCharacter())
    })

    from MV_combat_system.ecs.systems.facing_system import FacingSystem
    fs = FacingSystem(gs, eb)

    # Attempt to move (would normally rotate to (1,0))
    eb.publish('action_requested', entity_id=ent_id, action_name='Standard Move', target_tile=(5,1))

    # Direction should remain unchanged because mode is Fixed
    assert _approx_tuple(facing.direction, (0.0, 1.0)), f"Fixed mode changed direction to {facing.direction}"

    # Manual override still works
    fs.set_entity_facing_direction(ent_id, (1.0, 0.0))
    assert _approx_tuple(facing.direction, (1.0, 0.0)), "Manual set did not update facing in Fixed mode"


def test_facing_diagonal_direction_normalized():
    gs = GameState(); eb = EventBus(); gs.set_event_bus(eb)
    ent_id = 'E1'
    facing = FacingComponent(direction=(1.0, 0.0))
    gs.add_entity(ent_id, {'position': PositionComponent(x=0, y=0, width=1, height=1), 'facing': facing, 'character_ref': MockCharRef(MockCharacter())})
    from MV_combat_system.ecs.systems.facing_system import FacingSystem
    fs = FacingSystem(gs, eb)
    eb.publish('action_requested', entity_id=ent_id, action_name='Standard Move', target_tile=(3,3))
    dx, dy = facing.direction
    # Expect roughly normalized (0.7071, 0.7071)
    assert math.isclose(dx, dy, rel_tol=1e-5)
    assert math.isclose((dx*dx+dy*dy), 1.0, rel_tol=1e-6)


def test_facing_no_change_same_tile():
    gs = GameState(); eb = EventBus(); gs.set_event_bus(eb)
    ent_id = 'E1'
    facing = FacingComponent(direction=(0.0, 1.0))
    gs.add_entity(ent_id, {'position': PositionComponent(x=2, y=2, width=1, height=1), 'facing': facing, 'character_ref': MockCharRef(MockCharacter())})
    from MV_combat_system.ecs.systems.facing_system import FacingSystem
    fs = FacingSystem(gs, eb)
    eb.publish('action_requested', entity_id=ent_id, action_name='Standard Move', target_tile=(2,2))
    assert _approx_tuple(facing.direction, (0.0, 1.0)), "Direction changed despite same-tile target"
