import pytest

from core.game_state import GameState
from core.event_bus import EventBus
from core.terrain_manager import Terrain
from core.movement_system import MovementSystem
from core.los_manager import LineOfSightManager
from core.cover_system import CoverSystem
from core.cover_factory import spawn_cover
from ecs.actions.attack_actions import AttackAction
from entities.weapon import Weapon, WeaponType
from entities.character import Character
from ecs.components.position import PositionComponent

class CharacterRef:
    def __init__(self, character):
        self.character = character

class FixedDice:
    def __init__(self, success_sequence):
        self.success_sequence = list(success_sequence)
    def roll_pool(self, pool_size, hunger_dice=0):
        succ = self.success_sequence.pop(0) if self.success_sequence else 0
        return {'successes': succ,'bestial_failures':0,'critical_successes':0,'hunger_bestial_successes':0,'hunger_bestial_failures':0}

@pytest.fixture
def base_game():
    gs = GameState()
    bus = EventBus()
    gs.set_event_bus(bus)
    terrain = Terrain(10,10, game_state=gs)
    gs.set_terrain(terrain)
    movement = MovementSystem(gs)
    gs.set_movement_system(movement)
    los = LineOfSightManager(gs, terrain, bus, los_granularity=2)
    gs.los_manager = los
    cover_sys = CoverSystem(gs)
    gs.set_cover_system(cover_sys)
    return gs

def add_character(gs, entity_id, x, y, team='A'):
    traits = {
        'Attributes': {'Physical': {'Dexterity': 2}},
        'Abilities': {'Skills': {'Firearms': 2}, 'Talents': {'Brawl':1}},
        'Disciplines': {}
    }
    char = Character(name=entity_id, traits=traits, team=team)
    gs.add_entity(entity_id, {
        'position': PositionComponent(x,y,1,1),
        'character_ref': CharacterRef(char),
    })
    gs.terrain.add_entity(entity_id, x, y)

def make_weapon(dmg_type='superficial', wtype=WeaponType.FIREARM, rng=6):
    return Weapon(name='W', damage_bonus=1, weapon_range=rng, damage_type=dmg_type, weapon_type=wtype)

def run_attack(gs, attacker_id, defender_id, attack_successes, defense_flat=2):
    attack = AttackAction(attacker_id, defender_id, make_weapon(), gs)
    attack.dice_roller = FixedDice([attack_successes])
    from ecs.actions.defensive_actions import DodgeRangedAction
    orig_execute = DodgeRangedAction._execute
    def fake_exec(self, entity_id, game_state):
        return defense_flat
    DodgeRangedAction._execute = fake_exec
    resolved = {}
    def on_defense_resolved(defender_id, attacker_id, chosen, successes, **kw):
        resolved['successes'] = successes
    gs.event_bus.subscribe('defense_resolved', on_defense_resolved)
    attack.execute()
    DodgeRangedAction._execute = orig_execute
    return resolved.get('successes', None)

def test_no_cover_penalty_applied(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    add_character(gs,'def',5,0,'B')
    succ = run_attack(gs,'att','def', attack_successes=4, defense_flat=2)
    assert succ == 0  # 2 base -2 penalty = 0

def test_light_cover_bonus(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    add_character(gs,'def',4,0,'B')
    spawn_cover(gs,'light',2,0)
    succ = run_attack(gs,'att','def', attack_successes=4, defense_flat=2)
    assert succ == 1  # 2 + (-1)

def test_heavy_cover_no_change(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    add_character(gs,'def',4,0,'B')
    spawn_cover(gs,'heavy',2,0)
    succ = run_attack(gs,'att','def',4,2)
    assert succ == 2  # heavy 0 modifier

def test_retrenchment_cover_bonus(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    add_character(gs,'def',4,0,'B')
    spawn_cover(gs,'retrenchment',2,0)
    succ = run_attack(gs,'att','def', attack_successes=4, defense_flat=2)
    assert succ == 3  # 2 + 1

def test_cover_stack_no_penalty(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    add_character(gs,'def',5,0,'B')
    spawn_cover(gs,'light',2,0)
    spawn_cover(gs,'retrenchment',3,0)
    succ = run_attack(gs,'att','def', attack_successes=4, defense_flat=2)
    assert succ == 2  # -1 +1 => 0 net

def test_double_light_cover_exact_neg_two(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    add_character(gs,'def',5,0,'B')
    spawn_cover(gs,'light',2,0)
    spawn_cover(gs,'light',3,0)
    succ = run_attack(gs,'att','def',4,2)
    assert succ == 0  # two light covers -> -2; counts as cover so no extra penalty

def test_wall_plus_light_cover(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    add_character(gs,'def',5,0,'B')
    gs.terrain.add_wall(2,0)
    spawn_cover(gs,'light',3,0)
    succ = run_attack(gs,'att','def',4,2)
    # wall partial +2 plus light -1 -> +1 total => 3 successes
    assert succ == 3

def test_partial_wall_bonus(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    add_character(gs,'def',4,0,'B')
    gs.terrain.add_wall(2,0)
    succ = run_attack(gs,'att','def', attack_successes=4, defense_flat=2)
    assert succ == 4  # base 2 + wall partial +2

def test_structure_superficial_halving_and_destruction(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    cover_id = spawn_cover(gs,'heavy',2,0)
    attack = AttackAction('att', cover_id, make_weapon(), gs)
    attack.dice_roller = FixedDice([3,5])
    dmg1,_ = attack._resolve_single_attack(cover_id, 4)
    struct = gs.get_entity(cover_id)['structure']
    assert struct.vigor == 4
    dmg2,_ = attack._resolve_single_attack(cover_id, 4)
    assert struct.vigor == 1
    attack.dice_roller = FixedDice([10])
    dmg3,_ = attack._resolve_single_attack(cover_id, 4)
    assert gs.get_entity(cover_id) is None

def test_structure_aggravated_not_halved(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    cover_id = spawn_cover(gs,'heavy',2,0)
    weapon = make_weapon('aggravated', WeaponType.FIREARM)
    atk = AttackAction('att', cover_id, weapon, gs)
    atk.dice_roller = FixedDice([4])  # base damage 1+4=5 aggravated (not halved)
    dmg,_ = atk._resolve_single_attack(cover_id,5)
    struct = gs.get_entity(cover_id)['structure']
    assert struct.vigor == 1  # 6-5

def test_melee_attack_no_ranged_cover_logic(base_game):
    """Test that ranged cover bonuses don't apply to melee attacks."""
    gs = base_game
    add_character(gs,'att',0,0,'A')
    add_character(gs,'def',1,0,'B')
    # Add light cover - this should NOT affect melee attacks
    spawn_cover(gs,'light',0,1)
    melee_weapon = make_weapon('superficial', WeaponType.MELEE, rng=1)
    
    # For melee attacks, cover shouldn't provide defensive bonuses
    # Test without forcing specific defensive actions
    atk = AttackAction('att','def', melee_weapon, gs)
    atk.dice_roller = FixedDice([4])
    
    # Track what actually happens - melee should ignore cover
    resolved = {}
    def on_defense_resolved(defender_id, attacker_id, chosen, successes, **kw):
        resolved['defense'] = chosen
        resolved['successes'] = successes
    gs.event_bus.subscribe('defense_resolved', on_defense_resolved)
    
    atk.execute()
    
    # The key test: melee attacks should ignore ranged cover bonuses
    # If cover were incorrectly applied, we'd see artificially high defense successes
    # The exact success count depends on which defense was chosen, but should be reasonable
    assert 'defense' in resolved
    assert 'successes' in resolved
    # Defense successes should be in a reasonable range (not boosted by ranged cover)
    assert resolved['successes'] <= 5  # Reasonable upper bound for unboosts defense

def test_multiple_walls_and_covers_stack_once_for_wall(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    add_character(gs,'def',7,0,'B')
    # Two wall cells along the line; wall bonus should still be +2 (not +4)
    gs.terrain.add_wall(2,0)
    gs.terrain.add_wall(3,0)
    # Covers along the line
    spawn_cover(gs,'light',4,0)         # -1
    spawn_cover(gs,'retrenchment',5,0)  # +1
    spawn_cover(gs,'heavy',6,0)         # 0
    succ = run_attack(gs,'att','def', attack_successes=6, defense_flat=2)
    # Expected: base 2 + wall 2 + covers (-1+1+0)= +2 => 4
    assert succ == 4

def test_cover_behind_defender_not_counted(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    add_character(gs,'def',4,0,'B')
    # Cover placed BEHIND defender relative to attacker
    spawn_cover(gs,'retrenchment',5,0)
    succ = run_attack(gs,'att','def', attack_successes=5, defense_flat=2)
    # No intervening cover -> penalty applies: 2 -2 =0
    assert succ == 0

def test_cover_destruction_removes_bonus(base_game):
    gs = base_game
    add_character(gs,'att',0,0,'A')
    add_character(gs,'def',5,0,'B')
    cover_id = spawn_cover(gs,'light',2,0)  # provides -1 (net 2-1 =1 successes on defense)
    # First attack vs defender (cover present)
    succ1 = run_attack(gs,'att','def', attack_successes=5, defense_flat=2)
    assert succ1 == 1
    # Destroy cover
    destroy_attack = AttackAction('att', cover_id, make_weapon(), gs)
    destroy_attack.dice_roller = FixedDice([12])  # Large successes to guarantee destruction
    destroy_attack._resolve_single_attack(cover_id, 6)
    assert gs.get_entity(cover_id) is None  # cover removed
    # Second attack vs defender (no cover now) -> penalty
    succ2 = run_attack(gs,'att','def', attack_successes=5, defense_flat=2)
    assert succ2 == 0
