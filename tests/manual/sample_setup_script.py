"""
This script provides a sample implementation of the automated game setup
using the new game_initializer module. It defines a scenario with large entities
(big fighters) to test the system's ability to handle non-1x1 footprints.
"""
from tests.manual.game_initializer import initialize_game, run_and_visualize_game, EntitySpec

def run_big_fighter_scenario():
    """
    Defines and runs a game scenario with large entities.
    """
    print("Setting up the Big Fighter scenario...")

    # Define the entities for two teams, including large units
    # 1 Goliath, 2 bruisers, 1 grenadier, and 3 scout and 5 warriors for each team.
    entity_specs = [
        # --- Team A ---
        EntitySpec(team="A", weapon_type="club",   size=(3, 3), pos=(2, 23), health_mult=2.0), # Goliath
        EntitySpec(team="A", weapon_type="club",   size=(2, 2), pos=(5, 18), health_mult=1.5), # Bruiser
        EntitySpec(team="A", weapon_type="club",   size=(2, 2), pos=(5, 28), health_mult=1.5), # Bruiser
        EntitySpec(team="A", weapon_type="grenade", size=(1, 1), pos=(8, 24)),              # Grenadier
        EntitySpec(team="A", weapon_type="pistol", size=(1, 1), pos=(11, 24)),              # Scout
        EntitySpec(team="A", weapon_type="pistol", size=(1, 1), pos=(14, 24)),              # Scout
        EntitySpec(team="A", weapon_type="club",   size=(1, 1), pos=(17, 24)),              # Warrior
        EntitySpec(team="A", weapon_type="club",   size=(1, 1), pos=(20, 24)),              # Warrior
        EntitySpec(team="A", weapon_type="club",   size=(1, 1), pos=(23, 24)),              # Warrior
        EntitySpec(team="A", weapon_type="club",   size=(1, 1), pos=(26, 24)),              # Warrior
        EntitySpec(team="A", weapon_type="club",   size=(1, 1), pos=(29, 24)),              # Warrior

        # --- Team B ---
        EntitySpec(team="B", weapon_type="club",   size=(3, 3), pos=(47, 23), health_mult=2.0), # Goliath
        EntitySpec(team="B", weapon_type="club",   size=(2, 2), pos=(44, 18), health_mult=1.5), # Bruiser
        EntitySpec(team="B", weapon_type="club",   size=(2, 2), pos=(44, 28), health_mult=1.5), # Bruiser
        EntitySpec(team="B", weapon_type="grenade", size=(1, 1), pos=(41, 24)),              # Grenadier
        EntitySpec(team="B", weapon_type="pistol", size=(1, 1), pos=(41, 24)),              # Scout
        EntitySpec(team="B", weapon_type="pistol", size=(1, 1), pos=(38, 24)),              # Scout
        EntitySpec(team="B", weapon_type="club",   size=(1, 1), pos=(35, 24)),              # Warrior
        EntitySpec(team="B", weapon_type="club",   size=(1, 1), pos=(32, 24)),              # Warrior
        EntitySpec(team="B", weapon_type="club",   size=(1, 1), pos=(29, 24)),              # Warrior
        EntitySpec(team="B", weapon_type="club",   size=(1, 1), pos=(26, 24)),              # Warrior
        EntitySpec(team="B", weapon_type="club",   size=(1, 1), pos=(23, 24)),              # Warrior
    ]

    # Initialize the game using the automated setup function
    game_setup = initialize_game(
        entity_specs=entity_specs,
        grid_size=50,
        max_rounds=100,
        map_dir="battle_maps_bigfighters"  # Specify the output directory
    )

    print("Game initialized. Running simulation...")

    # Run the game and generate the visualization
    run_and_visualize_game(game_setup, gif_name_prefix="big_fighters_test")

    print("Big Fighter scenario finished.")

if __name__ == "__main__":
    run_big_fighter_scenario()
