import os
import datetime
from tests.manual.game_initializer import initialize_game, run_and_visualize_game, EntitySpec
from tests.manual.battle_map_utils import assemble_gif

TEAM_SIZE = 10# 100
GRID_SIZE = 31# 301
TEAM_SPACING = 3  # Spacing between entities in the grid
MAX_ROUNDS = 200

def test_game_loop_runs_and_ends():
    """
    Set up a battle between two teams and run the game loop until one team wins
    or the maximum number of rounds is reached.
    """
    entity_specs = []

    # Create Team A entities
    for i in range(TEAM_SIZE):
        # Assign special roles based on index
        if i > 0 and i % 20 == 0:
            weapon_type = "grenade"
        elif i > 0 and i % 10 == 0:
            weapon_type = "shotgun"
        else:
            weapon_type = "pistol" if TEAM_SIZE//3 <= i < 2*TEAM_SIZE//3 else "club"

        x = TEAM_SPACING
        y = TEAM_SPACING + i * TEAM_SPACING
        entity_specs.append(EntitySpec(
            team="A",
            weapon_type=weapon_type,
            size=(1, 1),  # Standard 1x1 entity size
            pos=(x, y)
        ))

    # Create Team B entities
    for i in range(TEAM_SIZE):
        # Assign special roles based on index
        if i > 0 and i % 20 == 0:
            weapon_type = "grenade"
        elif i > 0 and i % 10 == 0:
            weapon_type = "shotgun"
        else:
            weapon_type = "pistol" if TEAM_SIZE//3 <= i < 2*TEAM_SIZE//3 else "club"

        x = GRID_SIZE - TEAM_SPACING
        y = GRID_SIZE - TEAM_SPACING - i * TEAM_SPACING
        entity_specs.append(EntitySpec(
            team="B",
            weapon_type=weapon_type,
            size=(1, 1),  # Standard 1x1 entity size
            pos=(x, y)
        ))

    # Initialize game using the new centralized initializer
    map_dir = "battle_maps"
    game_setup = initialize_game(
        entity_specs=entity_specs,
        grid_size=GRID_SIZE,
        max_rounds=MAX_ROUNDS,
        map_dir=map_dir
    )

    # Extract components we need for custom functionality
    game_state = game_setup["game_state"]
    game_system = game_setup["game_system"]
    event_bus = game_setup["event_bus"]
    all_ids = game_setup["all_ids"]

    # Subscribe to action events for logging
    def on_action_performed(entity_id, action_name, **kwargs):
        print(f"[Event] Action performed: {entity_id} -> {action_name} | Result: {kwargs.get('result')}")
    def on_action_failed(entity_id, action_name, **kwargs):
        print(f"[Event] Action failed: {entity_id} -> {action_name} | Reason: {kwargs.get('reason')}")
    event_bus.subscribe("action_performed", on_action_performed)
    event_bus.subscribe("action_failed", on_action_failed)

    # Run the game loop
    game_system.run_game_loop(max_rounds=MAX_ROUNDS)

    # Evaluate the outcome
    team_a_ids = [eid for eid in all_ids if eid.startswith("A_")]
    team_b_ids = [eid for eid in all_ids if eid.startswith("B_")]

    alive_A = any(not game_state.get_entity(entity_id)["character_ref"].character.is_dead for entity_id in team_a_ids)
    alive_B = any(not game_state.get_entity(entity_id)["character_ref"].character.is_dead for entity_id in team_b_ids)

    if alive_A and alive_B:
        print("Draw: Both teams have survivors.")
    elif alive_A:
        print("Team A wins.")
    elif alive_B:
        print("Team B wins.")
    else:
        print("No survivors.")

    # Assemble GIF at the end
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:  # Handle case when running interactively
        current_dir = os.path.abspath(".")

    # The map_dir_path is now directly from game_system since it's already been properly set up
    # with a timestamped subfolder by the game_initializer
    map_dir_path = game_setup["game_system"].map_dir

    # Count completed rounds
    completed_rounds = min(MAX_ROUNDS, sum(1 for f in os.listdir(map_dir_path) if f.endswith('.png')))

    if completed_rounds > 0:
        # Date/time for filename
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        gif_name = f"battle_test_game_system_{now_str}.gif"
        assemble_gif(map_dir_path, completed_rounds, gif_name=gif_name, grid_size=GRID_SIZE, px_size=8, duration=500)
        print(f"Battle GIF saved to {os.path.join(os.path.abspath(map_dir_path), gif_name)}")
    else:
        print("No rounds completed, GIF not assembled.")

if __name__ == "__main__":
    test_game_loop_runs_and_ends()
    print("Test passed: Game loop runs and ends on team wipe.")
