from tests.manual.game_initializer import EntitySpec, initialize_game
from core.game_system import GameSystem
from tests.manual.battle_map_utils import assemble_gif
import os

TEAM_SIZE = 12
GRID_SIZE = 50
TEAM_SPACING = 4
MAX_ROUNDS = 200

def build_team_specs(team: str, start_x: int, start_y: int, spacing: int) -> list:
    specs = []
    # 1 club 3x3 fighter (9x health)
    specs.append(EntitySpec(
        team=team,
        weapon_type="club",
        size=(3, 3),
        health_mult=9.0,
        pos=(start_x, start_y)
    ))
    # 2 club 1x2 fighters (2x health)
    specs.append(EntitySpec(
        team=team,
        weapon_type="club",
        size=(1, 2),
        health_mult=2.0,
        pos=(start_x, start_y + spacing)
    ))
    specs.append(EntitySpec(
        team=team,
        weapon_type="club",
        size=(1, 2),
        health_mult=2.0,
        pos=(start_x, start_y + 2 * spacing)
    ))
    # 9 standard fighters (1x1, normal health)
    for i in range(3, TEAM_SIZE):
        weapon_type = "pistol" if i < TEAM_SIZE // 3 else "club"
        specs.append(EntitySpec(
            team=team,
            weapon_type=weapon_type,
            size=(1, 1),
            health_mult=1.0,
            pos=(start_x, start_y + i * spacing)
        ))
    return specs

def test_bigfighters_game():
    teamA_specs = build_team_specs("A", TEAM_SPACING, TEAM_SPACING, TEAM_SPACING)
    teamB_specs = build_team_specs("B", GRID_SIZE - TEAM_SPACING, GRID_SIZE - TEAM_SPACING, -TEAM_SPACING)
    systems = initialize_game(teamA_specs, teamB_specs, GRID_SIZE, TEAM_SPACING, MAX_ROUNDS)
    game_state = systems["game_state"]
    prep_manager = systems["prep_manager"]
    event_bus = systems["event_bus"]
    turn_order = systems["turn_order"]
    all_ids = systems["all_ids"]

    # Alliances and teams are already set up by initializer
    game_system = GameSystem(game_state, prep_manager, event_bus=event_bus, enable_map_drawing=True)
    game_system.set_turn_order_system(turn_order)
    map_dir = "battle_maps_bigfighters"
    game_system.set_map_directory(map_dir)
    game_system.run_game_loop(max_rounds=MAX_ROUNDS)

    # Save GIF
    completed_rounds = min(MAX_ROUNDS, sum(1 for f in os.listdir(map_dir) if f.endswith('.png')))
    if completed_rounds > 0:
        gif_name = "battle_bigfighters.gif"
        assemble_gif(map_dir, completed_rounds, gif_name=gif_name, grid_size=GRID_SIZE, px_size=8, duration=500)
        print(f"Battle GIF saved to {os.path.join(os.path.abspath(map_dir), gif_name)}")
    else:
        print("No rounds completed, GIF not assembled.")

if __name__ == "__main__":
    test_bigfighters_game()
    print("Test passed: Big fighters game loop runs and ends.")

