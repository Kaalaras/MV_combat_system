import pytest
from core.game_state import GameState
from core.event_bus import EventBus
from core.terrain_manager import Terrain
from core.movement_system import MovementSystem
from core.los_manager import LineOfSightManager
from core.cover_system import CoverSystem
from core.cover_factory import spawn_cover
from ecs.systems.condition_system import ConditionSystem
from utils.condition_utils import INVISIBLE, SEE_INVISIBLE
from ecs.actions.attack_actions import AttackAction
from entities.weapon import Weapon, WeaponType
from entities.character import Character
from ecs.components.position import PositionComponent

class CharRef:
    def __init__(self, c): self.character=c

def make_char(name, dex=3, firearms=3):
    return Character(name=name, traits={
        'Attributes': {'Physical': {'Dexterity': dex}},
        'Abilities': {'Skills': {'Firearms': firearms}, 'Talents': {'Brawl': firearms}},
        'Disciplines': {}
    })

def make_weapon(rng=6, melee=False):
    if melee:
        return Weapon(name='M', damage_bonus=1, weapon_range=1, damage_type='superficial', weapon_type=WeaponType.MELEE)
    return Weapon(name='R', damage_bonus=1, weapon_range=rng, damage_type='superficial', weapon_type=WeaponType.FIREARM)

@pytest.fixture
def setup_env():
    gs = GameState()
    bus = EventBus(); gs.set_event_bus(bus)
    terrain = Terrain(20,20, game_state=gs); gs.set_terrain(terrain)
    movement = MovementSystem(gs); gs.set_movement_system(movement)
    los = LineOfSightManager(gs, terrain, bus, los_granularity=2); gs.los_manager=los
    cover_sys = CoverSystem(gs); gs.set_cover_system(cover_sys)
    cond = ConditionSystem(gs); gs.set_condition_system(cond)
    return gs

# Helper to add character
def add_char(gs, eid, x, y):
    c = make_char(eid)
    gs.add_entity(eid, {'position': PositionComponent(x,y,1,1), 'character_ref': CharRef(c)})
    gs.terrain.add_entity(eid, x, y)
    return c

# 1 Full wall barrier blocks LOS and no rays cast
def test_full_wall_blocks_los_no_rays(setup_env):
    gs = setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',0,0); add_char(gs,'B',5,0)
    # Add contiguous wall cells fully across line (cells 1..4)
    for x in range(1,5): gs.terrain.add_wall(x,0)
    entry = los.get_visibility_entry((0,0),(5,0))
    assert entry.has_los is False
    assert entry.partial_wall is False
    stats = los.get_stats()
    assert stats['rays_cast_total'] == 0

# 2 Partial wall triggers rays
def test_partial_wall_triggers_rays(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',0,0); add_char(gs,'B',5,0)
    gs.terrain.add_wall(2,0)  # single wall -> partial
    entry = los.get_visibility_entry((0,0),(5,0))
    assert entry.partial_wall is True
    assert entry.total_rays > 0 and entry.clear_rays >= 0
    stats = los.get_stats(); assert stats['rays_cast_total'] == entry.total_rays

# 3 Cache hit increments cache_hits and avoids recompute
def test_cache_hit_counts(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',0,0); add_char(gs,'B',3,0)
    los.get_visibility_entry((0,0),(3,0))
    first_stats = los.get_stats()['pair_recomputes']
    assert first_stats == 1
    los.get_visibility_entry((0,0),(3,0))
    stats = los.get_stats()
    assert stats['pair_recomputes'] == 1
    assert stats['cache_hits'] == 1

# 4 Terrain version bump triggers recompute
def test_wall_add_recompute(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',0,0); add_char(gs,'B',4,0)
    los.get_visibility_entry((0,0),(4,0))
    before = los.get_stats()['pair_recomputes']
    gs.terrain.add_wall(2,0)
    # New query forces recompute
    los.get_visibility_entry((0,0),(4,0))
    after = los.get_stats()['pair_recomputes']
    assert after == before + 1

# 5 Blocker movement triggers recompute
def test_blocker_move_recompute(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',0,0); mid = add_char(gs,'M',2,0); add_char(gs,'B',4,0)
    los.get_visibility_entry((0,0),(4,0))
    before = los.get_stats()['pair_recomputes']
    # Move middle character out of line
    gs.movement.move('M',(2,1))
    los.get_visibility_entry((0,0),(4,0))
    after = los.get_stats()['pair_recomputes']
    assert after == before + 1

# 6 Cover entry reuse (second call no recompute)
def test_cover_visibility_reuse(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',0,0); add_char(gs,'B',6,0)
    spawn_cover(gs,'light',3,0)
    gs.cover_system.compute_ranged_cover_bonus('A','B')
    before = los.get_stats()['pair_recomputes']
    gs.cover_system.compute_ranged_cover_bonus('A','B')
    after = los.get_stats()['pair_recomputes']
    assert after == before  # cached

# 7 Symmetry reuse
def test_symmetry_reuse(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',1,1); add_char(gs,'B',5,2)
    los.get_visibility_entry((1,1),(5,2))
    before = los.get_stats()['pair_recomputes']
    los.get_visibility_entry((5,2),(1,1))
    after = los.get_stats()['pair_recomputes']
    assert after == before

# 8 Stats reset
def test_stats_reset(setup_env):
    gs=setup_env; los=gs.los_manager
    add_char(gs,'A',0,0); add_char(gs,'B',2,0)
    los.get_visibility_entry((0,0),(2,0))
    assert los.get_stats()['pair_recomputes'] == 1
    los.reset_stats(); assert all(v==0 for v in los.get_stats().values())

# 9 Same cell LOS
def test_same_cell_los(setup_env):
    gs=setup_env; los=gs.los_manager
    add_char(gs,'A',3,3)
    entry = los.get_visibility_entry((3,3),(3,3))
    assert entry.has_los and entry.total_rays == 0

# 10 Integration: cover + invisibility + partial wall
class NoDefenseAttack(AttackAction):
    def get_available_defenses(self, defender, is_close_combat: bool, is_superficial: bool):
        return []

def test_cover_invisibility_partial_wall_integration(setup_env):
    gs=setup_env
    # Attacker & defender
    add_char(gs,'att',0,0); add_char(gs,'def',6,0)
    # Partial wall: one wall cell with clear space
    gs.terrain.add_wall(3,0)
    # Cover entity between (light -1) and retrenchment (+1)
    spawn_cover(gs,'light',2,0)
    spawn_cover(gs,'retrenchment',4,0)
    # Defender invisible; attacker has detection
    gs.condition_system.add_condition('def', INVISIBLE)
    gs.condition_system.add_condition('att', SEE_INVISIBLE)
    # Execute ranged attack
    atk = NoDefenseAttack('att','def', make_weapon(), gs)
    class FixedDice:
        def roll_pool(self, pool_size, hunger_dice=0):
            return {'successes':6,'bestial_failures':0,'critical_successes':0,'hunger_bestial_successes':0,'hunger_bestial_failures':0}
    atk.dice_roller = FixedDice()
    dmg = atk.execute()
    # Cover bonuses: light -1 + retrenchment +1 => 0; partial wall +2 -> defender defense would add +2, but no defense chosen -> damage should still be > base (attack successes) minus 0 because wall bonus only applies if a Dodge (ranged) defense; here no defense so just ensure attack proceeded.
    assert dmg > 0
    # Visibility entry asserts
    entry = gs.los_manager.get_visibility_entry((0,0),(6,0))
    assert entry.partial_wall is True
    assert entry.cover_sum == 0  # -1 + +1

# 11 Invisible intervening not blocking LOS and recompute after toggling visibility
def test_invisible_intervening_recompute(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',0,0); add_char(gs,'X',2,0); add_char(gs,'B',5,0)
    e1 = los.get_visibility_entry((0,0),(5,0)); recomputes1 = los.get_stats()['pair_recomputes']
    gs.condition_system.add_condition('X', INVISIBLE)
    e2 = los.get_visibility_entry((0,0),(5,0)); recomputes2 = los.get_stats()['pair_recomputes']
    assert recomputes2 == recomputes1 + 1
    assert e2.has_los
    # Remove invisibility -> another recompute
    gs.condition_system.remove_condition('X', INVISIBLE)
    los.get_visibility_entry((0,0),(5,0))
    assert los.get_stats()['pair_recomputes'] == recomputes2 + 1

# 12 Wall removal triggers recompute

def test_wall_removal_recompute(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',0,0); add_char(gs,'B',5,0)
    gs.terrain.add_wall(2,0)
    los.get_visibility_entry((0,0),(5,0))
    before = los.get_stats()['pair_recomputes']
    gs.terrain.remove_wall(2,0)
    los.get_visibility_entry((0,0),(5,0))
    after = los.get_stats()['pair_recomputes']
    assert after == before + 1

# 13 Cover-only does not trigger rays and has LOS

def test_cover_only_line_fastpath(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',0,0); add_char(gs,'B',6,0)
    spawn_cover(gs,'light',2,0); spawn_cover(gs,'heavy',4,0)
    entry = los.get_visibility_entry((0,0),(6,0))
    assert entry.has_los is True and entry.total_rays == 0 and entry.partial_wall is False
    stats = los.get_stats(); assert stats['rays_cast_total'] == 0 and stats['fastpath_skips'] >= 1

# 14 Cover removal recompute

def test_cover_removal_recompute(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',0,0); add_char(gs,'B',6,0)
    cover_id = spawn_cover(gs,'light',3,0)
    los.get_visibility_entry((0,0),(6,0))
    before = los.get_stats()['pair_recomputes']
    # Remove cover manually & bump
    gs.terrain.remove_entity(cover_id)
    gs.remove_entity(cover_id)
    if hasattr(gs,'bump_blocker_version'): gs.bump_blocker_version()
    los.get_visibility_entry((0,0),(6,0))
    after = los.get_stats()['pair_recomputes']
    assert after == before + 1

# 15 Multiple separated walls still partial (single bonus) and rays cast once

def test_multiple_walls_partial_single_bonus(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',0,0); add_char(gs,'B',7,0)
    gs.terrain.add_wall(2,0); gs.terrain.add_wall(5,0)  # separated by clear cells
    entry = los.get_visibility_entry((0,0),(7,0))
    assert entry.partial_wall is True and entry.wall_bonus == 2

# 16 Fastpath skip increments on simple clear line

def test_fastpath_skip_clear_line(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',1,1); add_char(gs,'B',2,1)
    entry = los.get_visibility_entry((1,1),(2,1))
    stats = los.get_stats()
    assert stats['fastpath_skips'] >= 1 and stats['rays_cast_total'] == 0

# 17 Rays stat stable on cached partial lookup

def test_rays_stat_not_increment_on_cache_hit(setup_env):
    gs=setup_env; los=gs.los_manager; los.reset_stats()
    add_char(gs,'A',0,0); add_char(gs,'B',5,0)
    gs.terrain.add_wall(3,0)
    entry1 = los.get_visibility_entry((0,0),(5,0))
    rays_first = los.get_stats()['rays_cast_total']
    entry2 = los.get_visibility_entry((0,0),(5,0))
    assert los.get_stats()['rays_cast_total'] == rays_first
