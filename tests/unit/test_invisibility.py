import pytest
from core.game_state import GameState
from core.event_bus import EventBus
from core.terrain_manager import Terrain
from core.movement_system import MovementSystem
from core.los_manager import LineOfSightManager
from core.cover_system import CoverSystem
from ecs.systems.condition_system import ConditionSystem
from ecs.actions.attack_actions import AttackAction
from entities.weapon import Weapon, WeaponType
from entities.character import Character
from ecs.components.position import PositionComponent
from ecs.components.character_ref import CharacterRefComponent
from ecs.ecs_manager import ECSManager
from utils.condition_utils import INVISIBLE, SEE_INVISIBLE

class FixedDice:
    def __init__(self, successes):
        self.successes = successes
    def roll_pool(self, pool_size, hunger_dice=0):
        return {'successes': self.successes,'bestial_failures':0,'critical_successes':0,'hunger_bestial_successes':0,'hunger_bestial_failures':0}

class NoDefenseAttack(AttackAction):
    def get_available_defenses(self, defender, is_close_combat: bool, is_superficial: bool):
        return []  # Disable defenses for deterministic tests

@pytest.fixture
def gs_full():
    bus = EventBus()
    ecs = ECSManager(bus)
    gs = GameState(ecs)
    gs.set_event_bus(bus)
    terrain = Terrain(12,12, game_state=gs)
    gs.set_terrain(terrain)
    movement = MovementSystem(gs, ecs, event_bus=bus)
    gs.set_movement_system(movement)
    los = LineOfSightManager(gs, terrain, bus, los_granularity=2)
    gs.los_manager = los
    cover_sys = CoverSystem(gs)
    gs.set_cover_system(cover_sys)
    cond = ConditionSystem(ecs, bus, game_state=gs)
    gs.set_condition_system(cond)
    return gs

def add_char(gs, eid, x, y, dex=3, firearms=3, team='A'):
    traits = {
        'Attributes': {'Physical': {'Dexterity': dex}},
        'Abilities': {'Skills': {'Firearms': firearms}, 'Talents': {'Brawl': 3}},
        'Disciplines': {}
    }
    c = Character(name=eid, traits=traits)
    gs.add_entity(eid, {'position': PositionComponent(x,y,1,1), 'character_ref': CharacterRefComponent(c)})
    gs.terrain.add_entity(eid, x, y)
    return c

def ranged_weapon():
    return Weapon(name='Rifle', damage_bonus=1, weapon_range=6, damage_type='superficial', weapon_type=WeaponType.FIREARM)

def melee_weapon():
    return Weapon(name='Claw', damage_bonus=1, weapon_range=1, damage_type='superficial', weapon_type=WeaponType.MELEE)

# 1. Ranged attack blocked by invisible defender
def test_ranged_blocked_by_invisible_defender(gs_full):
    gs = gs_full
    att = add_char(gs,'att',0,0)
    defc = add_char(gs,'def',4,0)
    gs.condition_system.add_condition('def', INVISIBLE)
    events = {}
    def on_defense_prompt(**kw): events['prompt']=True
    gs.event_bus.subscribe('defense_prompt', on_defense_prompt)
    atk = NoDefenseAttack('att','def', ranged_weapon(), gs)
    atk.dice_roller = FixedDice(6)
    dmg = atk.execute()
    assert dmg == 0
    assert 'prompt' not in events  # early gated

# 2. Detection allows ranged attack
def test_ranged_allowed_with_detection(gs_full):
    gs = gs_full
    add_char(gs,'att',0,0)
    add_char(gs,'def',4,0)
    gs.condition_system.add_condition('def', INVISIBLE)
    gs.condition_system.add_condition('att', SEE_INVISIBLE)
    atk = NoDefenseAttack('att','def', ranged_weapon(), gs)
    atk.dice_roller = FixedDice(5)
    dmg = atk.execute()
    assert dmg > 0  # attack proceeds

# 3. Melee attack bypasses invisibility gating
def test_melee_attack_ignores_invisibility(gs_full):
    gs = gs_full
    add_char(gs,'att',0,0)
    add_char(gs,'def',1,0)  # adjacent
    gs.condition_system.add_condition('def', INVISIBLE)
    atk = NoDefenseAttack('att','def', melee_weapon(), gs)
    atk.dice_roller = FixedDice(4)
    dmg = atk.execute()
    assert dmg > 0

# 4. Attacker invisible does not block attacking
def test_attacker_invisible_ranged_still_works(gs_full):
    gs = gs_full
    add_char(gs,'att',0,0)
    add_char(gs,'def',4,0)
    gs.condition_system.add_condition('att', INVISIBLE)
    atk = NoDefenseAttack('att','def', ranged_weapon(), gs)
    atk.dice_roller = FixedDice(4)
    dmg = atk.execute()
    assert dmg > 0

# 5. Toggle defender invisibility blocks then allows
def test_toggle_invisibility_defender(gs_full):
    gs = gs_full
    add_char(gs,'att',0,0)
    add_char(gs,'def',4,0)
    atk1 = NoDefenseAttack('att','def', ranged_weapon(), gs)
    atk1.dice_roller = FixedDice(5)
    base_dmg = atk1.execute()
    assert base_dmg > 0
    gs.condition_system.add_condition('def', INVISIBLE)
    atk2 = NoDefenseAttack('att','def', ranged_weapon(), gs)
    atk2.dice_roller = FixedDice(5)
    blocked = atk2.execute()
    assert blocked == 0
    gs.condition_system.remove_condition('def', INVISIBLE)
    atk3 = NoDefenseAttack('att','def', ranged_weapon(), gs)
    atk3.dice_roller = FixedDice(5)
    dmg3 = atk3.execute()
    assert dmg3 > 0

# 6. Intervening invisible character does not affect cover or LOS caching
def test_invisible_intervening_character(gs_full):
    gs = gs_full
    add_char(gs,'att',0,0)
    add_char(gs,'mid',2,0)
    add_char(gs,'def',4,0)
    entry_before = gs.los_manager.get_visibility_entry((0,0),(4,0))
    assert entry_before.has_los
    # Make middle invisible -> should bump blocker_version and recompute; cover remains none
    prev_blocker_v = gs.blocker_version
    gs.condition_system.add_condition('mid', INVISIBLE)
    assert gs.blocker_version == prev_blocker_v + 1
    entry_after = gs.los_manager.get_visibility_entry((0,0),(4,0))
    assert entry_after.has_los
    assert entry_after.cover_sum == 0
    # No cover => if attack allowed and no walls cover bonus would be -2 (checked via cover system directly)
    bonus = gs.cover_system.compute_ranged_cover_bonus('att','def')
    assert bonus == -2

# 7. SEE_INVISIBLE has no effect if defender not invisible (regression guard)
def test_detection_no_effect_when_not_invisible(gs_full):
    gs = gs_full
    add_char(gs,'att',0,0)
    add_char(gs,'def',4,0)
    gs.condition_system.add_condition('att', SEE_INVISIBLE)
    atk = NoDefenseAttack('att','def', ranged_weapon(), gs)
    atk.dice_roller = FixedDice(4)
    dmg = atk.execute()
    assert dmg > 0

# 8. Both invisible and attacker lacks detection -> fail; then add detection -> succeed
def test_both_invisible_then_detection(gs_full):
    gs = gs_full
    add_char(gs,'att',0,0)
    add_char(gs,'def',4,0)
    gs.condition_system.add_condition('att', INVISIBLE)
    gs.condition_system.add_condition('def', INVISIBLE)
    atk_fail = NoDefenseAttack('att','def', ranged_weapon(), gs)
    atk_fail.dice_roller = FixedDice(6)
    dmg_fail = atk_fail.execute()
    assert dmg_fail == 0
    gs.condition_system.add_condition('att', SEE_INVISIBLE)
    atk_succ = NoDefenseAttack('att','def', ranged_weapon(), gs)
    atk_succ.dice_roller = FixedDice(6)
    dmg_ok = atk_succ.execute()
    assert dmg_ok > 0


