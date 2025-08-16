import os
import datetime
from tests.manual.game_initializer import initialize_game, run_and_visualize_game, EntitySpec
from tests.manual.battle_map_utils import assemble_gif

TEAM_SIZE = 100
GRID_SIZE = 301
TEAM_SPACING = 3
MAX_ROUNDS = 200

# Four teams: A (left), B (right), C (top), D (bottom)
def test_fourway_battle():
    entity_specs = []
    # Helper to assign formation: ranged in middle, melee on flanks
    def assign_weapon(i):
        if i > 0 and i % 20 == 0:
            return "grenade"
        elif i > 0 and i % 10 == 0:
            return "shotgun"
        else:
            return "pistol" if TEAM_SIZE//3 <= i < 2*TEAM_SIZE//3 else "club"

    # Calculate a square root for grid formation
    import math
    block_size = int(math.ceil(math.sqrt(TEAM_SIZE)))
    # Margins for each team
    margin = TEAM_SPACING
    # Team A (left vertical block)
    for i in range(TEAM_SIZE):
        weapon_type = assign_weapon(i)
        row = i // block_size
        col = i % block_size
        x = margin + row
        y = margin + col
        entity_specs.append(EntitySpec(
            team="A",
            weapon_type=weapon_type,
            size=(1, 1),
            pos=(x, y)
        ))
    # Team B (right vertical block)
    for i in range(TEAM_SIZE):
        weapon_type = assign_weapon(i)
        row = i // block_size
        col = i % block_size
        x = GRID_SIZE - margin - block_size + row
        y = margin + col
        entity_specs.append(EntitySpec(
            team="B",
            weapon_type=weapon_type,
            size=(1, 1),
            pos=(x, y)
        ))
    # Team C (top horizontal block)
    for i in range(TEAM_SIZE):
        weapon_type = assign_weapon(i)
        row = i // block_size
        col = i % block_size
        x = margin + col
        y = margin + row
        entity_specs.append(EntitySpec(
            team="C",
            weapon_type=weapon_type,
            size=(1, 1),
            pos=(x, y)
        ))
    # Team D (bottom horizontal block)
    for i in range(TEAM_SIZE):
        weapon_type = assign_weapon(i)
        row = i // block_size
        col = i % block_size
        x = margin + col
        y = GRID_SIZE - margin - block_size + row
        entity_specs.append(EntitySpec(
            team="D",
            weapon_type=weapon_type,
            size=(1, 1),
            pos=(x, y)
        ))

    map_dir = "battle_maps"
    game_setup = initialize_game(
        entity_specs=entity_specs,
        grid_size=GRID_SIZE,
        max_rounds=MAX_ROUNDS,
        map_dir=map_dir
    )
    game_state = game_setup["game_state"]
    game_system = game_setup["game_system"]
    event_bus = game_setup["event_bus"]
    all_ids = game_setup["all_ids"]

    def on_action_performed(entity_id, action_name, **kwargs):
        print(f"[Event] Action performed: {entity_id} -> {action_name} | Result: {kwargs.get('result')}")
    def on_action_failed(entity_id, action_name, **kwargs):
        print(f"[Event] Action failed: {entity_id} -> {action_name} | Reason: {kwargs.get('reason')}")
    event_bus.subscribe("action_performed", on_action_performed)
    event_bus.subscribe("action_failed", on_action_failed)

    game_system.run_game_loop(max_rounds=MAX_ROUNDS)

    team_a_ids = [eid for eid in all_ids if eid.startswith("A_")]
    team_b_ids = [eid for eid in all_ids if eid.startswith("B_")]
    team_c_ids = [eid for eid in all_ids if eid.startswith("C_")]
    team_d_ids = [eid for eid in all_ids if eid.startswith("D_")]

    alive_A = any(not game_state.get_entity(entity_id)["character_ref"].character.is_dead for entity_id in team_a_ids)
    alive_B = any(not game_state.get_entity(entity_id)["character_ref"].character.is_dead for entity_id in team_b_ids)
    alive_C = any(not game_state.get_entity(entity_id)["character_ref"].character.is_dead for entity_id in team_c_ids)
    alive_D = any(not game_state.get_entity(entity_id)["character_ref"].character.is_dead for entity_id in team_d_ids)

    survivors = [t for t, alive in zip(["A", "B", "C", "D"], [alive_A, alive_B, alive_C, alive_D]) if alive]
    if len(survivors) > 1:
        print(f"Draw: Teams with survivors: {', '.join(survivors)}")
    elif len(survivors) == 1:
        print(f"Team {survivors[0]} wins.")
    else:
        print("No survivors.")

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        current_dir = os.path.abspath(".")
    map_dir_path = game_setup["game_system"].map_dir
    completed_rounds = min(MAX_ROUNDS, sum(1 for f in os.listdir(map_dir_path) if f.endswith('.png')))
    if completed_rounds > 0:
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        gif_name = f"battle_test_fourway_{now_str}.gif"
        assemble_gif(map_dir_path, completed_rounds, gif_name=gif_name, grid_size=GRID_SIZE, px_size=8, duration=500)
        print(f"Battle GIF saved to {os.path.join(os.path.abspath(map_dir_path), gif_name)}")
    else:
        print("No rounds completed, GIF not assembled.")

if __name__ == "__main__":
    test_fourway_battle()
    print("Test passed: Four-way battle runs and ends.")
